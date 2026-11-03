"""整理工具的查詢：螢幕截圖與文件、大檔案與大資料夾。"""

from __future__ import annotations

import sqlite3
from collections import defaultdict

FILENAME_WORDS = ["screenshot", "screen shot", "螢幕截圖", "螢幕快照", "截圖", "截屏", "スクリーンショット"]
SCENE_WORDS = ["螢幕截圖", "截圖", "screenshot", "文件", "document", "收據", "receipt", "發票", "單據", "表單", "螢幕"]
TAG_WORDS = ["螢幕截圖", "screenshot", "收據", "receipt", "發票", "invoice"]


def screens_and_documents(conn: sqlite3.Connection, limit: int = 3000) -> list[tuple[sqlite3.Row, str]]:
    """可能是螢幕截圖、文件、收據的照片，附上判斷理由。"""
    rows = conn.execute(
        "SELECT * FROM images WHERE status = 'ok' AND media_type = 'photo' ORDER BY sort_at DESC"
    ).fetchall()
    out = []
    for r in rows:
        name = r["rel_path"].rsplit("/", 1)[-1].lower()
        scene = (r["scene"] or "").strip().lower()
        text = (r["search_text"] or "").lower()
        reason = None
        if any(w in name for w in FILENAME_WORDS):
            reason = "檔名是截圖"
        elif scene and any(w.lower() in scene for w in SCENE_WORDS):
            reason = f"AI 判斷：{r['scene']}"
        elif any(w.lower() in text for w in TAG_WORDS) and r["analyzed_at"]:
            reason = "AI 關鍵字：截圖或收據"
        elif name.endswith(".png") and not (r["camera"] or "").strip() and not r["is_raw"]:
            reason = "PNG 而且沒有相機資訊"
        if reason:
            out.append((r, reason))
            if len(out) >= limit:
                break
    return out


def large_files(conn: sqlite3.Connection, kind: str = "all", limit: int = 200) -> list[sqlite3.Row]:
    where = ["status = 'ok'"]
    if kind == "video":
        where.append("media_type = 'video'")
    elif kind == "photo":
        where.append("media_type = 'photo'")
    elif kind == "raw":
        where.append("is_raw = 1")
    return conn.execute(
        f"SELECT * FROM images WHERE {' AND '.join(where)} ORDER BY size DESC LIMIT ?", (limit,)
    ).fetchall()


def large_folders(conn: sqlite3.Connection, limit: int = 60) -> list[dict]:
    """每個資料夾（含子資料夾）的總大小，由大到小。"""
    roots = {r["id"]: r["name"] for r in conn.execute("SELECT id, name FROM roots")}
    totals: dict[tuple[int, str], list[int]] = defaultdict(lambda: [0, 0, 0])  # 大小、檔案數、影片數
    for r in conn.execute("SELECT root_id, folder, size, media_type FROM images WHERE status = 'ok'"):
        parts = [p for p in (r["folder"] or "").split("/") if p]
        for depth in range(len(parts) + 1):
            key = (r["root_id"], "/".join(parts[:depth]))
            t = totals[key]
            t[0] += r["size"] or 0
            t[1] += 1
            t[2] += 1 if r["media_type"] == "video" else 0
    items = [
        {"root_id": rid, "root": roots.get(rid, ""), "path": path, "name": path.rsplit("/", 1)[-1] if path else roots.get(rid, ""),
         "bytes": v[0], "files": v[1], "videos": v[2]}
        for (rid, path), v in totals.items()
    ]
    items.sort(key=lambda x: x["bytes"], reverse=True)
    return items[:limit]
