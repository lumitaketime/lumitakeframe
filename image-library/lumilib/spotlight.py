"""Spotlight：Mac App 把「重要項目」放進 App 專用的 Spotlight 索引（Core Spotlight，只存在這台 Mac，不上傳）。

這裡只決定要放哪些項目；放進 Spotlight、點下去打開 Re'memor 跳到那裡，由 Mac App 外殼（desktop/src-tauri）處理。
放什麼：
- 每顆硬碟（包括沒接上的）與智慧資料夾。
- 目錄裡所有的資料夾與檔案，硬碟拔掉以後 Spotlight 也找得到；文件連 Re'memor 已經讀好的文字（含文字辨識、電子書）一起放
  （開頭一段），所以在 Spotlight 也能搜到「沒接上的硬碟裡、文件裡寫的字」，和 Re'memor 的搜尋找得到的一樣。
- 這台 Mac 內建磁碟上的檔案預設也放（設定 spotlight_internal）；關掉就只放外接硬碟（/Volumes 底下），
  因為 Mac 自己的 Spotlight 也找得到內建磁碟的檔案，可能會列兩次。

一百萬個項目不能每次都重送：spotlight_sync 記下已經交給 Spotlight 的每一項（和它的內容摘要），
每次只交「新增或改過的」，拿掉「已經不在的」。Mac App 分批來拿（/api/spotlight/changes），放好之後回報（ack）。

每一項：{id, path（Re'memor 裡的頁面）, title, description, keywords, type（Spotlight 用的內容類型）}。
id 就是「rememor:」加上頁面路徑，點下去時直接照著打開，不用另外記對照表。
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from urllib.parse import urlencode

from . import db
from .catalog import drives_overview


def _size(n: int) -> str:
    n = float(n or 0)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit in ("B", "KB") else f"{n:.1f} {unit}"
        n /= 1024
    return ""


def items(conn: sqlite3.Connection) -> list[dict]:
    out = []
    for d in drives_overview(conn):
        if not d["roots"]:
            continue
        path = f"/folders/{d['roots'][0]['id']}"
        state = "已接上" if d["online"] else "沒接上（目錄裡還看得到）"
        when = (d.get("last_scan") or "")[:10]
        desc = "硬碟 · " + " · ".join(x for x in (state, f"{d['files']:,} 個檔案", _size(d["bytes"]), f"上次掃描 {when}" if when else "") if x)
        out.append({"id": "rememor:" + path, "path": path, "title": d["name"], "description": desc,
                    "keywords": ["Re'memor", "硬碟", "drive", *[r["name"] for r in d["roots"]]], "type": "public.volume"})
    for r in conn.execute("SELECT id, name, query FROM smart_folders ORDER BY name"):
        try:
            q = json.loads(r["query"])
        except ValueError:
            q = {}
        params = {k: q[k] for k in ("q", "root", "path", "kind", "year", "size", "drive") if q.get(k) not in (None, "")}
        params["smart"] = r["id"]
        path = "/find?" + urlencode(params)
        out.append({"id": "rememor:" + path, "path": path, "title": r["name"], "description": f"智慧資料夾 · 搜尋「{q.get('q', '')}」",
                    "keywords": ["Re'memor", "智慧資料夾", "smart folder", str(q.get("q", ""))], "type": "public.folder"})
    return out


def payload(conn: sqlite3.Connection, enabled: bool = True) -> dict:
    """給 Mac App 的清單；version 變了才需要重新放進 Spotlight。"""
    if not enabled:
        return {"enabled": False, "version": "off", "items": []}
    data = items(conn)
    version = hashlib.sha1(json.dumps(data, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:12]
    return {"enabled": True, "version": version, "items": data}


# ---- 外接硬碟的資料夾與檔案：只交有變動的 ----

TEXT_CHARS = 20000  # 每份文件放進 Spotlight 的文字（開頭一段；一般的文件整份都放得下）
BATCH_CHARS = 2_000_000  # 一批最多帶多少字：文件很多時一批少放幾份，不讓一次傳太多
EXTERNAL_PREFIX = "/Volumes/"
_state = {"gen": 1, "clean": 0, "reset": False}  # gen：目錄有變動就加一；clean：上次整輪比對完時的 gen


def changed() -> None:
    """目錄有變動（掃描、讀文字、整理動作…做完）：下一次要再比對一輪。"""
    _state["gen"] += 1


def request_reset() -> None:
    """重新建立：清掉 Re'memor 放進 Spotlight 的所有項目，從頭放一次。"""
    _state["reset"] = True
    _state["gen"] += 1


def _synced_roots(conn: sqlite3.Connection, internal: bool = True) -> str:
    """要放進 Spotlight 的資料夾來源編號（逗號分隔，可以直接放進 SQL 的 IN）；沒有就是空字串。
    internal＝False：只放外接硬碟上的。"""
    return ",".join(str(r[0]) for r in conn.execute("SELECT id, path FROM roots")
                    if internal or str(r[1]).startswith(EXTERNAL_PREFIX))


KIND_TYPE = {"photo": "public.image", "raw": "public.camera-raw-image", "video": "public.movie", "audio": "public.audio",
             "document": "public.content", "archive": "public.archive", "package": "com.apple.package"}


def _folder_page(path: str) -> str:
    from urllib.parse import quote

    return quote(path, safe="")


def _file_item(r, text: str = "") -> dict:
    folder = r["folder"]
    page = f"/folders/{r['root_id']}?path={_folder_page(folder)}&select={_folder_page(r['name'])}"
    where = f"在「{r['drive']}」" + (f" › {folder}" if folder else "")
    when = time.strftime("%Y-%m-%d", time.localtime(r["mtime"])) if r["mtime"] else ""
    return {"id": "rememor:" + page, "path": page, "title": r["name"], "description": " · ".join(x for x in (where, _size(r["size"]), when) if x),
            "keywords": ["Re'memor", r["drive"], r["root"]], "type": KIND_TYPE.get(r["kind"], "public.data"), "text": text[:TEXT_CHARS]}


def _folder_item(r) -> dict:
    page = f"/folders/{r['root_id']}?path={_folder_page(r['path'])}"
    parent = r["path"].rpartition("/")[0]
    where = f"資料夾 · 在「{r['drive']}」" + (f" › {parent}" if parent else "")
    return {"id": "rememor:" + page, "path": page, "title": r["name"], "description": f"{where} · {_size(r['total_bytes'])}",
            "keywords": ["Re'memor", r["drive"], r["root"], "資料夾", "folder"], "type": "public.folder", "text": ""}


def changes(conn: sqlite3.Connection, cursor: str = "", limit: int = 500, enabled: bool = True, internal: bool = True) -> dict:
    """下一批要交給 Spotlight 的變動：{"upsert": [項目＋entity、sig], "delete": [{entity, id}], "cursor": 下一批或 None, "reset"}。
    cursor 是「這一輪開始時的 gen.階段.上次看到的編號」；每批最多看 limit 筆，再多的檔案也不會一次讀太多。"""
    from . import textindex

    out = {"upsert": [], "delete": [], "cursor": None, "reset": False}
    if not enabled:
        if conn.execute("SELECT 1 FROM spotlight_sync LIMIT 1").fetchone():
            conn.execute("DELETE FROM spotlight_sync")
            conn.commit()
            out["reset"] = True  # 關掉：把 Re'memor 放進去的全部拿掉
        out["synced"] = 0
        return out
    if not cursor:
        if _state["reset"]:
            _state["reset"] = False
            conn.execute("DELETE FROM spotlight_sync")
            conn.commit()
            out["reset"] = True
        elif _state["clean"] == _state["gen"]:
            out["synced"] = conn.execute("SELECT COUNT(*) FROM spotlight_sync").fetchone()[0]
            return out  # 上一輪比對完之後沒有變動
        cursor = f"{_state['gen']}.base.0"
    gen_s, phase, last_s = cursor.split(".", 2)
    gen, last = int(gen_s), int(last_s)
    def want(entity: str, item: dict, sig: str, old) -> None:
        """old：上次交給 Spotlight 的 {spot_id, sig}（沒交過是 None）。內容沒變就不重送。"""
        if old is not None and old["spot_id"] == item["id"] and old["sig"] == sig:
            return
        out["upsert"].append({**item, "entity": entity, "sig": sig})
        if old is not None and old["spot_id"] != item["id"]:
            out["delete"].append({"entity": None, "id": old["spot_id"]})  # 改名或搬家：舊的那一項拿掉

    if phase == "base":
        rows = {r["entity"]: r for r in conn.execute("SELECT entity, spot_id, sig FROM spotlight_sync "
                                                     "WHERE entity LIKE 'drive:%' OR entity LIKE 'smart:%'")}
        current = set()
        for it in items(conn):
            entity = ("smart:" if "smart=" in it["path"] else "drive:") + it["path"]
            current.add(entity)
            want(entity, {**it, "text": ""}, it["description"] + "|" + it["title"], rows.get(entity))
        for entity, r in rows.items():
            if entity not in current:
                out["delete"].append({"entity": entity, "id": r["spot_id"]})
        out["cursor"] = f"{gen}.folder.0"
    elif phase == "folder":
        ext = _synced_roots(conn, internal)
        ids = [r[0] for r in conn.execute(
            f"SELECT id FROM folders NOT INDEXED WHERE id > ? AND status = 'ok' AND path != '' AND root_id IN ({ext}) ORDER BY id LIMIT ?",
            (last, limit))] if ext else []
        rows = conn.execute(
            "SELECT d.id, d.root_id, d.name, d.path, d.total_bytes, r.name AS root, COALESCE(v.name, r.name) AS drive, "
            "s.spot_id, s.sig FROM folders d JOIN roots r ON r.id = d.root_id LEFT JOIN drives v ON v.id = r.drive_id "
            "LEFT JOIN spotlight_sync s ON s.entity = 'folder:' || d.id "
            f"WHERE d.id IN ({','.join('?' * len(ids))}) ORDER BY d.id", ids).fetchall() if ids else []
        for r in rows:
            item = _folder_item(r)
            want(f"folder:{r['id']}", item, f"{r['name']}|{r['path']}|{r['total_bytes']}|{r['drive']}",
                 {"spot_id": r["spot_id"], "sig": r["sig"]} if r["spot_id"] else None)
        out["cursor"] = f"{gen}.folder.{ids[-1]}" if len(ids) == limit else f"{gen}.file.0"
    elif phase == "file":
        # 先依編號（主鍵）挑出這一批，再讀細節：不讓 SQLite 先把整顆硬碟的檔案排序一遍
        ext = _synced_roots(conn, internal)
        ids = [r[0] for r in conn.execute(
            f"SELECT id FROM files NOT INDEXED WHERE id > ? AND status = 'ok' AND root_id IN ({ext}) ORDER BY id LIMIT ?",
            (last, limit))] if ext else []
        rows = conn.execute(
            "SELECT f.id, f.root_id, f.name, f.kind, f.size, f.mtime, d.path AS folder, r.name AS root, COALESCE(v.name, r.name) AS drive, "
            "t.chars, t.status AS tstatus, s.spot_id, s.sig FROM files f JOIN folders d ON d.id = f.folder_id JOIN roots r ON r.id = f.root_id "
            "LEFT JOIN drives v ON v.id = r.drive_id LEFT JOIN file_text t ON t.file_id = f.id "
            "LEFT JOIN spotlight_sync s ON s.entity = 'file:' || f.id "
            f"WHERE f.id IN ({','.join('?' * len(ids))}) ORDER BY f.id", ids).fetchall() if ids else []
        chars, seen, full = 0, last, False
        for r in rows:
            if chars >= BATCH_CHARS:
                full = True  # 這一批的字夠多了：剩下的下一批再放
                break
            seen = r["id"]
            sig = f"{r['name']}|{r['folder']}|{r['size']}|{r['mtime']}|{r['chars'] or 0}|{r['drive']}|{TEXT_CHARS}"
            old = {"spot_id": r["spot_id"], "sig": r["sig"]} if r["spot_id"] else None
            if old is not None and old["sig"] == sig:
                continue
            text = textindex.body(conn, r["id"])[:TEXT_CHARS] if r["tstatus"] == "ok" else ""
            chars += len(text)
            want(f"file:{r['id']}", _file_item(r, text), sig, old)
        out["cursor"] = f"{gen}.file.{seen}" if full or len(ids) == limit else f"{gen}.gone.0"
    elif phase == "gone":
        # 已經交給 Spotlight、但現在不在了（刪掉、遺失、硬碟從目錄移除）的資料夾與檔案；一批一批交給 SQLite 判斷
        ext = _synced_roots(conn, internal)
        page = conn.execute("SELECT MAX(rowid), COUNT(*) FROM (SELECT rowid FROM spotlight_sync WHERE rowid > ? ORDER BY rowid LIMIT ?)",
                            (last, limit * 4)).fetchone()
        top, n = page[0], page[1]
        if n:
            rows = conn.execute(
                "SELECT s.entity, s.spot_id FROM spotlight_sync s WHERE s.rowid > ? AND s.rowid <= ? AND ("
                f"(s.entity LIKE 'file:%' AND NOT EXISTS (SELECT 1 FROM files f "
                f"WHERE f.id = CAST(substr(s.entity, 6) AS INTEGER) AND f.status = 'ok' AND f.root_id IN ({ext or 'NULL'}))) OR "
                f"(s.entity LIKE 'folder:%' AND NOT EXISTS (SELECT 1 FROM folders d "
                f"WHERE d.id = CAST(substr(s.entity, 8) AS INTEGER) AND d.status = 'ok' AND d.root_id IN ({ext or 'NULL'}))))",
                (last, top)).fetchall()
            out["delete"] += [{"entity": r["entity"], "id": r["spot_id"]} for r in rows]
        if n == limit * 4:
            out["cursor"] = f"{gen}.gone.{top}"
        else:
            out["cursor"] = None
            if gen == _state["gen"]:
                _state["clean"] = gen  # 這一輪比對完了，中間也沒有新的變動
    out["synced"] = conn.execute("SELECT COUNT(*) FROM spotlight_sync").fetchone()[0]
    return out


def ack(conn: sqlite3.Connection, done: list, deleted: list) -> int:
    """Mac App 放好了：記下哪些已經在 Spotlight 裡（之後只交有變動的）。"""
    now = db.now_iso()
    rows = [(d["entity"], d["id"], d["sig"], now) for d in done if isinstance(d, dict) and d.get("entity")]
    conn.executemany("INSERT INTO spotlight_sync (entity, spot_id, sig, synced_at) VALUES (?, ?, ?, ?) "
                     "ON CONFLICT(entity) DO UPDATE SET spot_id = excluded.spot_id, sig = excluded.sig, synced_at = excluded.synced_at", rows)
    gone = [d for d in deleted if isinstance(d, str) and d]
    for start in range(0, len(gone), 500):
        part = gone[start:start + 500]
        conn.execute(f"DELETE FROM spotlight_sync WHERE entity IN ({','.join('?' * len(part))})", part)
    conn.commit()
    return len(rows)
