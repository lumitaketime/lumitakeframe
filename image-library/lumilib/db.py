"""SQLite 圖庫：資料夾根目錄、照片／影片紀錄、分析結果、相簿。

路徑以「根目錄 + 相對路徑」保存。外接 SSD 換了掛載點時用 relocate 更新根目錄即可。
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 11  # v11：EXIF 編輯紀錄（可復原）

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

CREATE TABLE IF NOT EXISTS albums (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    cover_id INTEGER REFERENCES images(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS persons (
    id INTEGER PRIMARY KEY,
    name TEXT,
    cover_face_id INTEGER,
    hidden INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS faces (
    id INTEGER PRIMARY KEY,
    image_id INTEGER NOT NULL REFERENCES images(id) ON DELETE CASCADE,
    person_id INTEGER REFERENCES persons(id) ON DELETE SET NULL,
    x1 REAL, y1 REAL, x2 REAL, y2 REAL,
    score REAL,
    embedding BLOB NOT NULL,
    model TEXT NOT NULL,
    manual INTEGER NOT NULL DEFAULT 0,
    excluded INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pets (
    id INTEGER PRIMARY KEY,
    name TEXT,
    kind TEXT NOT NULL,
    cover_id INTEGER,
    hidden INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pet_detections (
    id INTEGER PRIMARY KEY,
    image_id INTEGER NOT NULL REFERENCES images(id) ON DELETE CASCADE,
    pet_id INTEGER REFERENCES pets(id) ON DELETE SET NULL,
    kind TEXT NOT NULL,
    x1 REAL, y1 REAL, x2 REAL, y2 REAL,
    score REAL,
    embedding BLOB NOT NULL,
    model TEXT NOT NULL,
    manual INTEGER NOT NULL DEFAULT 0,
    excluded INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS edit_batches (
    id INTEGER PRIMARY KEY,
    created_at TEXT NOT NULL,
    label TEXT,
    items TEXT NOT NULL,
    undone INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS settings_kv (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS smart_albums (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    query TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS album_items (
    album_id INTEGER NOT NULL REFERENCES albums(id) ON DELETE CASCADE,
    image_id INTEGER NOT NULL REFERENCES images(id) ON DELETE CASCADE,
    added_at TEXT NOT NULL,
    PRIMARY KEY (album_id, image_id)
);
"""

# v2 新增欄位：(名稱, 型別定義)
V2_COLUMNS = [
    ("media_type", "TEXT NOT NULL DEFAULT 'photo'"),
    ("is_raw", "INTEGER NOT NULL DEFAULT 0"),
    ("folder", "TEXT NOT NULL DEFAULT ''"),
    ("sort_at", "TEXT"),
    ("tz_offset", "TEXT"),
    ("orientation", "INTEGER"),
    ("duration", "REAL"),
    ("fps", "REAL"),
    ("codec", "TEXT"),
    ("aperture", "REAL"),
    ("exposure_time", "REAL"),
    ("iso", "INTEGER"),
    ("focal_length", "REAL"),
    ("focal_35", "REAL"),
    ("altitude", "REAL"),
    ("rating", "INTEGER"),
    ("keywords", "TEXT"),
    ("title", "TEXT"),
    ("caption", "TEXT"),
    ("artist", "TEXT"),
    ("copyright", "TEXT"),
    ("software", "TEXT"),
    ("favorite", "INTEGER NOT NULL DEFAULT 0"),
    ("thumb_ok", "INTEGER NOT NULL DEFAULT 0"),
    ("faces_at", "TEXT"),
    ("faces_model", "TEXT"),
    ("pets_at", "TEXT"),
    ("pets_model", "TEXT"),
    ("clip", "BLOB"),
    ("clip_model", "TEXT"),
    ("place", "TEXT"),
    ("place_en", "TEXT"),
    ("country", "TEXT"),
    ("label", "TEXT"),
    ("label_text", "TEXT"),
    ("xmp_mtime", "REAL"),
    ("stack_id", "INTEGER"),
    ("stack_top", "INTEGER NOT NULL DEFAULT 1"),
    ("phash", "TEXT"),
    # 照片品質檢查（模糊、曝光），本機計算、不用 AI
    ("quality_at", "TEXT"),
    ("sharpness", "REAL"),
    ("luma", "REAL"),
    ("dark_frac", "REAL"),
    ("bright_frac", "REAL"),
    ("highlight", "REAL"),
]

INDEXES = """
CREATE INDEX IF NOT EXISTS idx_images_fingerprint ON images(fingerprint);
CREATE INDEX IF NOT EXISTS idx_images_status ON images(status);
CREATE INDEX IF NOT EXISTS idx_images_sort ON images(sort_at);
CREATE INDEX IF NOT EXISTS idx_images_folder ON images(root_id, folder);
CREATE INDEX IF NOT EXISTS idx_images_favorite ON images(favorite);
CREATE INDEX IF NOT EXISTS idx_album_items_image ON album_items(image_id);
CREATE INDEX IF NOT EXISTS idx_faces_image ON faces(image_id);
CREATE INDEX IF NOT EXISTS idx_faces_person ON faces(person_id);
CREATE INDEX IF NOT EXISTS idx_pet_det_image ON pet_detections(image_id);
CREATE INDEX IF NOT EXISTS idx_pet_det_pet ON pet_detections(pet_id);
CREATE INDEX IF NOT EXISTS idx_images_stack ON images(stack_id);
"""

# 由掃描時的中繼資料寫入的欄位
META_FIELDS = (
    "width", "height", "taken_at", "tz_offset", "camera", "lens", "lat", "lon", "altitude",
    "orientation", "duration", "fps", "codec", "aperture", "exposure_time", "iso", "focal_length",
    "focal_35", "rating", "keywords", "title", "caption", "artist", "copyright", "software", "label", "label_text",
)


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def folder_of(rel_path: str) -> str:
    return rel_path.rsplit("/", 1)[0] if "/" in rel_path else ""


def _migrate(conn: sqlite3.Connection) -> None:
    existing = {row[1] for row in conn.execute("PRAGMA table_info(images)")}
    for name, ddl in V2_COLUMNS:
        if name not in existing:
            conn.execute(f"ALTER TABLE images ADD COLUMN {name} {ddl}")
    conn.executescript(INDEXES)
    person_cols = {row[1] for row in conn.execute("PRAGMA table_info(persons)")}
    if "groups" not in person_cols:
        conn.execute("ALTER TABLE persons ADD COLUMN groups TEXT")
    # v7：已存的「a;b;c」關鍵字拆成多個
    for row in conn.execute("SELECT id, keywords FROM images WHERE keywords LIKE '%;%'").fetchall():
        from .media import split_keywords

        fixed = split_keywords(json_list(row["keywords"]))
        conn.execute("UPDATE images SET keywords = ? WHERE id = ?", (json.dumps(fixed, ensure_ascii=False), row["id"]))
        refresh_search_text(conn, row["id"])
    # v10：有命名人物或寵物的照片重建搜尋索引，舊版本留下的索引可能沒有名字
    for row in conn.execute(
        "SELECT DISTINCT f.image_id FROM faces f JOIN persons p ON p.id = f.person_id WHERE p.name IS NOT NULL AND p.name != ''"
        " UNION SELECT DISTINCT d.image_id FROM pet_detections d JOIN pets p ON p.id = d.pet_id WHERE p.name IS NOT NULL AND p.name != ''"
    ).fetchall():
        refresh_search_text(conn, row[0])
    if "folder" not in existing:  # 從 v1 升級：補齊資料夾與排序時間
        for row in conn.execute("SELECT id, rel_path, taken_at, mtime FROM images").fetchall():
            conn.execute(
                "UPDATE images SET folder = ?, sort_at = ? WHERE id = ?",
                (folder_of(row["rel_path"]), row["taken_at"] or local_iso(row["mtime"]), row["id"]),
            )


def local_iso(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp).replace(microsecond=0).isoformat()


def connect(db_path: str | Path) -> sqlite3.Connection:
    db_path = Path(db_path)
    if str(db_path) != ":memory:":
        db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version < SCHEMA_VERSION:
        conn.executescript(SCHEMA)
        _migrate(conn)
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        conn.commit()
    return conn


def json_list(value) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [str(x) for x in value]
    try:
        data = json.loads(value)
    except (ValueError, TypeError):
        return []
    return [str(x) for x in data] if isinstance(data, list) else []


def build_search_text(row: dict) -> str:
    """所有可搜尋欄位合併成小寫字串；中文、英文、檔名都以子字串比對。"""
    parts = [
        row.get("rel_path") or "",
        row.get("description") or "",
        " ".join(json_list(row.get("tags"))),
        " ".join(json_list(row.get("user_tags"))),
        " ".join(json_list(row.get("objects"))),
        " ".join(json_list(row.get("keywords"))),
        row.get("scene") or "",
        row.get("ocr_text") or "",
        row.get("camera") or "",
        row.get("lens") or "",
        row.get("title") or "",
        row.get("caption") or "",
        row.get("note") or "",
        row.get("artist") or "",
        " ".join(row.get("people") or []),
        row.get("place") or "",
        row.get("place_en") or "",
        " ".join(row.get("country_names") or []),
    ]
    return "\n".join(p for p in parts if p).lower()


def refresh_search_text(conn: sqlite3.Connection, image_id: int) -> None:
    row = conn.execute("SELECT * FROM images WHERE id = ?", (image_id,)).fetchone()
    if row is not None:
        data = dict(row)
        people = conn.execute(
            "SELECT DISTINCT p.name, p.groups FROM faces f JOIN persons p ON p.id = f.person_id WHERE f.image_id = ?",
            (image_id,),
        ).fetchall()
        data["people"] = [p["name"] for p in people if p["name"]] + [g for p in people for g in json_list(p["groups"])]
        try:
            pets = conn.execute(
                "SELECT DISTINCT p.name FROM pet_detections d JOIN pets p ON p.id = d.pet_id WHERE d.image_id = ? AND p.name IS NOT NULL",
                (image_id,),
            ).fetchall()
            data["people"] += [p["name"] for p in pets]
        except sqlite3.OperationalError:
            pass  # 舊資料庫尚未建立寵物表
        if data.get("country"):
            from .places import country_names

            data["country_names"] = list(country_names(data["country"]))
        conn.execute("UPDATE images SET search_text = ? WHERE id = ?", (build_search_text(data), image_id))


# ---- roots -----------------------------------------------------------------

def add_root(conn: sqlite3.Connection, path: str | Path, name: str | None = None) -> sqlite3.Row:
    resolved = Path(path).expanduser().resolve()
    if not resolved.is_dir():
        raise ValueError(f"資料夾不存在：{resolved}")
    name = (name or resolved.name or str(resolved)).strip()
    existing = conn.execute("SELECT * FROM roots WHERE name = ?", (name,)).fetchone()
    if existing:
        raise ValueError(f"名稱「{name}」已被使用（{existing['path']}），請換一個名稱")
    for row in conn.execute("SELECT * FROM roots"):
        other = Path(row["path"])
        if other == resolved or other in resolved.parents or resolved in other.parents:
            raise ValueError(f"與既有資料夾「{row['name']}」（{row['path']}）重疊")
    conn.execute("INSERT INTO roots (name, path, created_at) VALUES (?, ?, ?)", (name, str(resolved), now_iso()))
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

def absolute_path(conn: sqlite3.Connection, image) -> Path:
    root = conn.execute("SELECT path FROM roots WHERE id = ?", (image["root_id"],)).fetchone()
    return Path(root["path"]).joinpath(*image["rel_path"].split("/"))


def get_image(conn: sqlite3.Connection, image_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM images WHERE id = ?", (image_id,)).fetchone()


def set_user_fields(conn: sqlite3.Connection, image_id: int, user_tags=None, note=None, favorite=None) -> None:
    if user_tags is not None:
        clean: list[str] = []
        for tag in user_tags:
            tag = str(tag).strip()
            if tag and tag not in clean:
                clean.append(tag)
        conn.execute("UPDATE images SET user_tags = ? WHERE id = ?", (json.dumps(clean, ensure_ascii=False), image_id))
    if note is not None:
        conn.execute("UPDATE images SET note = ? WHERE id = ?", (str(note), image_id))
    if favorite is not None:
        conn.execute("UPDATE images SET favorite = ? WHERE id = ?", (1 if favorite else 0, image_id))
    if user_tags is not None or note is not None:
        conn.execute("UPDATE images SET embedding = NULL, embed_model = NULL WHERE id = ?", (image_id,))
        refresh_search_text(conn, image_id)
    conn.commit()


def stats(conn: sqlite3.Connection) -> dict:
    q = lambda sql: conn.execute(sql).fetchone()[0]  # noqa: E731
    return {
        "roots": q("SELECT COUNT(*) FROM roots"),
        "images": q("SELECT COUNT(*) FROM images WHERE status = 'ok'"),
        "photos": q("SELECT COUNT(*) FROM images WHERE status = 'ok' AND media_type = 'photo'"),
        "videos": q("SELECT COUNT(*) FROM images WHERE status = 'ok' AND media_type = 'video'"),
        "missing": q("SELECT COUNT(*) FROM images WHERE status = 'missing'"),
        "analyzed": q("SELECT COUNT(*) FROM images WHERE status = 'ok' AND analyzed_at IS NOT NULL"),
        "pending": q("SELECT COUNT(*) FROM images WHERE status = 'ok' AND analyzed_at IS NULL AND error IS NULL"),
        "failed": q("SELECT COUNT(*) FROM images WHERE status = 'ok' AND analyzed_at IS NULL AND error IS NOT NULL"),
        "embedded": q("SELECT COUNT(*) FROM images WHERE status = 'ok' AND embedding IS NOT NULL"),
        "favorites": q("SELECT COUNT(*) FROM images WHERE status = 'ok' AND favorite = 1"),
        "albums": q("SELECT COUNT(*) FROM albums"),
        "faces": q("SELECT COUNT(*) FROM faces"),
        "people": q("SELECT COUNT(*) FROM persons"),
        "faces_pending": q("SELECT COUNT(*) FROM images WHERE status = 'ok' AND media_type = 'photo' AND faces_at IS NULL"),
        "clip_done": q("SELECT COUNT(*) FROM images WHERE status = 'ok' AND clip IS NOT NULL"),
    }


# ---- albums ----------------------------------------------------------------

def create_album(conn: sqlite3.Connection, name: str, image_ids: list[int] | None = None) -> int:
    name = (name or "").strip() or "未命名相簿"
    now = now_iso()
    cur = conn.execute("INSERT INTO albums (name, created_at, updated_at) VALUES (?, ?, ?)", (name, now, now))
    album_id = cur.lastrowid
    if image_ids:
        add_to_album(conn, album_id, image_ids)
    conn.commit()
    return album_id


def add_to_album(conn: sqlite3.Connection, album_id: int, image_ids: list[int]) -> int:
    now = now_iso()
    cur = conn.executemany(
        "INSERT OR IGNORE INTO album_items (album_id, image_id, added_at) "
        "SELECT ?, id, ? FROM images WHERE id = ?",
        [(album_id, now, int(i)) for i in image_ids],
    )
    conn.execute("UPDATE albums SET updated_at = ? WHERE id = ?", (now, album_id))
    conn.commit()
    return cur.rowcount


def remove_from_album(conn: sqlite3.Connection, album_id: int, image_ids: list[int]) -> None:
    conn.executemany(
        "DELETE FROM album_items WHERE album_id = ? AND image_id = ?", [(album_id, int(i)) for i in image_ids]
    )
    conn.execute("UPDATE albums SET updated_at = ? WHERE id = ?", (now_iso(), album_id))
    conn.commit()


def list_albums(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """SELECT a.*,
                  COUNT(i.id) AS count,
                  MIN(i.sort_at) AS start_at,
                  MAX(i.sort_at) AS end_at,
                  COALESCE(a.cover_id, (
                      SELECT ai.image_id FROM album_items ai JOIN images x ON x.id = ai.image_id
                      WHERE ai.album_id = a.id AND x.status = 'ok' ORDER BY x.sort_at DESC LIMIT 1
                  )) AS cover
           FROM albums a
           LEFT JOIN album_items ai ON ai.album_id = a.id
           LEFT JOIN images i ON i.id = ai.image_id AND i.status = 'ok'
           GROUP BY a.id ORDER BY a.updated_at DESC"""
    ).fetchall()
    return [dict(r) for r in rows]


def get_album(conn: sqlite3.Connection, album_id: int) -> dict | None:
    for album in list_albums(conn):
        if album["id"] == album_id:
            return album
    return None


def update_album(conn: sqlite3.Connection, album_id: int, name=None, description=None, cover_id=None) -> None:
    if name is not None:
        conn.execute("UPDATE albums SET name = ? WHERE id = ?", (name.strip() or "未命名相簿", album_id))
    if description is not None:
        conn.execute("UPDATE albums SET description = ? WHERE id = ?", (description, album_id))
    if cover_id is not None:
        conn.execute("UPDATE albums SET cover_id = ? WHERE id = ?", (int(cover_id), album_id))
    conn.execute("UPDATE albums SET updated_at = ? WHERE id = ?", (now_iso(), album_id))
    conn.commit()


def delete_album(conn: sqlite3.Connection, album_id: int) -> None:
    conn.execute("DELETE FROM albums WHERE id = ?", (album_id,))
    conn.commit()
