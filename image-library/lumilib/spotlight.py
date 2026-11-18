"""Spotlight：Mac App 把「重要項目」放進 App 專用的 Spotlight 索引（Core Spotlight，只存在這台 Mac，不上傳）。

這裡只決定要放哪些項目；放進 Spotlight、點下去打開 Re'memor 跳到那裡，由 Mac App 外殼（desktop/src-tauri）處理。
試驗版：每顆硬碟（包括沒接上的）與智慧資料夾。不放一百萬個檔案，避免拖慢 Spotlight、蓋掉 Mac 上原本的結果。

每一項：{id, path（Re'memor 裡的頁面）, title, description, keywords, type（Spotlight 用的內容類型）}。
id 就是「rememor:」加上頁面路徑，點下去時直接照著打開，不用另外記對照表。
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from urllib.parse import urlencode

from .catalog import drives_overview


def _size(n: int) -> str:
    n = float(n or 0)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit in ("B", "KB") else f"{n:.1f} {unit}"
        n /= 1024
    return ""


def items(conn: sqlite3.Connection) -> list[dict]:
    out = []
    for d in drives_overview(conn):
        if not d["roots"]:
            continue
        path = f"/folders/{d['roots'][0]['id']}"
        state = "已接上" if d["online"] else "沒接上（目錄裡還看得到）"
        when = (d.get("last_scan") or "")[:10]
        desc = "硬碟 · " + " · ".join(x for x in (state, f"{d['files']:,} 個檔案", _size(d["bytes"]), f"上次掃描 {when}" if when else "") if x)
        out.append({"id": "rememor:" + path, "path": path, "title": d["name"], "description": desc,
                    "keywords": ["Re'memor", "硬碟", "drive", *[r["name"] for r in d["roots"]]], "type": "public.volume"})
    for r in conn.execute("SELECT id, name, query FROM smart_folders ORDER BY name"):
        try:
            q = json.loads(r["query"])
        except ValueError:
            q = {}
        params = {k: q[k] for k in ("q", "root", "path", "kind", "year", "size", "drive") if q.get(k) not in (None, "")}
        params["smart"] = r["id"]
        path = "/find?" + urlencode(params)
        out.append({"id": "rememor:" + path, "path": path, "title": r["name"], "description": f"智慧資料夾 · 搜尋「{q.get('q', '')}」",
                    "keywords": ["Re'memor", "智慧資料夾", "smart folder", str(q.get("q", ""))], "type": "public.folder"})
    return out


def payload(conn: sqlite3.Connection, enabled: bool = True) -> dict:
    """給 Mac App 的清單；version 變了才需要重新放進 Spotlight。"""
    if not enabled:
        return {"enabled": False, "version": "off", "items": []}
    data = items(conn)
    version = hashlib.sha1(json.dumps(data, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:12]
    return {"enabled": True, "version": version, "items": data}
