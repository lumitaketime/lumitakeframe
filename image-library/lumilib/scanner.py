"""掃描資料夾，把圖片登錄進圖庫。

- 增量掃描：大小與修改時間沒變的檔案直接略過。
- 搬移偵測：檔案換了資料夾或改名，用內容指紋找回原紀錄，分析結果不用重跑。
- 重複檔案：內容相同的副本直接沿用已完成的分析。
- 外接硬碟未接上時不會把檔案標成遺失。
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import db
from .config import Config
from .imaging import IMAGE_EXTENSIONS, ImageReadError, ensure_thumbnail, open_image

SKIP_DIRS = {
    "$recycle.bin", "system volume information", "@eadir", "#recycle",
    "node_modules", "__pycache__", ".thumbnails", ".trash", ".trashes",
}

ANALYSIS_FIELDS = (
    "analyzed_at", "model", "description", "tags", "objects", "scene",
    "ocr_text", "error", "embedding", "embed_model",
)

_CHUNK = 256 * 1024


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
    """以檔案大小 + 開頭與結尾各 256KB 計算指紋，大檔也很快。"""
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


def iter_image_files(root: Path, exclude: Path | None = None):
    for dirpath, dirnames, filenames in os.walk(root):
        current = Path(dirpath)
        dirnames[:] = sorted(
            d for d in dirnames
            if not d.startswith(".")
            and d.lower() not in SKIP_DIRS
            and (exclude is None or (current / d) != exclude)
        )
        for name in sorted(filenames):
            if name.startswith("._") or name.startswith("."):
                continue
            if Path(name).suffix.lower() in IMAGE_EXTENSIONS:
                yield current / name


def _root_online(conn: sqlite3.Connection, root_id: int) -> bool:
    row = conn.execute("SELECT path FROM roots WHERE id = ?", (root_id,)).fetchone()
    return row is not None and Path(row["path"]).is_dir()


def _find_moved(conn: sqlite3.Connection, fp: str, size: int) -> sqlite3.Row | None:
    """同指紋、但原位置檔案已不存在的紀錄 = 被搬走的檔案。"""
    for row in conn.execute(
        "SELECT * FROM images WHERE fingerprint = ? AND size = ? ORDER BY status = 'missing' DESC, id",
        (fp, size),
    ):
        if row["status"] == "missing":
            return row
        if _root_online(conn, row["root_id"]) and not db.absolute_path(conn, row).exists():
            return row
    return None


def _find_analyzed_copy(conn: sqlite3.Connection, fp: str, size: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM images WHERE fingerprint = ? AND size = ? AND analyzed_at IS NOT NULL LIMIT 1",
        (fp, size),
    ).fetchone()


def _read_meta(cfg: Config, path: Path, fp: str) -> tuple[dict, str | None]:
    try:
        img, meta = open_image(path, draft_side=cfg.thumb_size * 2)
        with img:
            ensure_thumbnail(img, cfg.thumbs_dir, fp, cfg.thumb_size)
        return meta, None
    except ImageReadError as exc:
        return {}, str(exc)
    except OSError as exc:
        return {}, f"無法讀取圖片：{exc}"


def _meta_values(meta: dict) -> tuple:
    return tuple(meta.get(k) for k in ("width", "height", "taken_at", "camera", "lens", "lat", "lon"))


def scan_root(
    conn: sqlite3.Connection,
    cfg: Config,
    root: sqlite3.Row,
    progress: Callable[[str], None] | None = None,
) -> ScanResult:
    result = ScanResult(root=root["name"])
    root_path = Path(root["path"])
    if not root_path.is_dir():
        result.offline = True
        return result

    existing = {
        row["rel_path"]: row
        for row in conn.execute("SELECT * FROM images WHERE root_id = ?", (root["id"],))
    }
    seen: set[str] = set()
    now = db.now_iso()
    exclude = cfg.home.resolve() if cfg.home.exists() else None

    for count, path in enumerate(iter_image_files(root_path, exclude), 1):
        rel = path.relative_to(root_path).as_posix()
        seen.add(rel)
        try:
            st = path.stat()
        except OSError as exc:
            result.errors.append(f"{rel}: {exc}")
            continue
        size, mtime = st.st_size, st.st_mtime
        row = existing.get(rel)

        if row is not None and row["size"] == size and row["mtime"] == mtime:
            if row["status"] != "ok":
                conn.execute("UPDATE images SET status = 'ok', last_seen = ? WHERE id = ?", (now, row["id"]))
                result.updated += 1
            else:
                result.unchanged += 1
            continue

        try:
            fp = fingerprint(path, size)
        except OSError as exc:
            result.errors.append(f"{rel}: {exc}")
            continue

        if row is not None:
            if row["fingerprint"] == fp:
                conn.execute(
                    "UPDATE images SET mtime = ?, status = 'ok', last_seen = ? WHERE id = ?",
                    (mtime, now, row["id"]),
                )
                result.unchanged += 1
                continue
            # 同一路徑內容被替換：重新讀取並清除舊分析
            meta, err = _read_meta(cfg, path, fp)
            conn.execute(
                f"""UPDATE images SET size = ?, mtime = ?, fingerprint = ?,
                        width = ?, height = ?, taken_at = ?, camera = ?, lens = ?, lat = ?, lon = ?,
                        status = 'ok', last_seen = ?,
                        {", ".join(f"{f} = NULL" for f in ANALYSIS_FIELDS)}
                    WHERE id = ?""",
                (size, mtime, fp, *_meta_values(meta), now, row["id"]),
            )
            if err:
                conn.execute("UPDATE images SET error = ? WHERE id = ?", (err, row["id"]))
            db.refresh_search_text(conn, row["id"])
            result.updated += 1
        else:
            moved = _find_moved(conn, fp, size)
            if moved is not None:
                conn.execute(
                    """UPDATE images SET root_id = ?, rel_path = ?, mtime = ?, status = 'ok', last_seen = ?
                       WHERE id = ?""",
                    (root["id"], rel, mtime, now, moved["id"]),
                )
                if moved["root_id"] == root["id"]:
                    existing.pop(moved["rel_path"], None)
                db.refresh_search_text(conn, moved["id"])
                result.moved += 1
            else:
                meta, err = _read_meta(cfg, path, fp)
                cur = conn.execute(
                    """INSERT INTO images (root_id, rel_path, size, mtime, fingerprint,
                           width, height, taken_at, camera, lens, lat, lon,
                           status, first_seen, last_seen, error)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ok', ?, ?, ?)""",
                    (root["id"], rel, size, mtime, fp, *_meta_values(meta), now, now, err),
                )
                new_id = cur.lastrowid
                copy = _find_analyzed_copy(conn, fp, size)
                if copy is not None and not err:
                    conn.execute(
                        f"UPDATE images SET {', '.join(f'{f} = ?' for f in ANALYSIS_FIELDS)} WHERE id = ?",
                        (*(copy[f] for f in ANALYSIS_FIELDS), new_id),
                    )
                    result.reused += 1
                db.refresh_search_text(conn, new_id)
                result.added += 1

        if count % 200 == 0:
            conn.commit()
            if progress:
                progress(f"{root['name']}: 已檢查 {count} 個檔案")

    for rel, row in existing.items():
        if rel in seen or row["status"] != "ok":
            continue
        # 只標記仍停在原位置的紀錄（搬移處理可能已把它改到別處）
        cur = conn.execute(
            "UPDATE images SET status = 'missing' WHERE id = ? AND root_id = ? AND rel_path = ?",
            (row["id"], root["id"], rel),
        )
        result.missing += cur.rowcount
    conn.execute("UPDATE roots SET last_scan = ? WHERE id = ?", (now, root["id"]))
    conn.commit()
    return result


def scan_all(
    conn: sqlite3.Connection,
    cfg: Config,
    root_names: list[str] | None = None,
    progress: Callable[[str], None] | None = None,
) -> list[ScanResult]:
    roots = db.list_roots(conn)
    if root_names:
        wanted = set(root_names)
        roots = [r for r in roots if r["name"] in wanted or str(r["id"]) in wanted]
    return [scan_root(conn, cfg, root, progress) for root in roots]
