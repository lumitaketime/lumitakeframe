"""助理的對話紀錄：每一段對話（問題、回答、查詢步驟、找到的來源、提出的動作）存在這台電腦的目錄資料庫，
換頁、關掉 App 再打開都還看得到；可以多選刪除。只存在 Re'memor 的資料庫，不會上傳（核心原則二）。
刪除紀錄只刪 Re'memor 存的對話，不會動到任何檔案，也不會復原或取消已經執行的動作。"""

from __future__ import annotations

import json
import sqlite3

from . import db

TITLE_CHARS = 40


def create(conn: sqlite3.Connection, question: str) -> int:
    title = " ".join(question.split())[:TITLE_CHARS] or "新對話"
    now = db.now_iso()
    cur = conn.execute("INSERT INTO assistant_chats (title, created_at, updated_at) VALUES (?, ?, ?)", (title, now, now))
    conn.commit()
    return cur.lastrowid


def exists(conn: sqlite3.Connection, chat_id: int) -> bool:
    return conn.execute("SELECT 1 FROM assistant_chats WHERE id = ?", (int(chat_id),)).fetchone() is not None


def add_message(conn: sqlite3.Connection, chat_id: int, role: str, content: str, steps=None, sources=None,
                actions=None, error: str = "") -> int:
    now = db.now_iso()
    cur = conn.execute(
        "INSERT INTO assistant_messages (chat_id, role, content, steps, sources, actions, error, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (int(chat_id), role, content or "", json.dumps(steps or [], ensure_ascii=False), json.dumps(sources or [], ensure_ascii=False),
         json.dumps(actions or [], ensure_ascii=False), error or "", now))
    conn.execute("UPDATE assistant_chats SET updated_at = ? WHERE id = ?", (now, int(chat_id)))
    conn.commit()
    return cur.lastrowid


def listing(conn: sqlite3.Connection, limit: int = 200) -> list[dict]:
    rows = conn.execute(
        "SELECT c.id, c.title, c.created_at, c.updated_at, COUNT(m.id) AS n FROM assistant_chats c "
        "LEFT JOIN assistant_messages m ON m.chat_id = c.id GROUP BY c.id ORDER BY c.updated_at DESC, c.id DESC LIMIT ?",
        (max(1, min(limit, 1000)),)).fetchall()
    return [{"id": r["id"], "title": r["title"], "created_at": r["created_at"], "updated_at": r["updated_at"], "messages": r["n"]}
            for r in rows]


def load(conn: sqlite3.Connection, chat_id: int) -> dict | None:
    from .actions import ActionError, get

    c = conn.execute("SELECT * FROM assistant_chats WHERE id = ?", (int(chat_id),)).fetchone()
    if c is None:
        return None
    out = []
    for m in conn.execute("SELECT * FROM assistant_messages WHERE chat_id = ? ORDER BY id", (int(chat_id),)):
        acts = []
        for aid in json.loads(m["actions"] or "[]"):
            try:
                acts.append(get(conn, aid))  # 動作現在的狀態（之後可能已經執行或復原）
            except ActionError:
                continue
        out.append({"role": m["role"], "content": m["content"], "steps": json.loads(m["steps"] or "[]"),
                    "sources": json.loads(m["sources"] or "[]"), "actions": acts, "error": m["error"] or "",
                    "created_at": m["created_at"]})
    return {"id": c["id"], "title": c["title"], "created_at": c["created_at"], "updated_at": c["updated_at"], "messages": out}


def delete(conn: sqlite3.Connection, ids: list) -> int:
    ids = [int(i) for i in ids or []][:1000]
    if not ids:
        return 0
    marks = ",".join("?" * len(ids))
    conn.execute(f"DELETE FROM assistant_messages WHERE chat_id IN ({marks})", ids)
    n = conn.execute(f"DELETE FROM assistant_chats WHERE id IN ({marks})", ids).rowcount
    conn.commit()
    return n


def rename(conn: sqlite3.Connection, chat_id: int, title: str) -> None:
    title = " ".join(str(title or "").split())[:80]
    if title:
        conn.execute("UPDATE assistant_chats SET title = ? WHERE id = ?", (title, int(chat_id)))
        conn.commit()
