"""動到硬碟檔案的操作：移到垃圾桶（使用者確認後）、在 Finder 顯示。

- 刪除一律「移到垃圾桶」（macOS 的垃圾桶，外接硬碟則是該硬碟的垃圾桶），可以還原。
  之後會由「待刪除清單」取代。
- 刪除會一併處理同名的附屬檔（Lightroom .xmp、iPhone .aae），避免留下孤立的編輯紀錄。
"""

from __future__ import annotations

import sqlite3
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from . import db
from .media import RAW_EXTENSIONS, SIDECAR_EXTENSIONS


@dataclass
class OpResult:
    done: list[int] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _has_sibling_raw(path: Path) -> bool:
    """RAW+JPEG 同名雙檔時，IMG_1.xmp 屬於 RAW，搬 JPEG 不能把它帶走。"""
    if path.suffix.lower() in RAW_EXTENSIONS:
        return False
    try:
        return any(
            p.stem == path.stem and p.suffix.lower() in RAW_EXTENSIONS for p in path.parent.iterdir() if p != path
        )
    except OSError:
        return False


def sidecars(path: Path) -> list[Path]:
    """同名附屬檔。直接比對資料夾中實際存在的檔名（不分大小寫），
    避免 macOS 不分大小寫的磁碟把 IMG_1.xmp 與 IMG_1.XMP 算成兩個檔案。"""
    wanted = {(path.name + ext).lower() for ext in SIDECAR_EXTENSIONS}
    if not _has_sibling_raw(path):
        wanted |= {(path.stem + ext).lower() for ext in SIDECAR_EXTENSIONS}
    else:
        wanted |= {(path.stem + ".aae").lower()}
    try:
        entries = list(path.parent.iterdir())
    except OSError:
        return []
    found, seen = [], set()
    for entry in sorted(entries):
        if entry.name.lower() in wanted and entry.name.lower() != path.name.lower() and entry.is_file():
            key = entry.name.lower()
            if key not in seen:
                seen.add(key)
                found.append(entry)
    return found


def _send_to_trash(path: Path) -> None:
    try:
        from send2trash import send2trash
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("需要安裝 send2trash：pip install send2trash") from exc
    send2trash(str(path))


def trash_images(conn: sqlite3.Connection, image_ids: list[int], trash=_send_to_trash) -> OpResult:
    result = OpResult()
    for image_id in image_ids:
        image = db.get_image(conn, int(image_id))
        if image is None:
            continue
        path = db.absolute_path(conn, image)
        try:
            if path.exists():
                for extra in sidecars(path):
                    trash(extra)
                trash(path)
            elif image["status"] == "ok":
                raise FileNotFoundError("找不到檔案（硬碟可能未連接）")
        except Exception as exc:
            result.errors.append(f"{image['rel_path']}: {exc}")
            continue
        conn.execute("DELETE FROM images WHERE id = ?", (image["id"],))
        result.done.append(image["id"])
    conn.commit()
    return result


def safe_folder(root_path: Path, folder: str) -> Path:
    """把使用者輸入的相對資料夾轉成實際路徑，並確認仍在根目錄內。"""
    parts = [p for p in str(folder or "").replace("\\", "/").split("/") if p not in ("", ".")]
    if any(p == ".." or p.startswith("~") for p in parts):
        raise ValueError("資料夾名稱不合法")
    target = root_path.joinpath(*parts).resolve() if parts else root_path.resolve()
    if target != root_path.resolve() and root_path.resolve() not in target.parents:
        raise ValueError("目的地必須在圖庫資料夾內")
    return target


def reveal(path: Path, select: bool = True) -> None:
    if sys.platform == "darwin":
        subprocess.Popen(["open", "-R", str(path)] if select else ["open", str(path)])
    elif sys.platform.startswith("win"):
        subprocess.Popen(["explorer", f"/select,{path}"] if select else ["explorer", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path.parent if select else path)])


def pick_folder() -> str | None:
    """在 Mac 上跳出「選擇資料夾」視窗（只在本機使用）。"""
    if sys.platform != "darwin":
        return None
    proc = subprocess.run(
        ["osascript", "-e", 'POSIX path of (choose folder with prompt "選擇要加入圖庫的資料夾")'],
        capture_output=True, text=True, timeout=600,
    )
    path = proc.stdout.strip()
    return path.rstrip("/") or "/" if path else None
