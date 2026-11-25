"""主動提醒：只提醒、不動手。總覽頁的「需要注意」與選單列會顯示，每一則都可以先不要提醒（七天）。

- 硬碟剛接上：Re'memor 接著做了哪些事
- 重複的資料夾：一模一樣、可以省多少
- 打算淘汰的硬碟：還有多少只在它上面
- 硬碟接著、還有可能的副本沒確認
- 很久沒掃描的硬碟
全部只讀目錄（淘汰檢查只用算好的結果）。
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import db

SNOOZE_KEY = "reminders_snoozed"
BIG_FOLDER = 100_000_000  # 重複資料夾至少可以省這麼多才提醒
STALE_DAYS = 180
DID = {"scan": "接著掃描", "covers": "做文件封面", "extract": "讀文件文字", "ocr": "文字辨識", "retire_verify": "確認副本",
       "consolidate": "接著複製", "compare": "比對內容", "photos": "做照片縮圖", "embed_docs": "建立語意索引"}


def _snoozed(conn) -> dict:
    r = conn.execute("SELECT value FROM settings_kv WHERE key = ?", (SNOOZE_KEY,)).fetchone()
    try:
        out = json.loads(r["value"]) if r else {}
    except ValueError:
        out = {}
    now = db.now_iso()
    return {k: v for k, v in (out.items() if isinstance(out, dict) else []) if v > now}


def snooze(conn, key: str, days: int = 7) -> None:
    out = _snoozed(conn)
    out[str(key)[:200]] = (datetime.now(timezone.utc) + timedelta(days=max(1, min(int(days), 365)))).isoformat(timespec="seconds")
    conn.execute("INSERT OR REPLACE INTO settings_kv (key, value) VALUES (?, ?)", (SNOOZE_KEY, json.dumps(out, ensure_ascii=False)))
    conn.commit()


def _bytes(n: int) -> str:
    for unit, size in (("TB", 1e12), ("GB", 1e9), ("MB", 1e6), ("KB", 1e3)):
        if n >= size:
            return f"{n / size:.1f} {unit}"
    return f"{n} B"


def compute(conn, limit: int = 8) -> list[dict]:
    from .autopilot import events
    from .retire import _name_of, planned

    out: list[dict] = []
    now = datetime.now(timezone.utc)
    # 剛接上的硬碟（兩小時內）
    for ev in events(conn, 5):
        try:
            at = datetime.fromisoformat(ev["at"])
        except (KeyError, ValueError):
            continue
        if now - at < timedelta(hours=2):
            did = "、".join(DID.get(k, k) for k in ev.get("did") or [])
            out.append({"key": f"event:{ev['root_id']}:{ev['at']}", "kind": "connected", "level": "info", "icon": "external-drive",
                        "text": f"「{ev['name']}」接上了，Re'memor 接著{did}", "href": "/activity"})
    roots = conn.execute("SELECT * FROM roots ORDER BY name").fetchall()
    names = {r["id"]: _name_of(conn, r) for r in roots}
    online = {r["id"] for r in roots if Path(r["path"]).is_dir()}
    runs = {r["root_id"]: json.loads(r["summary"]) for r in conn.execute("SELECT root_id, summary FROM retire_runs")}
    # 打算淘汰的硬碟還有東西只在它上面
    for rid in sorted(planned(conn)):
        sm = runs.get(rid)
        if sm and sm["states"]["only"]["files"]:
            out.append({"key": f"retire:{rid}", "kind": "retire", "level": "warn", "icon": "exclamation-triangle",
                        "text": f"你打算淘汰的「{names.get(rid, rid)}」還有 {sm['states']['only']['files']:,} 個檔案（{_bytes(sm['states']['only']['bytes'])}）只在它上面",
                        "href": f"/retire/{rid}"})
    # 接著的硬碟還有可能的副本沒確認
    for rid in sorted(online):
        sm = runs.get(rid)
        if sm and sm["states"]["maybe"]["files"]:
            out.append({"key": f"maybe:{rid}", "kind": "maybe", "level": "info", "icon": "duplicate",
                        "text": f"「{names.get(rid, rid)}」接著，可以確認 {sm['states']['maybe']['files']:,} 個可能的副本", "href": f"/retire/{rid}"})
    # 一模一樣的重複資料夾
    try:
        from .dupes import duplicate_folders

        for g in duplicate_folders(conn, limit=5)["groups"]:
            if g["confirmed"] and g["releasable"] >= BIG_FOLDER:
                where = "、".join(f"「{i.get('drive') or ''}」" for i in g["items"][:3])
                out.append({"key": f"dupfolder:{g['key']}", "kind": "dupfolder", "level": "info", "icon": "duplicate",
                            "text": f"「{g['name']}」在 {where} 各有一份、內容一模一樣，可以省 {_bytes(g['releasable'])}", "href": "/duplicates"})
    except Exception:  # noqa: BLE001
        pass
    # 很久沒掃描
    old = (now - timedelta(days=STALE_DAYS)).isoformat(timespec="seconds")
    for r in roots:
        if r["last_scan"] and r["last_scan"] < old:
            out.append({"key": f"stale:{r['id']}", "kind": "stale", "level": "info", "icon": "clock",
                        "text": f"「{names[r['id']]}」超過半年沒掃描了，接上後可以重新掃描", "href": "/drives"})
    hidden = _snoozed(conn)
    return [x for x in out if x["key"] not in hidden][:limit]
