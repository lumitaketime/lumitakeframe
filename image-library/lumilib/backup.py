"""目錄檔管理：備份、還原、刪除搬移後留下的舊目錄、刪除整份目錄重新開始。

只動 Re'memor 自己的目錄（資料庫、縮圖、設定），絕不碰被掃描的硬碟上的檔案（核心原則七）；
備份也不能放在被掃描的資料夾裡。

- 備份：一個檔案「Re'memor 目錄備份 日期.rememor-backup」（其實是 zip），裡面是目錄資料庫（含文件文字索引）、
  設定（不含 API 金鑰與登入密碼）與 manifest.json。用 SQLite 的備份功能複製，App 開著、正在掃描也是一份完整的。
  縮圖與模型不放：縮圖可以重新產生、模型可以重新下載，備份檔會小很多。
- 每週自動備份：只保留最近幾份「自動」備份；本人按的「立即備份」永遠不會被自動拿掉。
- 還原：先把備份裡的資料庫解出來、檢查完整，記下「下次開啟時改用它」，重新開啟時才換（不在使用中替換）。
  目前那份不刪除，收進「還原前的目錄 日期」資料夾。
- 刪除整份目錄：一樣在重新開啟時做，資料庫與縮圖移到垃圾桶（不是直接刪除）；設定與已下載的模型保留。
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path

from .location import DB_FILES, POINTER

PREFIX = "Re'memor 目錄備份 "
EXT = ".rememor-backup"
MANIFEST = "manifest.json"
PENDING = "pending-action.json"  # 下次開啟時要做的事：還原或重新開始
RESTORED_DB = "還原中.library.db"
SECRET = ("_key", "password")  # 設定裡這些不放進備份


class BackupError(Exception):
    """給使用者看的錯誤訊息。"""


def _inside(path: Path, folder: Path) -> bool:
    try:
        path.relative_to(folder)
        return True
    except ValueError:
        return False


def check_dest(dest: str | Path, home: Path, roots: list[str]) -> tuple[Path | None, str]:
    """備份能不能放在 dest：回傳（資料夾, 錯誤說明）。"""
    raw = Path(str(dest or "")).expanduser()
    if not str(dest or "").strip() or not raw.is_absolute():
        return None, "請選一個存放備份的資料夾。"
    if not raw.is_dir():
        return None, "找不到這個資料夾。如果在外接磁碟上，請確認磁碟接著。"
    resolved = raw.resolve()
    if _inside(resolved, home.resolve()):
        return None, "備份不能放在目錄資料夾裡面（目錄壞掉時備份也會一起不見）。請換一個位置，最好是另一顆磁碟。"
    for root in roots:
        try:
            rp = Path(root).resolve()
        except OSError:
            continue
        if _inside(resolved, rp) and not any(p.startswith(".") for p in resolved.relative_to(rp).parts):
            return None, f"這個位置在已加入目錄的「{root}」裡面。Re'memor 不會在被掃描的資料夾裡寫入任何東西，請換一個位置。"
    if not os.access(raw, os.W_OK):
        return None, "這個位置不能寫入（可能是唯讀的硬碟，例如 NTFS）。請換一個位置。"
    return resolved, ""


def _clean_config(home: Path) -> bytes | None:
    try:
        data = json.loads((home / "config.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    data = {k: v for k, v in data.items() if not any(k.endswith(s) for s in SECRET)}
    return json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")


@dataclass
class BackupResult:
    path: Path | None = None
    bytes: int = 0
    stopped: bool = False


def create(db_path: Path, home: Path, dest: Path, auto: bool = False, version: str = "", progress=None, stop=None) -> BackupResult:
    """做一份備份放在 dest。先寫成暫存檔、檢查完整後才改成正式的名字（做到一半中斷不會留下壞掉的備份）。"""
    from . import db

    result = BackupResult()
    size = db_path.stat().st_size if db_path.exists() else 0
    free = shutil.disk_usage(dest).free
    if free < size * 1.2 + 100_000_000:
        raise BackupError(f"空間不夠：備份需要約 {size / 1e9:.1f} GB，這個位置只剩 {free / 1e9:.1f} GB。")
    name = PREFIX + time.strftime("%Y-%m-%d %H%M%S") + (" 自動" if auto else "") + EXT
    tmp_db = dest / f".{name}.db.tmp"
    tmp_zip = dest / f".{name}.tmp"
    try:
        # 1. 資料庫：SQLite 的備份功能，即使正在掃描也是一份完整一致的
        src = sqlite3.connect(str(db_path))
        out = sqlite3.connect(str(tmp_db))
        try:
            src.backup(out, pages=4096, progress=lambda _s, remaining, pages: progress and progress(
                int(size * (pages - remaining) / max(1, pages) * 0.5), size, "目錄資料庫"))
            out.commit()
            files = out.execute("SELECT COUNT(*) FROM files").fetchone()[0]
        finally:
            out.close()
            src.close()
        if stop is not None and stop.is_set():
            result.stopped = True
            return result
        # 2. 壓縮成一個檔案
        manifest = {"app": "Re'memor", "kind": "catalog-backup", "version": version, "schema": db.SCHEMA_VERSION,
                    "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "auto": auto, "files": files, "db_bytes": tmp_db.stat().st_size}
        with zipfile.ZipFile(tmp_zip, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            z.writestr(MANIFEST, json.dumps(manifest, ensure_ascii=False, indent=2))
            config = _clean_config(home)
            if config:
                z.writestr("config.json", config)
            z.write(tmp_db, "library.db")
        if progress:
            progress(int(size * 0.9), size, "檢查備份")
        # 3. 檢查完整：zip 讀得出來，裡面的資料庫也通過檢查
        with zipfile.ZipFile(tmp_zip) as z:
            if z.testzip() is not None:
                raise BackupError("備份檔檢查沒有通過，請再試一次。")
        final = dest / name
        os.replace(tmp_zip, final)
        result.path, result.bytes = final, final.stat().st_size
        if progress:
            progress(size, size, "完成")
        return result
    finally:
        tmp_db.unlink(missing_ok=True)
        tmp_zip.unlink(missing_ok=True)


def read_manifest(path: Path) -> dict | None:
    """不是 Re'memor 的目錄備份就回傳 None。"""
    try:
        with zipfile.ZipFile(path) as z:
            m = json.loads(z.read(MANIFEST).decode("utf-8"))
            if m.get("app") != "Re'memor" or m.get("kind") != "catalog-backup" or "library.db" not in z.namelist():
                return None
            return m
    except (OSError, KeyError, ValueError, zipfile.BadZipFile):
        return None


def list_backups(dest: Path | None) -> list[dict]:
    """這個資料夾裡的 Re'memor 目錄備份，新的在前。"""
    if not dest or not Path(dest).is_dir():
        return []
    out = []
    for p in Path(dest).iterdir():
        if not (p.name.startswith(PREFIX) and p.name.endswith(EXT)) or not p.is_file():
            continue
        m = read_manifest(p)
        if m is None:
            continue
        out.append({"name": p.name, "path": str(p), "bytes": p.stat().st_size, "created_at": m.get("created_at"),
                    "auto": bool(m.get("auto")), "files": m.get("files"), "version": m.get("version")})
    return sorted(out, key=lambda b: b["created_at"] or "", reverse=True)


def prune(dest: Path, keep: int) -> list[str]:
    """自動備份只留最近 keep 份（Re'memor 自己做的自動備份；本人按的「立即備份」不動）。"""
    autos = [b for b in list_backups(dest) if b["auto"]]
    removed = []
    for b in autos[max(1, keep):]:
        try:
            Path(b["path"]).unlink()
            removed.append(b["name"])
        except OSError:
            pass
    return removed


def due(last: str | None, days: int = 7) -> bool:
    """距離上次自動備份超過 days 天了沒（沒做過＝該做了）。"""
    if not last:
        return True
    try:
        t = time.mktime(time.strptime(last[:19], "%Y-%m-%dT%H:%M:%S"))
    except ValueError:
        return True
    return time.time() - t >= days * 86400


# ---- 還原、重新開始：下次開啟時才做（不在資料庫使用中替換） ----

def prepare_restore(home: Path, backup: Path) -> dict:
    """把備份裡的資料庫解出來、檢查完整，記下「下次開啟時改用它」。回傳 manifest。"""
    from . import db

    m = read_manifest(backup)
    if m is None:
        raise BackupError("這不是 Re'memor 的目錄備份，或檔案壞了。")
    if int(m.get("schema") or 0) > db.SCHEMA_VERSION:
        raise BackupError("這份備份是比較新的 Re'memor 做的，請先更新 Re'memor 再還原。")
    target = home / RESTORED_DB
    target.unlink(missing_ok=True)
    with zipfile.ZipFile(backup) as z, z.open("library.db") as src, open(target, "wb") as out:
        shutil.copyfileobj(src, out, 1024 * 1024)
    check = sqlite3.connect(str(target))
    try:
        ok = check.execute("PRAGMA quick_check").fetchone()[0] == "ok"
    finally:
        check.close()
    if not ok:
        target.unlink(missing_ok=True)
        raise BackupError("備份裡的目錄資料庫檢查沒有通過，沒有還原。")
    _write_pending(home, {"action": "restore", "from": backup.name, "at": time.strftime("%Y-%m-%dT%H:%M:%S")})
    return m


def prepare_reset(home: Path) -> None:
    """記下「下次開啟時把整份目錄移到垃圾桶、從頭開始」。"""
    _write_pending(home, {"action": "reset", "at": time.strftime("%Y-%m-%dT%H:%M:%S")})


def cancel_pending(home: Path) -> None:
    (home / PENDING).unlink(missing_ok=True)
    (home / RESTORED_DB).unlink(missing_ok=True)


def _write_pending(home: Path, data: dict) -> None:
    tmp = home / (PENDING + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, home / PENDING)


def _trash(path: Path) -> None:
    try:
        from send2trash import send2trash

        send2trash(str(path))
    except Exception:  # noqa: BLE001  沒辦法移到垃圾桶：改收進「已刪除的目錄」資料夾，一樣不直接刪除
        keep = path.parent / time.strftime("已刪除的目錄 %Y-%m-%d %H%M%S")
        keep.mkdir(exist_ok=True)
        os.replace(path, keep / path.name)


def apply_pending(home: Path) -> str | None:
    """開啟時（還沒連上資料庫之前）做上次記下的還原或重新開始。回傳做了什麼（給紀錄看），沒有就是 None。"""
    marker = home / PENDING
    try:
        data = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    marker.unlink(missing_ok=True)
    action = data.get("action")
    if action == "restore":
        new = home / RESTORED_DB
        if not new.exists():
            return None
        keep = home / time.strftime("還原前的目錄 %Y-%m-%d %H%M%S")
        keep.mkdir()
        for n in DB_FILES:
            if (home / n).exists():
                os.replace(home / n, keep / n)  # 目前這份不刪除：收起來
        os.replace(new, home / "library.db")
        return f"已改用備份「{data.get('from')}」；原本的目錄收在「{keep.name}」"
    if action == "reset":
        for n in (*DB_FILES, "thumbs"):
            p = home / n
            if p.exists():
                _trash(p)
        return "已把整份目錄移到垃圾桶，從頭開始"
    return None


# ---- 搬移後留下的舊目錄 ----

def old_copies(base: Path, home: Path) -> list[dict]:
    """搬移目錄後留下的舊資料：[{path, bytes}]。只列 Re'memor 自己留下的。"""
    from .location import folder_size, pointed

    out = []
    if pointed(base) is not None and home.resolve() != base.resolve() and (base / "library.db").exists():
        size = sum(_size(base / n) for n in os.listdir(base) if n not in (POINTER,) and not n.startswith(("舊的目錄 ", "還原前的目錄 ")))
        out.append({"path": str(base), "bytes": size, "kind": "moved"})
    for folder in {base, home}:
        if folder.is_dir():
            for p in sorted(folder.iterdir()):
                if p.is_dir() and p.name.startswith(("舊的目錄 ", "還原前的目錄 ", "已刪除的目錄 ")):
                    out.append({"path": str(p), "bytes": folder_size(p)[0], "kind": "stash"})
    return out


def _size(p: Path) -> int:
    if p.is_symlink():
        return 0
    if p.is_file():
        return p.stat().st_size
    total = 0
    for dirpath, _dirs, names in os.walk(p):
        for n in names:
            try:
                total += os.lstat(os.path.join(dirpath, n)).st_size
            except OSError:
                pass
    return total


def trash_old_copy(base: Path, home: Path, path: str) -> int:
    """把一份舊目錄移到垃圾桶（只接受 old_copies 列出來的）。回傳釋出多少空間。"""
    match = next((c for c in old_copies(base, home) if c["path"] == path), None)
    if match is None:
        raise BackupError("找不到這份舊目錄（可能已經移走了）。")
    p = Path(path)
    if match["kind"] == "moved":
        # 起點資料夾裡的舊資料：location.json（記著目錄現在在哪裡）留著，其他移到垃圾桶
        for n in os.listdir(p):
            if n != POINTER and not n.startswith(("舊的目錄 ", "還原前的目錄 ")):
                _trash(p / n)
    else:
        _trash(p)
    return match["bytes"]
