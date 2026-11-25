"""整理計畫：把檔案複製到另一顆硬碟（例如淘汰前，把「只在這顆上」的檔案備份到別顆）。

安全原則（核心原則一、七）：
- 只在本人按下確認後才做；只寫入本人選的那顆目標硬碟，來源硬碟只讀。
- 先複製成暫時的名字，兩邊都從頭到尾算完整指紋，一模一樣才改成正式的名字；不一樣就丟掉那份暫存、記下原因。
- 目標已經有同名的檔案：內容一樣就不再複製（記成「已經有了」）；不一樣就另取名字，絕不覆蓋。
- 不刪除任何原本的檔案。選了「標記原本那份」時，只把原本那份放進「待刪除」清單（之後還要本人確認才會清理）。
- 復原：把複製過去的檔案移到垃圾桶（先確認還是當初複製的那份），原本的檔案不動。
- 可以暫停、拔掉硬碟，下次從還沒做的接著做。
"""
from __future__ import annotations

import os
import shutil
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import db
from .classify import pretty_name

TMP_PREFIX = ".rememor-copying-"
DEFAULT_DIR = "Re'memor 集中"
FREE_MARGIN = 1_000_000_000  # 目標硬碟至少要多留 1GB
COMMIT_SECONDS = 2.0


class PlanError(ValueError):
    """計畫做不了，訊息是給使用者看的。"""


def _root(conn: sqlite3.Connection, root_id) -> sqlite3.Row:
    r = conn.execute("SELECT * FROM roots WHERE id = ?", (int(root_id),)).fetchone()
    if r is None:
        raise PlanError("找不到這顆硬碟")
    return r


def _name(conn: sqlite3.Connection, r) -> str:
    from .retire import _name_of

    return _name_of(conn, r)


def _read_only(conn: sqlite3.Connection, r) -> bool:
    if r["drive_id"] is None:
        return False
    d = conn.execute("SELECT read_only, fs_type FROM drives WHERE id = ?", (r["drive_id"],)).fetchone()
    return bool(d and (d["read_only"] or (d["fs_type"] or "").lower() == "ntfs"))


def _clean_rel(rel: str) -> str:
    parts = [p for p in str(rel or "").replace("\\", "/").split("/") if p not in ("", ".", "..")]
    return "/".join(parts)


def source_files(conn: sqlite3.Connection, source, states=("only",), folder: str | None = None) -> list[sqlite3.Row]:
    """要複製的檔案：某個資料夾裡的全部檔案，或淘汰檢查裡某幾類（預設「只在這顆上」）。系統小檔案不複製。"""
    from .retire import _junk_sql, analyze

    if folder is not None:
        rel = _clean_rel(folder)
        like = rel.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "/%"
        return conn.execute(
            "SELECT f.id, f.name, f.ext, f.kind, f.size, f.mtime, f.content_hash, f.quick_sig, d.path AS folder FROM files f "
            "JOIN folders d ON d.id = f.folder_id WHERE f.root_id = ? AND f.status = 'ok' "
            f"AND (? = '' OR d.path = ? OR d.path LIKE ? ESCAPE '\\') AND NOT {_junk_sql()} ORDER BY d.path, f.name",
            (source["id"], rel, rel, like)).fetchall()
    analyze(conn, source["id"])
    states = [s for s in states if s in ("only", "maybe", "risky")] or ["only"]
    return conn.execute(
        "SELECT f.id, f.name, f.ext, f.kind, f.size, f.mtime, f.content_hash, f.quick_sig, d.path AS folder FROM retire_files r "
        f"JOIN files f ON f.id = r.file_id JOIN folders d ON d.id = f.folder_id WHERE r.root_id = ? AND r.state IN ({','.join('?' * len(states))}) "
        "ORDER BY d.path, f.name", (source["id"], *states)).fetchall()


def plan(conn: sqlite3.Connection, source_root, target_root, dest: str | None = None, states=("only",),
         folder: str | None = None) -> dict:
    """整理計畫的內容（還沒做任何事）：要複製哪些檔案、放到哪裡、要多少空間。"""
    src, dst = _root(conn, source_root), _root(conn, target_root)
    from .retire import _drive_key

    if _drive_key(src) == _drive_key(dst):
        raise PlanError("來源和目標在同一顆硬碟上，複製過去也不算備份；請選另一顆硬碟")
    if _read_only(conn, dst):
        raise PlanError(f"「{_name(conn, dst)}」是唯讀的硬碟（例如 NTFS），Mac 不能寫入；請選別顆")
    rows = source_files(conn, src, states, folder)
    if not rows:
        raise PlanError("沒有要複製的檔案")
    base = _clean_rel(dest) if dest else f"{DEFAULT_DIR}/{_name(conn, src)}"
    if not base:
        raise PlanError("請選目標硬碟上的資料夾")
    total = sum(r["size"] for r in rows)
    free = None
    if Path(dst["path"]).is_dir():
        try:
            free = shutil.disk_usage(dst["path"]).free
        except OSError:
            free = None
    return {"source_root": src["id"], "target_root": dst["id"], "source": _name(conn, src), "target": _name(conn, dst),
            "dest": base, "states": list(states), "folder": folder, "files": len(rows), "bytes": total, "free": free,
            "enough": free is None or free >= total + FREE_MARGIN,
            "examples": [{"name": pretty_name(r["name"]), "from": pretty_name("/".join(p for p in (r["folder"], r["name"]) if p)),
                          "to": pretty_name("/".join(p for p in (base, r["folder"], r["name"]) if p)), "size": r["size"]} for r in rows[:8]]}


def stage(conn: sqlite3.Connection, action_id: int, payload: dict) -> int:
    """按下確認：把這次要複製的每一個檔案記下來（之後中斷了也知道做到哪裡）。"""
    src = _root(conn, payload["source_root"])
    rows = source_files(conn, src, payload.get("states") or ("only",), payload.get("folder"))
    base = payload["dest"]
    conn.executemany(
        "INSERT OR IGNORE INTO consolidate_items (action_id, file_id, dst_path, size) VALUES (?, ?, ?, ?)",
        [(action_id, r["id"], "/".join(p for p in (base, r["folder"], r["name"]) if p), r["size"]) for r in rows])
    conn.commit()
    return len(rows)


@dataclass
class CopyResult:
    copied: int = 0
    same: int = 0
    failed: int = 0
    bytes: int = 0
    stopped: bool = False
    interrupted: list[str] = field(default_factory=list)
    error: str = ""
    marked: int = 0


def _free_name(path: Path) -> Path:
    stem, suf = path.stem, path.suffix
    for n in range(2, 1000):
        cand = path.with_name(f"{stem} ({n}){suf}")
        if not cand.exists():
            return cand
    raise OSError("找不到可以用的檔名")


def _ensure_folder(conn: sqlite3.Connection, root_id: int, rel: str, now: str) -> int:
    """目錄裡補上剛建立的資料夾（和上層）。"""
    rel = _clean_rel(rel)
    row = conn.execute("SELECT id FROM folders WHERE root_id = ? AND path = ?", (root_id, rel)).fetchone()
    if row:
        conn.execute("UPDATE folders SET status = 'ok' WHERE id = ?", (row["id"],))
        return row["id"]
    parent = None if rel == "" else _ensure_folder(conn, root_id, rel.rsplit("/", 1)[0] if "/" in rel else "", now)
    gen = conn.execute("SELECT scan_gen FROM roots WHERE id = ?", (root_id,)).fetchone()[0] or 0
    return conn.execute("INSERT INTO folders (root_id, parent_id, path, name, first_seen, last_seen, scan_gen) VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (root_id, parent, rel, rel.rsplit("/", 1)[-1] if rel else "", now, now, gen)).lastrowid


def run(conn: sqlite3.Connection, action_id: int, payload: dict, progress=None, stop=None) -> CopyResult:
    """複製還沒做的檔案。每一個都先複製成暫存檔、兩邊完整比對一樣才改成正式名字。"""
    from .dupes import Stopped, hash_file
    from .scanner import fingerprint

    res = CopyResult()
    src, dst = _root(conn, payload["source_root"]), _root(conn, payload["target_root"])
    src_path, dst_path = Path(src["path"]), Path(dst["path"])
    for r, label in ((src, "來源"), (dst, "目標")):
        if not Path(r["path"]).is_dir():
            res.error = f"{label}硬碟「{_name(conn, r)}」沒有接上，接上後可以繼續"
            return res
    todo = conn.execute(
        "SELECT c.file_id, c.dst_path, c.size, f.name, f.ext, f.kind, f.mtime, f.content_hash, d.path AS folder FROM consolidate_items c "
        "JOIN files f ON f.id = c.file_id JOIN folders d ON d.id = f.folder_id WHERE c.action_id = ? AND c.status = 'todo' "
        "ORDER BY c.dst_path", (action_id,)).fetchall()
    need = sum(r["size"] for r in todo)
    try:
        if shutil.disk_usage(dst_path).free < need + FREE_MARGIN:
            res.error = f"「{_name(conn, dst)}」的空間不夠（還要 {need / 1e9:.1f} GB，另外要多留 1 GB）"
            return res
    except OSError:
        pass
    total = len(todo)
    last = time.monotonic()
    now = db.now_iso()

    def mark(r, status: str, note: str = "", new_id=None, mtime=None, dst_rel=None) -> None:
        conn.execute("UPDATE consolidate_items SET status = ?, note = ?, new_file_id = ?, dst_mtime = ?, dst_path = COALESCE(?, dst_path) "
                     "WHERE action_id = ? AND file_id = ?", (status, note[:200], new_id, mtime, dst_rel, action_id, r["file_id"]))

    def register(r, final: Path, digest: str) -> int:
        """目錄裡記下複製出來的那份（含完整指紋），淘汰檢查馬上就認得它是副本。"""
        rel = final.relative_to(dst_path).as_posix()
        folder_rel = rel.rsplit("/", 1)[0] if "/" in rel else ""
        fid = _ensure_folder(conn, dst["id"], folder_rel, now)
        st = final.stat()
        old = conn.execute("SELECT id, size FROM files WHERE folder_id = ? AND name = ?", (fid, final.name)).fetchone()
        if old is not None and old["size"] == st.st_size:  # 目錄裡已經有這一筆（例如本來就在目標上）：補上指紋就好
            conn.execute("UPDATE files SET status = 'ok', mtime = ?, content_hash = ?, hashed_at = ?, last_seen = ? WHERE id = ?",
                         (st.st_mtime, digest, now, now, old["id"]))
            return old["id"]
        if old is not None:
            conn.execute("DELETE FROM files WHERE id = ?", (old["id"],))
        return conn.execute(
            "INSERT INTO files (root_id, folder_id, name, ext, kind, size, mtime, ctime, first_seen, last_seen, content_hash, hashed_at, quick_sig) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (dst["id"], fid, final.name, r["ext"], r["kind"], st.st_size, st.st_mtime, getattr(st, "st_birthtime", st.st_ctime), now, now,
             digest, now, fingerprint(final, st.st_size))).lastrowid

    try:
        for i, r in enumerate(todo):
            if stop is not None and stop.is_set():
                raise Stopped
            if progress:
                progress(i, total, r["name"])
            source = src_path.joinpath(*[p for p in (r["folder"] or "").split("/") if p], r["name"])
            target = dst_path.joinpath(*r["dst_path"].split("/"))
            tmp = target.with_name(TMP_PREFIX + target.name)
            try:
                st = source.stat()
                if st.st_size != r["size"] or st.st_mtime != r["mtime"]:
                    mark(r, "failed", "掃描之後這個檔案被改過，先重新掃描來源硬碟")
                    res.failed += 1
                    continue
                digest = r["content_hash"] or hash_file(source, stop)
                if r["content_hash"] is None:
                    conn.execute("UPDATE files SET content_hash = ?, hashed_at = ? WHERE id = ? AND size = ? AND mtime = ?",
                                 (digest, now, r["file_id"], r["size"], r["mtime"]))
                if target.exists():
                    if target.is_file() and target.stat().st_size == r["size"] and hash_file(target, stop) == digest:
                        new_id = register(r, target, digest)
                        mark(r, "same", "目標已經有一模一樣的檔案", new_id, None)  # 不是這次複製的：復原時不動它
                        res.same += 1
                        continue
                    target = _free_name(target)  # 同名但內容不同：另取名字，不覆蓋
                    tmp = target.with_name(TMP_PREFIX + target.name)
                target.parent.mkdir(parents=True, exist_ok=True)
                if tmp.exists():
                    tmp.unlink()  # 上次中斷留下的暫存（是 Re'memor 自己建立的）
                shutil.copy2(source, tmp)
                if hash_file(tmp, stop) != digest:
                    tmp.unlink()
                    mark(r, "failed", "複製後比對內容不一樣，已經丟掉那份暫存，請檢查目標硬碟")
                    res.failed += 1
                    continue
                if target.exists():  # 複製的過程中有人放了同名的檔案：不覆蓋
                    target = _free_name(target)
                os.replace(tmp, target)
                new_id = register(r, target, digest)
                mark(r, "done", "", new_id, target.stat().st_mtime, target.relative_to(dst_path).as_posix())
                res.copied += 1
                res.bytes += r["size"]
            except Stopped:
                if tmp.exists():
                    tmp.unlink()
                raise
            except OSError as exc:
                if tmp.exists():
                    try:
                        tmp.unlink()
                    except OSError:
                        pass
                gone = [n for n, p in ((_name(conn, src), src_path), (_name(conn, dst), dst_path)) if not p.is_dir()]
                if gone:  # 硬碟被拔掉：先停，下次接著做
                    res.interrupted = gone
                    break
                mark(r, "failed", f"讀寫失敗：{exc.strerror or exc}")
                res.failed += 1
            if time.monotonic() - last >= COMMIT_SECONDS:
                conn.commit()
                last = time.monotonic()
    except Stopped:
        res.stopped = True
    conn.commit()
    from .catalog import update_folder_totals
    from .dupes import update_folder_signatures

    update_folder_totals(conn, dst["id"])
    update_folder_signatures(conn, dst["id"])
    if payload.get("mark_source") and not res.stopped and not res.interrupted:
        res.marked = _mark_sources(conn, action_id)
    conn.commit()
    if progress:
        progress(total, total, "")
    return res


def _mark_sources(conn: sqlite3.Connection, action_id: int) -> int:
    """複製並確認好的：原本那份放進「待刪除」清單（只是標記，清理還要本人確認）。"""
    from .pending import MarkError, mark

    n = 0
    for r in conn.execute("SELECT file_id, new_file_id FROM consolidate_items WHERE action_id = ? AND status IN ('done', 'same') "
                          "AND new_file_id IS NOT NULL", (action_id,)).fetchall():
        try:
            n += mark(conn, "file", [r["new_file_id"]], [r["file_id"]])
        except MarkError:
            continue
    return n


def counts(conn: sqlite3.Connection, action_id: int) -> dict:
    out = {"todo": 0, "done": 0, "same": 0, "failed": 0, "undone": 0, "bytes": 0}
    for r in conn.execute("SELECT status, COUNT(*) AS n, SUM(size) AS b FROM consolidate_items WHERE action_id = ? GROUP BY status", (action_id,)):
        out[r["status"]] = r["n"]
        if r["status"] == "done":
            out["bytes"] = r["b"] or 0
    out["failures"] = [{"name": r["dst_path"].rsplit("/", 1)[-1], "note": r["note"]} for r in conn.execute(
        "SELECT dst_path, note FROM consolidate_items WHERE action_id = ? AND status = 'failed' LIMIT 20", (action_id,))]
    return out


def undo(conn: sqlite3.Connection, action_id: int, payload: dict, trash=None) -> list[str]:
    """復原：複製過去的檔案移到垃圾桶（先確認還是當初那份），目錄裡也拿掉；待刪除的標記取消。原本的檔案不動。"""
    from .fileops import _send_to_trash

    trash = trash or _send_to_trash
    dst = _root(conn, payload["target_root"])
    base = Path(dst["path"])
    if not base.is_dir():
        raise PlanError(f"請先接上「{_name(conn, dst)}」再復原")
    problems = []
    conn.execute("DELETE FROM delete_marks WHERE kind = 'file' AND item_id IN (SELECT file_id FROM consolidate_items "
                 "WHERE action_id = ? AND status IN ('done', 'same'))", (action_id,))
    for r in conn.execute("SELECT file_id, dst_path, size, dst_mtime, new_file_id FROM consolidate_items WHERE action_id = ? AND status = 'done'",
                          (action_id,)).fetchall():
        p = base.joinpath(*r["dst_path"].split("/"))
        try:
            st = p.stat()
        except FileNotFoundError:
            conn.execute("UPDATE consolidate_items SET status = 'undone' WHERE action_id = ? AND file_id = ?", (action_id, r["file_id"]))
            continue
        if st.st_size != r["size"] or (r["dst_mtime"] is not None and st.st_mtime != r["dst_mtime"]):
            problems.append(f"{p.name}：複製之後被改過，留著沒動")
            continue
        try:
            trash(p)
        except OSError as exc:
            problems.append(f"{p.name}：{exc}")
            continue
        if r["new_file_id"]:
            conn.execute("DELETE FROM files WHERE id = ?", (r["new_file_id"],))
        conn.execute("UPDATE consolidate_items SET status = 'undone' WHERE action_id = ? AND file_id = ?", (action_id, r["file_id"]))
    from .catalog import update_folder_totals

    update_folder_totals(conn, dst["id"])
    conn.commit()
    return problems


def describe(r: CopyResult, payload: dict) -> str:
    if r.error:
        return f"沒辦法複製：{r.error}"
    text = f"複製到「{payload.get('target')}」：{r.copied:,} 個檔案複製並比對確認一模一樣"
    if r.same:
        text += f"，{r.same:,} 個目標已經有了"
    if r.failed:
        text += f"，{r.failed:,} 個沒做成（原因寫在動作紀錄裡）"
    if r.marked:
        text += f"；原本的 {r.marked:,} 個放進「待刪除」（還沒刪，要你確認才會清理）"
    if r.interrupted:
        text += "；中途被拔掉：" + "、".join(f"「{n}」" for n in r.interrupted) + "，接上後可以繼續"
    if r.stopped:
        text += "；已暫停，之後會接著做"
    return text
