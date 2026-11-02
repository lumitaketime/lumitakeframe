"""SQLite 圖庫：資料夾根目錄、圖片紀錄與分析結果。

圖片路徑以「根目錄 + 相對路徑」保存。外接 SSD 換了磁碟代號或掛載點時，
只要用 `relocate` 更新根目錄位置，所有分析結果都會保留。
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS roots (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    path TEXT NOT NULL,
    created_at TEXT NOT NULL,
    last_scan TEXT
);

CREATE TABLE IF NOT EXISTS images (
    id INTEGER PRIMARY KEY,
    root_id INTEGER NOT NULL REFERENCES roots(id) ON DELETE CASCADE,
    rel_path TEXT NOT NULL,
    size INTEGER NOT NULL,
    mtime REAL NOT NULL,
    fingerprint TEXT NOT NULL,
    width INTEGER,
    height INTEGER,
    taken_at TEXT,
    camera TEXT,
    lens TEXT,
    lat REAL,
    lon REAL,
    status TEXT NOT NULL DEFAULT 'ok',
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    analyzed_at TEXT,
    model TEXT,
    description TEXT,
    tags TEXT,
    objects TEXT,
    scene TEXT,
    ocr_text TEXT,
    user_tags TEXT,
    note TEXT,
    error TEXT,
    search_text TEXT NOT NULL DEFAULT '',
    embedding BLOB,
    embed_model TEXT,
    UNIQUE (root_id, rel_path)
);

CREATE INDEX IF NOT EXISTS idx_images_fingerprint ON images(fingerprint);
CREATE INDEX IF NOT EXISTS idx_images_status ON images(status);
CREATE INDEX IF NOT EXISTS idx_images_taken ON images(taken_at);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def connect(db_path: str | Path) -> sqlite3.Connection:
    db_path = Path(db_path)
    if str(db_path) != ":memory:":
        db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.executescript(SCHEMA)
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    conn.commit()
    return conn


def json_list(value) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        return value
    try:
        data = json.loads(value)
    except ValueError:
        return []
    return [str(x) for x in data] if isinstance(data, list) else []


def build_search_text(row: dict) -> str:
    """把所有可搜尋欄位合併成一個小寫字串，中文、英文、檔名都能直接以子字串比對。"""
    parts = [
        row.get("rel_path") or "",
        row.get("description") or "",
        " ".join(json_list(row.get("tags"))),
        " ".join(json_list(row.get("user_tags"))),
        " ".join(json_list(row.get("objects"))),
        row.get("scene") or "",
        row.get("ocr_text") or "",
        row.get("camera") or "",
        row.get("lens") or "",
        row.get("note") or "",
    ]
    return "\n".join(p for p in parts if p).lower()


def refresh_search_text(conn: sqlite3.Connection, image_id: int) -> None:
    row = conn.execute("SELECT * FROM images WHERE id = ?", (image_id,)).fetchone()
    if row is None:
        return
    conn.execute(
        "UPDATE images SET search_text = ? WHERE id = ?",
        (build_search_text(dict(row)), image_id),
    )


# ---- roots -----------------------------------------------------------------

def add_root(conn: sqlite3.Connection, path: str | Path, name: str | None = None) -> sqlite3.Row:
    resolved = Path(path).expanduser().resolve()
    if not resolved.is_dir():
        raise ValueError(f"資料夾不存在：{resolved}")
    name = name or resolved.name or str(resolved)
    existing = conn.execute("SELECT * FROM roots WHERE name = ?", (name,)).fetchone()
    if existing:
        raise ValueError(f"名稱「{name}」已被使用（{existing['path']}），請用 --name 指定其他名稱")
    for row in conn.execute("SELECT * FROM roots"):
        other = Path(row["path"])
        if other == resolved or other in resolved.parents or resolved in other.parents:
            raise ValueError(f"與既有資料夾「{row['name']}」（{row['path']}）重疊")
    conn.execute(
        "INSERT INTO roots (name, path, created_at) VALUES (?, ?, ?)",
        (name, str(resolved), now_iso()),
    )
    conn.commit()
    return get_root(conn, name)


def get_root(conn: sqlite3.Connection, name_or_id) -> sqlite3.Row | None:
    if isinstance(name_or_id, int) or str(name_or_id).isdigit():
        row = conn.execute("SELECT * FROM roots WHERE id = ?", (int(name_or_id),)).fetchone()
        if row:
            return row
    return conn.execute("SELECT * FROM roots WHERE name = ?", (str(name_or_id),)).fetchone()


def list_roots(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """SELECT r.*,
                  (SELECT COUNT(*) FROM images i WHERE i.root_id = r.id AND i.status = 'ok') AS image_count
           FROM roots r ORDER BY r.name"""
    ).fetchall()


def relocate_root(conn: sqlite3.Connection, name_or_id, new_path: str | Path) -> sqlite3.Row:
    root = get_root(conn, name_or_id)
    if root is None:
        raise ValueError(f"找不到資料夾：{name_or_id}")
    resolved = Path(new_path).expanduser().resolve()
    if not resolved.is_dir():
        raise ValueError(f"資料夾不存在：{resolved}")
    conn.execute("UPDATE roots SET path = ? WHERE id = ?", (str(resolved), root["id"]))
    conn.commit()
    return get_root(conn, root["id"])


def remove_root(conn: sqlite3.Connection, name_or_id) -> int:
    root = get_root(conn, name_or_id)
    if root is None:
        raise ValueError(f"找不到資料夾：{name_or_id}")
    count = conn.execute("SELECT COUNT(*) FROM images WHERE root_id = ?", (root["id"],)).fetchone()[0]
    conn.execute("DELETE FROM roots WHERE id = ?", (root["id"],))
    conn.commit()
    return count


# ---- images ----------------------------------------------------------------

def absolute_path(conn: sqlite3.Connection, image: sqlite3.Row | dict) -> Path:
    root = conn.execute("SELECT path FROM roots WHERE id = ?", (image["root_id"],)).fetchone()
    return Path(root["path"]).joinpath(*image["rel_path"].split("/"))


def get_image(conn: sqlite3.Connection, image_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM images WHERE id = ?", (image_id,)).fetchone()


def set_user_fields(conn: sqlite3.Connection, image_id: int, user_tags=None, note=None) -> None:
    if user_tags is not None:
        clean = []
        for tag in user_tags:
            tag = str(tag).strip()
            if tag and tag not in clean:
                clean.append(tag)
        conn.execute(
            "UPDATE images SET user_tags = ? WHERE id = ?",
            (json.dumps(clean, ensure_ascii=False), image_id),
        )
    if note is not None:
        conn.execute("UPDATE images SET note = ? WHERE id = ?", (str(note), image_id))
    # 標籤變了，語意向量要重算
    conn.execute("UPDATE images SET embedding = NULL, embed_model = NULL WHERE id = ?", (image_id,))
    refresh_search_text(conn, image_id)
    conn.commit()


def stats(conn: sqlite3.Connection) -> dict:
    q = lambda sql: conn.execute(sql).fetchone()[0]  # noqa: E731
    return {
        "roots": q("SELECT COUNT(*) FROM roots"),
        "images": q("SELECT COUNT(*) FROM images WHERE status = 'ok'"),
        "missing": q("SELECT COUNT(*) FROM images WHERE status = 'missing'"),
        "analyzed": q("SELECT COUNT(*) FROM images WHERE status = 'ok' AND analyzed_at IS NOT NULL"),
        "pending": q("SELECT COUNT(*) FROM images WHERE status = 'ok' AND analyzed_at IS NULL AND error IS NULL"),
        "failed": q("SELECT COUNT(*) FROM images WHERE status = 'ok' AND analyzed_at IS NULL AND error IS NOT NULL"),
        "embedded": q("SELECT COUNT(*) FROM images WHERE status = 'ok' AND embedding IS NOT NULL"),
    }
