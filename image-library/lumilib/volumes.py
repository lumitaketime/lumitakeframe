"""辨識硬碟：用作業系統給的卷宗編號（Volume UUID）認出每一顆硬碟。

- 只向系統查詢（macOS 的 diskutil），不在硬碟上寫入任何識別檔，符合「只讀不寫硬碟」。
- 硬碟改名、換接口、掛載位置變成「/Volumes/名稱 1」時，靠編號仍認得是同一顆。
- 兩顆硬碟取了一樣的名字時，靠編號分得出來，不會把 B 當成 A 掃描。
- 系統查不到編號時（少數格式或其他作業系統），退而用「名稱＋容量＋格式」辨識。
"""

from __future__ import annotations

import os
import plistlib
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

_CACHE: dict[str, tuple[float, dict | None]] = {}
_LOCK = threading.Lock()
_TTL = 20.0  # 秒；掃描時同一顆硬碟會被查詢很多次

# diskutil 回報的格式名稱 → 一般人看得懂的名稱
FS_NAMES = {
    "apfs": "APFS", "hfs": "Mac OS 擴充格式（HFS+）", "exfat": "ExFAT", "msdos": "FAT32",
    "ntfs": "NTFS（Mac 只能讀取）", "ufsd_ntfs": "NTFS", "tuxera_ntfs": "NTFS", "smbfs": "網路磁碟", "nfs": "網路磁碟",
}


def mount_point(path: str | Path) -> Path:
    """path 所在的掛載點（外接硬碟通常是 /Volumes/名稱）。"""
    p = Path(path).resolve()
    while not os.path.ismount(p) and p.parent != p:
        p = p.parent
    return p


def _diskutil(target: str) -> dict | None:
    try:
        out = subprocess.run(["diskutil", "info", "-plist", target], capture_output=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if out.returncode != 0 or not out.stdout:
        return None
    try:
        return plistlib.loads(out.stdout)
    except Exception:  # noqa: BLE001  輸出格式不對就當作查不到
        return None


def _fs_type_linux(mount: Path) -> str | None:
    try:
        with open("/proc/mounts", encoding="utf-8") as fh:
            best = None
            for line in fh:
                parts = line.split()
                if len(parts) >= 3 and Path(parts[1].replace("\\040", " ")) == mount:
                    best = parts[2]
            return best
    except OSError:
        return None


def _lookup(mount: Path) -> dict | None:
    if not mount.exists():
        return None
    info = {"uuid": None, "name": mount.name or str(mount), "fs_type": None, "capacity": None,
            "mount": str(mount), "read_only": False}
    if sys.platform == "darwin":
        d = _diskutil(str(mount))
        if d:
            info["uuid"] = d.get("VolumeUUID") or d.get("DiskUUID")
            info["name"] = d.get("VolumeName") or info["name"]
            info["fs_type"] = (d.get("FilesystemType") or d.get("FilesystemName") or "").lower() or None
            info["capacity"] = d.get("TotalSize") or d.get("Size")
            info["read_only"] = not d.get("WritableVolume", True)
    elif sys.platform.startswith("linux"):
        info["fs_type"] = _fs_type_linux(mount)
    if not info["capacity"]:
        try:
            info["capacity"] = shutil.disk_usage(mount).total
        except OSError:
            pass
    if not info["read_only"]:
        info["read_only"] = not os.access(mount, os.W_OK)
    return info


def volume_info(path: str | Path) -> dict | None:
    """path 所在硬碟的資料：uuid、name、fs_type、capacity（位元組）、mount、read_only。查不到時回傳 None。"""
    try:
        mount = mount_point(path)
    except OSError:
        return None
    key = str(mount)
    now = time.monotonic()
    with _LOCK:
        hit = _CACHE.get(key)
        if hit and now - hit[0] < _TTL:
            return hit[1]
    info = _lookup(mount)
    with _LOCK:
        _CACHE[key] = (now, info)
    return info


def forget(path: str | Path | None = None) -> None:
    """清除查詢暫存（硬碟拔掉或接上時）。"""
    with _LOCK:
        if path is None:
            _CACHE.clear()
        else:
            _CACHE.pop(str(mount_point(path)), None)


def drive_key(info: dict) -> str:
    """一顆硬碟的唯一鍵：優先用系統編號，查不到才用名稱、容量與格式。"""
    if info.get("uuid"):
        return f"uuid:{info['uuid']}"
    return f"vol:{info.get('name') or ''}|{info.get('capacity') or 0}|{info.get('fs_type') or ''}"


def mounted_volumes() -> list[Path]:
    """目前接著的硬碟掛載點（macOS 的 /Volumes 底下，加上開機磁碟）。"""
    out = [Path("/")]
    base = Path("/Volumes")
    if base.is_dir():
        try:
            out += sorted(p for p in base.iterdir() if p.is_dir() and os.path.ismount(p))
        except OSError:
            pass
    return out


def find_mount(uuid: str | None) -> Path | None:
    """依編號找出這顆硬碟現在掛在哪裡（硬碟改名後掛載位置會跟著變）。"""
    if not uuid:
        return None
    for mount in mounted_volumes():
        info = volume_info(mount)
        if info and info.get("uuid") == uuid:
            return Path(info["mount"])
    return None


def fs_label(fs_type: str | None) -> str:
    return FS_NAMES.get((fs_type or "").lower(), (fs_type or "未知").upper())
