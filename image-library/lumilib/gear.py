"""器材：依 EXIF 統計相機、鏡頭、焦段、光圈、ISO，並列出符合的照片（完全比對）。"""

from __future__ import annotations

import sqlite3

from . import db

# 焦段以等效 35mm 為準（沒有時用實際焦距）
FOCAL_BUCKETS = [
    ("超廣角", 0, 20), ("廣角", 20, 35), ("標準", 35, 70), ("中望遠", 70, 135), ("望遠", 135, 300), ("超望遠", 300, 10000),
]
APERTURE_BUCKETS = [
    ("f/1.4 以下", 0, 1.45), ("f/1.8–2", 1.45, 2.05), ("f/2.8", 2.05, 3.0), ("f/4", 3.0, 4.5),
    ("f/5.6–8", 4.5, 8.5), ("f/11 以上", 8.5, 100),
]
ISO_BUCKETS = [
    ("ISO 200 以下", 0, 200), ("ISO 400–800", 201, 800), ("ISO 1600–3200", 801, 3200),
    ("ISO 6400–12800", 3201, 12800), ("ISO 25600 以上", 12801, 10_000_000),
]
FOCAL_SQL = "COALESCE(i.focal_35, i.focal_length)"


def _buckets(conn, expr: str, buckets) -> list[dict]:
    out = []
    for label, lo, hi in buckets:
        n = conn.execute(
            f"SELECT COUNT(*) FROM images i WHERE i.status = 'ok' AND i.stack_top = 1 AND {expr} > ? AND {expr} <= ?",
            (lo, hi),
        ).fetchone()[0]
        out.append({"label": label, "min": lo, "max": hi, "count": n})
    return out


def stats(conn: sqlite3.Connection) -> dict:
    def grouped(column: str, extra: str = ""):
        rows = conn.execute(
            f"""SELECT {column} AS name, COUNT(*) AS count, MIN(i.sort_at) AS first, MAX(i.sort_at) AS last,
                       MAX(i.id) AS cover {extra}
                FROM images i WHERE i.status = 'ok' AND i.stack_top = 1 AND {column} IS NOT NULL AND {column} != ''
                GROUP BY {column} ORDER BY count DESC"""
        ).fetchall()
        return [dict(r) for r in rows]

    cameras = grouped("i.camera")
    lenses = grouped("i.lens")
    for lens in lenses:
        lens["cameras"] = [r[0] for r in conn.execute(
            "SELECT camera FROM images WHERE lens = ? AND camera IS NOT NULL GROUP BY camera ORDER BY COUNT(*) DESC LIMIT 3",
            (lens["name"],),
        )]
    combos = [dict(r) for r in conn.execute(
        """SELECT i.camera AS camera, i.lens AS lens, COUNT(*) AS count FROM images i
           WHERE i.status = 'ok' AND i.stack_top = 1 AND i.camera IS NOT NULL AND i.lens IS NOT NULL
           GROUP BY i.camera, i.lens ORDER BY count DESC LIMIT 20"""
    )]
    no_exif = conn.execute(
        "SELECT COUNT(*) FROM images WHERE status = 'ok' AND stack_top = 1 AND (camera IS NULL OR camera = '')"
    ).fetchone()[0]
    return {
        "cameras": cameras,
        "lenses": lenses,
        "combos": combos,
        "focal": _buckets(conn, FOCAL_SQL, FOCAL_BUCKETS),
        "aperture": _buckets(conn, "i.aperture", APERTURE_BUCKETS),
        "iso": _buckets(conn, "i.iso", ISO_BUCKETS),
        "no_exif": no_exif,
    }


def _range(value: str | None) -> tuple[float, float] | None:
    if not value:
        return None
    lo, _, hi = str(value).partition("-")
    try:
        return float(lo), float(hi) if hi else float(lo)
    except ValueError:
        return None


def assets(conn: sqlite3.Connection, camera=None, lens=None, focal=None, aperture=None, iso=None,
           limit: int = 3000) -> list[sqlite3.Row]:
    """完全比對相機、鏡頭；焦段／光圈／ISO 為 'min-max'（不含 min、含 max）。"""
    from .search import STACK_COUNT_SQL

    where, params = ["i.status = 'ok'", "i.stack_top = 1"], []
    if camera:
        where.append("i.camera = ?")
        params.append(camera)
    if lens:
        where.append("i.lens = ?")
        params.append(lens)
    for expr, value in ((FOCAL_SQL, focal), ("i.aperture", aperture), ("i.iso", iso)):
        r = _range(value)
        if r:
            where.append(f"{expr} > ? AND {expr} <= ?")
            params += [r[0], r[1]]
    return conn.execute(
        f"SELECT i.*, {STACK_COUNT_SQL} FROM images i WHERE {' AND '.join(where)} "
        f"ORDER BY i.sort_at DESC, i.id DESC LIMIT ?",
        params + [limit],
    ).fetchall()


def count(conn: sqlite3.Connection, **filters) -> int:
    return len(assets(conn, limit=10_000_000, **filters))


def keyword_counts(conn: sqlite3.Connection, source: str = "all", year: str | None = None,
                   limit: int = 300) -> list[dict]:
    """關鍵字雲：依出現在幾張照片排序（同一張照片同一個詞只算一次，不分大小寫）。

    source：all（全部）、ai（AI 關鍵字）、mine（我的關鍵字＋Lightroom）。
    """
    cols = {"ai": ["tags"], "mine": ["keywords", "user_tags"]}.get(source, ["tags", "keywords", "user_tags"])
    where = "status = 'ok'"
    params: list = []
    if year and str(year).isdigit():
        where += " AND substr(sort_at, 1, 4) = ?"
        params.append(str(year))
    counts: dict[str, int] = {}
    display: dict[str, str] = {}
    kinds: dict[str, set] = {}
    for row in conn.execute(f"SELECT {', '.join(cols)} FROM images WHERE {where}", params):
        seen = set()
        for col in cols:
            for tag in db.json_list(row[col]):
                key = tag.strip().lower()
                if not key or key in seen:
                    continue
                seen.add(key)
                counts[key] = counts.get(key, 0) + 1
                display.setdefault(key, tag.strip())
                kinds.setdefault(key, set()).add("ai" if col == "tags" else "mine")
    top = sorted(counts.items(), key=lambda x: (-x[1], x[0]))[:limit]
    return [{"tag": display[k], "count": n, "kind": "mine" if "mine" in kinds[k] else "ai"} for k, n in top]


def years(conn: sqlite3.Connection) -> list[str]:
    return [r[0] for r in conn.execute(
        "SELECT DISTINCT substr(sort_at, 1, 4) FROM images WHERE status = 'ok' AND sort_at IS NOT NULL ORDER BY 1 DESC"
    )]
