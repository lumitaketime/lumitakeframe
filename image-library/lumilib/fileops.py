"""真正動到硬碟檔案的操作：移到垃圾桶、搬移、建立資料夾、在 Finder 顯示。

- 刪除一律「移到垃圾桶」（macOS 的垃圾桶，外接硬碟則是該硬碟的垃圾桶），可以還原。
- 搬移與刪除會一併處理同名的附屬檔（Lightroom .xmp、iPhone .aae），避免編輯紀錄遺失。
- 目的地只能是已登錄的資料夾內部，不能跳出去。
"""

from __future__ import annotations

import shutil
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
    found = []
    shared_ok = not _has_sibling_raw(path)
    for ext in SIDECAR_EXTENSIONS:
        candidates = [path.with_name(path.name + ext)]
        if shared_ok or ext.lower() == ".aae":
            candidates.append(path.with_suffix(ext))
        for candidate in candidates:
            if candidate.exists() and candidate not in found and candidate != path:
                found.append(candidate)
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


def create_folder(conn: sqlite3.Connection, root_id: int, folder: str) -> str:
    root = db.get_root(conn, root_id)
    if root is None:
        raise ValueError("找不到資料夾")
    root_path = Path(root["path"])
    if not root_path.is_dir():
        raise ValueError("硬碟未連接")
    target = safe_folder(root_path, folder)
    target.mkdir(parents=True, exist_ok=True)
    return target.relative_to(root_path.resolve()).as_posix() if target != root_path.resolve() else ""


def _unique(target: Path) -> Path:
    if not target.exists():
        return target
    stem, suffix = target.stem, target.suffix
    for n in range(1, 10_000):
        candidate = target.with_name(f"{stem} ({n}){suffix}")
        if not candidate.exists():
            return candidate
    raise RuntimeError("目的地同名檔案過多")


def move_images(conn: sqlite3.Connection, image_ids: list[int], root_id: int, folder: str) -> OpResult:
    result = OpResult()
    root = db.get_root(conn, root_id)
    if root is None:
        raise ValueError("找不到目的地資料夾")
    root_path = Path(root["path"]).resolve()
    if not root_path.is_dir():
        raise ValueError("目的地硬碟未連接")
    target_dir = safe_folder(root_path, folder)
    target_dir.mkdir(parents=True, exist_ok=True)
    for image_id in image_ids:
        image = db.get_image(conn, int(image_id))
        if image is None:
            continue
        src = db.absolute_path(conn, image)
        try:
            if not src.exists():
                raise FileNotFoundError("找不到檔案（硬碟可能未連接）")
            if src.parent.resolve() == target_dir:
                result.done.append(image["id"])
                continue
            dest = _unique(target_dir / src.name)
            extras = sidecars(src)
            shutil.move(str(src), str(dest))
            for extra in extras:
                suffix = extra.name[len(src.stem):] if extra.name.startswith(src.stem) else extra.suffix
                try:
                    shutil.move(str(extra), str(_unique(dest.with_name(dest.stem + suffix))))
                except OSError:
                    pass
        except Exception as exc:
            result.errors.append(f"{image['rel_path']}: {exc}")
            continue
        rel = dest.relative_to(root_path).as_posix()
        conn.execute(
            "UPDATE images SET root_id = ?, rel_path = ?, folder = ?, mtime = ?, status = 'ok' WHERE id = ?",
            (root["id"], rel, db.folder_of(rel), dest.stat().st_mtime, image["id"]),
        )
        db.refresh_search_text(conn, image["id"])
        result.done.append(image["id"])
    conn.commit()
    return result


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
