"""整理工具：RAW+JPEG／連拍疊放、重複與相似照片、智慧相簿、那年今日。"""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime
from pathlib import Path

import numpy as np
from PIL import Image

from . import db
from .config import Config
from .media import RAW_EXTENSIONS, thumb_path

# ---- 疊放 ---------------------------------------------------------------------
# stack_id：NULL＝未疊放、>0＝自動疊放、0＝使用者解除（不再自動）、<0＝手動疊放（-封面 id）


def _ts(iso: str | None) -> float | None:
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso).timestamp()
    except ValueError:
        return None


def rebuild_stacks(conn: sqlite3.Connection, cfg: Config) -> int:
    """重新計算自動疊放，回傳疊放組數。手動疊放與手動解除的照片不受影響。"""
    conn.execute("UPDATE images SET stack_id = NULL, stack_top = 1 WHERE stack_id > 0")
    if not cfg.stack_enabled:
        conn.commit()
        return 0
    rows = conn.execute(
        "SELECT id, root_id, folder, rel_path, camera, taken_at, sort_at, rating, favorite, is_raw, media_type, stack_id "
        "FROM images WHERE status = 'ok' AND media_type = 'photo' "
        "ORDER BY root_id, folder, camera, taken_at, rel_path"
    ).fetchall()

    # 1) 同資料夾同檔名（不含副檔名）的 RAW＋JPEG 視為一張「影格」
    frames: dict[tuple, list] = {}
    order: list[tuple] = []
    for r in rows:
        if r["stack_id"] is not None:  # 手動處理過的不動
            continue
        stem = Path(r["rel_path"]).stem.lower()
        key = (r["root_id"], r["folder"], stem)
        if key not in frames:
            frames[key] = []
            order.append(key)
        frames[key].append(r)

    # 2) 依時間排序，連續且間隔不超過 burst_seconds、同相機的影格合成連拍
    def frame_time(members):
        return min((t for t in (_ts(m["taken_at"]) for m in members) if t is not None), default=None)

    groups: list[list] = []
    current: list = []
    last_key = None
    last_time = None
    seq = sorted(order, key=lambda k: (k[0], k[1], frames[k][0]["camera"] or "", frame_time(frames[k]) or 0, k[2]))
    for key in seq:
        members = frames[key]
        t = frame_time(members)
        same_place = last_key is not None and key[:2] == last_key[:2] and (members[0]["camera"] or "") == (frames[last_key][0]["camera"] or "")
        if current and same_place and t is not None and last_time is not None and t - last_time <= cfg.burst_seconds:
            current.append(members)
        else:
            if current:
                groups.append(current)
            current = [members]
        last_key, last_time = key, t
    if current:
        groups.append(current)

    count = 0
    for group in groups:
        is_burst = len(group) >= 3
        if is_burst:
            items = [m for frame in group for m in frame]
        else:
            # 不是連拍：只疊放 RAW＋JPEG 同名組
            for frame in group:
                if len(frame) > 1 and any(m["is_raw"] for m in frame) and any(not m["is_raw"] for m in frame):
                    _assign(conn, frame)
                    count += 1
            continue
        _assign(conn, items)
        count += 1
    conn.commit()
    return count


def _cover(items: list) -> sqlite3.Row:
    """封面：星等最高 → 我的最愛 → 非 RAW（顯示較快）→ 最早的一張。"""
    return sorted(items, key=lambda m: (-(m["rating"] or 0), -(m["favorite"] or 0), m["is_raw"], m["sort_at"] or "", m["id"]))[0]


def _assign(conn: sqlite3.Connection, items: list, manual: bool = False) -> int:
    cover = _cover(items)
    stack_id = -cover["id"] if manual else cover["id"]
    conn.executemany(
        "UPDATE images SET stack_id = ?, stack_top = ? WHERE id = ?",
        [(stack_id, 1 if m["id"] == cover["id"] else 0, m["id"]) for m in items],
    )
    return stack_id


def stack_members(conn: sqlite3.Connection, stack_id: int) -> list[sqlite3.Row]:
    if not stack_id:
        return []
    return conn.execute(
        "SELECT * FROM images WHERE stack_id = ? AND status = 'ok' ORDER BY stack_top DESC, sort_at, rel_path",
        (stack_id,),
    ).fetchall()


def unstack(conn: sqlite3.Connection, stack_id: int) -> None:
    conn.execute("UPDATE images SET stack_id = 0, stack_top = 1 WHERE stack_id = ?", (stack_id,))
    conn.commit()


def make_stack(conn: sqlite3.Connection, image_ids: list[int]) -> int:
    rows = conn.execute(
        f"SELECT * FROM images WHERE id IN ({','.join('?' * len(image_ids))})", [int(i) for i in image_ids]
    ).fetchall()
    if len(rows) < 2:
        raise ValueError("至少選兩張才能疊放")
    old = {r["stack_id"] for r in rows if r["stack_id"]}
    for sid in old:  # 合併原本的疊放
        rows += [r for r in stack_members(conn, sid) if r["id"] not in {x["id"] for x in rows}]
    stack_id = _assign(conn, rows, manual=True)
    conn.commit()
    return stack_id


def set_cover(conn: sqlite3.Connection, image_id: int) -> None:
    row = db.get_image(conn, image_id)
    if row is None or not row["stack_id"]:
        raise ValueError("這張不在疊放中")
    members = stack_members(conn, row["stack_id"])
    # 改了封面就變成手動疊放，避免下次自動計算又改回去
    new_id = -image_id
    conn.executemany(
        "UPDATE images SET stack_id = ?, stack_top = ? WHERE id = ?",
        [(new_id, 1 if m["id"] == image_id else 0, m["id"]) for m in members],
    )
    conn.commit()


# ---- 重複與相似 -----------------------------------------------------------------

def dhash(img: Image.Image) -> str:
    """64 位元差異雜湊（形狀）＋四個象限的平均顏色。

    差異雜湊只看明暗變化，縮圖、重新壓縮、改尺寸後仍幾乎相同；
    再加上顏色，避免構圖相似但顏色完全不同的照片被當成重複。
    """
    small = img.convert("L").resize((9, 8), Image.Resampling.LANCZOS)
    px = np.asarray(small, dtype=np.int16)
    bits = (px[:, 1:] > px[:, :-1]).flatten()
    value = 0
    for b in bits:
        value = (value << 1) | int(b)
    quads = np.asarray(img.convert("RGB").resize((2, 2), Image.Resampling.BOX), dtype=np.uint8).flatten()
    return f"{value:016x}" + quads.tobytes().hex()


HASH_LEN = 16 + 24


def fill_hashes(conn: sqlite3.Connection, cfg: Config, progress=None, stop=None) -> int:
    rows = conn.execute(
        "SELECT id, fingerprint FROM images WHERE status = 'ok' AND thumb_ok = 1 "
        "AND (phash IS NULL OR length(phash) != ?)", (HASH_LEN,)
    ).fetchall()
    done = 0
    for n, r in enumerate(rows, 1):
        if stop is not None and stop.is_set():
            break
        path = thumb_path(cfg.thumbs_dir, r["fingerprint"])
        if not path.exists():
            continue
        try:
            with Image.open(path) as img:
                h = dhash(img)
        except OSError:
            continue
        conn.execute("UPDATE images SET phash = ? WHERE id = ?", (h, r["id"]))
        done += 1
        if n % 500 == 0:
            conn.commit()
            if progress:
                progress(n, len(rows), "計算相似度指紋")
    conn.commit()
    return done


def _popcount(x: np.ndarray) -> np.ndarray:
    if hasattr(np, "bitwise_count"):
        return np.bitwise_count(x)
    table = np.array([bin(i).count("1") for i in range(256)], dtype=np.uint8)
    return table[x.view(np.uint8).reshape(*x.shape, 8)].sum(axis=-1)


def find_duplicates(conn: sqlite3.Connection, cfg: Config, threshold: int | None = None, color_tolerance: int = 22,
                    progress=None, stop=None) -> dict:
    """回傳 {"exact": [[id...]], "similar": [[id...]]} 並存到資料目錄。"""
    if threshold is None:
        threshold = int(getattr(cfg, "dup_threshold", 6) or 6)
    fill_hashes(conn, cfg, progress, stop)
    exact = [
        [int(x) for x in r[0].split(",")]
        for r in conn.execute(
            "SELECT GROUP_CONCAT(id) FROM images WHERE status = 'ok' GROUP BY fingerprint, size HAVING COUNT(*) > 1"
        )
    ]
    exact_ids = {i for g in exact for i in g}
    rows = conn.execute(
        "SELECT id, phash, root_id, folder, rel_path FROM images WHERE status = 'ok' AND length(phash) = ? ORDER BY id",
        (HASH_LEN,),
    ).fetchall()
    ids = np.array([r["id"] for r in rows], dtype=np.int64)
    hashes = np.array([int(r["phash"][:16], 16) for r in rows], dtype=np.uint64)
    colors = np.array([list(bytes.fromhex(r["phash"][16:])) for r in rows], dtype=np.int16).reshape(-1, 12)
    stems = [(r["root_id"], r["folder"], Path(r["rel_path"]).stem.lower()) for r in rows]
    parent = list(range(len(rows)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    chunk = 256
    for start in range(0, len(rows), chunk):
        if stop is not None and stop.is_set():
            break
        block = hashes[start:start + chunk]
        dist = _popcount(block[:, None] ^ hashes[None, :])
        ii, jj = np.nonzero(dist <= threshold)
        for a, b in zip(ii + start, jj):
            if b <= a or stems[a] == stems[b]:  # 同名 RAW＋JPEG 不算重複
                continue
            if np.abs(colors[a] - colors[b]).mean() > color_tolerance:  # 形狀像但顏色不同
                continue
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb
        if progress:
            progress(min(start + chunk, len(rows)), len(rows), "比對相似照片")

    clusters: dict[int, list[int]] = {}
    for i in range(len(rows)):
        clusters.setdefault(find(i), []).append(int(ids[i]))
    similar = [g for g in clusters.values() if len(g) > 1 and not set(g) <= exact_ids]
    ignored = {r[0] for r in conn.execute("SELECT value FROM settings_kv WHERE key LIKE 'dup_ignore:%'")}
    key = lambda g: ",".join(map(str, sorted(g)))  # noqa: E731
    result = {
        "computed_at": db.now_iso(),
        "exact": [g for g in exact if key(g) not in ignored],
        "similar": sorted([g for g in similar if key(g) not in ignored], key=len, reverse=True),
    }
    (cfg.home / "duplicates.json").write_text(json.dumps(result), encoding="utf-8")
    return result


def ignore_group(conn: sqlite3.Connection, ids: list[int]) -> None:
    value = ",".join(map(str, sorted(int(i) for i in ids)))
    conn.execute("INSERT OR REPLACE INTO settings_kv (key, value) VALUES (?, ?)", (f"dup_ignore:{value}", value))
    conn.commit()


def load_duplicates(conn: sqlite3.Connection, cfg: Config) -> dict | None:
    path = cfg.home / "duplicates.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    alive = {r[0] for r in conn.execute("SELECT id FROM images WHERE status = 'ok'")}
    ignored = {r[0] for r in conn.execute("SELECT value FROM settings_kv WHERE key LIKE 'dup_ignore:%'")}
    for kind in ("exact", "similar"):
        groups = []
        for g in data.get(kind, []):
            g = [i for i in g if i in alive]
            if len(g) > 1 and ",".join(map(str, sorted(g))) not in ignored:
                groups.append(g)
        data[kind] = groups
    return data


def suggest_keep(rows: list) -> int:
    """建議保留：星等 → 我的最愛 → RAW → 解析度 → 檔案大 → 最早。"""
    return sorted(rows, key=lambda r: (
        -(r["rating"] or 0), -(r["favorite"] or 0), -r["is_raw"], -((r["width"] or 0) * (r["height"] or 0)),
        -(r["size"] or 0), r["sort_at"] or "", r["id"],
    ))[0]["id"]


# ---- 智慧相簿 -------------------------------------------------------------------

def list_smart(conn: sqlite3.Connection) -> list[dict]:
    from .search import search

    out = []
    for r in conn.execute("SELECT * FROM smart_albums ORDER BY updated_at DESC").fetchall():
        res = search(conn, r["query"], limit=1)
        out.append({**dict(r), "count": res["total"], "cover": res["results"][0]["id"] if res["results"] else None})
    return out


def save_smart(conn: sqlite3.Connection, name: str, query: str, smart_id: int | None = None) -> int:
    name = (name or "").strip() or query.strip() or "智慧相簿"
    if not query.strip():
        raise ValueError("搜尋條件不能是空的")
    now = db.now_iso()
    if smart_id:
        conn.execute("UPDATE smart_albums SET name = ?, query = ?, updated_at = ? WHERE id = ?", (name, query, now, smart_id))
    else:
        smart_id = conn.execute(
            "INSERT INTO smart_albums (name, query, created_at, updated_at) VALUES (?, ?, ?, ?)", (name, query, now, now)
        ).lastrowid
    conn.commit()
    return smart_id


# ---- 那年今日 -------------------------------------------------------------------

def memories(conn: sqlite3.Connection, today: date | None = None, window: int = 3, per_year: int = 40) -> list[dict]:
    """往年同一天（前後 window 天）的照片，依年份分組；優先星等高、我的最愛。"""
    today = today or date.today()
    days = []
    for d in range(-window, window + 1):
        x = date.fromordinal(today.toordinal() + d)
        days.append(f"{x.month:02d}-{x.day:02d}")
    rows = conn.execute(
        f"SELECT * FROM images WHERE status = 'ok' AND taken_at IS NOT NULL AND stack_top = 1 "
        f"AND substr(taken_at, 6, 5) IN ({','.join('?' * len(days))}) AND substr(taken_at, 1, 4) < ? "
        f"ORDER BY taken_at",
        (*days, str(today.year)),
    ).fetchall()
    by_year: dict[int, list] = {}
    for r in rows:
        by_year.setdefault(int(r["taken_at"][:4]), []).append(r)
    out = []
    for year in sorted(by_year, reverse=True):
        items = by_year[year]
        best = sorted(items, key=lambda r: (-(r["rating"] or 0), -(r["favorite"] or 0), r["taken_at"]))
        out.append({"year": year, "years_ago": today.year - year, "count": len(items), "rows": best[:per_year]})
    return out
