"""AI 分析的時機：隨時、依排程（星期幾、幾點到幾點、符合哪些條件），或每次開始前先問。

條件都在這台 Mac 上判斷，不需要連網：
- 接上電源（pmset）
- 電量高於某個百分比（pmset）
- 電腦閒置超過幾分鐘（IOKit 的 HIDIdleTime；有人在用時會暫停，離開後自動繼續）
"""

from __future__ import annotations

import re
import subprocess
import sys
import time
from datetime import datetime, timedelta

from .config import Config

MODES = {"always": "隨時", "schedule": "依排程", "ask": "每次先問我"}
DAY_NAMES = "一二三四五六日"
_cache: dict = {}


def _cached(key: str, ttl: float, fn):
    now = time.monotonic()
    hit = _cache.get(key)
    if hit and now - hit[0] < ttl:
        return hit[1]
    value = fn()
    _cache[key] = (now, value)
    return value


def _pmset_batt() -> str:
    if sys.platform != "darwin":
        return ""
    try:
        return subprocess.run(["pmset", "-g", "batt"], capture_output=True, text=True, timeout=3).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def on_ac_power() -> bool:
    """是否接上電源（桌機或無法判斷時視為有接）。"""
    return _cached("ac", 30, lambda: "Battery Power" not in _pmset_batt())


def battery_percent() -> int | None:
    """電池電量；桌機或無法判斷時回傳 None。"""
    def read():
        m = re.search(r"(\d+)%", _pmset_batt())
        return int(m.group(1)) if m else None

    return _cached("batt", 60, read)


def idle_minutes() -> float | None:
    """多久沒有碰鍵盤滑鼠（分鐘）；無法判斷時回傳 None。"""
    def read():
        if sys.platform != "darwin":
            return None
        try:
            out = subprocess.run(["ioreg", "-c", "IOHIDSystem", "-d", "4"], capture_output=True, text=True, timeout=3).stdout
        except (OSError, subprocess.SubprocessError):
            return None
        m = re.search(r'"HIDIdleTime"\s*=\s*(\d+)', out)
        return int(m.group(1)) / 1e9 / 60 if m else None

    return _cached("idle", 20, read)


def _hm(text: str, default: str) -> tuple[int, int]:
    m = re.fullmatch(r"\s*(\d{1,2}):(\d{2})\s*", str(text or default))
    if not m:
        m = re.fullmatch(r"(\d{1,2}):(\d{2})", default)
    return int(m.group(1)) % 24, int(m.group(2)) % 60


def effective(cfg: Config) -> dict:
    """目前的排程設定（舊版的「只在夜間／接電源」也轉換成新的格式）。"""
    mode = cfg.analyze_schedule
    s = {
        "mode": mode if mode in MODES else "always",
        "days": "".join(d for d in str(cfg.schedule_days or "1234567") if d in "1234567") or "1234567",
        "start": cfg.schedule_start, "end": cfg.schedule_end,
        "ac": bool(cfg.schedule_ac), "idle": int(cfg.schedule_idle or 0), "battery": int(cfg.schedule_battery or 0),
    }
    if mode in ("ac", "night", "ac_night"):  # 舊版設定
        s["mode"] = "schedule"
        s["ac"] = mode in ("ac", "ac_night")
        if mode in ("night", "ac_night"):
            s["start"], s["end"] = f"{cfg.night_start % 24:02d}:00", f"{cfg.night_end % 24:02d}:00"
        else:
            s["start"] = s["end"] = "00:00"
    return s


def _in_window(s: dict, now: datetime) -> bool:
    """星期與時段。跨午夜的時段（例如 22:00–07:00）以開始那天的星期為準。"""
    sh, sm = _hm(s["start"], "00:00")
    eh, em = _hm(s["end"], "00:00")
    start, end = sh * 60 + sm, eh * 60 + em
    minute = now.hour * 60 + now.minute
    day = str(now.isoweekday())
    if start == end:  # 全天
        return day in s["days"]
    if start < end:
        return start <= minute < end and day in s["days"]
    if minute >= start:
        return day in s["days"]
    if minute < end:
        return str((now - timedelta(days=1)).isoweekday()) in s["days"]
    return False


def describe(s: dict) -> str:
    """把排程寫成一句話，例如「週一至週五 22:00–07:00，接上電源且閒置 10 分鐘以上」。"""
    if s["mode"] == "always":
        return "有待分析的照片就開始"
    if s["mode"] == "ask":
        return "每次開始前先問你"
    days = s["days"]
    if days == "1234567":
        d = "每天"
    elif days == "12345":
        d = "週一至週五"
    elif days == "67":
        d = "週末"
    else:
        d = "每週" + "、".join(DAY_NAMES[int(x) - 1] for x in sorted(days))
    t = "全天" if s["start"] == s["end"] else f"{s['start']}–{s['end']}"
    conds = []
    if s["ac"]:
        conds.append("接上電源")
    if s["battery"]:
        conds.append(f"電量 {s['battery']}% 以上")
    if s["idle"]:
        conds.append(f"閒置 {s['idle']} 分鐘以上")
    return f"{d} {t}" + (f"，{'且'.join(conds)}時" if conds else "")


def analysis_allowed(cfg: Config, now: datetime | None = None) -> tuple[bool, str]:
    s = effective(cfg)
    if s["mode"] != "schedule":
        return True, ""
    now = now or datetime.now()
    if not _in_window(s, now):
        return False, f"等待排程時段（{describe({**s, 'ac': False, 'battery': 0, 'idle': 0})}）"
    if s["ac"] and not on_ac_power():
        return False, "使用電池中，接上電源後會自動繼續"
    if s["battery"]:
        pct = battery_percent()
        if pct is not None and not on_ac_power() and pct < s["battery"]:
            return False, f"電量 {pct}%，低於 {s['battery']}%"
    if s["idle"]:
        idle = idle_minutes()
        if idle is not None and idle < s["idle"]:
            return False, f"有人正在使用電腦，閒置 {s['idle']} 分鐘後會自動繼續"
    return True, ""


# 舊名稱相容
def in_night(cfg: Config, now: datetime | None = None) -> bool:
    return _in_window({"start": f"{cfg.night_start % 24:02d}:00", "end": f"{cfg.night_end % 24:02d}:00", "days": "1234567"},
                      now or datetime.now())
