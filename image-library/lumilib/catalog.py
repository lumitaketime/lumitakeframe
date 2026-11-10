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
