"""重複項目：內容完全相同的檔案與資料夾。

安全原則（核心原則第 1、7 條）：
- 「大小相同」只是候選；要把整個檔案從頭讀到尾算出完整指紋，才算確認相同。
  （掃描時的 fingerprint 只讀頭尾各 64KB，不能當刪除依據。）
- 這裡只讀取檔案、只寫 Re'memor 自己的資料庫；不刪除、不搬移、不在硬碟上建立任何東西。
- 還沒完整比對的組別標成「待確認」，不能標記為待刪除。
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import db

CHUNK = 1024 * 1024
BIG_FILE = 1_000_000_000  # 第一段只比對 1GB 以下的候選；更大的檔案等使用者決定要不要讀
COMMIT_ROWS = 200
COMMIT_SECONDS = 2.0
REPORT_SECONDS = 0.5
_CANDIDATE_SIZES = "SELECT size FROM files WHERE status = 'ok' AND size > 0 GROUP BY size HAVING COUNT(*) > 1"


class Stopped(Exception):
    pass


def hash_file(path: Path, stop=None, on_bytes=None) -> str:
    """整個檔案的內容指紋（BLAKE2b，從頭讀到尾）。只讀取。stop 被設定時中途放棄並丟出 Stopped。"""
    h = hashlib.blake2b(digest_size=16)
    with open(path, "rb") as fh:
        while True:
            if stop is not None and stop.is_set():
                raise Stopped
            block = fh.read(CHUNK)
            if not block:
                break
            h.update(block)
            if on_bytes:
                on_bytes(len(block))
    return h.hexdigest()


def compare_plan(conn: sqlite3.Connection) -> dict:
    """還要讀多少資料才能確認重複：1GB 以下、1GB 以上、硬碟沒接上的，各有幾個檔案與多少位元組。"""
    online = {r["id"]: Path(r["path"]).is_dir() for r in conn.execute("SELECT id, path FROM roots")}
    plan = {"small": [0, 0], "large": [0, 0], "offline": [0, 0], "done": 0}
    for r in conn.execute(
            f"SELECT root_id, size > {BIG_FILE} AS big, COUNT(*) AS n, SUM(size) AS b FROM files "
            f"WHERE status = 'ok' AND content_hash IS NULL AND size > 0 AND size IN ({_CANDIDATE_SIZES}) GROUP BY root_id, big"):
        slot = plan["offline"] if not online.get(r["root_id"]) else plan["large"] if r["big"] else plan["small"]
        slot[0] += r["n"]
        slot[1] += r["b"]
    plan["done"] = conn.execute("SELECT COUNT(*) FROM files WHERE status = 'ok' AND content_hash IS NOT NULL").fetchone()[0]
    return {k: ({"files": v[0], "bytes": v[1]} if isinstance(v, list) else v) for k, v in plan.items()}


@dataclass
class CompareResult:
    hashed: int = 0
    bytes: int = 0
    changed: int = 0  # 掃描之後被改過或不見了：跳過，下次掃描會更新
    unreadable: int = 0
    interrupted: list[str] = field(default_factory=list)  # 中途被拔掉的硬碟
    offline: int = 0
    stopped: bool = False


def run_compare(conn: sqlite3.Connection, large: bool = False, progress=None, stop=None) -> CompareResult:
    """比對內容：替「大小相同的候選檔案」算出完整指紋。分批寫入，可以隨時停止或拔掉硬碟，下次從還沒做的繼續。

    large＝False 只處理 1GB 以下的檔案。progress(done_bytes, total_bytes, message)。
    """
    result = CompareResult()
    roots = {r["id"]: r for r in conn.execute("SELECT * FROM roots")}
    online = {rid: Path(r["path"]).is_dir() for rid, r in roots.items()}
    limit = "" if large else f"AND f.size <= {BIG_FILE}"
    rows = conn.execute(
        f"SELECT f.id, f.root_id, f.name, f.size, f.mtime, d.path FROM files f JOIN folders d ON d.id = f.folder_id "
        f"WHERE f.status = 'ok' AND f.content_hash IS NULL AND f.size IN ({_CANDIDATE_SIZES}) {limit} "
        "ORDER BY f.root_id, d.path, f.name").fetchall()
    todo = [r for r in rows if online.get(r["root_id"])]
    result.offline = len(rows) - len(todo)
    total = sum(r["size"] for r in todo)
    done = 0
    pending, last_commit, last_report = 0, time.monotonic(), 0.0
    dead: set[int] = set()
    touched: set[int] = set()

    def report(name: str, force: bool = False) -> None:
        nonlocal last_report
        now = time.monotonic()
        if progress and (force or now - last_report >= REPORT_SECONDS):
            last_report = now
            progress(done, total, name)

    def count(n: int) -> None:
        nonlocal done
        done += n
        report(current)

    current = ""
    try:
        for r in todo:
            if stop is not None and stop.is_set():
                raise Stopped
            if r["root_id"] in dead:
                continue
            root = roots[r["root_id"]]
            path = Path(root["path"]).joinpath(*[p for p in r["path"].split("/") if p], r["name"])
            current = f"{root['name']}：{r['name']}"
            before = done
            try:
                st = path.stat()
                if st.st_size != r["size"] or st.st_mtime != r["mtime"]:
                    result.changed += 1
                    done = before + r["size"]
                    continue
                digest = hash_file(path, stop, count)
                st2 = path.stat()
                if st2.st_size != r["size"] or st2.st_mtime != r["mtime"]:  # 讀的過程中被改了：不採用
                    result.changed += 1
                    done = before + r["size"]
                    continue
            except Stopped:
                raise
            except OSError:
                done = before + r["size"]
                if not Path(root["path"]).is_dir():  # 硬碟被拔掉：這顆先停，其他硬碟繼續；不算錯誤
                    dead.add(r["root_id"])
                    result.interrupted.append(root["name"])
                else:
                    result.unreadable += 1
                continue
            conn.execute("UPDATE files SET content_hash = ?, hashed_at = ? WHERE id = ? AND size = ? AND mtime = ?",
                         (digest, db.now_iso(), r["id"], r["size"], r["mtime"]))
            result.hashed += 1
            result.bytes += r["size"]
            touched.add(r["root_id"])
            pending += 1
            if pending >= COMMIT_ROWS or time.monotonic() - last_commit >= COMMIT_SECONDS:
                conn.commit()
                pending, last_commit = 0, time.monotonic()
    except Stopped:
        result.stopped = True
    conn.commit()
    for rid in touched:  # 指紋有更新的硬碟：重算資料夾的內容簽章，才認得出重複資料夾
        update_folder_signatures(conn, rid)
    conn.commit()
    report(current, force=True)
    return result


def describe(r: CompareResult) -> str:
    parts = [f"比對了 {r.hashed:,} 個檔案"]
    if r.changed:
        parts.append(f"{r.changed:,} 個在掃描後有變動（重新掃描後再比對）")
    if r.unreadable:
        parts.append(f"{r.unreadable:,} 個無法讀取")
    if r.interrupted:
        parts.append("已中斷：" + "、".join(f"「{n}」" for n in r.interrupted) + "，接上後可繼續")
    if r.offline:
        parts.append(f"{r.offline:,} 個在沒接上的硬碟")
    return ("已停止。" if r.stopped else "") + "，".join(parts)


# ---- 資料夾簽章：認出「整個資料夾被備份了好幾次」----

def _sig(parts: list[str]) -> str:
    h = hashlib.blake2b(digest_size=16)
    for p in parts:
        h.update(p.encode("utf-8", "surrogatepass"))
        h.update(b"\0")
    return h.hexdigest()


def update_folder_signatures(conn: sqlite3.Connection, root_id: int) -> None:
    """每個資料夾兩個簽章，都不含資料夾自己的名稱（備份改了名字也認得出來）：

    shape_sig：裡面每個檔案的相對路徑與大小。只用目錄資料就能算，用來找「可能重複」的資料夾。
    content_sig：再加上每個檔案的完整內容指紋。裡面有任何一個檔案還沒比對內容就是空的（待確認）。
    沒有任何檔案的資料夾不算（不然所有空資料夾都會互相「重複」）。
    """
    folders = conn.execute("SELECT id, parent_id, name, path FROM folders WHERE root_id = ? AND status = 'ok'", (root_id,)).fetchall()
    if not folders:
        return
    shape: dict[int, list[str]] = {f["id"]: [] for f in folders}
    content: dict[int, list[str] | None] = {f["id"]: [] for f in folders}
    for fid, name, size, digest in conn.execute(
            "SELECT folder_id, name, size, content_hash FROM files WHERE root_id = ? AND status = 'ok' ORDER BY folder_id, name", (root_id,)):
        if fid not in shape:
            continue
        shape[fid].append(f"f\t{name}\t{size}")
        if content[fid] is not None:
            if digest and size > 0:
                content[fid].append(f"f\t{name}\t{size}\t{digest}")
            elif size == 0:
                content[fid].append(f"f\t{name}\t0")  # 空檔案不必讀
            else:
                content[fid] = None
    done_shape: dict[int, str | None] = {}
    done_content: dict[int, str | None] = {}
    depth = lambda p: 0 if not p else p.count("/") + 1  # noqa: E731
    for f in sorted(folders, key=lambda f: depth(f["path"]), reverse=True):  # 由最深的往上
        fid = f["id"]
        s = _sig(sorted(shape[fid])) if shape[fid] else None
        c = _sig(sorted(content[fid])) if content[fid] else None
        if content[fid] is None:
            c = None
        done_shape[fid], done_content[fid] = s, c
        parent = f["parent_id"]
        if parent in shape and s is not None:
            shape[parent].append(f"d\t{f['name']}\t{s}")
            if content[parent] is not None:
                if c is None:
                    content[parent] = None
                else:
                    content[parent].append(f"d\t{f['name']}\t{c}")
    conn.executemany("UPDATE folders SET shape_sig = ?, content_sig = ? WHERE id = ?",
                     [(done_shape[f["id"]], done_content[f["id"]], f["id"]) for f in folders])


# ---- 查詢 ----

def _place(conn: sqlite3.Connection) -> dict[int, dict]:
    """每個資料夾來源：名稱、所在硬碟、有沒有接上、是不是唯讀（NTFS 等）。"""
    out = {}
    for r in conn.execute("SELECT r.id, r.name, r.path, d.name AS drive, d.fs_type, d.read_only FROM roots r LEFT JOIN drives d ON d.id = r.drive_id"):
        out[r["id"]] = {"root_id": r["id"], "root": r["name"], "drive": r["drive"] or r["name"], "online": Path(r["path"]).is_dir(),
                        "read_only": bool(r["read_only"]) or (r["fs_type"] or "").lower() == "ntfs"}
    return out


def duplicate_folders(conn: sqlite3.Connection, offset: int = 0, limit: int = 100) -> dict:
    """重複資料夾：每組是內容相同的幾個資料夾，依可釋出的空間由大到小。

    只列最上層的重複（A 和 B 整個相同時，不再把它們底下的每個子資料夾各列一組）。
    confirmed＝每一份都完整比對過而且內容相同；否則是「待確認」（只知道檔名與大小都一樣）。
    """
    rows = conn.execute(
        "SELECT id, root_id, parent_id, name, path, mtime, total_bytes, total_files, shape_sig, content_sig FROM folders "
        "WHERE status = 'ok' AND shape_sig IN (SELECT shape_sig FROM folders WHERE status = 'ok' AND shape_sig IS NOT NULL "
        "GROUP BY shape_sig HAVING COUNT(*) > 1)").fetchall()
    by_shape: dict[str, list] = {}
    for r in rows:
        by_shape.setdefault(r["shape_sig"], []).append(r)
    sets: list[tuple[bool, list]] = []
    for members in by_shape.values():
        if all(m["content_sig"] for m in members):
            parts: dict[str, list] = {}
            for m in members:
                parts.setdefault(m["content_sig"], []).append(m)
            sets += [(True, ms) for ms in parts.values() if len(ms) > 1]  # 檔名大小都一樣但內容不同的，不是重複
        else:
            sets.append((False, members))
    # 上一層已經列為重複的，底下的子資料夾不再各列一組
    listed = {m["id"] for _, ms in sets for m in ms}
    place = _place(conn)
    groups = []
    for confirmed, ms in sets:
        if all(m["parent_id"] in listed for m in ms):
            continue
        size = ms[0]["total_bytes"]
        groups.append({
            "key": f"{'c' if confirmed else 's'}:{ms[0]['content_sig'] if confirmed else ms[0]['shape_sig']}",
            "name": ms[0]["name"], "size": size, "files": ms[0]["total_files"], "copies": len(ms),
            "releasable": size * (len(ms) - 1), "confirmed": confirmed,
            "items": [{"type": "folder", "id": m["id"], "name": m["name"], "path": m["path"], "mtime": m["mtime"], **place.get(m["root_id"], {})}
                      for m in sorted(ms, key=lambda m: (place.get(m["root_id"], {}).get("drive", ""), m["path"]))],
        })
    groups.sort(key=lambda g: (-g["releasable"], g["name"]))
    confirmed = [g for g in groups if g["confirmed"]]
    return {"total": len(groups), "confirmed": len(confirmed), "releasable": sum(g["releasable"] for g in confirmed),
            "groups": groups[offset:offset + limit]}


def duplicate_files(conn: sqlite3.Connection, offset: int = 0, limit: int = 100, pending: bool = False) -> dict:
    """重複檔案。pending＝False：完整指紋相同的（已確認）；True：檔名與大小都相同、但還沒比對內容的（待確認）。"""
    place = _place(conn)
    if pending:
        head = conn.execute(
            "SELECT size, name, COUNT(*) AS n FROM files WHERE status = 'ok' AND content_hash IS NULL AND size > 0 "
            "GROUP BY size, name HAVING n > 1 ORDER BY (n - 1) * size DESC, name LIMIT ? OFFSET ?", (limit, offset)).fetchall()
        stats = conn.execute(
            "SELECT COUNT(*), COALESCE(SUM((n - 1) * size), 0) FROM (SELECT size, COUNT(*) AS n FROM files "
            "WHERE status = 'ok' AND content_hash IS NULL AND size > 0 GROUP BY size, name HAVING n > 1)").fetchone()
        member_sql, key = "f.content_hash IS NULL AND f.size = ? AND f.name = ?", lambda g: (g["size"], g["name"])
    else:
        head = conn.execute(
            "SELECT content_hash, size, MIN(name) AS name, COUNT(*) AS n FROM files WHERE status = 'ok' AND content_hash IS NOT NULL "
            "GROUP BY content_hash, size HAVING n > 1 ORDER BY (n - 1) * size DESC, name LIMIT ? OFFSET ?", (limit, offset)).fetchall()
        stats = conn.execute(
            "SELECT COUNT(*), COALESCE(SUM((n - 1) * size), 0) FROM (SELECT size, COUNT(*) AS n FROM files "
            "WHERE status = 'ok' AND content_hash IS NOT NULL GROUP BY content_hash, size HAVING n > 1)").fetchone()
        member_sql, key = "f.content_hash = ? AND f.size = ?", lambda g: (g["content_hash"], g["size"])
    # 已經列為「重複資料夾」的資料夾：裡面的檔案組別加上記號，介面會標示「已包含在重複資料夾中」
    covered: dict[int, list[str]] = {}
    if not pending and head:
        for fg in duplicate_folders(conn, 0, 1_000_000)["groups"]:
            if fg["confirmed"]:
                for it in fg["items"]:
                    covered.setdefault(it.get("root_id"), []).append(it["path"])

    def inside(root_id: int, folder: str) -> bool:
        return any(folder == p or folder.startswith(p + "/") for p in covered.get(root_id, ()))

    groups = []
    for g in head:
        members = conn.execute(
            f"SELECT f.id, f.name, f.kind, f.mtime, f.root_id, f.image_id, d.path AS folder FROM files f JOIN folders d ON d.id = f.folder_id "
            f"WHERE f.status = 'ok' AND {member_sql}", key(g)).fetchall()
        groups.append({
            "key": f"{'p' if pending else 'h'}:{g['size']}:{g['name'] if pending else g['content_hash']}",
            "name": g["name"], "size": g["size"], "copies": len(members), "releasable": g["size"] * (len(members) - 1),
            "confirmed": not pending, "kind": members[0]["kind"] if members else "other",
            "in_folder": bool(members) and bool(covered) and all(inside(m["root_id"], m["folder"]) for m in members),
            "items": [{"type": "file", "id": m["id"], "name": m["name"], "path": f"{m['folder']}/{m['name']}" if m["folder"] else m["name"],
                       "mtime": m["mtime"], "image_id": m["image_id"], **place.get(m["root_id"], {})}
                      for m in sorted(members, key=lambda m: (place.get(m["root_id"], {}).get("drive", ""), m["folder"], m["name"]))],
        })
    return {"total": stats[0], "confirmed": 0 if pending else stats[0], "releasable": 0 if pending else stats[1],
            "pending_releasable": stats[1] if pending else 0, "groups": groups}
