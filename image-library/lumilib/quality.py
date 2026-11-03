"""照片品質檢查：失焦／手震（模糊）與曝光問題，全部在本機用 numpy 計算，不用 AI 模型。

- 清晰度：把照片縮到長邊 800px 的灰階圖，切成 4×4 格，分別算水平與垂直方向的邊緣強度變異數
  （取較弱的方向，抓得到單一方向的手震），再取最清楚的那一格。只要畫面上有一塊是清楚的（例如淺景深人像的眼睛），就不會被當成模糊。
- 曝光：亮度平均值，以及接近全黑（≤ 8）與接近全白（≥ 247）的像素比例。

結果是「建議」：刻意的動態模糊、夜景、高調／低調作品也可能被列出，由使用者決定。
"""

from __future__ import annotations

import sqlite3
import threading
from typing import Callable

import numpy as np
from PIL import Image

from . import db
from .config import Config
from .media import MediaError, load_image

# 清晰度門檻（越高越嚴格）
LEVELS = {"loose": 20.0, "standard": 45.0, "strict": 70.0}

EXPOSURE_LABELS = {
    "black": "幾乎全黑（例如誤按快門）",
    "white": "幾乎全白",
    "under": "嚴重欠曝",
    "over": "嚴重過曝",
}


def measure(img: Image.Image) -> dict:
    gray = img.convert("L")
    w, h = gray.size
    scale = 800 / max(w, h)
    if scale < 1:
        gray = gray.resize((max(1, round(w * scale)), max(1, round(h * scale))), Image.BILINEAR)
    a = np.asarray(gray, dtype=np.float32)
    # 水平與垂直方向分開算：手震通常只糊一個方向，取較弱的那個
    dxx = a[1:-1, 2:] - 2 * a[1:-1, 1:-1] + a[1:-1, :-2]
    dyy = a[2:, 1:-1] - 2 * a[1:-1, 1:-1] + a[:-2, 1:-1]
    tiles = []
    th, tw = dxx.shape[0] // 4, dxx.shape[1] // 4
    if th > 4 and tw > 4:
        for i in range(4):
            for j in range(4):
                sl = (slice(i * th, (i + 1) * th), slice(j * tw, (j + 1) * tw))
                tiles.append(min(float(dxx[sl].var()), float(dyy[sl].var())))
        tiles.sort(reverse=True)
        sharp = tiles[0]  # 最清楚的那一格（淺景深只有主體清楚也算清楚）
    else:
        sharp = min(float(dxx.var()), float(dyy.var())) if dxx.size else 0.0
    small = a  # 用 800px 的圖算亮度，小光點（夜景燈光）才不會被平均掉
    return {
        "sharpness": round(sharp, 2),
        "luma": round(float(small.mean()), 2),
        "dark_frac": round(float((small <= 8).mean()), 4),
        "bright_frac": round(float((small >= 247).mean()), 5),
        "highlight": round(float(np.percentile(small, 99.9)), 1),  # 最亮的 0.1%：判斷有沒有亮部（夜景的燈）
    }


def exposure_flag(luma: float | None, dark: float | None, bright: float | None, sharp: float | None = None,
                  highlight: float | None = None, under_luma: float = 25, over_frac: float = 0.45) -> str | None:
    if luma is None:
        return None
    flat = sharp is not None and sharp < 15  # 幾乎沒有細節（夜景有燈光、輪廓，不會是 flat）
    if luma < 12 and (dark or 0) > 0.9 and flat:
        return "black"
    if luma > 243 and (bright or 0) > 0.9 and flat:
        return "white"
    if luma < under_luma and (highlight if highlight is not None else 255) < 90:  # 整張很暗、連最亮處都不亮
        return "under"
    if (bright or 0) > over_frac:
        return "over"
    return None


def check_images(conn: sqlite3.Connection, cfg: Config, ids: list[int] | None = None, redo: bool = False,
                 progress: Callable[[int, int, str], None] | None = None,
                 stop: threading.Event | None = None) -> int:
    where = ["status = 'ok'", "media_type = 'photo'"]
    args: list = []
    if not redo:
        where.append("quality_at IS NULL")
    if ids:
        where.append(f"id IN ({','.join('?' * len(ids))})")
        args += [int(i) for i in ids]
    rows = conn.execute(f"SELECT * FROM images WHERE {' AND '.join(where)} ORDER BY sort_at DESC", args).fetchall()
    done = 0
    for n, image in enumerate(rows, 1):
        if stop is not None and stop.is_set():
            break
        path = db.absolute_path(conn, image)
        try:
            img = load_image(path, "photo", bool(image["is_raw"]), 1024, None, image["orientation"])
            m = measure(img)
        except (MediaError, OSError, ValueError):
            # 讀不到的檔案也記錄一下，避免每次都重試
            conn.execute("UPDATE images SET quality_at = ? WHERE id = ?", (db.now_iso(), image["id"]))
            continue
        conn.execute(
            "UPDATE images SET quality_at = ?, sharpness = ?, luma = ?, dark_frac = ?, bright_frac = ?, highlight = ? WHERE id = ?",
            (db.now_iso(), m["sharpness"], m["luma"], m["dark_frac"], m["bright_frac"], m["highlight"], image["id"]),
        )
        done += 1
        if n % 50 == 0:
            conn.commit()
        if progress:
            progress(n, len(rows), image["rel_path"].rsplit("/", 1)[-1])
    conn.commit()
    return done


def blurry(conn: sqlite3.Connection, level: str | float = "standard", limit: int = 2000) -> list[sqlite3.Row]:
    """level：寬鬆／標準／嚴格，或直接給清晰度門檻（設定頁可調）。"""
    threshold = float(level) if isinstance(level, (int, float)) else LEVELS.get(level, LEVELS["standard"])
    return conn.execute(
        "SELECT * FROM images WHERE status = 'ok' AND media_type = 'photo' AND sharpness IS NOT NULL "
        "AND sharpness < ? AND stack_top = 1 AND NOT (luma < 12 OR luma > 243) ORDER BY sharpness ASC LIMIT ?",
        (threshold, limit),
    ).fetchall()


def exposure_problems(conn: sqlite3.Connection, limit: int = 2000, under_luma: float = 25,
                      over_frac: float = 0.45) -> list[tuple[sqlite3.Row, str]]:
    rows = conn.execute(
        "SELECT * FROM images WHERE status = 'ok' AND media_type = 'photo' AND luma IS NOT NULL AND stack_top = 1 "
        "AND (luma < ? OR luma < 12 OR luma > 243 OR bright_frac > ?) ORDER BY sort_at DESC LIMIT ?",
        (under_luma, over_frac, limit),
    ).fetchall()
    out = []
    for r in rows:
        flag = exposure_flag(r["luma"], r["dark_frac"], r["bright_frac"], r["sharpness"], r["highlight"], under_luma, over_frac)
        if flag:
            out.append((r, flag))
    return out
