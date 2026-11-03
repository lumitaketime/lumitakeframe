"""儲存空間管理：看得到圖庫資料、縮圖快取與模型各佔多少空間，並能清掉不用的。

照片本身永遠不會被這裡的任何動作刪除；這裡只處理本程式產生的資料
（資料庫、縮圖、人臉縮圖、AI 分析結果、下載的模型）。
"""

from __future__ import annotations

import os
import shutil
import sqlite3
from pathlib import Path

from . import db
from .config import Config
from .media import thumb_path


def dir_size(path: Path) -> tuple[int, int]:
    """(位元組, 檔案數)"""
    total = files = 0
    if not path.exists():
        return 0, 0
    for dirpath, _dirs, names in os.walk(path):
        for name in names:
            try:
                total += os.path.getsize(os.path.join(dirpath, name))
                files += 1
            except OSError:
                pass
    return total, files


def _file_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _face_thumb(cfg: Config, face_id: int) -> Path:
    return cfg.thumbs_dir / "faces" / f"{face_id // 1000}" / f"{face_id}.webp"


def _thumb_files(cfg: Config) -> dict[str, Path]:
    """縮圖資料夾裡的照片縮圖：{fingerprint: path}（不含人臉縮圖）。"""
    out: dict[str, Path] = {}
    base = cfg.thumbs_dir
    if not base.exists():
        return out
    for sub in base.iterdir():
        if not sub.is_dir() or sub.name in ("faces", "pets"):
            continue
        for f in sub.iterdir():
            if f.suffix == ".webp":
                out[f.stem] = f
    return out


def _orphan_face_thumbs(conn: sqlite3.Connection, cfg: Config) -> list[Path]:
    face_dir = cfg.thumbs_dir / "faces"
    if not face_dir.exists():
        return []
    used = {r[0] for r in conn.execute("SELECT id FROM faces")}
    out = []
    for sub in face_dir.iterdir():
        if sub.is_dir():
            out.extend(f for f in sub.iterdir() if f.stem.isdigit() and int(f.stem) not in used)
    return out


def _orphan_pet_thumbs(conn: sqlite3.Connection, cfg: Config) -> list[Path]:
    pet_dir = cfg.thumbs_dir / "pets"
    if not pet_dir.exists():
        return []
    try:
        used = {r[0] for r in conn.execute("SELECT id FROM pet_detections")}
    except sqlite3.OperationalError:
        return []
    out = []
    for sub in pet_dir.iterdir():
        if sub.is_dir():
            out.extend(f for f in sub.iterdir() if f.stem.isdigit() and int(f.stem) not in used)
    return out


def _db_slack(conn: sqlite3.Connection, cfg: Config) -> int:
    """資料庫裡已刪除資料留下的空白，加上尚未併回的 WAL 記錄（壓縮後可釋放）。"""
    page_size = conn.execute("PRAGMA page_size").fetchone()[0]
    free_pages = conn.execute("PRAGMA freelist_count").fetchone()[0]
    return page_size * free_pages + _file_size(Path(str(cfg.db_path) + "-wal"))


def reclaimable(conn: sqlite3.Connection, cfg: Config) -> dict:
    """清理前先估算：可以刪掉哪些快取、能釋放多少空間。"""
    used_fps = {r[0] for r in conn.execute("SELECT fingerprint FROM images")}
    thumbs = [p for fp, p in _thumb_files(cfg).items() if fp not in used_fps]
    faces = _orphan_face_thumbs(conn, cfg) + _orphan_pet_thumbs(conn, cfg)
    t_bytes = sum(_file_size(p) for p in thumbs)
    f_bytes = sum(_file_size(p) for p in faces)
    slack = _db_slack(conn, cfg)
    return {
        "thumbs": {"files": len(thumbs), "bytes": t_bytes},
        "face_thumbs": {"files": len(faces), "bytes": f_bytes},
        "database": {"bytes": slack},
        "files": len(thumbs) + len(faces),
        "bytes": t_bytes + f_bytes + slack,
    }


def usage(conn: sqlite3.Connection, cfg: Config, ollama_models: list[dict] | None = None) -> dict:
    db_bytes = sum(_file_size(Path(str(cfg.db_path) + suffix)) for suffix in ("", "-wal", "-shm"))
    thumbs = _thumb_files(cfg)
    face_bytes, face_files = dir_size(cfg.thumbs_dir / "faces")

    roots = []
    for r in db.list_roots(conn):
        rows = conn.execute(
            "SELECT fingerprint, analyzed_at IS NOT NULL AS done FROM images WHERE root_id = ?", (r["id"],)
        ).fetchall()
        thumb_bytes = sum(_file_size(thumbs[row[0]]) for row in rows if row[0] in thumbs)
        faces = conn.execute(
            "SELECT COUNT(*) FROM faces f JOIN images i ON i.id = f.image_id WHERE i.root_id = ?", (r["id"],)
        ).fetchone()[0]
        roots.append({
            "id": r["id"], "name": r["name"], "path": r["path"], "online": Path(r["path"]).is_dir(),
            "items": len(rows), "analyzed": sum(1 for row in rows if row[1]), "faces": faces,
            "thumb_bytes": thumb_bytes,
        })

    models = []
    for m in ollama_models or []:
        roles = [label for key, label in (("vision_model", "照片分析"), ("embed_model", "語意搜尋"), ("text_model", "搜尋翻譯"))
                 if _same(getattr(cfg, key), m["name"])]
        models.append({"kind": "ollama", "name": m["name"], "bytes": m.get("size") or 0, "roles": roles,
                       "detail": m.get("parameter_size") or ""})
    folders = (("face", cfg.home / "models", cfg.face_model, cfg.face_enabled, "人臉辨識"),
               ("clip", cfg.home / "models" / "clip", cfg.clip_model, cfg.clip_enabled, "圖像搜尋"),
               ("pet", cfg.home / "models" / "pets", cfg.pet_model, cfg.pet_enabled, "寵物辨識"))
    for kind, folder, active, enabled, role in folders:
        if not folder.exists():
            continue
        for d in sorted(folder.iterdir()):
            if not d.is_dir() or (kind == "face" and d.name in ("clip", "pets")):
                continue
            size, _ = dir_size(d)
            if size:
                on = d.name == active and enabled
                models.append({"kind": kind, "name": d.name, "bytes": size, "roles": [role] if on else [], "detail": ""})

    return {
        "home": str(cfg.home),
        "database": {"bytes": db_bytes},
        "thumbs": {"bytes": sum(_file_size(p) for p in thumbs.values()), "files": len(thumbs)},
        "face_thumbs": {"bytes": face_bytes, "files": face_files},
        "orphans": reclaimable(conn, cfg),
        "roots": roots,
        "models": models,
    }


def _same(a: str, b: str) -> bool:
    norm = lambda x: x if ":" in x else f"{x}:latest"  # noqa: E731
    return bool(a and b) and norm(a) == norm(b)


def clean_orphans(conn: sqlite3.Connection, cfg: Config) -> dict:
    """刪除已經沒有任何照片使用的縮圖與人臉縮圖，並壓縮資料庫。"""
    used_fps = {r[0] for r in conn.execute("SELECT fingerprint FROM images")}
    freed = files = 0
    for fp, p in _thumb_files(cfg).items():
        if fp not in used_fps:
            freed += _file_size(p)
            p.unlink(missing_ok=True)
            files += 1
    for f in _orphan_face_thumbs(conn, cfg) + _orphan_pet_thumbs(conn, cfg):
        freed += _file_size(f)
        f.unlink(missing_ok=True)
        files += 1
    before = sum(_file_size(Path(str(cfg.db_path) + s)) for s in ("", "-wal"))
    conn.commit()
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    conn.execute("VACUUM")
    after = sum(_file_size(Path(str(cfg.db_path) + s)) for s in ("", "-wal"))
    freed += max(0, before - after)
    return {"freed": freed, "files": files}


def remove_root(conn: sqlite3.Connection, cfg: Config, root_id: int) -> dict:
    """從圖庫移除資料夾，連同它的縮圖、人臉縮圖與分析資料（硬碟上的照片不受影響）。"""
    root = db.get_root(conn, root_id)
    if root is None:
        raise ValueError("找不到資料夾")
    fps = {r[0] for r in conn.execute("SELECT fingerprint FROM images WHERE root_id = ?", (root_id,))}
    other = {r[0] for r in conn.execute("SELECT fingerprint FROM images WHERE root_id != ?", (root_id,))}
    face_ids = [r[0] for r in conn.execute(
        "SELECT f.id FROM faces f JOIN images i ON i.id = f.image_id WHERE i.root_id = ?", (root_id,))]
    pet_ids = [r[0] for r in conn.execute(
        "SELECT d.id FROM pet_detections d JOIN images i ON i.id = d.image_id WHERE i.root_id = ?", (root_id,))]
    count = db.remove_root(conn, root_id)  # 照片紀錄、分析、人臉會一起刪除（資料庫的連鎖刪除）
    # 沒有臉的人物也移除
    conn.execute("DELETE FROM persons WHERE id NOT IN (SELECT DISTINCT person_id FROM faces WHERE person_id IS NOT NULL)")
    conn.execute("DELETE FROM pets WHERE id NOT IN (SELECT DISTINCT pet_id FROM pet_detections WHERE pet_id IS NOT NULL)")
    conn.commit()
    freed = 0
    for fp in fps - other:
        p = thumb_path(cfg.thumbs_dir, fp)
        freed += _file_size(p)
        p.unlink(missing_ok=True)
    for fid in face_ids:
        p = _face_thumb(cfg, fid)
        freed += _file_size(p)
        p.unlink(missing_ok=True)
    from .petid import thumb_path as pet_thumb

    for pid in pet_ids:
        p = pet_thumb(cfg, pid)
        freed += _file_size(p)
        p.unlink(missing_ok=True)
    return {"removed": count, "freed": freed}


def clear_analysis(conn: sqlite3.Connection, root_id: int | None = None) -> int:
    """清除 AI 分析結果（描述、關鍵字、文字、向量），照片會回到「待分析」。"""
    where, args = ("WHERE root_id = ?", [root_id]) if root_id is not None else ("", [])
    ids = [r[0] for r in conn.execute(f"SELECT id FROM images {where}", args)]
    conn.execute(
        f"UPDATE images SET analyzed_at = NULL, model = NULL, description = NULL, tags = NULL, objects = NULL, "
        f"scene = NULL, ocr_text = NULL, error = NULL, embedding = NULL, embed_model = NULL {where}",
        args,
    )
    for image_id in ids:
        db.refresh_search_text(conn, image_id)
    conn.commit()
    return len(ids)


def delete_model_files(cfg: Config, kind: str, name: str) -> int:
    """刪除人臉或圖像搜尋模型的檔案，回傳釋放的位元組。"""
    if "/" in name or "\\" in name or name in ("", ".", ".."):
        raise ValueError("模型名稱不正確")
    folder = {"face": cfg.home / "models" / name, "pet": cfg.home / "models" / "pets" / name}.get(kind, cfg.home / "models" / "clip" / name)
    size, _ = dir_size(folder)
    shutil.rmtree(folder, ignore_errors=True)
    return size
