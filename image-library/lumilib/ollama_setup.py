"""在 App 裡一鍵安裝、更新、打開 Ollama（只在 Mac 上）。

只有本人按下「下載並安裝 Ollama」才會連網：從 Ollama 官方網站（或它在 GitHub 的正式發行頁）下載 Mac 版，
不會送出任何檔案或資料。下載的暫存檔放在目錄資料夾裡的 tmp，裝完就清掉。

安裝步驟：
1. 下載（可以中途停止）
2. 解開：zip 用 ditto；dmg 用 hdiutil 以唯讀方式掛載後複製出來
3. 檢查：Ollama.app 必須有完整、有效的 Apple「Developer ID」簽章，名稱是 Ollama，否則不安裝
4. 放進「應用程式」：更新時放回原本的位置（舊版移到垃圾桶，可以拿回來）；
   新裝時放進你帳號裡的「應用程式」資料夾（~/Applications），不需要輸入密碼
5. 打開 Ollama，等它準備好
"""
from __future__ import annotations

import os
import plistlib
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path
from typing import Callable

# 依序嘗試：Ollama 官網，再來是它在 GitHub 的正式發行頁（官網連不上時）
URLS = (
    "https://ollama.com/download/Ollama.dmg",
    "https://ollama.com/download/Ollama-darwin.zip",
    "https://github.com/ollama/ollama/releases/latest/download/Ollama.dmg",
    "https://github.com/ollama/ollama/releases/latest/download/Ollama-darwin.zip",
)
APP_NAME = "Ollama.app"

Progress = Callable[[str, int, int], None]


class InstallError(RuntimeError):
    """安裝失敗：訊息是給一般人看的。"""


def app_version(app: str | Path | None) -> str:
    """Ollama.app 的版本（讀 Info.plist）；讀不到回傳空字串。"""
    if not app:
        return ""
    try:
        with open(Path(app) / "Contents" / "Info.plist", "rb") as f:
            info = plistlib.load(f)
        return str(info.get("CFBundleShortVersionString") or info.get("CFBundleVersion") or "")
    except (OSError, ValueError, plistlib.InvalidFileException):
        return ""


def status() -> dict:
    """{"installed", "app", "cli", "version", "can_install", "brew"}：介面決定要顯示哪個按鈕。"""
    from .analyzer import ollama_installed

    info = ollama_installed()
    app = info.get("app")
    cli = info.get("cli") or ""
    return {
        **info,
        "version": app_version(app),
        "can_install": sys.platform == "darwin",
        # 用 Homebrew（終端機）裝的：只有指令、沒有 App
        "brew": bool(cli) and not app and ("/homebrew/" in cli or "/Cellar/" in cli or cli.startswith("/usr/local/")),
    }


def target_dir(existing_app: str | None) -> Path:
    """要裝到哪裡：更新時裝回原本的位置（能寫入的話），否則放在 ~/Applications（不需要密碼）。"""
    if existing_app:
        parent = Path(existing_app).parent
        if os.access(parent, os.W_OK):
            return parent
    return Path.home() / "Applications"


def _download(urls, dest: Path, progress: Progress | None, stop: threading.Event | None, opener=None) -> Path:
    opener = opener or urllib.request.urlopen
    errors = []
    for url in urls:
        name = url.rsplit("/", 1)[-1]
        out = dest / name
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Rememor"})
            with opener(req, timeout=60) as resp, open(out, "wb") as f:
                total = int(resp.headers.get("Content-Length") or 0)
                done = 0
                while True:
                    if stop is not None and stop.is_set():
                        return out
                    chunk = resp.read(1 << 20)
                    if not chunk:
                        break
                    f.write(chunk)
                    done += len(chunk)
                    if progress:
                        progress("download", done, total)
            if done < 1024 or (total and done < total):
                raise InstallError("下載的檔案不完整")
            return out
        except Exception as exc:  # noqa: BLE001  換下一個網址
            errors.append(f"{url}：{exc}")
            out.unlink(missing_ok=True)
    raise InstallError("沒辦法下載 Ollama，請確認網路連線後再試一次。\n" + "\n".join(errors))


def _find_app(root: Path) -> Path | None:
    for p in [root / APP_NAME, *root.glob("*/" + APP_NAME)]:
        if p.is_dir():
            return p
    return None


def _run(cmd: list[str], timeout: int = 300) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def extract(archive: Path, work: Path, run=_run) -> Path:
    """把下載的 zip 或 dmg 解開，回傳 Ollama.app 的位置（在暫存資料夾裡）。"""
    staged = work / "staged"
    shutil.rmtree(staged, ignore_errors=True)
    staged.mkdir(parents=True)
    with open(archive, "rb") as f:
        head = f.read(4)
    if head.startswith(b"PK"):
        r = run(["ditto", "-x", "-k", str(archive), str(staged)])  # ditto 會保留簽章與權限
        if r.returncode != 0:
            raise InstallError(f"解壓縮失敗：{(r.stderr or '').strip()[:200]}")
    else:
        mount = work / "mount"
        mount.mkdir(exist_ok=True)
        r = run(["hdiutil", "attach", "-nobrowse", "-readonly", "-noautoopen", "-mountpoint", str(mount), str(archive)])
        if r.returncode != 0:
            raise InstallError(f"打不開下載的安裝檔：{(r.stderr or '').strip()[:200]}")
        try:
            src = _find_app(mount)
            if src is None:
                raise InstallError("安裝檔裡找不到 Ollama")
            r = run(["ditto", str(src), str(staged / APP_NAME)])
            if r.returncode != 0:
                raise InstallError(f"複製失敗：{(r.stderr or '').strip()[:200]}")
        finally:
            run(["hdiutil", "detach", "-quiet", str(mount)], timeout=60)
    app = _find_app(staged)
    if app is None:
        raise InstallError("下載的檔案裡找不到 Ollama")
    return app


def verify(app: Path, run=_run) -> dict:
    """確認是 Ollama 官方簽章的 App：簽章完整有效、是 Apple 發給開發者的 Developer ID，名稱是 Ollama。"""
    r = run(["codesign", "--verify", "--deep", "--strict", str(app)])
    if r.returncode != 0:
        raise InstallError("下載的 Ollama 簽章檢查沒有通過，為了安全沒有安裝。請稍後再試，或到 ollama.com 手動下載。")
    r = run(["codesign", "-dv", "--verbose=2", str(app)])
    text = (r.stderr or "") + (r.stdout or "")
    if "Authority=Developer ID Application" not in text:
        raise InstallError("下載的 Ollama 不是由開發者正式簽署的，為了安全沒有安裝。")
    team = ""
    for line in text.splitlines():
        if line.startswith("TeamIdentifier="):
            team = line.split("=", 1)[1].strip()
    if "ollama" not in app_version_name(app).lower():
        raise InstallError("下載的檔案不是 Ollama，為了安全沒有安裝。")
    return {"team": team, "version": app_version(app)}


def app_version_name(app: Path) -> str:
    try:
        with open(app / "Contents" / "Info.plist", "rb") as f:
            info = plistlib.load(f)
        return str(info.get("CFBundleName") or info.get("CFBundleExecutable") or "")
    except (OSError, ValueError, plistlib.InvalidFileException):
        return ""


def _quit_running(run=_run) -> None:
    """更新前請正在執行的 Ollama 結束（像在選單列按「Quit Ollama」）。"""
    run(["osascript", "-e", 'tell application "Ollama" to quit'], timeout=20)
    time.sleep(2)


def _to_trash(path: Path) -> None:
    from send2trash import send2trash

    send2trash(str(path))


def place(app: Path, dest_dir: Path, run=_run, trash=_to_trash) -> Path:
    """把檢查過的 Ollama.app 放進「應用程式」：已經有舊版就先移到垃圾桶（可以拿回來）。"""
    dest_dir.mkdir(parents=True, exist_ok=True)
    final = dest_dir / APP_NAME
    if final.exists():
        _quit_running(run)
        try:
            trash(final)
        except Exception as exc:  # noqa: BLE001
            raise InstallError(f"沒辦法把舊版 Ollama 移到垃圾桶：{exc}") from exc
    r = run(["ditto", str(app), str(final)])
    if r.returncode != 0:
        raise InstallError(f"沒辦法放進「應用程式」資料夾：{(r.stderr or '').strip()[:200]}")
    return final


def wait_ready(url: str, seconds: int = 90, stop: threading.Event | None = None) -> bool:
    """等 Ollama 開好（每秒問一次）。"""
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if stop is not None and stop.is_set():
            return False
        try:
            with urllib.request.urlopen(url.rstrip("/") + "/api/version", timeout=3):
                return True
        except Exception:  # noqa: BLE001
            time.sleep(1)
    return False


def running_version(url: str) -> str:
    import json

    try:
        with urllib.request.urlopen(url.rstrip("/") + "/api/version", timeout=3) as resp:
            return str(json.loads(resp.read().decode("utf-8")).get("version") or "")
    except Exception:  # noqa: BLE001
        return ""


def install(home: Path, ollama_url: str, progress: Progress | None = None, stop: threading.Event | None = None,
            urls=URLS, run=_run, opener=None, trash=_to_trash, apps_dir: Path | None = None, wait=wait_ready) -> dict:
    """下載、檢查、安裝並打開 Ollama。回傳 {"app", "version", "updated", "ready", "stopped"}。"""
    if sys.platform != "darwin" and apps_dir is None:
        raise InstallError("一鍵安裝只支援 Mac。其他系統請到 ollama.com 下載。")
    before = status()
    existing = before.get("app")
    work = home / "tmp" / "ollama-install"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    try:
        say = (lambda step, done=0, total=0: progress(step, done, total)) if progress else (lambda *a, **k: None)
        archive = _download(urls, work, progress, stop, opener)
        if stop is not None and stop.is_set():
            return {"stopped": True}
        say("verify")
        staged = extract(archive, work, run)
        checked = verify(staged, run)
        say("install")
        final = place(staged, apps_dir or target_dir(existing), run, trash)
        say("open")
        run(["open", str(final)], timeout=30)
        ready = wait(ollama_url, 90, stop)
        return {"app": str(final), "version": checked.get("version") or app_version(final), "updated": bool(existing),
                "ready": ready, "stopped": False}
    finally:
        shutil.rmtree(work, ignore_errors=True)


STEP_TEXT = {"download": "下載 Ollama", "verify": "檢查簽章", "install": "放進「應用程式」", "open": "打開 Ollama"}


def describe(res: dict) -> str:
    if res.get("stopped"):
        return "已停止安裝 Ollama"
    v = f" {res['version']}" if res.get("version") else ""
    head = f"Ollama{v} 已{'更新' if res.get('updated') else '安裝'}"
    return head + ("，已經可以使用" if res.get("ready") else "。如果還沒看到選單列的小羊駝圖示，請到「應用程式」打開 Ollama")
