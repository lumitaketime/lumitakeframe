"""目錄放在哪裡：預設在這台 Mac 的 ~/.rememor，可以搬到其他磁碟（例如常接的 SSD）。

~/.rememor 是固定的「起點」：搬走之後，這裡只留一個 location.json 記著目錄的新位置（舊的那份資料也留著，
由本人決定要不要刪——永不自動刪除）。搬回這台 Mac 時，把 location.json 拿掉就好。
有設定 REMEMOR_HOME 時，起點改成那個資料夾（測試與開發用）。

搬移只複製 Re'memor 自己的資料（目錄資料庫、縮圖、模型、設定），不碰任何被掃描的硬碟；
目錄也不能放在被掃描的資料夾裡（隱藏資料夾除外，掃描本來就會略過）。
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path

POINTER = "location.json"
DB_FILES = ("library.db", "library.db-wal", "library.db-shm")
SKIP = {POINTER, *DB_FILES}


class CatalogUnavailable(Exception):
    """目錄放在一顆現在沒接上的磁碟上。"""

    def __init__(self, target: Path, anchor: Path):
        super().__init__(f"目錄放在「{target}」，那顆磁碟現在沒有接上。請接上後再開啟 Re'memor。")
        self.target = target
        self.anchor = anchor


def anchor() -> Path:
    """起點資料夾：REMEMOR_HOME，沒有的話是 ~/.rememor。"""
    env = os.environ.get("REMEMOR_HOME")
    return Path(env).expanduser() if env else Path.home() / ".rememor"


def pointed(base: Path | None = None) -> Path | None:
    """目錄搬走時記下的新位置；沒有搬過回傳 None。"""
    base = base or anchor()
    try:
        data = json.loads((base / POINTER).read_text(encoding="utf-8"))
        home = Path(data["home"]).expanduser()
        return None if home == base else home
    except (OSError, ValueError, KeyError, TypeError):
        return None


def current_home(base: Path | None = None) -> Path:
    """目錄現在的位置。搬到的那顆磁碟沒接上時丟出 CatalogUnavailable（不在空的位置另開一個新目錄）。"""
    base = base or anchor()
    target = pointed(base)
    if target is None:
        return base
    if not (target / "library.db").exists():
        raise CatalogUnavailable(target, base)
    return target


def use_home(base: Path, home: Path) -> None:
    """之後改用 home：寫下（或拿掉）location.json。"""
    base.mkdir(parents=True, exist_ok=True)
    if Path(home).resolve() == base.resolve():
        (base / POINTER).unlink(missing_ok=True)
    else:
        tmp = base / (POINTER + ".tmp")
        tmp.write_text(json.dumps({"home": str(home), "moved_at": time.strftime("%Y-%m-%dT%H:%M:%S")}, ensure_ascii=False),
                       encoding="utf-8")
        os.replace(tmp, base / POINTER)


def _inside(path: Path, folder: Path) -> bool:
    try:
        path.relative_to(folder)
        return True
    except ValueError:
        return False


def _stashed(name: str) -> bool:
    """搬回這台 Mac 時收起來的舊目錄（不再複製、不算進大小）。"""
    return name.startswith("舊的目錄 ") or name.endswith(".複製中")


def folder_size(home: Path) -> tuple[int, int]:
    """目錄資料夾總共多大、幾個檔案（不含 location.json）。"""
    total = files = 0
    for dirpath, dirs, names in os.walk(home):
        if Path(dirpath) == home:
            dirs[:] = [d for d in dirs if not _stashed(d)]
        for n in names:
            if Path(dirpath) == home and n == POINTER:
                continue
            try:
                total += os.lstat(os.path.join(dirpath, n)).st_size
                files += 1
            except OSError:
                pass
    return total, files


def check_target(dest: str | Path, home: Path, roots: list[str]) -> tuple[Path | None, str]:
    """檢查能不能搬到 dest。回傳（實際要用的資料夾, 錯誤說明）；可以搬時錯誤說明是空字串。

    dest 是使用者選的資料夾：裡面已經有 Re'memor 目錄就直接用；否則在裡面建一個「Re'memor 目錄」資料夾。"""
    raw = Path(str(dest)).expanduser()
    if not str(dest).strip() or not raw.is_absolute():
        return None, "請選一個資料夾。"
    if not raw.is_dir():
        return None, "找不到這個資料夾。請確認磁碟接著，再選一次。"
    base = anchor()
    # 搬回這台 Mac：放回起點資料夾（裡面舊的那份會先收進「舊的目錄」資料夾，不刪除）
    target = base if raw.resolve() == base.resolve() else raw if raw.name == "Re'memor 目錄" else raw / "Re'memor 目錄"
    resolved = target.resolve() if target.exists() else raw.resolve() / target.name
    if resolved == home.resolve():
        return None, "目錄已經在這裡了。"
    if _inside(resolved, home.resolve()):
        return None, "不能搬到目前目錄資料夾的裡面。"
    for root in roots:
        try:
            rp = Path(root).resolve()
        except OSError:
            continue
        hidden = any(part.startswith(".") for part in resolved.relative_to(rp).parts) if _inside(resolved, rp) else False
        if _inside(resolved, rp) and not hidden:
            return None, f"這個位置在已加入目錄的「{root}」裡面。目錄不能放在被掃描的資料夾裡，請換一個位置。"
    if not os.access(raw, os.W_OK):
        return None, "這個位置不能寫入（可能是唯讀的硬碟，例如 NTFS）。請換一個位置。"
    if target != base and (target / "library.db").exists():
        return None, "這裡已經有一份 Re'memor 目錄（可能是之前搬過的舊資料）。請換一個資料夾，或先自己把它移走。"
    need, _ = folder_size(home)
    free = shutil.disk_usage(raw).free
    if free < need * 1.1 + 200_000_000:
        return None, f"空間不夠：需要約 {need / 1e9:.1f} GB，這顆磁碟只剩 {free / 1e9:.1f} GB。"
    return target, ""


@dataclass
class MoveResult:
    copied: int = 0
    bytes: int = 0
    stopped: bool = False
    stash: Path | None = None
    errors: list[str] = field(default_factory=list)


def move_catalog(db_path: Path, home: Path, target: Path, progress=None, stop=None) -> MoveResult:
    """把目錄複製到 target 並確認完整。成功後才由呼叫的人改用新位置；舊的這份不刪除。"""
    result = MoveResult()
    total, _ = folder_size(home)
    work = target.parent / (target.name + ".複製中")
    if work.exists():
        shutil.rmtree(work)  # 上次中斷留下的半成品（Re'memor 自己剛建立的資料夾）
    work.mkdir(parents=True)
    done = 0

    def tick(n, name):
        nonlocal done
        done += n
        if progress:
            progress(done, total, name)

    # 1. 資料庫：用 SQLite 的備份功能複製，即使有人在讀寫也是一份完整一致的資料
    src = sqlite3.connect(str(db_path))
    dst = sqlite3.connect(str(work / "library.db"))
    try:
        size = db_path.stat().st_size
        src.backup(dst, pages=4096, progress=lambda _s, remaining, pages: progress and progress(
            done + int(size * (pages - remaining) / max(1, pages)), total, "library.db"))
        dst.commit()
    finally:
        dst.close()
        src.close()
    tick(db_path.stat().st_size, "library.db")
    if stop is not None and stop.is_set():
        shutil.rmtree(work, ignore_errors=True)
        result.stopped = True
        return result

    # 2. 其他檔案：縮圖、模型、設定
    for dirpath, dirs, names in os.walk(home):
        rel = Path(dirpath).relative_to(home)
        if rel == Path("."):
            dirs[:] = [d for d in dirs if not _stashed(d) and (home / d) != work]
        (work / rel).mkdir(parents=True, exist_ok=True)
        for n in names:
            if rel == Path(".") and n in SKIP:
                continue
            if stop is not None and stop.is_set():
                shutil.rmtree(work, ignore_errors=True)
                result.stopped = True
                return result
            s = Path(dirpath) / n
            try:
                if s.is_symlink():
                    continue
                shutil.copy2(s, work / rel / n)
                result.copied += 1
                tick(s.stat().st_size, str(rel / n))
            except OSError as e:
                result.errors.append(f"{rel / n}：{e}")
    # 3. 確認完整：資料庫檢查通過、檔案數與大小一致
    check = sqlite3.connect(str(work / "library.db"))
    try:
        ok = check.execute("PRAGMA quick_check").fetchone()[0] == "ok"
        n_new = check.execute("SELECT COUNT(*) FROM files").fetchone()[0]
    finally:
        check.close()
    src = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        n_old = src.execute("SELECT COUNT(*) FROM files").fetchone()[0]
    finally:
        src.close()
    if not ok or n_new != n_old:
        result.errors.append("複製後的目錄資料庫檢查沒有通過")
    if result.errors:
        shutil.rmtree(work, ignore_errors=True)
        return result
    if target.exists() and any(target.iterdir()):
        # 放回起點資料夾：裡面原本那份（舊的）收進「舊的目錄 日期」資料夾，不刪除
        stash = target / time.strftime("舊的目錄 %Y-%m-%d %H%M%S")
        stash.mkdir()
        for item in list(target.iterdir()):
            if item.name in (POINTER, stash.name) or item.name.startswith("舊的目錄 "):
                continue
            os.replace(item, stash / item.name)
        for item in list(work.iterdir()):
            os.replace(item, target / item.name)
        work.rmdir()
        result.stash = stash
    else:
        if target.exists():
            target.rmdir()  # 空的資料夾
        os.replace(work, target)
    result.bytes = done
    return result


def describe(res: MoveResult, target: Path, home: Path) -> str:
    if res.stopped:
        return "已停止搬移，目錄還在原本的位置。"
    if res.errors:
        return "搬移沒有完成，目錄還在原本的位置：" + "；".join(res.errors[:3])
    moved = f"已把目錄複製到「{target}」（{res.bytes / 1e9:.1f} GB）。"
    if res.stash:
        return moved + f"這裡原本那份舊的目錄收進了「{res.stash.name}」，確認沒問題後可以自己刪除。"
    return moved + f"原本那份還留在「{home}」，確認沒問題後可以自己刪除。"
