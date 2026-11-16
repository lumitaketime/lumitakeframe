"""待刪除：使用者在「重複項目」標記的多餘副本，以及最後由使用者親手確認的清理動作。

安全原則（核心原則第 1 條：永不自動刪除）：
- 標記只是在 Re'memor 的資料庫記一筆，硬碟上什麼都不變，隨時可以取消。
- 只有完整比對過、內容確定相同的組別能標記；每一組至少保留一份（這裡再檢查一次，不只靠介面）。
- 真正清理前再驗證一次：要移走的那份沒被改過、保留的那份還在而且也沒被改過。任何一項不符就跳過並說明原因。
- 只移到 macOS 的垃圾桶（可以救回），不直接刪除。唯讀的硬碟（例如 NTFS）改成匯出清單，不寫入那顆硬碟。
- 這個模組的清理函式只能由使用者在介面上按下確認後呼叫；背景工作、排程、AI 都不會呼叫它。
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from . import db, fileops
from .dupes import _place



class MarkError(ValueError):
    """標記被拒絕，訊息是給使用者看的。"""


def _rows(conn: sqlite3.Connection, kind: str, ids: list[int]) -> list[sqlite3.Row]:
    if kind not in ("file", "folder"):
        raise MarkError("不認得的項目種類")
    ids = [int(i) for i in ids]
    if not ids:
        return []
    marks = ",".join("?" * len(ids))
    if kind == "file":
        sql = (f"SELECT f.id, f.root_id, f.size, f.content_hash AS sig, f.status, d.path AS folder, f.name FROM files f "
               f"JOIN folders d ON d.id = f.folder_id WHERE f.id IN ({marks})")
    else:
        sql = f"SELECT id, root_id, total_bytes AS size, content_sig AS sig, status, path, name FROM folders WHERE id IN ({marks})"
    rows = conn.execute(sql, ids).fetchall()
    if len(rows) != len(set(ids)):
        raise MarkError("有項目已經不在目錄裡了，請重新整理後再試")
    return rows


def _path(kind: str, r: sqlite3.Row) -> str:
    return (f"{r['folder']}/{r['name']}" if r["folder"] else r["name"]) if kind == "file" else r["path"]


def marked_ids(conn: sqlite3.Connection, kind: str) -> set[int]:
    return {r[0] for r in conn.execute("SELECT item_id FROM delete_marks WHERE kind = ?", (kind,))}


def mark(conn: sqlite3.Connection, kind: str, keep: list[int], remove: list[int]) -> int:
    """把 remove 標記為待刪除；keep 是使用者要保留的。只寫資料庫，不動硬碟。"""
    keep, remove = [int(i) for i in keep or []], [int(i) for i in remove or []]
    if not remove:
        return 0
    if not keep:
        raise MarkError("至少要保留一份")
    if set(keep) & set(remove):
        raise MarkError("同一個項目不能同時保留又標記為待刪除")
    rows = _rows(conn, kind, keep + remove)
    sigs = {r["sig"] for r in rows}
    if None in sigs or any(r["status"] != "ok" for r in rows):
        raise MarkError("這一組還沒完整比對內容（待確認），不能標記為待刪除")
    if len(sigs) != 1:
        raise MarkError("這些項目的內容不完全相同，不能當成同一組")
    already = marked_ids(conn, kind)
    if any(i in already for i in keep):
        raise MarkError("要保留的項目已經被標記為待刪除，請先取消標記")
    by_id = {r["id"]: r for r in rows}
    now = db.now_iso()
    n = 0
    for i in remove:
        r = by_id[i]
        n += conn.execute(
            "INSERT OR IGNORE INTO delete_marks (kind, item_id, root_id, path, size, sig, marked_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (kind, i, r["root_id"], _path(kind, r), r["size"], r["sig"], now)).rowcount
    conn.commit()
    return n


def unmark(conn: sqlite3.Connection, mark_ids: list[int]) -> int:
    ids = [int(i) for i in mark_ids or []]
    if not ids:
        return 0
    n = conn.execute(f"DELETE FROM delete_marks WHERE id IN ({','.join('?' * len(ids))})", ids).rowcount
    conn.commit()
    return n


def _current_sig(conn: sqlite3.Connection, m: sqlite3.Row) -> str | None:
    if m["kind"] == "file":
        r = conn.execute("SELECT content_hash FROM files WHERE id = ? AND status = 'ok'", (m["item_id"],)).fetchone()
    else:
        r = conn.execute("SELECT content_sig FROM folders WHERE id = ? AND status = 'ok'", (m["item_id"],)).fetchone()
    return r[0] if r else None


def listing(conn: sqlite3.Connection) -> dict:
    """待刪除清單，依硬碟分組。stale＝標記之後內容變了或項目不見了，要重新比對才能清理。"""
    place = _place(conn)
    drives: dict[str, dict] = {}
    for m in conn.execute("SELECT * FROM delete_marks ORDER BY root_id, path"):
        p = place.get(m["root_id"], {})
        key = p.get("drive", "")
        d = drives.setdefault(key, {"drive": key, "online": False, "read_only": bool(p.get("read_only")), "items": [], "bytes": 0})
        d["online"] = d["online"] or bool(p.get("online"))
        stale = _current_sig(conn, m) != m["sig"]
        d["items"].append({"id": m["id"], "kind": m["kind"], "item_id": m["item_id"], "name": m["path"].rsplit("/", 1)[-1], "path": m["path"],
                           "size": m["size"], "root_id": m["root_id"], "root": p.get("root"), "online": bool(p.get("online")), "stale": stale})
        d["bytes"] += m["size"]
    out = sorted(drives.values(), key=lambda d: d["drive"].casefold())
    return {"drives": out, "count": sum(len(d["items"]) for d in out), "bytes": sum(d["bytes"] for d in out)}


def count(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) FROM delete_marks").fetchone()[0]


# ---- 清理前的驗證 ----

def _abs(conn: sqlite3.Connection, root_id: int, rel: str) -> Path | None:
    root = conn.execute("SELECT path FROM roots WHERE id = ?", (root_id,)).fetchone()
    if root is None:
        return None
    return fileops.safe_folder(Path(root["path"]), rel)


def _file_intact(path: Path, size: int, mtime: float) -> bool:
    try:
        st = path.stat()
    except OSError:
        return False
    return path.is_file() and st.st_size == size and st.st_mtime == mtime


def _folder_intact(conn: sqlite3.Connection, folder_id: int, root_id: int, rel: str) -> str | None:
    """資料夾和目錄裡記的一模一樣才回傳 None，否則回傳原因。多出任何檔案也不行（那是掃描之後才放進去的）。"""
    base = _abs(conn, root_id, rel)
    if base is None or not base.is_dir():
        return "資料夾不在原來的位置"
    like = rel.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    known = {}
    for r in conn.execute(
            "SELECT d.path AS folder, f.name, f.size, f.mtime FROM files f JOIN folders d ON d.id = f.folder_id "
            "WHERE f.root_id = ? AND f.status = 'ok' AND (d.path = ? OR d.path LIKE ? ESCAPE '\\')", (root_id, rel, like + "/%")):
        sub = r["folder"][len(rel):].strip("/")
        known[f"{sub}/{r['name']}" if sub else r["name"]] = (r["size"], r["mtime"])
    seen = 0
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for name in filenames:
            if name.startswith("."):
                continue  # 系統的隱藏檔（.DS_Store 等）掃描時本來就不記
            relname = str(Path(dirpath, name).relative_to(base)).replace(os.sep, "/")
            if relname not in known:
                return f"裡面多了目錄裡沒有的檔案（{relname}），請重新掃描"
            st = os.stat(os.path.join(dirpath, name))
            if (st.st_size, st.st_mtime) != known[relname]:
                return f"裡面的檔案在掃描後被改過（{relname}），請重新掃描並比對"
            seen += 1
    if seen != len(known):
        return "裡面少了目錄裡記錄的檔案，請重新掃描"
    return None


def _check(conn: sqlite3.Connection, kind: str, item_id: int) -> str | None:
    """這個項目現在和目錄裡記的一樣嗎？一樣回傳 None。"""
    if kind == "file":
        r = conn.execute("SELECT f.root_id, f.size, f.mtime, f.name, d.path AS folder FROM files f JOIN folders d ON d.id = f.folder_id "
                         "WHERE f.id = ? AND f.status = 'ok'", (item_id,)).fetchone()
        if r is None:
            return "已經不在目錄裡"
        path = _abs(conn, r["root_id"], f"{r['folder']}/{r['name']}" if r["folder"] else r["name"])
        return None if path and _file_intact(path, r["size"], r["mtime"]) else "檔案在掃描後被改過或不見了，請重新掃描並比對"
    r = conn.execute("SELECT root_id, path FROM folders WHERE id = ? AND status = 'ok'", (item_id,)).fetchone()
    if r is None:
        return "已經不在目錄裡"
    return _folder_intact(conn, item_id, r["root_id"], r["path"])


def _keepers(conn: sqlite3.Connection, m: sqlite3.Row) -> list[tuple[int, int]]:
    """同一組裡沒有被標記的其他副本：[(item_id, root_id)]。"""
    marked = marked_ids(conn, m["kind"])
    if m["kind"] == "file":
        rows = conn.execute("SELECT id, root_id FROM files WHERE content_hash = ? AND status = 'ok'", (m["sig"],)).fetchall()
    else:
        rows = conn.execute("SELECT id, root_id FROM folders WHERE content_sig = ? AND status = 'ok'", (m["sig"],)).fetchall()
    return [(r["id"], r["root_id"]) for r in rows if r["id"] not in marked and r["id"] != m["item_id"]]


def clean(conn: sqlite3.Connection, mark_ids: list[int], trash=None) -> dict:
    """把標記的項目移到垃圾桶。只能由使用者在介面上確認後呼叫。逐項驗證，不符的跳過並回報原因。"""
    trash = trash or fileops._send_to_trash
    place = _place(conn)
    ids = [int(i) for i in mark_ids or []]
    marks = conn.execute(f"SELECT * FROM delete_marks WHERE id IN ({','.join('?' * len(ids))}) ORDER BY root_id, path", ids).fetchall() if ids else []
    done, skipped, freed = [], [], 0
    touched: set[int] = set()

    def skip(m, why: str) -> None:
        skipped.append({"id": m["id"], "path": m["path"], "reason": why})

    for m in marks:
        p = place.get(m["root_id"], {})
        if not p.get("online"):
            skip(m, f"請接上「{p.get('drive', '')}」")
            continue
        if p.get("read_only"):
            skip(m, "這顆硬碟是唯讀的，請改用「匯出清單」")
            continue
        if _current_sig(conn, m) != m["sig"]:
            skip(m, "標記之後內容有變動，請重新比對")
            continue
        why = _check(conn, m["kind"], m["item_id"])
        if why:
            skip(m, why)
            continue
        # 至少要有一份保留的副本現在驗證得過，才可以移走這一份
        keepers = _keepers(conn, m)
        if not keepers:
            skip(m, "找不到要保留的那一份，為了安全不處理")
            continue
        verified, offline = False, False
        for kid, kroot in keepers:
            if not place.get(kroot, {}).get("online"):
                offline = True
                continue
            if _check(conn, m["kind"], kid) is None:
                verified = True
                break
        if not verified:
            skip(m, "保留的那一份所在的硬碟沒有接上，無法確認它還在" if offline else "保留的那一份在掃描後有變動，請重新掃描並比對")
            continue
        target = _abs(conn, m["root_id"], m["path"])
        try:
            trash(target)
        except Exception as exc:  # noqa: BLE001
            skip(m, f"無法移到垃圾桶：{exc}")
            continue
        # 目錄跟著更新：這些項目不在原來的位置了
        if m["kind"] == "file":
            conn.execute("UPDATE files SET status = 'missing' WHERE id = ?", (m["item_id"],))
        else:
            like = m["path"].replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            sub = "SELECT id FROM folders WHERE root_id = ? AND (path = ? OR path LIKE ? ESCAPE '\\')"
            args = (m["root_id"], m["path"], like + "/%")
            conn.execute(f"UPDATE files SET status = 'missing' WHERE folder_id IN ({sub})", args)
            conn.execute(f"UPDATE folders SET status = 'missing' WHERE id IN ({sub})", args)
        conn.execute("DELETE FROM delete_marks WHERE id = ?", (m["id"],))
        conn.commit()
        done.append({"id": m["id"], "path": m["path"]})
        freed += m["size"]
        touched.add(m["root_id"])
    if touched:
        from .catalog import update_folder_totals
        from .dupes import update_folder_signatures

        for rid in touched:
            update_folder_totals(conn, rid)
            update_folder_signatures(conn, rid)
        conn.commit()
    return {"trashed": done, "skipped": skipped, "bytes": freed}


def export_list(conn: sqlite3.Connection, home: Path, drive: str) -> Path:
    """把某顆硬碟的待刪除清單存成文字檔（存在 Re'memor 的資料目錄，不寫入那顆硬碟）。"""
    data = next((d for d in listing(conn)["drives"] if d["drive"] == drive), None)
    if not data or not data["items"]:
        raise MarkError("這顆硬碟沒有待刪除的項目")
    folder = Path(home) / "exports"
    folder.mkdir(parents=True, exist_ok=True)
    safe = "".join(c if c.isalnum() or c in " -_（）" else "_" for c in drive).strip() or "drive"
    out = folder / f"待刪除清單 {safe} {db.now_iso()[:10]}.txt"
    lines = [f"Re'memor 待刪除清單：{drive}", f"共 {len(data['items'])} 個項目，{data['bytes']:,} 位元組",
             "這些是你標記為多餘副本的項目；每一項在其他地方都有內容相同的副本。", ""]
    for it in data["items"]:
        mark = "資料夾" if it["kind"] == "folder" else "檔案"
        root = f"{it['root']}/" if it["root"] and it["root"] != drive else ""
        lines.append(f"{mark}\t{it['size']:,}\t{root}{it['path']}")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out
