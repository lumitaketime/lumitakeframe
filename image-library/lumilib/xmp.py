"""與 Lightroom 同步：星等、顏色標籤、旗標（拒絕）與關鍵字。

- RAW：寫入同名 .xmp 附屬檔（沒有就建立），保留 Lightroom 的修圖設定。
- JPEG／HEIC／TIFF／DNG：預設只存在圖庫裡；開啟「寫入檔案」後改寫檔案內嵌的 XMP
  （Lightroom 不讀這些格式的附屬檔）。
- 掃描時讀取附屬檔；Lightroom 改了 .xmp，下次掃描就會更新（即使 RAW 本身沒變）。

注意：Lightroom Classic 預設把修改存在目錄檔，要勾選「自動將變更寫入 XMP」才會更新 .xmp。
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from . import db
from .config import Config
from .media import RAW_EXTENSIONS, MediaError, exiftool, thumb_path

# 顏色標籤：標準名稱 → 各語系 Lightroom 可能寫入的文字
LABELS = {
    "red": ["Red", "紅色", "红色", "レッド", "Rot", "Rouge", "Rojo", "Rosso"],
    "yellow": ["Yellow", "黃色", "黄色", "イエロー", "Gelb", "Jaune", "Amarillo", "Giallo"],
    "green": ["Green", "綠色", "绿色", "グリーン", "Grün", "Vert", "Verde"],
    "blue": ["Blue", "藍色", "蓝色", "ブルー", "Blau", "Bleu", "Azul", "Blu"],
    "purple": ["Purple", "紫色", "パープル", "Lila", "Violet", "Morado", "Viola"],
}
_LOOKUP = {name.lower(): key for key, names in LABELS.items() for name in names}
WRITABLE_EMBEDDED = {".jpg", ".jpeg", ".heic", ".heif", ".tif", ".tiff", ".dng", ".png", ".webp"}


def normalize_label(text) -> str | None:
    if not text:
        return None
    return _LOOKUP.get(str(text).strip().lower())


def label_text(key: str | None, previous: str | None = None) -> str:
    """寫回時沿用原本的文字（例如中文版 Lightroom 寫的「紅色」），新標籤用英文預設值。"""
    if not key:
        return ""
    if previous and normalize_label(previous) == key:
        return previous
    return LABELS[key][0]


def sidecar_path(path: Path) -> Path | None:
    """Lightroom 的附屬檔：IMG_1.xmp（不分大小寫找現有的）。"""
    try:
        names = {p.name.lower(): p for p in path.parent.iterdir()}
    except OSError:
        return None
    for cand in (path.stem + ".xmp", path.name + ".xmp"):
        if cand.lower() in names:
            return names[cand.lower()]
    return None


def read_sidecars(paths: list[Path]) -> dict[Path, dict]:
    """讀取一批 .xmp：{xmp_path: {"rating", "label", "label_text", "keywords"}}"""
    et = exiftool()
    if not paths or not et.available:
        return {}
    try:
        raw = et.read(paths)
    except MediaError:
        return {}
    out = {}
    for p in paths:
        r = raw.get(str(p))
        if r is None:
            continue
        from .media import split_keywords

        kws = split_keywords(r.get("Subject"))
        rating = r.get("Rating")
        out[p] = {
            "rating": int(rating) if isinstance(rating, (int, float)) else None,
            "label": normalize_label(r.get("Label")),
            "label_text": r.get("Label"),
            "keywords": [str(k) for k in kws],
        }
    return out


def apply_sidecar(conn: sqlite3.Connection, image_id: int, info: dict, mtime: float) -> None:
    import json

    conn.execute(
        "UPDATE images SET rating = ?, label = ?, label_text = ?, keywords = ?, xmp_mtime = ? WHERE id = ?",
        (info["rating"], info["label"], info["label_text"],
         json.dumps(info["keywords"], ensure_ascii=False) if info["keywords"] else None, mtime, image_id),
    )
    db.refresh_search_text(conn, image_id)


def _write_args(rating, label_value, keywords) -> list[str]:
    args = []
    if rating is not None:
        args.append(f"-XMP-xmp:Rating={rating}" if rating != 0 else "-XMP-xmp:Rating=")
    if label_value is not None:
        args.append(f"-XMP-xmp:Label={label_value}")
    if keywords is not None:
        args.append("-XMP-dc:Subject=")
        args += [f"-XMP-dc:Subject={k}" for k in keywords]
    return args


def write(conn: sqlite3.Connection, cfg: Config, image_id: int, rating=None, label=None, keywords=None) -> str:
    """更新圖庫，並依設定寫回檔案。回傳寫入位置的說明（'sidecar'、'embedded'、'library'）。"""
    import json

    image = db.get_image(conn, image_id)
    if image is None:
        raise ValueError("找不到這個檔案")
    if label is not None and label != "" and label not in LABELS:
        raise ValueError("未知的顏色標籤")
    if rating is not None and not (-1 <= int(rating) <= 5):
        raise ValueError("星等必須是 -1（拒絕）到 5")

    # 先更新圖庫
    updates, params = [], []
    if rating is not None:
        updates.append("rating = ?")
        params.append(int(rating) if int(rating) != 0 else None)
    new_label_text = None
    if label is not None:
        new_label_text = label_text(label or None, image["label_text"])
        updates += ["label = ?", "label_text = ?"]
        params += [label or None, new_label_text or None]
    if keywords is not None:
        clean = list(dict.fromkeys(k.strip() for k in keywords if k and k.strip()))
        keywords = clean
        updates += ["keywords = ?", "user_tags = ?"]
        params += [json.dumps(clean, ensure_ascii=False) if clean else None, json.dumps(clean, ensure_ascii=False)]
    if updates:
        conn.execute(f"UPDATE images SET {', '.join(updates)} WHERE id = ?", (*params, image_id))
        db.refresh_search_text(conn, image_id)
        conn.commit()

    if not cfg.xmp_sync:
        return "library"
    path = db.absolute_path(conn, image)
    if not path.exists():
        return "library"
    et = exiftool()
    if not et.available:
        return "library"
    args = _write_args(None if rating is None else int(rating), None if label is None else new_label_text or "", keywords)
    if not args:
        return "library"

    ext = path.suffix.lower()
    if ext in RAW_EXTENSIONS and ext != ".dng":
        side = sidecar_path(path)
        if side is not None:
            et.execute("-overwrite_original", *args, str(side))
        else:
            side = path.with_suffix(".xmp")
            et.execute("-o", str(side), *args, str(path))
        if not side.exists():
            raise RuntimeError("無法建立 .xmp 附屬檔（資料夾可能是唯讀）")
        conn.execute("UPDATE images SET xmp_mtime = ? WHERE id = ?", (side.stat().st_mtime, image_id))
        conn.commit()
        return "sidecar"

    if cfg.xmp_embed and ext in WRITABLE_EMBEDDED:
        before = path.stat()
        et.execute("-overwrite_original", "-P", *args, str(path))
        after = path.stat()
        # exiftool 以安靜模式執行，用讀回的值確認是否真的寫入
        check = et.read([path]).get(str(path), {})
        if rating is not None and int(rating) != 0 and check.get("Rating") != int(rating):
            raise RuntimeError("這個檔案無法寫入 XMP（可能是唯讀或格式不支援）")
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns) or after.st_ino != before.st_ino:
            _refresh_identity(conn, cfg, image, path)
        return "embedded"
    return "library"


def _refresh_identity(conn: sqlite3.Connection, cfg: Config, image, path: Path) -> None:
    """檔案內容改了：更新大小、時間與指紋，沿用縮圖與所有分析（避免下次掃描當成新檔案）。"""
    from .scanner import fingerprint

    st = path.stat()
    new_fp = fingerprint(path, st.st_size)
    old_thumb = thumb_path(cfg.thumbs_dir, image["fingerprint"])
    if new_fp != image["fingerprint"] and old_thumb.exists():
        target = thumb_path(cfg.thumbs_dir, new_fp)
        target.parent.mkdir(parents=True, exist_ok=True)
        old_thumb.replace(target)
    conn.execute(
        "UPDATE images SET size = ?, mtime = ?, fingerprint = ? WHERE id = ?",
        (st.st_size, st.st_mtime, new_fp, image["id"]),
    )
    conn.commit()
