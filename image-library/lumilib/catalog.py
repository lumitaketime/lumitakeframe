"""硬碟目錄的查詢：硬碟清單、資料夾總大小、資料夾內容。硬碟拔掉時也能查（全部讀資料庫，不碰硬碟）。"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from . import filetypes, volumes


def update_folder_totals(conn: sqlite3.Connection, root_id: int) -> None:
    """重新計算每個資料夾的檔案數與大小：files／bytes 只算這一層，total_* 含所有子資料夾。

    由最深的資料夾往上累加，十萬個資料夾也只要一兩秒（統計交給 SQLite，不逐一讀檔案）。
    """
    folders = conn.execute(
        "SELECT id, parent_id, path FROM folders WHERE root_id = ? AND status = 'ok'", (root_id,)).fetchall()
    if not folders:
        return
    direct = {r[0]: (r[1], r[2]) for r in conn.execute(
        "SELECT folder_id, COUNT(*), COALESCE(SUM(size), 0) FROM files WHERE root_id = ? AND status = 'ok' GROUP BY folder_id",
        (root_id,))}
    total = {r["id"]: list(direct.get(r["id"], (0, 0))) for r in folders}
    subs = dict.fromkeys(total, 0)
    depth = lambda p: 0 if not p else p.count("/") + 1  # noqa: E731
    for r in sorted(folders, key=lambda r: depth(r["path"]), reverse=True):
        parent = r["parent_id"]
        if parent in total:
            total[parent][0] += total[r["id"]][0]
            total[parent][1] += total[r["id"]][1]
            subs[parent] += 1
    conn.executemany(
        "UPDATE folders SET files = ?, bytes = ?, total_files = ?, total_bytes = ?, subfolders = ? WHERE id = ?",
        [(*direct.get(fid, (0, 0)), t[0], t[1], subs[fid], fid) for fid, t in total.items()],
    )
    conn.execute("UPDATE folders SET files = 0, bytes = 0, total_files = 0, total_bytes = 0, subfolders = 0 "
                 "WHERE root_id = ? AND status != 'ok' AND total_files != 0", (root_id,))


def drive_dict(row: sqlite3.Row | None, online: bool | None = None) -> dict | None:
    if row is None:
        return None
    return {
        "id": row["id"], "name": row["name"], "fs_type": row["fs_type"], "fs_label": volumes.fs_label(row["fs_type"]),
        "capacity": row["capacity"], "read_only": bool(row["read_only"]), "last_seen": row["last_seen"],
        "online": online,
    }


def root_summary(conn: sqlite3.Connection, root: sqlite3.Row) -> dict:
    """資料夾來源的目錄摘要：所在硬碟、檔案數、總大小、上次掃描、掃描是否完成。"""
    top = conn.execute("SELECT total_files, total_bytes, subfolders FROM folders WHERE root_id = ? AND path = ''",
                       (root["id"],)).fetchone()
    drive = conn.execute("SELECT * FROM drives WHERE id = ?", (root["drive_id"],)).fetchone() if root["drive_id"] else None
    online = Path(root["path"]).is_dir()
    return {
        "drive": drive_dict(drive, online),
        "files": top["total_files"] if top else 0,
        "bytes": top["total_bytes"] if top else 0,
        "scan_state": root["scan_state"],
        "scanned": top is not None,
    }


def folder_listing(conn: sqlite3.Connection, root_id: int, path: str = "") -> dict | None:
    """一個資料夾的內容（子資料夾與所有檔案），硬碟沒接上也能看。"""
    folder = conn.execute("SELECT * FROM folders WHERE root_id = ? AND path = ?", (root_id, path)).fetchone()
    if folder is None:
        return None
    subfolders = [
        {"name": r["name"], "path": r["path"], "files": r["total_files"], "bytes": r["total_bytes"],
         "subfolders": r["subfolders"], "status": r["status"]}
        for r in conn.execute(
            "SELECT name, path, total_files, total_bytes, subfolders, status FROM folders "
            "WHERE parent_id = ? ORDER BY status != 'ok', name COLLATE NOCASE", (folder["id"],))
    ]
    files = [
        {"id": r["id"], "name": r["name"], "kind": r["kind"], "size": r["size"], "mtime": r["mtime"],
         "status": r["status"], "image_id": r["image_id"]}
        for r in conn.execute(
            "SELECT id, name, kind, size, mtime, status, image_id FROM files WHERE folder_id = ? "
            "ORDER BY status != 'ok', name COLLATE NOCASE", (folder["id"],))
    ]
    kinds: dict[str, list[int]] = {}
    for f in files:
        if f["status"] == "ok":
            k = kinds.setdefault(f["kind"], [0, 0])
            k[0] += 1
            k[1] += f["size"]
    return {
        "path": path, "name": folder["name"], "status": folder["status"],
        "files_here": folder["files"], "bytes_here": folder["bytes"],
        "total_files": folder["total_files"], "total_bytes": folder["total_bytes"],
        "subfolders": subfolders, "files": files,
        "kinds": [{"kind": k, "label": filetypes.LABELS.get(k, k), "files": v[0], "bytes": v[1]}
                  for k, v in sorted(kinds.items(), key=lambda kv: -kv[1][1])],
    }


def drives_overview(conn: sqlite3.Connection, scanning: dict | None = None, detail: bool = False) -> list[dict]:
    """側邊欄的硬碟清單：每顆硬碟（不論有沒有接上）的容量、已編目的檔案數與大小、連線與掃描狀態。

    scanning 是正在執行的掃描工作回報的 {"root_id", "files"}。只讀資料庫，另外用「資料夾還在不在」判斷有沒有接上。
    還沒用新版掃描過的資料夾來源沒有硬碟資料，各自列成一項（drive_id 為 None）。
    """
    rows = conn.execute(
        """SELECT r.id, r.name, r.path, r.drive_id, r.last_scan, r.scan_state,
                  COALESCE(f.total_files, 0) AS files, COALESCE(f.total_bytes, 0) AS bytes
           FROM roots r LEFT JOIN folders f ON f.root_id = r.id AND f.path = ''
           ORDER BY r.name COLLATE NOCASE""").fetchall()
    drives = {d["id"]: d for d in conn.execute("SELECT * FROM drives")}
    out: dict = {}
    for r in rows:
        d = drives.get(r["drive_id"])
        key = f"drive:{d['id']}" if d else f"root:{r['id']}"
        item = out.get(key)
        if item is None:
            item = out[key] = {
                "key": key, "drive_id": d["id"] if d else None, "name": d["name"] if d else r["name"],
                "fs_label": volumes.fs_label(d["fs_type"]) if d else None,
                "capacity": d["capacity"] if d else None, "read_only": bool(d["read_only"]) if d else False,
                "online": False, "files": 0, "bytes": 0, "last_scan": None, "complete": True,
                "scanning": False, "progress": None, "roots": [],
            }
        online = Path(r["path"]).is_dir()
        item["roots"].append({"id": r["id"], "name": r["name"], "online": online, "files": r["files"], "bytes": r["bytes"]})
        item["online"] = item["online"] or online
        item["files"] += r["files"]
        item["bytes"] += r["bytes"]
        if r["last_scan"] and (item["last_scan"] is None or r["last_scan"] > item["last_scan"]):
            item["last_scan"] = r["last_scan"]
        if r["scan_state"] != "done":
            item["complete"] = False
        if scanning and scanning.get("root_id") == r["id"]:
            item["scanning"] = True
            # 以前完整掃過才估得出百分比（用上次的檔案數當總數）；第一次掃描只知道「正在掃」
            if r["last_scan"] and r["files"]:
                item["progress"] = min(0.99, (scanning.get("files") or 0) / r["files"])
    if detail:  # 硬碟總覽：每顆硬碟各類型的檔案數與大小（容量條依類型分色）
        by_root: dict[int, dict[str, list[int]]] = {}
        for r in conn.execute("SELECT root_id, kind, COUNT(*) AS n, COALESCE(SUM(size), 0) AS b FROM files INDEXED BY idx_files_root_kind "
                              "WHERE status = 'ok' GROUP BY root_id, kind"):
            by_root.setdefault(r["root_id"], {})[r["kind"]] = [r["n"], r["b"]]
        for item in out.values():
            total: dict[str, list[int]] = {}
            for root in item["roots"]:
                for kind, (n, b) in by_root.get(root["id"], {}).items():
                    t = total.setdefault(kind, [0, 0])
                    t[0] += n
                    t[1] += b
            item["kinds"] = [{"kind": k, "files": total[k][0], "bytes": total[k][1]} for k in filetypes.KINDS if k in total]
    return sorted(out.values(), key=lambda x: x["name"].casefold())


def new_volumes(conn: sqlite3.Connection) -> list[dict]:
    """這台電腦上已經接著、但還沒加入目錄的硬碟（只讀取名稱、格式與容量，不讀內容；開機磁碟不列）。"""
    roots = [Path(r["path"]) for r in conn.execute("SELECT path FROM roots")]
    out = []
    for mount in volumes.mounted_volumes():
        if mount == Path("/") or any(r == mount or mount in r.parents for r in roots):
            continue
        info = volumes.volume_info(mount)
        if not info:
            continue
        out.append({"path": str(mount), "name": info.get("name") or mount.name, "fs_label": volumes.fs_label(info.get("fs_type")),
                    "capacity": info.get("capacity"), "read_only": bool(info.get("read_only"))})
    return out


def kinds_overview(conn: sqlite3.Connection) -> list[dict]:
    """側邊欄「類型」：每種檔案類型在所有硬碟上的檔案數與總大小（交給 SQLite 統計，用 idx_files_kind）。"""
    got = {r["kind"]: (r["n"], r["b"]) for r in conn.execute(
        "SELECT kind, COUNT(*) AS n, COALESCE(SUM(size), 0) AS b FROM files WHERE status = 'ok' GROUP BY kind")}
    return [{"kind": k, "files": got.get(k, (0, 0))[0], "bytes": got.get(k, (0, 0))[1]} for k in filetypes.KINDS]


# ---- 瀏覽：列表與圖像檢視只要求「看得到的那一段」----

# 側邊欄「類型」的六個分組（RAW 算照片，App 與套件算其他）
KIND_GROUPS = {
    "video": ("video",), "photo": ("photo", "raw"), "document": ("document",), "audio": ("audio",),
    "archive": ("archive",), "other": ("package", "other"),
}
LABELS = ("red", "yellow", "green", "blue", "purple")
PAGE_MAX = 500
_FILE_ORDER = {"name": "f.name COLLATE NOCASE", "size": "f.size", "mtime": "f.mtime", "kind": "f.kind"}
_FOLDER_ORDER = {"name": "d.name COLLATE NOCASE", "size": "d.total_bytes", "mtime": "d.mtime", "kind": "d.name COLLATE NOCASE"}
_ALL_INDEX = {"name": "idx_files_all_name", "size": "idx_files_all_size", "mtime": "idx_files_all_mtime"}


def _file_item(r: sqlite3.Row) -> dict:
    folder = r["folder_path"]
    return {"type": "file", "id": r["id"], "name": r["name"], "kind": r["kind"], "size": r["size"], "mtime": r["mtime"],
            "root_id": r["root_id"], "folder": folder, "path": f"{folder}/{r['name']}" if folder else r["name"],
            "image_id": r["image_id"], "label": r["label"]}


def _folder_item(r: sqlite3.Row) -> dict:
    return {"type": "folder", "id": r["id"], "name": r["name"], "kind": "folder", "size": r["total_bytes"], "mtime": r["mtime"],
            "root_id": r["root_id"], "folder": r["path"].rpartition("/")[0], "path": r["path"],
            "files": r["total_files"], "label": r["label"]}


def items_page(conn: sqlite3.Connection, *, root_id: int | None = None, path: str = "", kind: str | None = None,
               label: str | None = None, offset: int = 0, limit: int = 200, sort: str = "name", desc: bool = False) -> dict | None:
    """一段項目（offset 起 limit 筆）與總數。排序、篩選都交給 SQLite，不把整個資料夾讀進來。

    三種範圍：root_id＋path＝一個資料夾的內容（資料夾排前面）；kind＝所有硬碟上這個類型的檔案；
    label＝所有硬碟上有這個顏色標籤的資料夾與檔案。硬碟沒接上也能查。
    """
    sort = sort if sort in _FILE_ORDER else "name"
    offset, limit = max(0, int(offset)), max(1, min(PAGE_MAX, int(limit)))
    way = "DESC" if desc else "ASC"
    file_cols = "f.id, f.name, f.kind, f.size, f.mtime, f.root_id, f.image_id, f.label, d.path AS folder_path"

    if kind is not None:
        kinds = KIND_GROUPS.get(kind)
        if not kinds:
            return None
        marks = ",".join("?" * len(kinds))
        total = conn.execute(f"SELECT COUNT(*) FROM files WHERE status = 'ok' AND kind IN ({marks})", kinds).fetchone()[0]
        # 沿著「狀態＋排序欄位＋類型」的索引走，邊走邊挑類型：不必先把幾十萬筆排好再取一段
        index = f"INDEXED BY {_ALL_INDEX[sort]}" if sort in _ALL_INDEX else ""
        rows = conn.execute(
            f"SELECT {file_cols} FROM (SELECT id FROM files {index} WHERE status = 'ok' AND kind IN ({marks}) "
            f"ORDER BY {_FILE_ORDER[sort].replace('f.', '')} {way} LIMIT ? OFFSET ?) p "
            "JOIN files f ON f.id = p.id JOIN folders d ON d.id = f.folder_id", (*kinds, limit, offset)).fetchall()
        return {"total": total, "folders": 0, "offset": offset, "items": [_file_item(r) for r in rows]}

    if label is not None:
        if label not in LABELS:
            return None
        folders = conn.execute(
            f"SELECT d.* FROM folders d WHERE d.label = ? AND d.status = 'ok' ORDER BY {_FOLDER_ORDER[sort]} {way}", (label,)).fetchall()
        files = conn.execute(
            f"SELECT {file_cols} FROM files f JOIN folders d ON d.id = f.folder_id WHERE f.label = ? AND f.status = 'ok' "
            f"ORDER BY {_FILE_ORDER[sort]} {way}, f.id", (label,)).fetchall()
        items = [_folder_item(r) for r in folders] + [_file_item(r) for r in files]
        return {"total": len(items), "folders": len(folders), "offset": offset, "items": items[offset:offset + limit]}

    here = conn.execute("SELECT id FROM folders WHERE root_id = ? AND path = ?", (root_id, path.strip("/"))).fetchone()
    if here is None:
        return None
    n_folders = conn.execute("SELECT COUNT(*) FROM folders WHERE parent_id = ? AND status = 'ok'", (here["id"],)).fetchone()[0]
    n_files = conn.execute("SELECT COUNT(*) FROM files WHERE folder_id = ? AND status = 'ok'", (here["id"],)).fetchone()[0]
    items: list[dict] = []
    if offset < n_folders:
        items += [_folder_item(r) for r in conn.execute(
            f"SELECT d.* FROM folders d WHERE d.parent_id = ? AND d.status = 'ok' ORDER BY {_FOLDER_ORDER[sort]} {way}, d.id "
            "LIMIT ? OFFSET ?", (here["id"], limit, offset))]
    if len(items) < limit:
        items += [_file_item(r) for r in conn.execute(
            f"SELECT {file_cols} FROM files f JOIN folders d ON d.id = f.folder_id WHERE f.folder_id = ? AND f.status = 'ok' "
            f"ORDER BY {_FILE_ORDER[sort]} {way}, f.id LIMIT ? OFFSET ?",
            (here["id"], limit - len(items), max(0, offset - n_folders)))]
    return {"total": n_folders + n_files, "folders": n_folders, "offset": offset, "items": items}


def location_info(conn: sqlite3.Connection, root_id: int, path: str = "") -> dict | None:
    """目前位置的資訊（路徑列、狀態列、資訊欄用）：所在硬碟、每一層的名稱、總檔案數與大小。"""
    path = path.strip("/")
    root = conn.execute("SELECT * FROM roots WHERE id = ?", (root_id,)).fetchone()
    folder = conn.execute("SELECT * FROM folders WHERE root_id = ? AND path = ?", (root_id, path)).fetchone() if root else None
    if folder is None:
        return None
    drive = conn.execute("SELECT * FROM drives WHERE id = ?", (root["drive_id"],)).fetchone() if root["drive_id"] else None
    online = Path(root["path"]).is_dir()
    parts, crumbs = [p for p in path.split("/") if p], []
    for i, name in enumerate(parts):
        crumbs.append({"name": name, "path": "/".join(parts[:i + 1])})
    return {
        "root": {"id": root["id"], "name": root["name"], "online": online, "last_scan": root["last_scan"], "scan_state": root["scan_state"]},
        "drive": drive_dict(drive, online),
        "path": path, "name": folder["name"] if path else root["name"], "crumbs": crumbs,
        "abs_path": str(Path(root["path"]).joinpath(*parts)),
        "files": folder["total_files"], "bytes": folder["total_bytes"], "subfolders": folder["subfolders"],
        "label": folder["label"], "folder_id": folder["id"],
    }
