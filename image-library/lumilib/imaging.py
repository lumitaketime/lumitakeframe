"""讀圖、EXIF、縮圖，以及送進模型前的縮小與編碼。"""

from __future__ import annotations

import base64
import io
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageOps

try:  # HEIC / HEIF（iPhone 照片）需要 pillow-heif
    from pillow_heif import register_heif_opener

    register_heif_opener()
    HEIF_SUPPORT = True
except ImportError:  # pragma: no cover - depends on optional package
    HEIF_SUPPORT = False

IMAGE_EXTENSIONS = {
    ".jpg", ".jpeg", ".jpe", ".png", ".webp", ".gif", ".bmp",
    ".tif", ".tiff", ".heic", ".heif", ".avif",
}

Image.MAX_IMAGE_PIXELS = 300_000_000  # 允許大型全景照，仍防止惡意超大檔

_EXIF_IFD = 0x8769
_GPS_IFD = 0x8825
_TAG_MAKE = 271
_TAG_MODEL = 272
_TAG_DATETIME = 306
_TAG_ORIENTATION = 274
_TAG_DATETIME_ORIGINAL = 36867
_TAG_LENS_MODEL = 42036


class ImageReadError(Exception):
    pass


def open_image(path: str | Path, draft_side: int | None = None) -> tuple[Image.Image, dict]:
    """開啟圖片並讀取中繼資料。

    draft_side 只用於 JPEG：讓解碼器直接以較小尺寸解碼，產生縮圖快很多。
    中繼資料（原始寬高、EXIF）在縮小解碼前讀取，因此仍是原圖數值。
    """
    path = Path(path)
    if path.suffix.lower() in {".heic", ".heif"} and not HEIF_SUPPORT:
        raise ImageReadError("需要安裝 pillow-heif 才能讀取 HEIC：pip install pillow-heif")
    try:
        img = Image.open(path)
        meta = read_metadata(img)
        if draft_side and img.format == "JPEG":
            img.draft("RGB", (draft_side, draft_side))
        img.load()
        return img, meta
    except Exception as exc:  # Pillow 會丟出各種例外
        raise ImageReadError(f"無法讀取圖片：{exc}") from exc


def _clean_str(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        value = value.decode("utf-8", "ignore")
    value = str(value).replace("\x00", "").strip()
    return value or None


def _parse_exif_datetime(value) -> str | None:
    value = _clean_str(value)
    if not value:
        return None
    for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y:%m:%d %H:%M"):
        try:
            return datetime.strptime(value[:19], fmt).isoformat()
        except ValueError:
            continue
    return None


def _gps_to_deg(values, ref) -> float | None:
    try:
        d, m, s = (float(x) for x in values)
    except (TypeError, ValueError, ZeroDivisionError):
        return None
    deg = d + m / 60 + s / 3600
    ref = _clean_str(ref) or ""
    if ref.upper() in {"S", "W"}:
        deg = -deg
    return round(deg, 6)


def read_metadata(img: Image.Image) -> dict:
    """回傳寬高（已依方向轉正）、拍攝時間、相機、鏡頭與 GPS。"""
    meta: dict = {"width": img.width, "height": img.height}
    try:
        exif = img.getexif()
    except Exception:
        return meta
    if not exif:
        return meta

    if exif.get(_TAG_ORIENTATION) in (5, 6, 7, 8):
        meta["width"], meta["height"] = img.height, img.width

    sub = {}
    try:
        sub = exif.get_ifd(_EXIF_IFD) or {}
    except Exception:
        pass

    taken = _parse_exif_datetime(sub.get(_TAG_DATETIME_ORIGINAL)) or _parse_exif_datetime(exif.get(_TAG_DATETIME))
    if taken:
        meta["taken_at"] = taken

    make = _clean_str(exif.get(_TAG_MAKE))
    model = _clean_str(exif.get(_TAG_MODEL))
    if model:
        camera = model if make and model.lower().startswith(make.lower().split()[0]) else " ".join(x for x in (make, model) if x)
        meta["camera"] = camera
    elif make:
        meta["camera"] = make

    lens = _clean_str(sub.get(_TAG_LENS_MODEL))
    if lens:
        meta["lens"] = lens

    try:
        gps = exif.get_ifd(_GPS_IFD) or {}
    except Exception:
        gps = {}
    if gps.get(2) and gps.get(4):
        lat = _gps_to_deg(gps.get(2), gps.get(1))
        lon = _gps_to_deg(gps.get(4), gps.get(3))
        if lat is not None and lon is not None and not (lat == 0 and lon == 0):
            meta["lat"], meta["lon"] = lat, lon
    return meta


def _to_rgb(img: Image.Image) -> Image.Image:
    img = ImageOps.exif_transpose(img)
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        rgba = img.convert("RGBA")
        bg = Image.new("RGB", rgba.size, (255, 255, 255))
        bg.paste(rgba, mask=rgba.split()[-1])
        return bg
    return img.convert("RGB")


def make_jpeg(img: Image.Image, max_side: int, quality: int = 85) -> bytes:
    """轉正、轉 RGB、縮小長邊，回傳 JPEG 位元組。"""
    if getattr(img, "n_frames", 1) > 1:
        img.seek(0)
    rgb = _to_rgb(img)
    rgb.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    rgb.save(buf, "JPEG", quality=quality, optimize=True)
    return buf.getvalue()


def encode_for_model(img: Image.Image, max_side: int) -> str:
    return base64.b64encode(make_jpeg(img, max_side)).decode("ascii")


def thumb_path(thumbs_dir: Path, fingerprint: str) -> Path:
    return thumbs_dir / fingerprint[:2] / f"{fingerprint}.jpg"


def ensure_thumbnail(img: Image.Image, thumbs_dir: Path, fingerprint: str, size: int) -> Path:
    target = thumb_path(thumbs_dir, fingerprint)
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(".tmp")
        tmp.write_bytes(make_jpeg(img, size, quality=80))
        tmp.replace(target)
    return target
