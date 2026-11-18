"""硬碟健康：先看硬碟自己的檢測（SMART）與 Re'memor 讀取時遇到的錯誤；有問題就先停下來問本人，不自己繼續。

為什麼：老硬碟長時間連續讀取有故障風險（規劃書「限制與注意事項」）。有狀況的硬碟應該先備份重要檔案，
而不是繼續整顆讀過一遍。所以：
- 每次要在一顆硬碟上做事（掃描、比對內容、讀文件文字、文字辨識）之前，先看它的健康狀態。
- 「注意」或「有問題」而且本人還沒決定怎麼處理：這顆硬碟先不碰，其他硬碟照常；畫面上提醒並請本人選：
  先暫停（我去備份）／只記錄檔名、不讀內容／照常進行。本人的決定記下來，狀況變得更糟時會再問一次。
- 做事途中讀取錯誤（I/O error）累積到一定數量，也立刻停下這顆硬碟的工作，再問一次。

怎麼看：
- macOS 的 diskutil 會告訴我們硬碟自我檢測（SMART）的結論：正常、即將故障、或不支援（USB 外接盒多半不支援）。
- 有安裝 smartctl（smartmontools）的話，再讀詳細數字：壞軌、等待替換的磁區、無法修正的錯誤、使用時數。
- 都只讀取，不寫入硬碟，也不做表面掃描（那會整顆讀一遍）。
"""

from __future__ import annotations

import errno
import json
import os
import plistlib
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

from . import db

IO_WARN = 10  # 讀取錯誤累積到這麼多次：「注意」
IO_FAIL = 100  # 累積到這麼多次：「有問題」
RECHECK_SECONDS = 6 * 3600  # 多久重新看一次硬碟的自我檢測
IO_ERRNOS = {errno.EIO, errno.ENXIO, getattr(errno, "ETIMEDOUT", 60)}
LEVEL = {"ok": 0, "unknown": 0, "warn": 1, "fail": 2}
DECISIONS = ("pause", "light", "continue")  # 先暫停／只記錄檔名、不讀內容／照常進行



# ---- 硬碟是誰 ----

def key_of(root: sqlite3.Row | dict) -> str:
    """同一顆實體硬碟上的幾個資料夾來源共用一筆健康紀錄。"""
    return f"d:{root['drive_id']}" if root["drive_id"] is not None else f"r:{root['id']}"


def _name(conn: sqlite3.Connection, root) -> str:
    if root["drive_id"] is not None:
        r = conn.execute("SELECT name FROM drives WHERE id = ?", (root["drive_id"],)).fetchone()
        if r and r["name"]:
            return r["name"]
    return root["name"]


# ---- 讀硬碟的自我檢測 ----

def _run(args: list[str], timeout: int = 20) -> bytes | None:
    try:
        return subprocess.run(args, capture_output=True, timeout=timeout).stdout
    except (OSError, subprocess.SubprocessError):
        return None


def smartctl() -> str | None:
    for p in ("/opt/homebrew/sbin/smartctl", "/usr/local/sbin/smartctl", "/opt/homebrew/bin/smartctl", "/usr/local/bin/smartctl"):
        if os.path.exists(p):
            return p
    return shutil.which("smartctl")


def read_smart(path: str) -> dict:
    """{"smart": Verified／Failing／Not Supported／None, "attrs": {...}, "device": "disk4", "usb": bool}。只讀取。"""
    out: dict = {"smart": None, "attrs": {}, "device": None, "usb": False}
    if sys.platform != "darwin":
        return out
    raw = _run(["diskutil", "info", "-plist", path])
    if raw:
        try:
            info = plistlib.loads(raw)
        except Exception:  # noqa: BLE001
            info = {}
        out["smart"] = info.get("SMARTStatus")
        out["device"] = info.get("ParentWholeDisk") or info.get("DeviceIdentifier")
        out["usb"] = str(info.get("BusProtocol") or info.get("Protocol") or "").upper() == "USB"
    tool = smartctl()
    if tool and out["device"]:
        for extra in ([], ["-d", "sat"]):
            raw = _run([tool, "-j", "-a", *extra, f"/dev/{out['device']}"], timeout=30)
            try:
                data = json.loads(raw or b"{}")
            except ValueError:
                continue
            if data.get("smart_status") or data.get("ata_smart_attributes") or data.get("nvme_smart_health_information_log"):
                out["attrs"] = _attrs(data)
                break
    return out


def _attrs(data: dict) -> dict:
    a: dict = {}
    if isinstance(data.get("smart_status"), dict) and "passed" in data["smart_status"]:
        a["passed"] = bool(data["smart_status"]["passed"])
    names = {5: "reallocated", 187: "uncorrectable_reported", 197: "pending", 198: "offline_uncorrectable", 199: "crc"}
    for row in (data.get("ata_smart_attributes") or {}).get("table") or []:
        if row.get("id") in names:
            a[names[row["id"]]] = int((row.get("raw") or {}).get("value") or 0)
    nvme = data.get("nvme_smart_health_information_log") or {}
    if nvme:
        a["critical_warning"] = int(nvme.get("critical_warning") or 0)
        a["media_errors"] = int(nvme.get("media_errors") or 0)
        a["percentage_used"] = int(nvme.get("percentage_used") or 0)
    hours = (data.get("power_on_time") or {}).get("hours")
    if hours:
        a["hours"] = int(hours)
    return a


def assess(smart: str | None, attrs: dict, io_errors: int) -> tuple[str, list[dict]]:
    """依自我檢測與讀取錯誤判斷：ok／warn／fail／unknown，以及給人看的發現（每一項 {level, text}）。"""
    found: list[dict] = []

    def add(level: str, text: str) -> None:
        found.append({"level": level, "text": text})

    if smart == "Failing" or attrs.get("passed") is False:
        add("fail", "硬碟的自我檢測回報「即將故障」")
    bad = attrs.get("reallocated", 0)
    if bad:
        add("fail" if bad >= 100 else "warn", f"有 {bad:,} 個壞掉、已經被替換掉的磁區")
    pend = attrs.get("pending", 0) + attrs.get("offline_uncorrectable", 0)
    if pend:
        add("fail" if pend >= 50 else "warn", f"有 {pend:,} 個讀不穩定的磁區（裡面的資料可能已經讀不出來）")
    unc = attrs.get("uncorrectable_reported", 0) + attrs.get("media_errors", 0)
    if unc:
        add("warn", f"發生過 {unc:,} 次無法修正的讀取錯誤")
    if attrs.get("critical_warning"):
        add("fail", "固態硬碟回報嚴重警告")
    if attrs.get("percentage_used", 0) >= 90:
        add("warn", f"固態硬碟的壽命已經用掉 {attrs['percentage_used']}%")
    if attrs.get("crc"):
        add("info", f"傳輸時出錯 {attrs['crc']:,} 次：多半是線材或接頭鬆了，可以換條線試試")
    if attrs.get("hours", 0) >= 35_000:
        add("info", f"已經運轉大約 {attrs['hours'] // 8760} 年（{attrs['hours']:,} 小時）")
    if io_errors >= IO_FAIL:
        add("fail", f"Re'memor 讀取時遇到 {io_errors:,} 次讀取錯誤")
    elif io_errors >= IO_WARN:
        add("warn", f"Re'memor 讀取時遇到 {io_errors:,} 次讀取錯誤")
    if any(f["level"] == "fail" for f in found):
        return "fail", found
    if any(f["level"] == "warn" for f in found):
        return "warn", found
    if smart == "Verified" or attrs:
        return "ok", found
    return "unknown", found


# ---- 紀錄 ----

def _row(conn: sqlite3.Connection, key: str):
    return conn.execute("SELECT * FROM drive_health WHERE key = ?", (key,)).fetchone()


def check(conn: sqlite3.Connection, root, force: bool = False, reader=read_smart) -> dict:
    """看一顆硬碟的健康（只讀取）。最近看過就用上次的結果，除非 force。"""
    key = key_of(root)
    old = _row(conn, key)
    if old is not None and not force and old["checked_at"]:
        try:
            age = time.time() - time.mktime(time.strptime(old["checked_at"][:19], "%Y-%m-%dT%H:%M:%S"))
        except ValueError:
            age = RECHECK_SECONDS
        if age < RECHECK_SECONDS:
            return public(old)
    data = reader(root["path"]) if Path(root["path"]).is_dir() else {"smart": None, "attrs": {}}
    io_errors = old["io_errors"] if old is not None else 0
    status, findings = assess(data.get("smart"), data.get("attrs") or {}, io_errors)
    _save(conn, key, _name(conn, root), status, data.get("smart"), findings, io_errors, old)
    return public(_row(conn, key))


def _save(conn, key, name, status, smart, findings, io_errors, old) -> None:
    conn.execute(
        "INSERT INTO drive_health (key, name, status, smart, findings, io_errors, checked_at) VALUES (?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(key) DO UPDATE SET name = excluded.name, status = excluded.status, smart = excluded.smart, "
        "findings = excluded.findings, io_errors = excluded.io_errors, checked_at = excluded.checked_at",
        (key, name, status, smart, json.dumps(findings, ensure_ascii=False), io_errors, db.now_iso()))
    conn.commit()


def public(r) -> dict:
    status = r["status"]
    need = LEVEL.get(status, 0) > 0 and (r["decision"] is None or (r["decided_level"] or 0) < LEVEL[status])
    return {"key": r["key"], "name": r["name"], "status": status, "smart": r["smart"],
            "findings": json.loads(r["findings"] or "[]"), "io_errors": r["io_errors"], "checked_at": r["checked_at"],
            "decision": None if need else r["decision"], "needs_decision": need}


def listing(conn: sqlite3.Connection) -> list[dict]:
    return [public(r) for r in conn.execute("SELECT * FROM drive_health ORDER BY name")]


def alerts(conn: sqlite3.Connection) -> list[dict]:
    """等本人決定怎麼處理的硬碟。"""
    return [h for h in listing(conn) if h["needs_decision"]]


def decide(conn: sqlite3.Connection, key: str, decision: str) -> dict:
    if decision not in DECISIONS:
        raise ValueError("不認得的處理方式")
    r = _row(conn, key)
    if r is None:
        raise ValueError("找不到這顆硬碟")
    conn.execute("UPDATE drive_health SET decision = ?, decided_level = ?, decided_at = ? WHERE key = ?",
                 (decision, LEVEL.get(r["status"], 0), db.now_iso(), key))
    conn.commit()
    return public(_row(conn, key))


# ---- 在硬碟上做事之前：可以做嗎？ ----

def gate(conn: sqlite3.Connection, root, purpose: str, reader=read_smart) -> str:
    """purpose：scan（只看檔名與資料夾）或 read（讀檔案內容：比對、讀文字、辨識）。
    回傳 go（可以做）或 hold（先不碰，等本人決定或本人選了暫停）。只在硬碟接著時才看。"""
    if not Path(root["path"]).is_dir():
        return "go"  # 沒接上：各工作自己會略過
    h = check(conn, root, reader=reader)
    if LEVEL.get(h["status"], 0) == 0:
        return "go"
    if h["needs_decision"] or h["decision"] == "pause":
        return "hold"
    if h["decision"] == "light":
        return "go" if purpose == "scan" else "hold"
    return "go"


def held_roots(conn: sqlite3.Connection, purpose: str, reader=read_smart) -> set[int]:
    """這次工作要先跳過的資料夾來源（硬碟有狀況、等本人決定）。"""
    out = set()
    for r in conn.execute("SELECT * FROM roots").fetchall():
        try:
            if gate(conn, r, purpose, reader) == "hold":
                out.add(r["id"])
        except Exception:  # noqa: BLE001  健康檢查本身出錯不擋工作
            continue
    return out


def io_error(conn: sqlite3.Connection, root_id: int, exc: BaseException) -> bool:
    """做事途中讀取出錯。是硬碟的讀取錯誤（I/O error）就記下來；累積到門檻、本人還沒決定的話回傳 True＝這顆先停。"""
    if not isinstance(exc, OSError) or exc.errno not in IO_ERRNOS:
        return False
    root = conn.execute("SELECT * FROM roots WHERE id = ?", (root_id,)).fetchone()
    if root is None:
        return False
    key = key_of(root)
    old = _row(conn, key)
    n = (old["io_errors"] if old is not None else 0) + 1
    findings = json.loads(old["findings"] or "[]") if old is not None else []
    smart = old["smart"] if old is not None else None
    status = old["status"] if old is not None else "unknown"
    status, findings = assess(smart, {}, n) if old is None else _merge(old, n)  # 每次都更新次數
    conn.execute(
        "INSERT INTO drive_health (key, name, status, smart, findings, io_errors, checked_at) VALUES (?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(key) DO UPDATE SET io_errors = excluded.io_errors, status = excluded.status, findings = excluded.findings",
        (key, _name(conn, root), status, smart, json.dumps(findings, ensure_ascii=False), n, db.now_iso()))
    conn.commit()
    return public(_row(conn, key))["needs_decision"]


def _merge(old, n: int) -> tuple[str, list[dict]]:
    """在原本的發現上，更新「讀取錯誤」那一項。"""
    findings = [f for f in json.loads(old["findings"] or "[]") if "讀取時遇到" not in f["text"]]
    level = "fail" if n >= IO_FAIL else "warn" if n >= IO_WARN else None
    if level:
        findings.append({"level": level, "text": f"Re'memor 讀取時遇到 {n:,} 次讀取錯誤"})
    status = old["status"]
    if level and LEVEL[level] > LEVEL.get(status, 0):
        status = level
    return status, findings


__all__ = ["check", "gate", "held_roots", "io_error", "decide", "alerts", "listing", "assess", "read_smart", "DECISIONS"]
