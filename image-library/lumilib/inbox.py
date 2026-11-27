"""待辦：所有等本人決定的事集中在一個地方（只整理入口，各項目的確認規則不變）。

依急迫程度排：
1. 硬碟有狀況，要先決定怎麼處理
2. 計畫卡（分類、複製、助理提的整理動作）
3. 分類沒把握、請你確認的資料夾
4. 待刪除清單（每顆硬碟一項）
5. 主動提醒（只提醒，不算在「幾件事」裡）
全部只讀目錄。
"""
from __future__ import annotations

import sqlite3

from . import db


def _health(conn: sqlite3.Connection) -> list[dict]:
    from . import health

    rows = {r["key"]: r for r in conn.execute("SELECT * FROM drive_health")}
    out, seen = [], set()
    for root in db.list_roots(conn):
        key = health.key_of(root)
        if key in seen or key not in rows:
            continue
        seen.add(key)
        h = health.public(rows[key])
        if h["needs_decision"]:
            out.append({**h, "root_id": root["id"]})
    return out


def _actions(conn: sqlite3.Connection, limit: int = 30) -> list[dict]:
    from .actions import get, refresh_plan

    out = []
    for r in conn.execute("SELECT id, kind FROM assistant_actions WHERE state = 'proposed' ORDER BY id DESC LIMIT ?", (limit,)).fetchall():
        a = refresh_plan(conn, r["id"]) if r["kind"] == "category_plan" else get(conn, r["id"])
        if a["state"] == "proposed":  # 試算後發現已經做不了的卡會自動收起來
            out.append(a)
    return out


def _pending(conn: sqlite3.Connection) -> list[dict]:
    from .pending import listing

    return [{"drive": d["drive"], "online": d["online"], "read_only": d["read_only"], "count": len(d["items"]), "bytes": d["bytes"],
             "stale": sum(1 for it in d["items"] if it["stale"])} for d in listing(conn)["drives"]]


def count(conn: sqlite3.Connection) -> int:
    """側邊欄的數字：有幾件事等你決定（很快，不重算計畫卡）。"""
    from . import health
    from .classify import review_count

    n = sum(1 for r in conn.execute("SELECT * FROM drive_health") if health.public(r)["needs_decision"])
    n += conn.execute("SELECT COUNT(*) FROM assistant_actions WHERE state = 'proposed'").fetchone()[0]
    n += 1 if review_count(conn) else 0
    # 待刪除：每顆硬碟一件（用資料夾來源所在的硬碟分；不必逐項驗證）
    n += conn.execute("SELECT COUNT(DISTINCT COALESCE('d' || r.drive_id, 'r' || r.id)) FROM delete_marks m JOIN roots r ON r.id = m.root_id").fetchone()[0]
    return n


def build(conn: sqlite3.Connection) -> dict:
    from . import reminders
    from .classify import review_count, review_list

    health = _health(conn)
    actions = _actions(conn)
    review = {"count": review_count(conn), "examples": [{"folder_id": r["folder_id"], "name": r["name"], "root": r["root"]}
                                                       for r in review_list(conn, 5)]}
    pending = _pending(conn)
    notes = reminders.compute(conn)
    total = len(health) + len(actions) + (1 if review["count"] else 0) + len(pending)
    return {"total": total, "health": health, "actions": actions, "review": review, "pending": pending, "reminders": notes}
