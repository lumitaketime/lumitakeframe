"""關鍵字雲：依出現在幾張照片統計 AI 關鍵字、檔案內原有的關鍵字與我的標籤。"""

from __future__ import annotations

import sqlite3

from . import db


def keyword_counts(conn: sqlite3.Connection, source: str = "all", year: str | None = None,
                   limit: int = 300) -> list[dict]:
    """關鍵字雲：依出現在幾張照片排序（同一張照片同一個詞只算一次，不分大小寫）。

    source：all（全部）、ai（AI 關鍵字）、mine（我的關鍵字＋檔案內原有的關鍵字）。
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
