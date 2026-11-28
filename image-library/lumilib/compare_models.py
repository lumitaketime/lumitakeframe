"""實測比較：用你自己的幾張照片，讓兩個（或更多）模型各跑一次，比較花的時間和寫出來的結果。

- 只讀照片，不寫進圖庫（分析結果不會被換掉），結果只存在目錄資料庫的 settings_kv
- 一個模型跑完全部照片再換下一個，避免兩個大模型同時佔用記憶體
- 第一張包含「把模型載入記憶體」的時間，所以速度用其餘照片的中位數
"""
from __future__ import annotations

import json
import random
import sqlite3
import statistics
import threading
import time
from datetime import datetime
from typing import Callable

KEY = "model_compare"
MAX_PHOTOS = 20
MAX_MODELS = 3


def sample(conn: sqlite3.Connection, n: int, seed: int | None = None) -> list[sqlite3.Row]:
    """挑 n 張現在讀得到的照片（硬碟沒接上的跳過）。"""
    from . import db

    rows = conn.execute("SELECT * FROM images WHERE status = 'ok' AND media_type = 'photo' ORDER BY id DESC LIMIT 5000").fetchall()
    random.Random(seed).shuffle(rows)
    out = []
    for r in rows:
        try:
            if db.absolute_path(conn, r).is_file():
                out.append(r)
        except (OSError, TypeError):
            continue
        if len(out) >= n:
            break
    return out


def run(conn: sqlite3.Connection, cfg, client, models: list[str], n: int = 8, stop: threading.Event | None = None,
        progress: Callable[[int, int, str], None] | None = None, seed: int | None = None) -> dict:
    from . import db
    from .analyzer import build_prompt, normalize_result
    from .media import analysis_images

    models = [m for i, m in enumerate(dict.fromkeys(str(x).strip() for x in models if str(x).strip())) if i < MAX_MODELS]
    if len(models) < 2:
        raise ValueError("請選兩個不同的模型來比較")
    photos = sample(conn, max(2, min(MAX_PHOTOS, n)), seed)
    if not photos:
        raise ValueError("目前沒有讀得到的照片：請先接上有照片的硬碟")
    # 先把照片準備好（縮小成送進模型的大小），每個模型用同一份，比較才公平
    prepared = []
    for p in photos:
        try:
            imgs = analysis_images(db.absolute_path(conn, p), p["media_type"], bool(p["is_raw"]), cfg.analyze_max_side,
                                   p["duration"], p["orientation"])
            prepared.append((p, imgs))
        except Exception:  # noqa: BLE001  讀不了的照片就跳過
            continue
    total, done = len(prepared) * len(models), 0
    items = [{"id": p["id"], "name": p["rel_path"].rsplit("/", 1)[-1], "results": {}} for p, _ in prepared]
    stopped = False
    for model in models:
        for k, (p, imgs) in enumerate(prepared):
            if progress:
                progress(done, total, f"{model}：{items[k]['name']}")
            if stop is not None and stop.is_set():
                stopped = True
                break
            t0 = time.monotonic()
            try:
                res = normalize_result(client.describe(model, build_prompt(cfg, p, len(imgs)), imgs))
                out = {"seconds": round(time.monotonic() - t0, 1), **res}
                if not (res["description"] or res["tags"]):
                    out["error"] = "模型回傳空白結果"
            except Exception as exc:  # noqa: BLE001  錯誤照實記下來
                out = {"seconds": round(time.monotonic() - t0, 1), "error": str(exc)[:300]}
            items[k]["results"][model] = out
            done += 1
        if stopped:
            break
    summary = []
    for model in models:
        rs = [it["results"][model] for it in items if model in it["results"]]
        ok = [r for r in rs if not r.get("error")]
        warm = [r["seconds"] for r in ok[1:]] or [r["seconds"] for r in ok]
        summary.append({
            "model": model, "count": len(rs), "ok": len(ok), "errors": len(rs) - len(ok),
            "first_seconds": rs[0]["seconds"] if rs else None,
            "median_seconds": round(statistics.median(warm), 1) if warm else None,
            "tags_avg": round(sum(len(r.get("tags") or []) for r in ok) / len(ok), 1) if ok else 0,
            "text_found": sum(1 for r in ok if r.get("ocr_text")),
        })
    result = {"at": datetime.now().isoformat(timespec="seconds"), "models": summary, "items": items,
              "stopped": stopped, "done": done}
    conn.execute("INSERT OR REPLACE INTO settings_kv (key, value) VALUES (?, ?)", (KEY, json.dumps(result, ensure_ascii=False)))
    conn.commit()
    return result


def last(conn: sqlite3.Connection) -> dict | None:
    r = conn.execute("SELECT value FROM settings_kv WHERE key = ?", (KEY,)).fetchone()
    try:
        return json.loads(r["value"]) if r else None
    except ValueError:
        return None


def describe(res: dict) -> str:
    parts = []
    for m in res.get("models", []):
        speed = f"每張約 {m['median_seconds']} 秒" if m.get("median_seconds") is not None else "沒有成功"
        parts.append(f"{m['model']}：{speed}")
    head = "已停止比較" if res.get("stopped") else "比較完成"
    return head + ("（" + "；".join(parts) + "）" if parts else "")
