"""AI 分析的時段：可以設定只在接上電源、或只在夜間進行，避免筆電耗電與發熱。"""

from __future__ import annotations

import subprocess
import sys
import time
from datetime import datetime

from .config import Config

MODES = {"always": "隨時", "ac": "只在接上電源時", "night": "只在夜間", "ac_night": "夜間且接上電源時"}
_power: dict = {"at": 0.0, "ac": True}


def on_ac_power() -> bool:
    """Mac 是否接上電源（桌機或無法判斷時視為有接）。結果快取 30 秒。"""
    now = time.monotonic()
    if now - _power["at"] < 30:
        return _power["ac"]
    ac = True
    if sys.platform == "darwin":
        try:
            out = subprocess.run(["pmset", "-g", "batt"], capture_output=True, text=True, timeout=3).stdout
            if "Battery Power" in out:
                ac = False
        except (OSError, subprocess.SubprocessError):
            pass
    _power.update(at=now, ac=ac)
    return ac


def in_night(cfg: Config, now: datetime | None = None) -> bool:
    hour = (now or datetime.now()).hour
    start, end = cfg.night_start % 24, cfg.night_end % 24
    if start == end:
        return True
    return start <= hour < end if start < end else hour >= start or hour < end


def analysis_allowed(cfg: Config, now: datetime | None = None) -> tuple[bool, str]:
    mode = cfg.analyze_schedule if cfg.analyze_schedule in MODES else "always"
    if mode in ("ac", "ac_night") and not on_ac_power():
        return False, "使用電池中，接上電源後會自動繼續"
    if mode in ("night", "ac_night") and not in_night(cfg, now):
        return False, f"等待夜間時段（{cfg.night_start}:00–{cfg.night_end}:00）"
    return True, ""
