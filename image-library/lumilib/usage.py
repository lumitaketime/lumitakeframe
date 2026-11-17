"""佔比圖（方塊圖、環狀圖）與連線圖的資料：從目前的資料夾一路往下拆到每個子資料夾、每個「檔案」，
直到小到畫面上畫不出來為止；畫不出來的合併成一塊「其他」，可以再點開看清單。

大小用「資料夾」表預先算好的 total_bytes，檔案直接查 files 表；一層一層往下展開，每一層只查幾次（IN 一批資料夾），
一百萬個檔案也不用全部讀進來。只讀資料庫，硬碟沒接上也能看。
查詢都用 INDEXED BY 固定走「依資料夾」的索引：資料庫的估計更新後，SQLite 曾改成「把所有大檔案掃一遍」，慢上百倍。
"""

from __future__ import annotations

import sqlite3

MAX_NODES = 30_000  # 一張圖最多幾塊
PER_FOLDER = 4_000  # 一個資料夾裡最多拆出幾塊（其餘併入「其他」）
CHUNK = 400

FOLDER, FILE, REST = 0, 1, 2


def usage_tree(conn: sqlite3.Connection, root_id: int, path: str = "", px: int = 1_000_000, max_nodes: int = MAX_NODES,
               depth: int = 64) -> dict | None:
    """回傳一棵扁平的樹（每個欄位一個陣列，第 0 個是目前的資料夾）：
    parent、type（0 資料夾／1 檔案／2 其他）、id、name、path、bytes、files、kind。
    px＝畫面大約有多少像素：小於約 6 個像素的項目合併成「其他」。"""
    path = (path or "").strip("/")
    here = conn.execute("SELECT id, name, path, total_bytes, total_files, main_kind FROM folders "
                        "WHERE root_id = ? AND path = ? AND status = 'ok'", (root_id, path)).fetchone()
    if here is None:
        return None
    total = here["total_bytes"] or 0
    least = max(1, int(total * 6 / max(10_000, px)))
    cols = {k: [] for k in ("parent", "type", "id", "name", "path", "bytes", "files", "kind", "depth")}

    def add(parent, kind_of, id_, name, p, size, files, kind, d) -> int:
        cols["parent"].append(parent)
        cols["type"].append(kind_of)
        cols["id"].append(id_)
        cols["name"].append(name)
        cols["path"].append(p)
        cols["bytes"].append(int(size or 0))
        cols["files"].append(int(files or 0))
        cols["kind"].append(kind)
        cols["depth"].append(d)
        return len(cols["parent"]) - 1

    add(-1, FOLDER, here["id"], here["name"] or "", path, total, here["total_files"], here["main_kind"], 0)
    frontier = [(0, here["id"])]  # (節點, 資料夾 id)：還要往下拆的資料夾
    level = 0
    while frontier and len(cols["parent"]) < max_nodes and level < depth:
        level += 1
        frontier.sort(key=lambda f: -cols["bytes"][f[0]])
        nxt = []
        for start in range(0, len(frontier), CHUNK):
            if len(cols["parent"]) >= max_nodes:
                break  # 剩下的資料夾就畫成一整塊，不再往下拆
            chunk = frontier[start:start + CHUNK]
            node_of = {fid: n for n, fid in chunk}
            ids = list(node_of)
            marks = ",".join("?" * len(ids))
            kids: dict[int, list] = {fid: [] for fid in ids}
            small: dict[int, list[int]] = {fid: [0, 0, 0] for fid in ids}  # 數量、大小、檔案數
            for r in conn.execute(f"SELECT id, parent_id, name, path, total_bytes, total_files, main_kind FROM folders INDEXED BY idx_folders_parent "
                                  f"WHERE parent_id IN ({marks}) AND status = 'ok' AND total_bytes > 0", ids):
                if r["total_bytes"] >= least:
                    kids[r["parent_id"]].append((FOLDER, r["id"], r["name"], r["path"], r["total_bytes"], r["total_files"], r["main_kind"]))
                else:
                    s = small[r["parent_id"]]
                    s[0] += 1
                    s[1] += r["total_bytes"]
                    s[2] += r["total_files"] or 0
            for r in conn.execute(f"SELECT id, folder_id, name, size, kind FROM files INDEXED BY idx_files_folder_size "
                                  f"WHERE folder_id IN ({marks}) AND status = 'ok' AND size >= ?", ids + [least]):
                kids[r["folder_id"]].append((FILE, r["id"], r["name"], "", r["size"], 1, r["kind"]))  # 檔案的路徑＝上一層的路徑＋名稱（介面組合，省傳輸）
            for r in conn.execute(f"SELECT folder_id, COUNT(*) AS n, COALESCE(SUM(size), 0) AS b FROM files INDEXED BY idx_files_folder_size "
                                  f"WHERE folder_id IN ({marks}) AND status = 'ok' AND size < ? GROUP BY folder_id", ids + [least]):
                s = small[r["folder_id"]]
                s[0] += r["n"]
                s[1] += r["b"]
                s[2] += r["n"]
            for fid in ids:
                parent = node_of[fid]
                items = sorted(kids[fid], key=lambda k: -k[4])
                rest = small[fid]
                if len(items) > PER_FOLDER:
                    for k in items[PER_FOLDER:]:
                        rest[0] += 1
                        rest[1] += k[4]
                        rest[2] += k[5] or 0
                    items = items[:PER_FOLDER]
                d = cols["depth"][parent] + 1
                fpath = cols["path"][parent]
                for k in items:
                    n = add(parent, k[0], k[1], k[2], k[3], k[4], k[5], k[6], d)
                    if k[0] == FOLDER and (k[5] or 0) > 0:
                        nxt.append((n, k[1]))
                if rest[1] > 0:  # 名稱欄放「其他」裡有幾項（介面組成「其他 N 個項目」）；id 是所在資料夾
                    add(parent, REST, fid, str(rest[0]), fpath, rest[1], rest[2], "other", d)
        frontier = nxt
    return {"root": root_id, "path": path, "name": here["name"] or "", "bytes": total, "files": here["total_files"],
            "least": least, "nodes": cols}


def usage_rest(conn: sqlite3.Connection, folder_id: int, below: int, offset: int = 0, limit: int = 200) -> dict:
    """「其他」裡面的項目：這個資料夾裡小於 below 的子資料夾與檔案，由大到小。"""
    d = conn.execute("SELECT root_id, path FROM folders WHERE id = ?", (folder_id,)).fetchone()
    if d is None:
        return {"total": 0, "items": []}
    rows = conn.execute(
        "SELECT * FROM ("
        " SELECT 'folder' AS type, id, name, path, total_bytes AS size, total_files AS files, main_kind AS kind FROM folders "
        "  WHERE parent_id = ? AND status = 'ok' AND total_bytes > 0 AND total_bytes < ?"
        " UNION ALL"
        " SELECT 'file', id, name, ? || name, size, 1, kind FROM files WHERE folder_id = ? AND status = 'ok' AND size < ?"
        ") ORDER BY size DESC LIMIT ? OFFSET ?",
        (folder_id, below, f"{d['path']}/" if d["path"] else "", folder_id, below, limit, offset)).fetchall()
    total = conn.execute(
        "SELECT (SELECT COUNT(*) FROM folders WHERE parent_id = ? AND status = 'ok' AND total_bytes > 0 AND total_bytes < ?)"
        " + (SELECT COUNT(*) FROM files WHERE folder_id = ? AND status = 'ok' AND size < ?)",
        (folder_id, below, folder_id, below)).fetchone()[0]
    return {"total": total, "root": d["root_id"], "items": [dict(r) for r in rows]}
