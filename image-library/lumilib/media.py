"""照片、RAW、影片的讀取：中繼資料（exiftool）、縮圖、預覽與分析用畫面。

- exiftool：讀所有格式的 EXIF／XMP／QuickTime 資訊（拍攝時間、相機、鏡頭、曝光、GPS、關鍵字）
  並取出 RAW 檔內嵌的 JPEG 預覽。沒有安裝時，照片退回 Pillow、影片退回 ffprobe。
- ffmpeg：影片縮圖與分析用的關鍵畫面。
"""

from __future__ import annotations

import base64
import io
import json
import os
import secrets
import shutil
import subprocess
import threading
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageOps

try:  # HEIC / HEIF
    from pillow_heif import register_heif_opener

    register_heif_opener()
    HEIF_SUPPORT = True
except ImportError:  # pragma: no cover
    HEIF_SUPPORT = False

Image.MAX_IMAGE_PIXELS = 400_000_000

PHOTO_EXTENSIONS = {
    ".jpg", ".jpeg", ".jpe", ".png", ".webp", ".gif", ".bmp",
    ".tif", ".tiff", ".heic", ".heif", ".avif",
}
RAW_EXTENSIONS = {
    ".cr2", ".cr3", ".crw", ".nef", ".nrw", ".arw", ".srf", ".sr2", ".raf", ".orf",
    ".rw2", ".dng", ".pef", ".srw", ".x3f", ".3fr", ".iiq", ".rwl", ".erf", ".mos", ".kdc", ".mrw",
}
VIDEO_EXTENSIONS = {
    ".mp4", ".m4v", ".mov", ".avi", ".mkv", ".mts", ".m2ts", ".3gp", ".webm",
    ".wmv", ".mpg", ".mpeg", ".insv", ".lrv",
}
MEDIA_EXTENSIONS = PHOTO_EXTENSIONS | RAW_EXTENSIONS | VIDEO_EXTENSIONS
SIDECAR_EXTENSIONS = (".xmp", ".XMP", ".aae", ".AAE")

# 瀏覽器可以直接播放的影片（Safari 也支援 HEVC）
BROWSER_VIDEO = {".mp4", ".m4v", ".mov", ".webm"}


class MediaError(Exception):
    pass


def media_kind(path: str | Path) -> tuple[str, bool] | None:
    """回傳 (media_type, is_raw)，不支援的檔案回傳 None。"""
    ext = Path(path).suffix.lower()
    if ext in VIDEO_EXTENSIONS:
        return "video", False
    if ext in RAW_EXTENSIONS:
        return "photo", True
    if ext in PHOTO_EXTENSIONS:
        return "photo", False
    return None


def _bundled_tool_dirs() -> list[Path]:
    """Mac App 內建的工具：LUMILIB_TOOLS 或打包後執行檔旁的 tools/。"""
    dirs = []
    env = os.environ.get("LUMILIB_TOOLS")
    if env:
        dirs.append(Path(env))
    import sys

    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        dirs += [base / "tools", Path(sys.executable).parent / "tools"]
    return dirs


def which(name: str) -> str | None:
    for d in _bundled_tool_dirs():
        for candidate in (d / name, d / name / name):
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return str(candidate)
    found = shutil.which(name)
    if found:
        return found
    if name == "ffmpeg":
        try:  # pip 套件 imageio-ffmpeg 內附的 ffmpeg
            import imageio_ffmpeg

            return imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            pass
    for prefix in ("/opt/homebrew/bin", "/usr/local/bin"):  # macOS 從 Finder 啟動時 PATH 可能不含 Homebrew
        candidate = Path(prefix) / name
        if candidate.exists():
            return str(candidate)
    return None


# ---- exiftool ----------------------------------------------------------------

EXIF_TAGS = [
    "-Make", "-Model", "-LensModel", "-Lens", "-FNumber", "-ExposureTime", "-ISO",
    "-FocalLength", "-FocalLengthIn35mmFormat", "-DateTimeOriginal", "-SubSecDateTimeOriginal",
    "-CreateDate", "-CreationDate", "-MediaCreateDate", "-OffsetTimeOriginal", "-ModifyDate",
    "-GPSLatitude", "-GPSLongitude", "-GPSAltitude", "-ImageWidth", "-ImageHeight",
    "-ExifImageWidth", "-ExifImageHeight", "-Orientation", "-Rotation", "-Duration", "-Rating",
    "-Subject", "-Keywords", "-Title", "-Description", "-ImageDescription", "-Caption-Abstract",
    "-Artist", "-Creator", "-Copyright", "-Software", "-VideoFrameRate", "-CompressorID", "-MIMEType",
]


class ExifTool:
    """常駐的 exiftool 程序（-stay_open），大量讀檔時比每張啟動一次快很多。"""

    def __init__(self, executable: str | None = None):
        self.executable = executable or which("exiftool")
        self.proc: subprocess.Popen | None = None
        self.lock = threading.Lock()

    @property
    def available(self) -> bool:
        return bool(self.executable)

    def _start(self) -> None:
        if self.proc and self.proc.poll() is None:
            return
        if not self.executable:
            raise MediaError("找不到 exiftool，請執行：brew install exiftool")
        self.proc = subprocess.Popen(
            [self.executable, "-stay_open", "True", "-@", "-", "-common_args", "-charset", "filename=utf8",
             "-api", "QuickTimeUTC=1", "-api", "LargeFileSupport=1", "-q", "-q"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        )

    def execute(self, *args: str) -> bytes:
        with self.lock:
            self._start()
            token = str(secrets.randbelow(10**9))
            sentinel = f"{{ready{token}}}".encode()
            payload = "\n".join(args) + f"\n-execute{token}\n"
            assert self.proc and self.proc.stdin and self.proc.stdout
            try:
                self.proc.stdin.write(payload.encode("utf-8"))
                self.proc.stdin.flush()
                fd = self.proc.stdout.fileno()
                buf = bytearray()
                while True:
                    chunk = os.read(fd, 65536)
                    if not chunk:
                        raise MediaError("exiftool 意外結束")
                    buf += chunk
                    idx = buf.rfind(sentinel)
                    if idx != -1 and buf[idx + len(sentinel):].strip() == b"":
                        return bytes(buf[:idx])
            except (BrokenPipeError, OSError) as exc:
                self.close()
                raise MediaError(f"exiftool 錯誤：{exc}") from exc

    def read(self, paths: list[Path]) -> dict[str, dict]:
        if not paths:
            return {}
        out = self.execute("-j", "-n", *EXIF_TAGS, *[str(p) for p in paths])
        try:
            items = json.loads(out.decode("utf-8", "replace") or "[]")
        except ValueError:
            items = []
        return {item.get("SourceFile", ""): item for item in items}

    def preview(self, path: Path) -> bytes | None:
        """RAW 內嵌的 JPEG，依大到小嘗試。"""
        for tag in ("-JpgFromRaw", "-PreviewImage", "-OtherImage", "-ThumbnailImage"):
            data = self.execute("-b", tag, str(path))
            if len(data) > 1000 and data[:2] == b"\xff\xd8":
                return data
        return None

    def close(self) -> None:
        if self.proc and self.proc.poll() is None:
            try:
                assert self.proc.stdin
                self.proc.stdin.write(b"-stay_open\nFalse\n")
                self.proc.stdin.flush()
                self.proc.wait(timeout=3)
            except Exception:
                self.proc.kill()
        if self.proc:
            for stream in (self.proc.stdin, self.proc.stdout):
                try:
                    if stream:
                        stream.close()
                except OSError:
                    pass
        self.proc = None


_exiftool: ExifTool | None = None
_exiftool_lock = threading.Lock()


def exiftool() -> ExifTool:
    global _exiftool
    with _exiftool_lock:
        if _exiftool is None:
            _exiftool = ExifTool()
        return _exiftool


def tool_status() -> dict:
    return {
        "exiftool": which("exiftool") is not None,
        "ffmpeg": which("ffmpeg") is not None,
        "ffprobe": which("ffprobe") is not None,
        "heif": HEIF_SUPPORT,
    }


# ---- 中繼資料正規化 ---------------------------------------------------------------

def _num(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        try:  # "1/250"
            a, b = str(value).split("/")
            return float(a) / float(b)
        except (ValueError, ZeroDivisionError):
            return None


def _str(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, list):
        value = ", ".join(str(v) for v in value)
    value = str(value).replace("\x00", "").strip()
    return value or None


def parse_datetime(value) -> tuple[str | None, str | None]:
    """'2023:07:14 18:30:00.12+08:00' → ('2023-07-14T18:30:00', '+08:00')"""
    value = _str(value)
    if not value or value.startswith("0000"):
        return None, None
    main, offset = value, None
    for sign in ("+", "-"):
        pos = value.rfind(sign)
        if pos > 10:
            main, offset = value[:pos], value[pos:]
            break
    if main.endswith("Z"):
        main, offset = main[:-1], "+00:00"
    main = main.split(".")[0].strip()
    for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y:%m:%d %H:%M", "%Y:%m:%d"):
        try:
            dt = datetime.strptime(main, fmt)
        except ValueError:
            continue
        if dt.year < 1900:
            return None, None
        return dt.isoformat(), offset
    return None, None


def _keywords(raw: dict) -> list[str]:
    out: list[str] = []
    for key in ("Subject", "Keywords"):
        value = raw.get(key)
        if value is None:
            continue
        items = value if isinstance(value, list) else str(value).split(",")
        for item in items:
            text = str(item).strip()
            if text and text not in out:
                out.append(text)
    return out


def normalize_exiftool(raw: dict, media_type: str) -> dict:
    meta: dict = {}
    if media_type == "video":
        candidates = ("CreationDate", "DateTimeOriginal", "CreateDate", "MediaCreateDate")
    else:
        candidates = ("SubSecDateTimeOriginal", "DateTimeOriginal", "CreateDate", "CreationDate")
    for key in candidates:
        taken, offset = parse_datetime(raw.get(key))
        if taken:
            meta["taken_at"] = taken
            meta["tz_offset"] = offset or _str(raw.get("OffsetTimeOriginal"))
            break

    width = _num(raw.get("ExifImageWidth")) or _num(raw.get("ImageWidth"))
    height = _num(raw.get("ExifImageHeight")) or _num(raw.get("ImageHeight"))
    orientation = int(_num(raw.get("Orientation")) or 1)
    rotation = int(_num(raw.get("Rotation")) or 0)
    if width and height:
        if orientation in (5, 6, 7, 8) or rotation in (90, 270):
            width, height = height, width
        meta["width"], meta["height"] = int(width), int(height)
    meta["orientation"] = orientation

    make, model = _str(raw.get("Make")), _str(raw.get("Model"))
    if model:
        meta["camera"] = model if make and model.lower().startswith(make.lower().split()[0]) else " ".join(
            x for x in (make, model) if x
        )
    elif make:
        meta["camera"] = make
    lens = _str(raw.get("LensModel")) or _str(raw.get("Lens"))
    if lens and lens not in ("----", "0"):
        meta["lens"] = lens

    meta["aperture"] = _num(raw.get("FNumber"))
    meta["exposure_time"] = _num(raw.get("ExposureTime"))
    iso = _num(raw.get("ISO"))
    meta["iso"] = int(iso) if iso else None
    meta["focal_length"] = _num(raw.get("FocalLength"))
    meta["focal_35"] = _num(raw.get("FocalLengthIn35mmFormat"))

    lat, lon = _num(raw.get("GPSLatitude")), _num(raw.get("GPSLongitude"))
    if lat is not None and lon is not None and not (lat == 0 and lon == 0) and abs(lat) <= 90 and abs(lon) <= 180:
        meta["lat"], meta["lon"] = round(lat, 6), round(lon, 6)
        meta["altitude"] = _num(raw.get("GPSAltitude"))

    if media_type == "video":
        meta["duration"] = _num(raw.get("Duration"))
        meta["fps"] = _num(raw.get("VideoFrameRate"))
        meta["codec"] = _str(raw.get("CompressorID"))
    rating = _num(raw.get("Rating"))
    meta["rating"] = int(rating) if rating is not None else None
    meta["keywords"] = _keywords(raw)
    meta["title"] = _str(raw.get("Title"))
    meta["caption"] = _str(raw.get("Description")) or _str(raw.get("ImageDescription")) or _str(raw.get("Caption-Abstract"))
    meta["artist"] = _str(raw.get("Artist")) or _str(raw.get("Creator"))
    meta["copyright"] = _str(raw.get("Copyright"))
    meta["software"] = _str(raw.get("Software"))
    return {k: v for k, v in meta.items() if v not in (None, "", [])}


def _pillow_metadata(path: Path) -> dict:
    """沒有 exiftool 時的照片中繼資料。"""
    try:
        with Image.open(path) as img:
            meta: dict = {"width": img.width, "height": img.height}
            exif = img.getexif()
            sub = exif.get_ifd(0x8769) if exif else {}
            gps = exif.get_ifd(0x8825) if exif else {}
    except Exception as exc:
        raise MediaError(f"無法讀取圖片：{exc}") from exc
    raw = {
        "Make": exif.get(271), "Model": exif.get(272), "Orientation": exif.get(274),
        "DateTimeOriginal": sub.get(36867) or exif.get(306), "OffsetTimeOriginal": sub.get(36881),
        "LensModel": sub.get(42036), "FNumber": sub.get(33437), "ExposureTime": sub.get(33434),
        "ISO": sub.get(34855), "FocalLength": sub.get(37386), "FocalLengthIn35mmFormat": sub.get(41989),
        "ImageWidth": meta["width"], "ImageHeight": meta["height"], "Artist": exif.get(315),
        "Copyright": exif.get(33432), "Software": exif.get(305), "ImageDescription": exif.get(270),
    }
    if gps.get(2) and gps.get(4):
        def deg(v, ref):
            try:
                d, m, s = (float(x) for x in v)
            except (TypeError, ValueError, ZeroDivisionError):
                return None
            val = d + m / 60 + s / 3600
            return -val if str(ref).upper().startswith(("S", "W")) else val

        raw["GPSLatitude"], raw["GPSLongitude"] = deg(gps.get(2), gps.get(1)), deg(gps.get(4), gps.get(3))
    for key, value in list(raw.items()):
        if hasattr(value, "numerator") and not isinstance(value, int):
            raw[key] = float(value)
        elif isinstance(value, bytes):
            raw[key] = value.decode("utf-8", "ignore")
    return normalize_exiftool(raw, "photo")


def _ffprobe_metadata(path: Path) -> dict:
    exe = which("ffprobe")
    if not exe:
        raise MediaError("找不到 ffprobe，請執行：brew install ffmpeg")
    proc = subprocess.run(
        [exe, "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", str(path)],
        capture_output=True, timeout=60,
    )
    try:
        data = json.loads(proc.stdout or b"{}")
    except ValueError:
        data = {}
    if not data.get("streams"):
        raise MediaError("無法讀取影片")
    video = next((s for s in data["streams"] if s.get("codec_type") == "video"), {})
    tags = {k.lower(): v for k, v in (data.get("format", {}).get("tags") or {}).items()}
    raw = {
        "ImageWidth": video.get("width"), "ImageHeight": video.get("height"),
        "Duration": data.get("format", {}).get("duration"),
        "CreationDate": tags.get("com.apple.quicktime.creationdate") or tags.get("creation_time"),
        "Make": tags.get("com.apple.quicktime.make"), "Model": tags.get("com.apple.quicktime.model"),
        "CompressorID": video.get("codec_name"),
    }
    side = video.get("side_data_list") or []
    rotation = next((abs(int(s.get("rotation", 0))) for s in side if "rotation" in s), 0)
    raw["Rotation"] = rotation
    loc = tags.get("com.apple.quicktime.location.iso6709") or tags.get("location")
    if loc:
        import re

        m = re.match(r"([+-]\d+(?:\.\d+)?)([+-]\d+(?:\.\d+)?)", loc)
        if m:
            raw["GPSLatitude"], raw["GPSLongitude"] = m.group(1), m.group(2)
    return normalize_exiftool(raw, "video")


def read_metadata_batch(paths: list[Path]) -> dict[Path, dict | MediaError]:
    """一次讀一批檔案的中繼資料；個別失敗以 MediaError 表示。"""
    result: dict[Path, dict | MediaError] = {}
    et = exiftool()
    if et.available:
        try:
            raw_map = et.read(paths)
        except MediaError:
            raw_map = {}
        for path in paths:
            kind = media_kind(path)
            raw = raw_map.get(str(path))
            if raw is not None and kind:
                result[path] = normalize_exiftool(raw, kind[0])
    for path in paths:
        if path in result:
            continue
        kind = media_kind(path)
        try:
            if kind and kind[0] == "video":
                result[path] = _ffprobe_metadata(path)
            elif kind and kind[1]:
                raise MediaError("RAW 檔需要 exiftool：brew install exiftool")
            else:
                result[path] = _pillow_metadata(path)
        except MediaError as exc:
            result[path] = exc
    return result


# ---- 影像 ---------------------------------------------------------------------

_ORIENT_OPS = {
    2: [Image.Transpose.FLIP_LEFT_RIGHT], 3: [Image.Transpose.ROTATE_180],
    4: [Image.Transpose.FLIP_TOP_BOTTOM], 5: [Image.Transpose.TRANSPOSE],
    6: [Image.Transpose.ROTATE_270], 7: [Image.Transpose.TRANSVERSE], 8: [Image.Transpose.ROTATE_90],
}


def _rgb(img: Image.Image) -> Image.Image:
    if getattr(img, "n_frames", 1) > 1:
        img.seek(0)
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        rgba = img.convert("RGBA")
        bg = Image.new("RGB", rgba.size, (255, 255, 255))
        bg.paste(rgba, mask=rgba.split()[-1])
        return bg
    return img.convert("RGB")


def video_frame(path: Path, at: float, max_side: int) -> Image.Image:
    exe = which("ffmpeg")
    if not exe:
        raise MediaError("影片需要 ffmpeg：brew install ffmpeg")
    vf = f"scale=w={max_side}:h={max_side}:force_original_aspect_ratio=decrease"
    for seek in (at, 0.0):
        proc = subprocess.run(
            [exe, "-v", "error", "-ss", f"{max(seek, 0):.2f}", "-i", str(path), "-frames:v", "1",
             "-vf", vf, "-f", "image2pipe", "-vcodec", "mjpeg", "-q:v", "3", "-"],
            capture_output=True, timeout=120,
        )
        if proc.stdout[:2] == b"\xff\xd8":
            return Image.open(io.BytesIO(proc.stdout)).convert("RGB")
    raise MediaError("無法擷取影片畫面")


def load_image(path: Path, media_type: str, is_raw: bool, max_side: int,
               duration: float | None = None, orientation: int | None = None) -> Image.Image:
    """回傳已轉正的 RGB 影像，長邊約 max_side（可能更大，由呼叫者再縮）。"""
    path = Path(path)
    try:
        if media_type == "video":
            at = min(1.0, (duration or 0) * 0.1)
            return video_frame(path, at, max_side)
        if is_raw:
            et = exiftool()
            data = et.preview(path) if et.available else None
            if not data:
                raise MediaError("無法取得 RAW 預覽（需要 exiftool）")
            img = Image.open(io.BytesIO(data))
            img.draft("RGB", (max_side, max_side))
            img = _rgb(img)
            embedded = Image.open(io.BytesIO(data)).getexif().get(274)
            if not embedded or embedded == 1:  # 內嵌預覽沒有方向資訊時套用 RAW 的方向
                for op in _ORIENT_OPS.get(orientation or 1, []):
                    img = img.transpose(op)
                return img
            return _rgb(ImageOps.exif_transpose(Image.open(io.BytesIO(data))))
        if path.suffix.lower() in {".heic", ".heif"} and not HEIF_SUPPORT:
            raise MediaError("需要 pillow-heif 才能讀取 HEIC")
        img = Image.open(path)
        if img.format == "JPEG":
            img.draft("RGB", (max_side, max_side))
        img = ImageOps.exif_transpose(img)
        return _rgb(img)
    except MediaError:
        raise
    except Exception as exc:
        raise MediaError(f"無法讀取：{exc}") from exc


def encode(img: Image.Image, max_side: int | tuple[int, int], fmt: str = "JPEG", quality: int = 85) -> bytes:
    img = img.copy()
    box = max_side if isinstance(max_side, tuple) else (max_side, max_side)
    img.thumbnail(box, Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    if fmt == "WEBP":
        img.save(buf, "WEBP", quality=quality, method=4)
    else:
        img.save(buf, "JPEG", quality=quality, optimize=True, progressive=True)
    return buf.getvalue()


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def thumb_path(thumbs_dir: Path, fingerprint: str) -> Path:
    return thumbs_dir / fingerprint[:2] / f"{fingerprint}.webp"


def write_thumbnail(img: Image.Image, thumbs_dir: Path, fingerprint: str, height: int) -> Path:
    target = thumb_path(thumbs_dir, fingerprint)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + ".tmp")
    tmp.write_bytes(encode(img, (height * 3, height), "WEBP", 74))
    tmp.replace(target)
    return target


def analysis_images(path: Path, media_type: str, is_raw: bool, max_side: int,
                    duration: float | None, orientation: int | None, frames: int = 4) -> list[str]:
    """送進模型的圖片（base64 JPEG）。影片取多個關鍵畫面。"""
    if media_type == "video":
        dur = duration or 0
        points = [dur * f for f in (0.08, 0.35, 0.62, 0.9)][:frames] if dur > 2 else [0.0]
        images = []
        for t in points:
            try:
                images.append(b64(encode(video_frame(path, t, max_side), max_side)))
            except MediaError:
                continue
        if not images:
            raise MediaError("無法擷取影片畫面")
        return images
    img = load_image(path, media_type, is_raw, max_side * 2, duration, orientation)
    return [b64(encode(img, max_side))]
