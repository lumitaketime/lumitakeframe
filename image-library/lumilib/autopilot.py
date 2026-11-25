"""接上硬碟就接著做：目錄裡已經有的硬碟接上時（或打開 App 時它已經接著），把上次沒做完的工作接著做。

本人選的做法（只接著做沒做完的）：
- 上次沒掃完的 → 接著掃；中途被拔掉、關掉 App 而中斷的工作（確認副本、複製、讀文字…）→ 接著做。
- 本人自己按「停止」「暫停」的不動；已經掃完的不重掃；還沒加入目錄的新硬碟不會自動掃描。
- 掃描前照舊會先做健康檢查（硬碟有狀況時先停下來等本人決定）。
- 全部只讀硬碟；複製（整理計畫）只會接著做本人已經確認過的那一張。
設定裡可以關掉（auto_continue）。
"""
from __future__ import annotations

import json
import threading
from pathlib import Path

from . import db

EVENTS_KEY = "drive_events"
INTERVAL = 10.0  # 每幾秒看一次哪些硬碟接著
GLOBAL_KINDS = ("extract", "ocr", "covers", "compare", "photos", "embed_docs")  # 不分硬碟的工作：接著的硬碟都會處理


def _events(conn) -> list[dict]:
    r = conn.execute("SELECT value FROM settings_kv WHERE key = ?", (EVENTS_KEY,)).fetchone()
    try:
        out = json.loads(r["value"]) if r else []
    except ValueError:
        out = []
    return out if isinstance(out, list) else []


def events(conn, limit: int = 10) -> list[dict]:
    return _events(conn)[-limit:][::-1]


def _record(conn, root, did: list[str]) -> None:
    from .retire import _name_of

    ev = _events(conn)
    ev.append({"root_id": root["id"], "name": _name_of(conn, root), "at": db.now_iso(), "did": did})
    conn.execute("INSERT OR REPLACE INTO settings_kv (key, value) VALUES (?, ?)", (EVENTS_KEY, json.dumps(ev[-30:], ensure_ascii=False)))
    conn.commit()


def _matches(kind: str, options: dict, root, conn) -> bool:
    """這筆中斷的工作跟這顆硬碟有沒有關係。"""
    if kind in ("scan", "index"):
        roots = options.get("roots")
        return not roots or root["name"] in [str(x) for x in roots] or str(root["id"]) in [str(x) for x in roots]
    if kind == "retire_verify":
        return int(options.get("root_id") or 0) == root["id"]
    if kind == "consolidate":
        r = conn.execute("SELECT payload, state FROM assistant_actions WHERE id = ?", (int(options.get("action_id") or 0),)).fetchone()
        if r is None or r["state"] not in ("running", "partial"):
            return False
        p = json.loads(r["payload"] or "{}")
        others = [p.get("source_root"), p.get("target_root")]
        if root["id"] not in others:
            return False
        roots = {x["id"]: x for x in conn.execute("SELECT id, path FROM roots")}
        return all(rid in roots and Path(roots[rid]["path"]).is_dir() for rid in others)  # 兩顆都接上才接著複製
    return kind in GLOBAL_KINDS


def _user_stopped(conn, root) -> bool:
    """這顆硬碟最近一次的掃描是本人自己按停止或暫停的：不自動接著掃。"""
    for r in conn.execute("SELECT kind, options, state FROM job_log WHERE kind IN ('scan', 'index') ORDER BY id DESC LIMIT 30"):
        if _matches(r["kind"], json.loads(r["options"] or "{}"), root, conn):
            return r["state"] in ("stopped", "paused")
    return False


def on_connect(conn, runner, cfg, root) -> list[str]:
    """這顆硬碟剛接上：接著做沒做完的工作。回傳做了哪些（給提醒用的白話）。"""
    did: list[str] = []
    snap = runner.snapshot()
    busy = {(j["kind"], j.get("target")) for j in snap["active"] + snap["queued"]}
    seen: set = set()
    rows = conn.execute("SELECT id, kind, options FROM job_log WHERE state = 'interrupted' ORDER BY id DESC LIMIT 50").fetchall()
    for r in rows:
        if r["kind"] not in runner.RESUMABLE or r["kind"] in ("scan", "index"):  # 掃描另外看（下面）
            continue
        opts = json.loads(r["options"] or "{}")
        key = (r["kind"], json.dumps(opts, sort_keys=True))
        if key in seen or not _matches(r["kind"], opts, root, conn):
            continue
        seen.add(key)
        if (r["kind"], opts.get("target")) in busy:
            continue
        try:
            runner.submit(r["kind"], **opts)
            did.append(r["kind"])
        except Exception:  # noqa: BLE001  某一個接不下去不影響其他
            continue
    if root["scan_state"] == "partial" and not any(k in ("scan", "index") for k, _ in busy) and not _user_stopped(conn, root):
        runner.submit("scan", roots=[root["name"]])  # 上次沒掃完：只接著掃這一顆（已經掃過的資料夾會跳過）
        did.append("scan")
    if "scan" not in did and "index" not in did:  # 有掃描的話，掃完會自己接著做後續（讀文字、封面）
        from .covers import plan as covers_plan

        if covers_plan(conn)["todo"] and ("covers", None) not in busy:
            runner.submit("covers")
            did.append("covers")
        if cfg.auto_extract:
            from .textindex import extract_plan

            if extract_plan(conn)["todo"]["files"] and ("extract", None) not in busy and "extract" not in did:
                runner.submit("extract")
                did.append("extract")
    return did


class DriveWatcher:
    """每隔幾秒看一次哪些硬碟接著；剛接上的（以及打開 App 時就接著的）接著做沒做完的工作。"""

    def __init__(self, cfg, runner, interval: float = INTERVAL):
        self.cfg, self.runner, self.interval = cfg, runner, interval
        self.online: set[int] = set()
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._loop, daemon=True, name="rememor-drive-watcher")

    def start(self) -> "DriveWatcher":
        self.thread.start()
        return self

    def close(self) -> None:
        self.stop.set()

    def tick(self) -> list[tuple[str, list[str]]]:
        """看一次；回傳這次剛接上的硬碟和接著做了什麼（測試用）。"""
        out = []
        conn = db.connect(self.cfg.db_path)
        try:
            roots = conn.execute("SELECT * FROM roots").fetchall()
            now = {r["id"] for r in roots if Path(r["path"]).is_dir()}
            fresh = [r for r in roots if r["id"] in now and r["id"] not in self.online]
            self.online = now
            if not getattr(self.cfg, "auto_continue", True):
                return out
            for r in fresh:
                did = on_connect(conn, self.runner, self.cfg, r)
                if did:
                    _record(conn, r, did)
                out.append((r["name"], did))
        finally:
            conn.close()
        return out

    def _loop(self) -> None:
        while not self.stop.is_set():
            try:
                self.tick()
            except Exception:  # noqa: BLE001  看不到就下次再看
                pass
            self.stop.wait(self.interval)
