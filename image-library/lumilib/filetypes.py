"""檔案類型：依副檔名把每個檔案分成照片、RAW、影片、音樂、文件、壓縮檔、套件與其他。

只看檔名，不讀檔案內容，所以掃描很快；之後的階段才會讀文件文字、壓縮檔清單、音樂標籤。
"""

from __future__ import annotations

from .media import PHOTO_EXTENSIONS, RAW_EXTENSIONS, VIDEO_EXTENSIONS

AUDIO_EXTENSIONS = {
    ".mp3", ".flac", ".wav", ".aac", ".m4a", ".aif", ".aiff", ".ogg", ".oga", ".opus", ".wma", ".ape",
    ".alac", ".dsf", ".dff", ".mid", ".midi", ".caf", ".m4b", ".amr",
}
DOCUMENT_EXTENSIONS = {
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".xlsm", ".ppt", ".pptx", ".pps", ".ppsx", ".key", ".pages", ".numbers",
    ".txt", ".md", ".rtf", ".rtfd", ".odt", ".ods", ".odp", ".epub", ".mobi", ".azw", ".azw3", ".csv", ".tsv",
    ".htm", ".html", ".tex", ".hwp", ".wps", ".djvu", ".xps", ".one", ".msg", ".eml",
}
ARCHIVE_EXTENSIONS = {
    ".zip", ".rar", ".7z", ".tar", ".gz", ".tgz", ".bz2", ".tbz", ".xz", ".txz", ".zst", ".lz", ".lzh", ".cab",
    ".dmg", ".iso", ".sparsebundle", ".sparseimage",
}

# 在 Finder 裡看起來是「一個檔案」、其實是資料夾的套件：當成一個項目記錄（大小＝裡面所有檔案加總），
# 不把內部成千上萬個檔案一一列進目錄，也不把裡面的預覽圖當成照片。
PACKAGE_SUFFIXES = (
    ".app", ".photoslibrary", ".photolibrary", ".lrdata", ".lrcat-data", ".cocatalog", ".fcpbundle",
    ".imovielibrary", ".tvlibrary", ".musiclibrary", ".logicx", ".band", ".rtfd", ".pages", ".numbers", ".key",
    ".sparsebundle", ".bundle", ".framework", ".plugin", ".xcodeproj", ".xcworkspace", ".aplibrary", ".migratedphotolibrary",
)

KINDS = ("photo", "raw", "video", "audio", "document", "archive", "package", "other")
LABELS = {
    "photo": "照片", "raw": "RAW", "video": "影片", "audio": "音樂與音訊", "document": "文件",
    "archive": "壓縮檔與映像檔", "package": "App 與資料庫套件", "other": "其他",
}


def ext_of(name: str) -> str:
    """小寫、不含點的副檔名；沒有副檔名回傳空字串。"""
    dot = name.rfind(".")
    return name[dot + 1:].lower() if dot > 0 else ""


def kind_of(name: str) -> str:
    ext = "." + ext_of(name)
    if ext == ".":
        return "other"
    if ext in VIDEO_EXTENSIONS:
        return "video"
    if ext in RAW_EXTENSIONS:
        return "raw"
    if ext in PHOTO_EXTENSIONS:
        return "photo"
    if ext in AUDIO_EXTENSIONS:
        return "audio"
    if ext in DOCUMENT_EXTENSIONS:
        return "document"
    if ext in ARCHIVE_EXTENSIONS:
        return "archive"
    return "other"


def is_package(name: str) -> bool:
    return name.lower().endswith(PACKAGE_SUFFIXES)


def package_kind(name: str) -> str:
    """套件本身的類型：Pages、Keynote 這類文件套件算「文件」，其他算「套件」。"""
    kind = kind_of(name)
    return kind if kind in ("document", "archive") else "package"
