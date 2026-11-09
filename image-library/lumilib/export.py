"""批次匯出交件：縮成指定長邊的 JPEG，可加文字浮水印、移除 GPS、依規則重新命名。

- 原始照片不會被修改，輸出到另一個資料夾。
- RAW 檔預設直接複製原始檔（交 RAW 就是要給原檔），有同名的 .xmp 附屬檔就一起附上，只依規則改檔名；
  也可以選擇轉成 JPEG（使用相機內嵌的預覽圖，部分機型尺寸較小）。
- 保留拍攝資訊（相機、鏡頭、時間）與色彩描述檔；方向已經轉正，所以寫入「方向＝正常」。
"""

from __future__ import annotations

import re
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Callable

from PIL import Image, ImageDraw, ImageFont, ImageOps

from . import db
from .config import Config
from .media import MediaError, exiftool, load_image

GPS_IFD = 0x8825
ORIENTATION = 0x0112

FONT_CANDIDATES = [
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/Library/Fonts/Arial Unicode.ttf",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "C:/Windows/Fonts/msjh.ttc",
]


def default_dest() -> Path:
    return Path.home() / "Pictures" / "Lumitake 匯出" / datetime.now().strftime("%Y-%m-%d %H%M")


def _font(size: int):
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    try:
        return ImageFont.load_default(size)
    except TypeError:  # 舊版 Pillow
        return ImageFont.load_default()


def watermark(img: Image.Image, text: str, position: str = "br", size_pct: float = 3.0, opacity: int = 70) -> Image.Image:
    """在照片上加文字浮水印。size_pct：字高佔短邊的百分比；opacity：0–100。"""
    if not text.strip():
        return img
    base = img.convert("RGBA")
    short = min(base.size)
    font = _font(max(12, int(short * size_pct / 100)))
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    box = draw.textbbox((0, 0), text, font=font)
    tw, th = box[2] - box[0], box[3] - box[1]
    margin = int(short * 0.03)
    w, h = base.size
    x = {"bl": margin, "tl": margin, "br": w - tw - margin, "tr": w - tw - margin, "center": (w - tw) // 2}.get(position, w - tw - margin)
    y = {"tl": margin, "tr": margin, "bl": h - th - margin, "br": h - th - margin, "center": (h - th) // 2}.get(position, h - th - margin)
    alpha = int(255 * max(0, min(100, opacity)) / 100)
    shadow = max(1, int(short * 0.002))
    draw.text((x - box[0] + shadow, y - box[1] + shadow), text, font=font, fill=(0, 0, 0, alpha // 2))
    draw.text((x - box[0], y - box[1]), text, font=font, fill=(255, 255, 255, alpha))
    return Image.alpha_composite(base, layer).convert("RGB")


def _clean_name(text: str) -> str:
    text = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", text).strip().strip(".")
    return text[:180] or "photo"


def output_name(pattern: str, image, seq: int, total: int) -> str:
    """命名規則：{name} 原檔名、{date} 拍攝日期、{time} 時間、{seq} 序號、{camera} 相機、{folder} 資料夾名稱。"""
    rel = image["rel_path"]
    stem = Path(rel).stem
    taken = (image["taken_at"] or image["sort_at"] or "")
    date = taken[:10].replace("-", "") if taken else "nodate"
    time = taken[11:19].replace(":", "") if len(taken) >= 19 else ""
    width = max(3, len(str(total)))
    values = {
        "name": stem, "date": date, "time": time, "seq": str(seq).zfill(width),
        "camera": (image["camera"] or "").replace(" ", "-"), "folder": Path(rel).parent.name,
    }
    out = re.sub(r"\{(\w+)\}", lambda m: values.get(m.group(1), m.group(0)), pattern or "{name}")
    return _clean_name(out)


def _exif_bytes(path: Path, strip_gps: bool, keep_exif: bool) -> tuple[bytes | None, bytes | None]:
    """原檔的 EXIF（方向改成正常、可移除 GPS）與色彩描述檔。"""
    try:
        with Image.open(path) as src:
            icc = src.info.get("icc_profile")
            if not keep_exif:
                return None, icc
            exif = src.getexif()
            if not exif:
                return None, icc
            exif[ORIENTATION] = 1
            if strip_gps and GPS_IFD in exif:
                del exif[GPS_IFD]
            return exif.tobytes(), icc
    except Exception:  # noqa: BLE001  RAW 或讀不到時就不帶 EXIF
        return None, None


def _copy_raw(src: Path, out: Path, strip_gps: bool) -> None:
    """複製原始 RAW（保留時間），有同名的 .xmp 附屬檔就一起複製並改成相同檔名。"""
    import shutil

    from .media import sidecar_path

    shutil.copy2(src, out)
    side = sidecar_path(src)
    outs = [out]
    if side is not None and side.exists():
        target = out.with_suffix(".xmp")
        shutil.copy2(side, target)
        outs.append(target)
    if strip_gps:
        et = exiftool()
        if et.available:
            for p in outs:
                try:
                    et.execute("-overwrite_original", "-P", "-gps:all=", str(p))
                except Exception:  # noqa: BLE001  移除失敗時保留原樣
                    pass


def _copy_raw_tags(src: Path, out: Path, strip_gps: bool) -> None:
    """RAW 的拍攝資訊用 exiftool 複製到輸出的 JPEG（方向已轉正）。"""
    et = exiftool()
    if not et.available:
        return
    args = ["-overwrite_original", "-TagsFromFile", str(src), "-exif:all", "-xmp:all", "-iptc:all", "-n", "-Orientation=1"]
    if strip_gps:
        args.append("-gps:all=")
    try:
        et.execute(*args, str(out))
    except Exception:  # noqa: BLE001  複製失敗只少了拍攝資訊
        pass


def export_images(conn: sqlite3.Connection, cfg: Config, ids: list[int], opts: dict,
                  progress: Callable[[int, int, str], None] | None = None,
                  stop: threading.Event | None = None) -> dict:
    long_side = int(opts.get("long_side") or 0)
    quality = max(50, min(100, int(opts.get("quality") or 90)))
    strip_gps = bool(opts.get("strip_gps", True))
    keep_exif = bool(opts.get("keep_exif", True))
    wm = opts.get("watermark") or {}
    pattern = str(opts.get("rename") or "{name}")
    dest = Path(opts.get("dest") or default_dest()).expanduser()
    dest.mkdir(parents=True, exist_ok=True)

    raw_mode = str(opts.get("raw_mode") or "original")
    rows = [db.get_image(conn, int(i)) for i in ids]
    rows = [r for r in rows if r is not None]
    used: set[str] = {p.name.lower() for p in dest.iterdir()} if dest.exists() else set()
    done, skipped, small, raw_copied = 0, [], 0, 0
    for seq, image in enumerate(rows, 1):
        if stop is not None and stop.is_set():
            break
        name = image["rel_path"].rsplit("/", 1)[-1]
        if image["media_type"] != "photo":
            skipped.append(f"{name}（影片不匯出）")
            continue
        path = db.absolute_path(conn, image)
        if image["is_raw"] and raw_mode == "original":
            if not path.exists():
                skipped.append(f"{name}（檔案不存在或硬碟未連接）")
                continue
            base = output_name(pattern, image, seq, len(rows))
            ext = path.suffix
            final, n = f"{base}{ext}", 2
            while final.lower() in used:
                final, n = f"{base}-{n}{ext}", n + 1
            used.add(final.lower())
            _copy_raw(path, dest / final, strip_gps)
            raw_copied += 1
            done += 1
            if progress:
                progress(seq, len(rows), final)
            continue
        try:
            img = load_image(path, "photo", bool(image["is_raw"]), max(long_side, 8000) if long_side else 20000,
                             None, image["orientation"])
        except (MediaError, OSError) as exc:
            skipped.append(f"{name}（{exc}）")
            continue
        if long_side and max(img.size) > long_side:
            ratio = long_side / max(img.size)
            img = img.resize((max(1, round(img.width * ratio)), max(1, round(img.height * ratio))), Image.LANCZOS)
        elif long_side and max(img.size) < long_side:
            small += 1
        if wm.get("enabled") and wm.get("text"):
            img = watermark(img, str(wm["text"]), str(wm.get("position") or "br"),
                            float(wm.get("size") or 3), int(wm.get("opacity") or 70))
        exif, icc = (None, None) if image["is_raw"] else _exif_bytes(path, strip_gps, keep_exif)
        base = output_name(pattern, image, seq, len(rows))
        final, n = f"{base}.jpg", 2
        while final.lower() in used:
            final, n = f"{base}-{n}.jpg", n + 1
        used.add(final.lower())
        save = {"quality": quality, "optimize": True, "progressive": True}
        if exif:
            save["exif"] = exif
        if icc:
            save["icc_profile"] = icc
        img.convert("RGB").save(dest / final, "JPEG", **save)
        if image["is_raw"] and keep_exif:
            _copy_raw_tags(path, dest / final, strip_gps)
        done += 1
        if progress:
            progress(seq, len(rows), final)
    return {"exported": done, "skipped": skipped, "smaller": small, "raw_copied": raw_copied, "dest": str(dest)}
