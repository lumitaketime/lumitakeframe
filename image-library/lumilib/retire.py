"""硬碟淘汰檢查：這顆硬碟上的每個檔案，在別顆硬碟上有沒有一模一樣的副本。

怎麼判斷（核心原則第 1、7 條）：
1. 先查目錄（不用接硬碟）：別顆硬碟上沒有任何大小一樣的檔案 → 「只有這一顆有」。
   大小一樣的 → 「可能有副本」，還不能算數。
2. 確認（要接上硬碟）：先讀開頭結尾各 64KB 比對（快速指紋），不一樣就不是副本，不必讀完；
   一樣的才把兩邊整個檔案從頭讀到尾，算出完整指紋。完整指紋一樣才算「別顆有副本」。
- 只看內容，不看檔名；同一顆實體硬碟上的另一份不算副本（硬碟淘汰掉，兩份一起沒了）。
- 副本只在「健康檢查有狀況」或「也打算淘汰」的硬碟上：另外標出來，不算安全。
- .DS_Store 這類系統自動產生的小檔案、空檔案不算在「只有這一顆有」裡，另外列出有幾個。
- 全程只讀硬碟；結果只寫在目錄資料庫裡。不刪除、不搬移任何檔案。
"""
from __future__ import annotations

import csv
import io
import json
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import db

STATES = ("copy", "risky", "maybe", "only", "junk")
JUNK_NAMES = (".ds_store", "thumbs.db", "ehthumbs.db", "desktop.ini", ".localized", ".directory", "icon\r", ".picasa.ini", "picasa.ini")
PLAN_KEY = "retire_plan"  # 本人打算淘汰的硬碟（root id）
COMMIT_ROWS = 200
COMMIT_SECONDS = 2.0
_LOCK = threading.Lock()  # 同一時間只重算一次（兩個畫面同時打開也不會互相卡住）


# ---- 打算淘汰的硬碟（副本只在這些硬碟上，不算安全） ----

def planned(conn: sqlite3.Connection) -> set[int]:
    r = conn.execute("SELECT value FROM settings_kv WHERE key = ?", (PLAN_KEY,)).fetchone()
    try:
        return {int(x) for x in json.loads(r["value"])} if r else set()
    except (ValueError, TypeError):
        return set()


def set_planned(conn: sqlite3.Connection, root_id: int, on: bool) -> set[int]:
    have = planned(conn)
    (have.add if on else have.discard)(int(root_id))
    conn.execute("INSERT OR REPLACE INTO settings_kv (key, value) VALUES (?, ?)", (PLAN_KEY, json.dumps(sorted(have))))
    conn.commit()
    return have


def _drive_key(r) -> str:
    return f"d:{r['drive_id']}" if r["drive_id"] is not None else f"r:{r['id']}"


def _risky(conn: sqlite3.Connection, roots: list) -> set[int]:
    """健康檢查有狀況，或本人打算淘汰的硬碟。"""
    bad = {r["key"] for r in conn.execute("SELECT key FROM drive_health WHERE status IN ('warn', 'fail')")}
    plan = planned(conn)
    return {r["id"] for r in roots if r["id"] in plan or _drive_key(r) in bad}


def _junk_sql(alias: str = "f") -> str:
    names = ", ".join("'" + n.replace("'", "''") + "'" for n in JUNK_NAMES)
    return f"({alias}.size = 0 OR lower({alias}.name) IN ({names}) OR substr({alias}.name, 1, 2) = '._')"


def _signature(conn: sqlite3.Connection, root_id: int, risky: set[int]) -> str:
    """目錄有變（掃描過、比對過、計畫淘汰的硬碟或健康狀況變了）才重算。"""
    a = conn.execute("SELECT COUNT(*), COALESCE(MAX(id), 0), COUNT(content_hash), COUNT(quick_sig), COALESCE(SUM(size), 0) "
                     "FROM files WHERE status = 'ok'").fetchone()
    b = conn.execute("SELECT COALESCE(MAX(hashed_at), ''), (SELECT GROUP_CONCAT(id || ':' || COALESCE(last_scan, '') || ':' || "
                     "COALESCE(drive_id, '')) FROM roots) FROM files").fetchone()
    return json.dumps([root_id, list(a), list(b), sorted(risky)])


def _other_roots(conn: sqlite3.Connection, root) -> tuple[list, set[int]]:
    roots = conn.execute("SELECT * FROM roots").fetchall()
    key = _drive_key(root)
    others = [r for r in roots if _drive_key(r) != key]
    return others, _risky(conn, others)


def _fill_temp(conn: sqlite3.Connection, others: list, risky: set[int]) -> None:
    conn.execute("CREATE TEMP TABLE IF NOT EXISTS _ret_roots (id INTEGER PRIMARY KEY, safe INTEGER NOT NULL)")
    conn.execute("DELETE FROM _ret_roots")
    conn.executemany("INSERT INTO _ret_roots (id, safe) VALUES (?, ?)", [(r["id"], 0 if r["id"] in risky else 1) for r in others])
    conn.execute("CREATE TEMP TABLE IF NOT EXISTS _ret_sizes (size INTEGER PRIMARY KEY)")
    conn.execute("DELETE FROM _ret_sizes")
    conn.execute("INSERT OR IGNORE INTO _ret_sizes (size) SELECT f.size FROM files f JOIN _ret_roots o ON o.id = f.root_id WHERE f.status = 'ok'")
    conn.execute("CREATE TEMP TABLE IF NOT EXISTS _ret_hash (h TEXT PRIMARY KEY, safe INTEGER NOT NULL, holders TEXT) WITHOUT ROWID")
    conn.execute("DELETE FROM _ret_hash")
    conn.execute("INSERT INTO _ret_hash (h, safe, holders) SELECT f.content_hash, MAX(o.safe), GROUP_CONCAT(DISTINCT f.root_id) "
                 "FROM files f JOIN _ret_roots o ON o.id = f.root_id WHERE f.status = 'ok' AND f.content_hash IS NOT NULL "
                 "GROUP BY f.content_hash")


# 別顆硬碟上「還可能是副本」的檔案：大小一樣，而且還沒被證明不一樣
# （兩邊都有完整指紋卻不同、或兩邊都有快速指紋卻不同，就確定不是）
_MAYBE = ("g.size = f.size AND g.status = 'ok' AND (g.content_hash IS NULL OR f.content_hash IS NULL) "
          "AND (g.quick_sig IS NULL OR f.quick_sig IS NULL OR g.quick_sig = f.quick_sig)")


def analyze(conn: sqlite3.Connection, root_id: int, force: bool = False) -> dict:
    """算出（或拿上次算好的）這顆硬碟的淘汰檢查結果摘要。一百萬個檔案約數秒；目錄沒變就直接用上次的。"""
    root = conn.execute("SELECT * FROM roots WHERE id = ?", (int(root_id),)).fetchone()
    if root is None:
        raise ValueError("找不到這顆硬碟")
    others, risky = _other_roots(conn, root)
    sig = _signature(conn, root["id"], risky)
    run = conn.execute("SELECT * FROM retire_runs WHERE root_id = ?", (root["id"],)).fetchone()
    if run is not None and run["sig"] == sig and not force:
        out = json.loads(run["summary"])
        out["planned"] = root["id"] in planned(conn)
        return out
    with _LOCK:
        return _recompute(conn, root, force)


def _recompute(conn: sqlite3.Connection, root, force: bool) -> dict:
    # 先拿到寫入權再開始（背景工作同時在寫的時候會等它，不會讀到一半才發現被搶先而失敗）
    conn.commit()
    conn.execute("BEGIN IMMEDIATE")
    others, risky = _other_roots(conn, root)
    sig = _signature(conn, root["id"], risky)
    run = conn.execute("SELECT * FROM retire_runs WHERE root_id = ?", (root["id"],)).fetchone()
    if run is not None and run["sig"] == sig and not force:  # 等鎖的時候別人已經算好了
        conn.commit()
        out = json.loads(run["summary"])
        out["planned"] = root["id"] in planned(conn)
        return out
    _fill_temp(conn, others, risky)
    conn.execute("DELETE FROM retire_files WHERE root_id = ?", (root["id"],))
    conn.execute(
        "INSERT INTO retire_files (root_id, file_id, folder_id, state, size, kind, holders) "
        "SELECT f.root_id, f.id, f.folder_id, CASE "
        f"WHEN {_junk_sql()} THEN 'junk' "
        "WHEN h.h IS NOT NULL THEN CASE WHEN h.safe = 1 THEN 'copy' ELSE 'risky' END "
        # 還沒比對過的（大多數）：別顆有一樣大小的就是「可能」，查大小表就好；比對過的才逐一看是不是已經證明不一樣
        "WHEN f.content_hash IS NULL AND f.quick_sig IS NULL THEN CASE WHEN f.size IN (SELECT size FROM _ret_sizes) THEN 'maybe' ELSE 'only' END "
        f"WHEN EXISTS (SELECT 1 FROM files g JOIN _ret_roots o ON o.id = g.root_id WHERE {_MAYBE}) THEN 'maybe' "
        "ELSE 'only' END, f.size, f.kind, h.holders "
        "FROM files f LEFT JOIN _ret_hash h ON h.h = f.content_hash WHERE f.root_id = ? AND f.status = 'ok'", (root["id"],))
    summary = _summary(conn, root, others, risky)
    conn.execute("INSERT OR REPLACE INTO retire_runs (root_id, sig, computed_at, summary) VALUES (?, ?, ?, ?)",
                 (root["id"], sig, summary["computed_at"], json.dumps(summary, ensure_ascii=False)))
    conn.commit()
    summary["planned"] = root["id"] in planned(conn)
    return summary


def _name_of(conn: sqlite3.Connection, r) -> str:
    if r["drive_id"] is not None:
        d = conn.execute("SELECT name FROM drives WHERE id = ?", (r["drive_id"],)).fetchone()
        if d and d["name"]:
            return d["name"]
    return r["name"]


def _summary(conn: sqlite3.Connection, root, others: list, risky: set[int]) -> dict:
    states = {s: {"files": 0, "bytes": 0} for s in STATES}
    for r in conn.execute("SELECT state, COUNT(*) AS n, COALESCE(SUM(size), 0) AS b FROM retire_files WHERE root_id = ? GROUP BY state",
                          (root["id"],)):
        states[r["state"]] = {"files": r["n"], "bytes": r["b"]}
    names = {r["id"]: _name_of(conn, r) for r in others}
    # 副本只在有狀況、或也要淘汰的硬碟上：是哪幾顆
    risky_on: dict[int, dict] = {}
    for r in conn.execute("SELECT holders, COUNT(*) AS n, SUM(size) AS b FROM retire_files WHERE root_id = ? AND state = 'risky' "
                          "GROUP BY holders", (root["id"],)):
        for rid in {int(x) for x in (r["holders"] or "").split(",") if x}:
            slot = risky_on.setdefault(rid, {"root_id": rid, "name": names.get(rid, str(rid)), "files": 0, "bytes": 0,
                                             "planned": rid in planned(conn)})
            slot["files"] += r["n"]
            slot["bytes"] += r["b"] or 0
    kinds = [{"kind": r["kind"], "files": r["n"], "bytes": r["b"]} for r in conn.execute(
        "SELECT kind, COUNT(*) AS n, SUM(size) AS b FROM retire_files WHERE root_id = ? AND state = 'only' GROUP BY kind ORDER BY b DESC",
        (root["id"],))]
    total = {"files": sum(v["files"] for v in states.values()), "bytes": sum(v["bytes"] for v in states.values())}
    unsafe = states["only"]["files"] + states["maybe"]["files"] + states["risky"]["files"]
    return {"root_id": root["id"], "name": _name_of(conn, root), "online": Path(root["path"]).is_dir(), "last_scan": root["last_scan"],
            "total": total, "states": states, "kinds": kinds, "risky_on": sorted(risky_on.values(), key=lambda x: -x["bytes"]),
            "ready": total["files"] > 0 and unsafe == 0, "scanned": bool(root["last_scan"]), "computed_at": db.now_iso()}


def folders(conn: sqlite3.Connection, root_id: int, state: str = "only", offset: int = 0, limit: int = 100) -> dict:
    """這一類的檔案在哪些資料夾（最大的在前）。"""
    state = state if state in STATES else "only"
    rows = conn.execute(
        "SELECT r.folder_id, d.path, d.name, COUNT(*) AS n, SUM(r.size) AS b FROM retire_files r JOIN folders d ON d.id = r.folder_id "
        "WHERE r.root_id = ? AND r.state = ? GROUP BY r.folder_id ORDER BY b DESC, d.path LIMIT ? OFFSET ?",
        (int(root_id), state, max(1, min(int(limit), 500)), max(0, int(offset)))).fetchall()
    total = conn.execute("SELECT COUNT(DISTINCT folder_id) FROM retire_files WHERE root_id = ? AND state = ?", (int(root_id), state)).fetchone()[0]
    return {"total": total, "folders": [{"id": r["folder_id"], "path": r["path"], "name": r["name"] or "", "files": r["n"], "bytes": r["b"]}
                                        for r in rows]}


def files(conn: sqlite3.Connection, root_id: int, state: str = "only", folder_id: int | None = None,
          offset: int = 0, limit: int = 200) -> dict:
    state = state if state in STATES else "only"
    where, args = "r.root_id = ? AND r.state = ?", [int(root_id), state]
    if folder_id is not None:
        where += " AND r.folder_id = ?"
        args.append(int(folder_id))
    rows = conn.execute(
        f"SELECT f.id, f.name, f.kind, f.size, f.mtime, f.root_id, f.image_id, d.path AS folder_path, r.holders FROM retire_files r "
        f"JOIN files f ON f.id = r.file_id JOIN folders d ON d.id = r.folder_id WHERE {where} ORDER BY r.size DESC, f.name "
        f"LIMIT ? OFFSET ?", (*args, max(1, min(int(limit), 1000)), max(0, int(offset)))).fetchall()
    total = conn.execute(f"SELECT COUNT(*) FROM retire_files r WHERE {where}", args).fetchone()[0]
    return {"total": total, "files": [{"id": r["id"], "type": "file", "name": r["name"], "kind": r["kind"], "size": r["size"],
                                       "mtime": r["mtime"], "root_id": r["root_id"], "image_id": r["image_id"],
                                       "folder": r["folder_path"]} for r in rows]}


STATE_TEXT = {"copy": "別顆有副本", "risky": "副本只在有狀況或也要淘汰的硬碟", "maybe": "可能有副本（還沒確認）",
              "only": "只有這一顆有", "junk": "系統小檔案或空檔案"}


def export_csv(conn: sqlite3.Connection, root_id: int, states=("only", "maybe", "risky")) -> str:
    """清單（試算表可以打開的 CSV）：位置、名稱、大小、修改日期、狀態。只產生文字，不寫到任何硬碟。"""
    from datetime import datetime

    out = io.StringIO()
    out.write("﻿")  # Excel 才認得中文
    w = csv.writer(out)
    w.writerow(["狀態", "資料夾", "檔名", "大小（位元組）", "修改日期"])
    marks = ",".join("?" * len(states))
    for r in conn.execute(
            f"SELECT r.state, d.path, f.name, f.size, f.mtime FROM retire_files r JOIN files f ON f.id = r.file_id "
            f"JOIN folders d ON d.id = r.folder_id WHERE r.root_id = ? AND r.state IN ({marks}) ORDER BY r.state, d.path, f.name",
            (int(root_id), *states)):
        when = datetime.fromtimestamp(r["mtime"]).strftime("%Y-%m-%d %H:%M") if r["mtime"] else ""
        w.writerow([STATE_TEXT.get(r["state"], r["state"]), r["path"] or "/", r["name"], r["size"], when])
    return out.getvalue()


# ---- 確認副本：只讀需要確認的檔案 ----

def _candidates(conn: sqlite3.Connection, root) -> tuple[list, dict]:
    """這顆硬碟上「可能有副本」的檔案，以及每一個在別顆硬碟上可能相同的檔案。"""
    others, risky = _other_roots(conn, root)
    _fill_temp(conn, others, risky)
    mine = conn.execute(
        "SELECT f.id, f.root_id, f.name, f.size, f.mtime, f.quick_sig, f.content_hash, d.path FROM retire_files r "
        "JOIN files f ON f.id = r.file_id JOIN folders d ON d.id = f.folder_id WHERE r.root_id = ? AND r.state = 'maybe' "
        "ORDER BY d.path, f.name", (root["id"],)).fetchall()
    partners: dict[int, list] = {}
    for f in mine:
        partners[f["id"]] = conn.execute(
            "SELECT g.id, g.root_id, g.name, g.size, g.mtime, g.quick_sig, g.content_hash, d.path FROM files g "
            f"JOIN _ret_roots o ON o.id = g.root_id JOIN folders d ON d.id = g.folder_id, (SELECT ? AS size, ? AS content_hash, ? AS quick_sig) f "
            f"WHERE {_MAYBE}", (f["size"], f["content_hash"], f["quick_sig"])).fetchall()
    conn.commit()  # 結束這段讀取（之後寫入時才不會因為別的工作先寫了而失敗）
    return mine, partners


def verify_plan(conn: sqlite3.Connection, root_id: int) -> dict:
    """確認副本要讀多少、要接上哪些硬碟。"""
    root = conn.execute("SELECT * FROM roots WHERE id = ?", (int(root_id),)).fetchone()
    if root is None:
        raise ValueError("找不到這顆硬碟")
    analyze(conn, root["id"])
    mine, partners = _candidates(conn, root)
    roots = {r["id"]: r for r in conn.execute("SELECT * FROM roots")}
    online = {rid: Path(r["path"]).is_dir() for rid, r in roots.items()}
    need: dict[int, dict] = {}
    bytes_ = sum(f["size"] for f in mine if not f["content_hash"])
    seen: set[int] = set()
    for f in mine:
        for g in partners[f["id"]]:
            if g["id"] in seen:
                continue
            seen.add(g["id"])
            if not g["content_hash"]:
                bytes_ += g["size"]
            if not online.get(g["root_id"]):
                slot = need.setdefault(g["root_id"], {"root_id": g["root_id"], "name": _name_of(conn, roots[g["root_id"]]), "files": 0})
                slot["files"] += 1
    return {"files": len(mine), "bytes": bytes_, "online": online.get(root["id"], False), "need": list(need.values())}


@dataclass
class VerifyResult:
    checked: int = 0
    copies: int = 0
    different: int = 0
    bytes: int = 0
    changed: int = 0
    unreadable: int = 0
    waiting: int = 0  # 另一顆硬碟沒接上，還沒辦法確認
    stopped: bool = False
    interrupted: list[str] = field(default_factory=list)


def _abs(roots: dict, r) -> Path:
    root = roots[r["root_id"]]
    return Path(root["path"]).joinpath(*[p for p in (r["path"] or "").split("/") if p], r["name"])


def verify(conn: sqlite3.Connection, root_id: int, progress=None, stop=None, hold: set[int] | None = None) -> VerifyResult:
    """確認「可能有副本」的檔案：先比快速指紋，一樣的才讀完整內容。分批寫入，可以隨時停止或拔掉硬碟，下次接著做。"""
    from .dupes import Stopped, hash_file
    from .health import io_error
    from .scanner import fingerprint

    res = VerifyResult()
    root = conn.execute("SELECT * FROM roots WHERE id = ?", (int(root_id),)).fetchone()
    if root is None:
        raise ValueError("找不到這顆硬碟")
    analyze(conn, root["id"])
    mine, partners = _candidates(conn, root)
    roots = {r["id"]: r for r in conn.execute("SELECT * FROM roots")}
    online = {rid: Path(r["path"]).is_dir() for rid, r in roots.items()}
    dead: set[int] = set(hold or ())  # 健康檢查有狀況、等本人決定的硬碟先不讀
    state = {"pending": 0, "last": time.monotonic()}

    def save(sql: str, args: tuple) -> None:
        conn.execute(sql, args)
        state["pending"] += 1
        if state["pending"] >= COMMIT_ROWS or time.monotonic() - state["last"] >= COMMIT_SECONDS:
            conn.commit()
            state["pending"], state["last"] = 0, time.monotonic()

    def read(r, fn):
        """讀一個檔案（快速指紋或完整指紋）；讀之前和之後都檢查大小、修改時間，被改過的不採用。"""
        if r["root_id"] in dead or not online.get(r["root_id"]):
            return None
        path = _abs(roots, r)
        try:
            st = path.stat()
            if st.st_size != r["size"] or st.st_mtime != r["mtime"]:
                res.changed += 1
                return None
            value = fn(path)
            st2 = path.stat()
            if st2.st_size != r["size"] or st2.st_mtime != r["mtime"]:
                res.changed += 1
                return None
            return value
        except Stopped:
            raise
        except OSError as exc:
            if not Path(roots[r["root_id"]]["path"]).is_dir():  # 硬碟被拔掉：這顆先停
                dead.add(r["root_id"])
                res.interrupted.append(_name_of(conn, roots[r["root_id"]]))
            else:
                res.unreadable += 1
                if io_error(conn, r["root_id"], exc):
                    dead.add(r["root_id"])
            return None

    def quick(r) -> str | None:
        if r["quick_sig"]:
            return r["quick_sig"]
        v = read(r, lambda p: fingerprint(p, r["size"]))
        if v:
            save("UPDATE files SET quick_sig = ? WHERE id = ? AND size = ? AND mtime = ?", (v, r["id"], r["size"], r["mtime"]))
        return v

    def full(r) -> str | None:
        if r["content_hash"]:
            return r["content_hash"]
        v = read(r, lambda p: hash_file(p, stop))
        if v:
            res.bytes += r["size"]
            save("UPDATE files SET content_hash = ?, hashed_at = ? WHERE id = ? AND size = ? AND mtime = ?",
                 (v, db.now_iso(), r["id"], r["size"], r["mtime"]))
        return v

    touched: set[int] = set()
    try:
        for i, f in enumerate(mine):
            if stop is not None and stop.is_set():
                raise Stopped
            if progress:
                progress(i, len(mine), f["name"])
            qf = quick(f)
            if qf is None:
                res.waiting += 1
                continue
            same, unsure = [], False
            for g in partners[f["id"]]:
                qg = quick(g)
                if qg is None:
                    unsure = True
                elif qg == qf:
                    same.append(g)
            found = False
            if same:
                hf = full(f)
                if hf is None:
                    res.waiting += 1
                    continue
                touched.add(f["root_id"])
                for g in same:
                    hg = full(g)
                    if hg is None:
                        unsure = True
                        continue
                    touched.add(g["root_id"])
                    if hg == hf:
                        found = True
                        break
            res.checked += 1
            if found:
                res.copies += 1
            elif unsure:
                res.waiting += 1
            else:
                res.different += 1
    except Stopped:
        res.stopped = True
    conn.commit()
    if touched:
        from .dupes import update_folder_signatures

        for rid in touched:
            update_folder_signatures(conn, rid)
        conn.commit()
    analyze(conn, root["id"], force=True)
    if progress:
        progress(len(mine), len(mine), "")
    return res


def describe(r: VerifyResult, name: str = "") -> str:
    parts = [f"確認了 {r.checked:,} 個檔案：{r.copies:,} 個在別顆硬碟有一模一樣的副本，{r.different:,} 個其實不一樣"]
    if r.waiting:
        parts.append(f"{r.waiting:,} 個要接上其他硬碟才能確認")
    if r.changed:
        parts.append(f"{r.changed:,} 個在掃描後有變動（重新掃描後再確認）")
    if r.unreadable:
        parts.append(f"{r.unreadable:,} 個無法讀取")
    if r.interrupted:
        parts.append("中途被拔掉：" + "、".join(f"「{n}」" for n in r.interrupted))
    return ("已暫停。" if r.stopped else "") + (f"「{name}」" if name else "") + "，".join(parts)


def describe_summary(s: dict) -> str:
    """給助理用的白話摘要。"""
    st, total = s["states"], s["total"]

    def pct(n):
        return f"{(n / total['bytes'] * 100):.0f}%" if total["bytes"] else "0%"

    if not total["files"]:
        return f"「{s['name']}」還沒有掃描過的檔案。"
    text = (f"「{s['name']}」共 {total['files']:,} 個檔案（{_bytes(total['bytes'])}）："
            f"別顆有確認過的副本 {pct(st['copy']['bytes'])}（{st['copy']['files']:,} 個）、"
            f"可能有副本但還沒確認 {pct(st['maybe']['bytes'])}（{st['maybe']['files']:,} 個）、"
            f"只有這一顆有 {pct(st['only']['bytes'])}（{st['only']['files']:,} 個，{_bytes(st['only']['bytes'])}）")
    if st["risky"]["files"]:
        text += "；另有 " + f"{st['risky']['files']:,} 個的副本只在" + "、".join(f"「{x['name']}」" for x in s["risky_on"][:3]) + "上（這些硬碟有狀況或也要淘汰）"
    if st["junk"]["files"]:
        text += f"；系統小檔案與空檔案 {st['junk']['files']:,} 個不算在內"
    text += "。" + ("可以淘汰：每個檔案在別顆健康的硬碟上都有確認過的副本。" if s["ready"] else "還不能淘汰。")
    return text


def _bytes(n: int) -> str:
    for unit, size in (("TB", 1e12), ("GB", 1e9), ("MB", 1e6), ("KB", 1e3)):
        if n >= size:
            return f"{n / size:.1f} {unit}"
    return f"{n} B"
