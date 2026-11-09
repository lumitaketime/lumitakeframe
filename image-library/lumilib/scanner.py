"""掃描資料夾，把照片與影片登錄進圖庫。

- 增量掃描：大小與修改時間沒變的檔案直接略過。
- 搬移偵測：檔案換資料夾或改名，用內容指紋找回原紀錄，分析與相簿都保留。
- 重複檔案：內容相同的副本直接沿用已完成的分析。
- 外接硬碟未接上時不會把檔案標成遺失。
- 中繼資料以 exiftool 一批一批讀取，大量檔案也不會太慢。
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import db
from .config import Config
from .media import MediaError, load_image, media_kind, read_metadata_batch, write_thumbnail

SKIP_DIRS = {
    "$recycle.bin", "system volume information", "@eadir", "#recycle", "node_modules",
    "__pycache__", ".thumbnails", ".trash", ".trashes", ".spotlight-v100", ".fseventsd",
    ".documentrevisions-v100", ".temporaryitems",
}
# Lightroom / Capture One / 蘋果照片的資料庫套件內部不掃
SKIP_SUFFIXES = (".lrdata", ".cocatalog", ".photoslibrary", ".photolibrary", ".lrcat-data", ".app")

ANALYSIS_FIELDS = (
    "analyzed_at", "model", "description", "tags", "objects", "scene",
    "ocr_text", "error", "embedding", "embed_model",
)
RESET_FIELDS = ANALYSIS_FIELDS + ("faces_at", "faces_model", "clip", "clip_model", "place", "place_en", "country")

_CHUNK = 64 * 1024
BATCH = 48


@dataclass
class ScanResult:
    root: str
    offline: bool = False
    added: int = 0
    updated: int = 0
    moved: int = 0
    reused: int = 0
    unchanged: int = 0
    missing: int = 0
    errors: list[str] = field(default_factory=list)


def fingerprint(path: Path, size: int) -> str:
    """檔案大小 + 開頭與結尾各 64KB 的雜湊，大檔也很快。"""
    h = hashlib.blake2b(digest_size=16)
    h.update(size.to_bytes(8, "little"))
    with open(path, "rb") as fh:
        if size <= _CHUNK * 2:
            h.update(fh.read())
        else:
            h.update(fh.read(_CHUNK))
            fh.seek(-_CHUNK, os.SEEK_END)
            h.update(fh.read(_CHUNK))
    return h.hexdigest()


def iter_media_files(root: Path, exclude: Path | None = None):
    for dirpath, dirnames, filenames in os.walk(root):
        current = Path(dirpath)
        dirnames[:] = sorted(
            d for d in dirnames
            if not d.startswith(".")
            and d.lower() not in SKIP_DIRS
            and not d.lower().endswith(SKIP_SUFFIXES)
            and (exclude is None or (current / d) != exclude)
        )
        for name in sorted(filenames):
            if not name.startswith(".") and media_kind(name):
                yield current / name


def _root_online(conn: sqlite3.Connection, root_id: int) -> bool:
    row = conn.execute("SELECT path FROM roots WHERE id = ?", (root_id,)).fetchone()
    return row is not None and Path(row["path"]).is_dir()


def _find_moved(conn: sqlite3.Connection, fp: str, size: int) -> sqlite3.Row | None:
    for row in conn.execute(
        "SELECT * FROM images WHERE fingerprint = ? AND size = ? ORDER BY status = 'missing' DESC, id", (fp, size)
    ):
        if row["status"] == "missing":
            return row
        if _root_online(conn, row["root_id"]) and not db.absolute_path(conn, row).exists():
            return row
    return None


def _meta_values(meta: dict) -> list:
    values = []
    for key in db.META_FIELDS:
        value = meta.get(key)
        if key == "keywords":
            value = json.dumps(value, ensure_ascii=False) if value else None
        values.append(value)
    return values


def make_thumbnail(cfg: Config, path: Path, kind: tuple[str, bool], fp: str, meta: dict) -> str | None:
    try:
        img = load_image(path, kind[0], kind[1], cfg.thumb_size * 2, meta.get("duration"), meta.get("orientation"))
        write_thumbnail(img, cfg.thumbs_dir, fp, cfg.thumb_size)
        if not meta.get("width") and img:  # 沒有尺寸資訊時用縮圖比例
            meta["width"], meta["height"] = img.width, img.height
        return None
    except MediaError as exc:
        return str(exc)


@dataclass
class _Pending:
    path: Path
    rel: str
    size: int
    mtime: float
    fp: str
    kind: tuple[str, bool]
    row: sqlite3.Row | None  # 同一路徑既有紀錄（內容被替換）


def _process_batch(conn: sqlite3.Connection, cfg: Config, root: sqlite3.Row, batch: list[_Pending],
                   result: ScanResult, now: str) -> None:
    metas = read_metadata_batch([p.path for p in batch])
    set_meta = ", ".join(f"{f} = ?" for f in db.META_FIELDS)
    for item in batch:
        meta = metas.get(item.path)
        err = None
        if isinstance(meta, MediaError):
            err, meta = str(meta), {}
        meta = meta or {}
        thumb_err = make_thumbnail(cfg, item.path, item.kind, item.fp, meta)
        err = err or thumb_err
        sort_at = meta.get("taken_at") or db.local_iso(item.mtime)
        values = _meta_values(meta)
        if item.row is not None:
            conn.execute(
                f"""UPDATE images SET size = ?, mtime = ?, fingerprint = ?, media_type = ?, is_raw = ?,
                        sort_at = ?, status = 'ok', last_seen = ?, thumb_ok = ?, {set_meta},
                        {", ".join(f"{f} = NULL" for f in RESET_FIELDS)}
                    WHERE id = ?""",
                (item.size, item.mtime, item.fp, item.kind[0], int(item.kind[1]), sort_at, now,
                 0 if thumb_err else 1, *values, item.row["id"]),
            )
            conn.execute("DELETE FROM faces WHERE image_id = ?", (item.row["id"],))
            image_id = item.row["id"]
            result.updated += 1
        else:
            cur = conn.execute(
                f"""INSERT INTO images (root_id, rel_path, folder, size, mtime, fingerprint, media_type, is_raw,
                        sort_at, status, first_seen, last_seen, thumb_ok, {", ".join(db.META_FIELDS)})
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'ok', ?, ?, ?, {", ".join("?" * len(db.META_FIELDS))})""",
                (root["id"], item.rel, db.folder_of(item.rel), item.size, item.mtime, item.fp, item.kind[0],
                 int(item.kind[1]), sort_at, now, now, 0 if thumb_err else 1, *values),
            )
            image_id = cur.lastrowid
            result.added += 1
            copy = conn.execute(
                "SELECT * FROM images WHERE fingerprint = ? AND size = ? AND analyzed_at IS NOT NULL AND id != ? LIMIT 1",
                (item.fp, item.size, image_id),
            ).fetchone()
            if copy is not None and not err:
                conn.execute(
                    f"UPDATE images SET {', '.join(f'{f} = ?' for f in ANALYSIS_FIELDS)} WHERE id = ?",
                    (*(copy[f] for f in ANALYSIS_FIELDS), image_id),
                )
                result.reused += 1
        if err:
            conn.execute("UPDATE images SET error = ? WHERE id = ?", (err, image_id))
            result.errors.append(f"{item.rel}: {err}")
        db.refresh_search_text(conn, image_id)
    conn.commit()


def scan_root(
    conn: sqlite3.Connection,
    cfg: Config,
    root: sqlite3.Row,
    progress: Callable[[str], None] | None = None,
    stop=None,
) -> ScanResult:
    result = ScanResult(root=root["name"])
    root_path = Path(root["path"])
    if not root_path.is_dir():
        result.offline = True
        return result

    existing = {row["rel_path"]: row for row in conn.execute("SELECT * FROM images WHERE root_id = ?", (root["id"],))}
    seen: set[str] = set()
    now = db.now_iso()
    exclude = cfg.home.resolve() if cfg.home.exists() else None
    batch: list[_Pending] = []
    stopped = False

    for count, path in enumerate(iter_media_files(root_path, exclude), 1):
        if stop is not None and stop.is_set():
            stopped = True
            break
        rel = path.relative_to(root_path).as_posix()
        seen.add(rel)
        try:
            st = path.stat()
        except OSError as exc:
            result.errors.append(f"{rel}: {exc}")
            continue
        size, mtime = st.st_size, st.st_mtime
        row = existing.get(rel)
        kind = media_kind(path)

        if row is not None and row["size"] == size and row["mtime"] == mtime:
            if row["status"] != "ok":
                conn.execute("UPDATE images SET status = 'ok', last_seen = ? WHERE id = ?", (now, row["id"]))
                result.updated += 1
            else:
                result.unchanged += 1
        else:
            try:
                fp = fingerprint(path, size)
            except OSError as exc:
                result.errors.append(f"{rel}: {exc}")
                continue
            if row is not None and row["fingerprint"] == fp:
                conn.execute("UPDATE images SET mtime = ?, status = 'ok', last_seen = ? WHERE id = ?", (mtime, now, row["id"]))
                result.unchanged += 1
            elif row is not None:
                batch.append(_Pending(path, rel, size, mtime, fp, kind, row))
            else:
                moved = _find_moved(conn, fp, size)
                if moved is not None:
                    conn.execute(
                        "UPDATE images SET root_id = ?, rel_path = ?, folder = ?, mtime = ?, status = 'ok', last_seen = ? WHERE id = ?",
                        (root["id"], rel, db.folder_of(rel), mtime, now, moved["id"]),
                    )
                    if moved["root_id"] == root["id"]:
                        existing.pop(moved["rel_path"], None)
                    db.refresh_search_text(conn, moved["id"])
                    result.moved += 1
                else:
                    batch.append(_Pending(path, rel, size, mtime, fp, kind, None))

        if len(batch) >= BATCH:
            _process_batch(conn, cfg, root, batch, result, now)
            batch = []
        if count % 200 == 0:
            conn.commit()
            if progress:
                progress(f"{root['name']}：已檢查 {count} 個檔案，新增 {result.added}")

    if batch:
        _process_batch(conn, cfg, root, batch, result, now)

    if not stopped:  # 中途停止時不能判定其他檔案遺失
        for rel, row in existing.items():
            if rel in seen or row["status"] != "ok":
                continue
            cur = conn.execute(
                "UPDATE images SET status = 'missing' WHERE id = ? AND root_id = ? AND rel_path = ?",
                (row["id"], root["id"], rel),
            )
            result.missing += cur.rowcount
        conn.execute("UPDATE roots SET last_scan = ? WHERE id = ?", (now, root["id"]))
    conn.commit()
    return result


def scan_all(conn, cfg, root_names=None, progress=None, stop=None) -> list[ScanResult]:
    roots = db.list_roots(conn)
    if root_names:
        wanted = {str(n) for n in root_names}
        roots = [r for r in roots if r["name"] in wanted or str(r["id"]) in wanted]
    results = []
    for root in roots:
        if stop is not None and stop.is_set():
            break
        results.append(scan_root(conn, cfg, root, progress, stop))
    from .organize import rebuild_stacks
    from .places import geocode_images

    geocode_images(conn, progress)
    rebuild_stacks(conn, cfg)
    return results
