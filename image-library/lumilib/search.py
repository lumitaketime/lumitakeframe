"""關鍵字搜尋（可選語意搜尋）。

查詢語法（以空白分隔，全部條件都要符合）：
    貓 沙發             同時包含「貓」與「沙發」
    "日落 海邊"          完整片語
    -狗                 排除包含「狗」的圖片
    tag:貓              只比對關鍵字欄位（模型產生 + 手動標籤）
    folder:京都          路徑包含「京都」
    camera:iphone       相機型號
    ext:heic            副檔名
    year:2023           拍攝年份；after:2023-05-01（含當天）、before:2023-06-01（不含當天）
    root:外接SSD         限定某個登錄的資料夾
    is:pending / is:failed / is:analyzed / is:missing
"""

from __future__ import annotations

import re
import shlex
import sqlite3
from dataclasses import dataclass, field

from . import db

FILTER_KEYS = {"tag", "folder", "camera", "ext", "year", "after", "before", "root", "is"}


@dataclass
class Query:
    terms: list[str] = field(default_factory=list)
    excludes: list[str] = field(default_factory=list)
    filters: list[tuple[str, str]] = field(default_factory=list)

    @property
    def text(self) -> str:
        return " ".join(self.terms)


def parse_query(q: str) -> Query:
    query = Query()
    try:
        tokens = shlex.split(q or "", posix=True)
    except ValueError:  # 引號沒有成對
        tokens = (q or "").replace('"', " ").split()
    for token in tokens:
        token = token.strip()
        if not token:
            continue
        if token.startswith("-") and len(token) > 1:
            query.excludes.append(token[1:].lower())
            continue
        key, sep, value = token.partition(":")
        if sep and key.lower() in FILTER_KEYS and value:
            query.filters.append((key.lower(), value))
            continue
        query.terms.append(token.lower())
    return query


def _like(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _filter_sql(query: Query, include_terms: bool) -> tuple[str, list]:
    where: list[str] = []
    params: list = []
    statuses = {"ok"}
    for key, value in query.filters:
        low = value.lower()
        if key == "tag":
            where.append("(lower(i.tags) LIKE ? ESCAPE '\\' OR lower(i.user_tags) LIKE ? ESCAPE '\\')")
            params += [_like(low), _like(low)]
        elif key == "folder":
            where.append("lower(i.rel_path) LIKE ? ESCAPE '\\'")
            params.append(_like(low))
        elif key == "camera":
            where.append("lower(i.camera) LIKE ? ESCAPE '\\'")
            params.append(_like(low))
        elif key == "ext":
            where.append("lower(i.rel_path) LIKE ? ESCAPE '\\'")
            params.append("%." + low.lstrip(".").replace("%", "").replace("_", "\\_"))
        elif key == "year" and re.fullmatch(r"\d{4}", value):
            where.append("substr(i.taken_at, 1, 4) = ?")
            params.append(value)
        elif key == "after":
            where.append("i.taken_at >= ?")
            params.append(value)
        elif key == "before":
            where.append("i.taken_at < ?")
            params.append(value)
        elif key == "root":
            where.append("(r.name = ? OR CAST(r.id AS TEXT) = ?)")
            params += [value, value]
        elif key == "is":
            if low == "missing":
                statuses = {"missing"}
            elif low == "pending":
                where.append("i.analyzed_at IS NULL AND i.error IS NULL")
            elif low == "failed":
                where.append("i.analyzed_at IS NULL AND i.error IS NOT NULL")
            elif low == "analyzed":
                where.append("i.analyzed_at IS NOT NULL")
    where.insert(0, "i.status IN (%s)" % ",".join("?" * len(statuses)))
    params = sorted(statuses) + params
    for term in query.excludes:
        where.append("i.search_text NOT LIKE ? ESCAPE '\\'")
        params.append(_like(term))
    if include_terms:
        for term in query.terms:
            where.append("i.search_text LIKE ? ESCAPE '\\'")
            params.append(_like(term))
    return " AND ".join(where), params


def keyword_score(row: sqlite3.Row, terms: list[str]) -> float:
    if not terms:
        return 0.0
    tags = [t.lower() for t in db.json_list(row["tags"]) + db.json_list(row["user_tags"])]
    filename = row["rel_path"].rsplit("/", 1)[-1].lower()
    body = " ".join(
        [row["description"] or "", row["scene"] or "", " ".join(db.json_list(row["objects"])), row["note"] or ""]
    ).lower()
    score = 0.0
    for term in terms:
        if term in tags:
            score += 5
        elif any(term in t for t in tags):
            score += 3
        if term in filename:
            score += 2
        if term in body:
            score += 1.5
        if term in (row["ocr_text"] or "").lower():
            score += 1
        score += 0.5  # 已由 SQL 保證至少某處包含
    return score


def _to_result(conn: sqlite3.Connection, row: sqlite3.Row, score: float, match: str) -> dict:
    return {
        "id": row["id"],
        "root": row["root_name"],
        "rel_path": row["rel_path"],
        "path": str(db.absolute_path(conn, row)),
        "filename": row["rel_path"].rsplit("/", 1)[-1],
        "description": row["description"] or "",
        "tags": db.json_list(row["tags"]),
        "user_tags": db.json_list(row["user_tags"]),
        "scene": row["scene"] or "",
        "taken_at": row["taken_at"],
        "camera": row["camera"],
        "width": row["width"],
        "height": row["height"],
        "status": row["status"],
        "analyzed": row["analyzed_at"] is not None,
        "error": row["error"],
        "fingerprint": row["fingerprint"],
        "score": round(score, 3),
        "match": match,
    }


def _cosine_scores(query_vec, blobs: list[bytes]) -> list[float]:
    try:
        import numpy as np
    except ImportError:  # 沒有 numpy 時用純 Python（較慢，適合小型圖庫）
        from math import sqrt

        from .analyzer import unpack_vector

        qn = sqrt(sum(x * x for x in query_vec)) or 1.0
        out = []
        for blob in blobs:
            v = unpack_vector(blob)
            if len(v) != len(query_vec):
                out.append(-1.0)
                continue
            vn = sqrt(sum(x * x for x in v)) or 1.0
            out.append(sum(a * b for a, b in zip(query_vec, v)) / (qn * vn))
        return out
    q = np.asarray(query_vec, dtype=np.float32)
    q /= np.linalg.norm(q) or 1.0
    out = []
    for blob in blobs:
        v = np.frombuffer(blob, dtype=np.float32)
        if v.shape[0] != q.shape[0]:
            out.append(-1.0)
            continue
        out.append(float(v @ q / (np.linalg.norm(v) or 1.0)))
    return out


def search(
    conn: sqlite3.Connection,
    q: str,
    limit: int = 100,
    offset: int = 0,
    semantic: bool = False,
    embedder=None,
    embed_model: str = "",
    min_similarity: float = 0.45,
) -> dict:
    """回傳 {"total": 符合數量, "results": [...], "mode": "keyword"|"hybrid"}。

    semantic=True 且提供 embedder（有 embed(model, texts) 方法）時，
    先列出關鍵字命中的結果，再補上語意相近但字面不同的圖片。
    """
    query = parse_query(q)
    base = "SELECT i.*, r.name AS root_name FROM images i JOIN roots r ON r.id = i.root_id"
    use_semantic = bool(semantic and embedder and embed_model and query.terms)

    where, params = _filter_sql(query, include_terms=True)
    rows = conn.execute(f"{base} WHERE {where}", params).fetchall()
    scored = [(keyword_score(r, query.terms), r, "keyword") for r in rows]

    if use_semantic:
        hit_ids = {r["id"] for r in rows}
        f_where, f_params = _filter_sql(query, include_terms=False)
        candidates = conn.execute(
            f"{base} WHERE {f_where} AND i.embedding IS NOT NULL AND i.embed_model = ?",
            f_params + [embed_model],
        ).fetchall()
        vectors = embedder.embed(embed_model, [query.text])
        if vectors and candidates:
            sims = _cosine_scores(vectors[0], [c["embedding"] for c in candidates])
            sim_by_id = {c["id"]: s for c, s in zip(candidates, sims)}
            scored = [(s + 10 + sim_by_id.get(r["id"], 0.0), r, m) for s, r, m in scored]
            for cand, sim in zip(candidates, sims):
                if cand["id"] not in hit_ids and sim >= min_similarity:
                    scored.append((sim, cand, "semantic"))

    if query.terms:
        scored.sort(key=lambda x: (-x[0], -(_ts(x[1]["taken_at"])), x[1]["id"]))
    else:
        scored.sort(key=lambda x: (-(_ts(x[1]["taken_at"])), -x[1]["id"]))

    page = scored[offset:offset + limit]
    return {
        "total": len(scored),
        "mode": "hybrid" if use_semantic else "keyword",
        "query": {"terms": query.terms, "excludes": query.excludes, "filters": query.filters},
        "results": [_to_result(conn, r, s, m) for s, r, m in page],
    }


def _ts(value: str | None) -> float:
    if not value:
        return 0.0
    digits = re.sub(r"\D", "", value)[:14]
    return float(digits or 0)


def top_tags(conn: sqlite3.Connection, limit: int = 60) -> list[tuple[str, int]]:
    counts: dict[str, int] = {}
    for row in conn.execute("SELECT tags, user_tags FROM images WHERE status = 'ok' AND (tags IS NOT NULL OR user_tags IS NOT NULL)"):
        for tag in set(db.json_list(row["tags"]) + db.json_list(row["user_tags"])):
            counts[tag] = counts.get(tag, 0) + 1
    return sorted(counts.items(), key=lambda x: (-x[1], x[0]))[:limit]
