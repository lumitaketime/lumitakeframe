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
    lens:50mm           鏡頭
    type:video / type:photo / type:raw
    person:媽媽          人物（人臉辨識後命名的人）
    is:favorite / is:pending / is:failed / is:analyzed / is:missing
"""

from __future__ import annotations

import re
import shlex
import sqlite3
from dataclasses import dataclass, field

from . import db

FILTER_KEYS = {"tag", "folder", "camera", "lens", "ext", "year", "after", "before", "root", "is", "type", "album", "person"}


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


def _filter_sql(query: Query, include_terms: bool, groups: list[list[str]] | None = None) -> tuple[str, list]:
    where: list[str] = []
    params: list = []
    statuses = {"ok"}
    for key, value in query.filters:
        low = value.lower()
        if key == "tag":
            where.append(
                "(lower(i.tags) LIKE ? ESCAPE '\\' OR lower(i.user_tags) LIKE ? ESCAPE '\\'"
                " OR lower(i.keywords) LIKE ? ESCAPE '\\')"
            )
            params += [_like(low), _like(low), _like(low)]
        elif key == "lens":
            where.append("lower(i.lens) LIKE ? ESCAPE '\\'")
            params.append(_like(low))
        elif key == "type":
            if low in ("video", "影片"):
                where.append("i.media_type = 'video'")
            elif low in ("photo", "照片"):
                where.append("i.media_type = 'photo'")
            elif low == "raw":
                where.append("i.is_raw = 1")
        elif key == "person":
            where.append(
                "i.id IN (SELECT f.image_id FROM faces f JOIN persons p ON p.id = f.person_id "
                "WHERE lower(p.name) = ? OR CAST(p.id AS TEXT) = ?)"
            )
            params += [low, value]
        elif key == "album" and value.isdigit():
            where.append("i.id IN (SELECT image_id FROM album_items WHERE album_id = ?)")
            params.append(int(value))
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
            where.append("substr(i.sort_at, 1, 4) = ?")
            params.append(value)
        elif key == "after":
            where.append("i.sort_at >= ?")
            params.append(value)
        elif key == "before":
            where.append("i.sort_at < ?")
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
            elif low in ("favorite", "fav"):
                where.append("i.favorite = 1")
    where.insert(0, "i.status IN (%s)" % ",".join("?" * len(statuses)))
    params = sorted(statuses) + params
    for term in query.excludes:
        where.append("i.search_text NOT LIKE ? ESCAPE '\\'")
        params.append(_like(term))
    if include_terms:
        # 每個搜尋詞一組（原詞＋翻譯與同義詞），組內任一個符合即可，各組都要符合
        for group in groups or [[t] for t in query.terms]:
            where.append("(" + " OR ".join(["i.search_text LIKE ? ESCAPE '\\'"] * len(group)) + ")")
            params += [_like(t) for t in group]
    return " AND ".join(where), params


def keyword_score(row: sqlite3.Row, terms: list[str], groups: list[list[str]] | None = None) -> float:
    if groups:
        # 每組取最好的一個詞；翻譯／同義詞的分數打八折
        return sum(
            max(keyword_score(row, [t]) * (1.0 if i == 0 else 0.8) for i, t in enumerate(g)) for g in groups
        )
    if not terms:
        return 0.0
    tags = [t.lower() for t in db.json_list(row["tags"]) + db.json_list(row["user_tags"]) + db.json_list(row["keywords"])]
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


def summarize(row) -> dict:
    """網格顯示用的精簡資料（時間軸、資料夾、相簿、搜尋共用）。"""
    return {
        "id": row["id"],
        "type": row["media_type"],
        "raw": bool(row["is_raw"]),
        "w": row["width"] or 1,
        "h": row["height"] or 1,
        "duration": row["duration"],
        "at": row["sort_at"],
        "fav": bool(row["favorite"]),
        "fp": row["fingerprint"][:10],
        "name": row["rel_path"].rsplit("/", 1)[-1],
        "missing": row["status"] != "ok",
    }


def _to_result(conn: sqlite3.Connection, row: sqlite3.Row, score: float, match: str) -> dict:
    return {
        **summarize(row),
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
    groups: list[list[str]] | None = None,
    clip_rank=None,
    clip_texts: list[str] | None = None,
) -> dict:
    """回傳 {"total", "results", "mode", "expanded"}。

    - groups：查詢改寫後的同義詞組（與 terms 一一對應），讓中文查詢也能找到英文標籤，反之亦然。
    - clip_rank(texts, allowed_ids) -> [(id, 相似度)]：多語言 CLIP 直接比對畫面。
    - semantic + embedder：描述文字的語意向量。
    先列出字面相符的結果（再依畫面相似度微調），接著補上畫面相近、但沒有相符文字的圖片。
    """
    query = parse_query(q)
    base = "SELECT i.*, r.name AS root_name FROM images i JOIN roots r ON r.id = i.root_id"
    if groups is not None and len(groups) != len(query.terms):
        groups = None
    use_semantic = bool(semantic and embedder and embed_model and query.terms)
    use_clip = bool(clip_rank and query.terms)

    where, params = _filter_sql(query, include_terms=True, groups=groups)
    rows = conn.execute(f"{base} WHERE {where}", params).fetchall()
    scored = {r["id"]: [keyword_score(r, query.terms, groups), r, "keyword"] for r in rows}
    modes = ["keyword"]

    if use_clip or use_semantic:
        f_where, f_params = _filter_sql(query, include_terms=False)
        allowed = {r[0] for r in conn.execute(f"SELECT i.id FROM images i JOIN roots r ON r.id = i.root_id WHERE {f_where}", f_params)}

    if use_clip:
        ranked = clip_rank(clip_texts or [query.text], allowed)
        if ranked:
            modes.append("image")
            top = ranked[0][1]
            # 只補上和最佳結果差不多相似的圖片，避免列出一大堆不相關的
            cutoff = max(top - 0.08, top * 0.75)
            extra = {}
            for image_id, sim in ranked:
                if image_id in scored:
                    scored[image_id][0] += 10 + sim * 10
                elif sim >= cutoff and len(extra) < 500:
                    extra[image_id] = sim
            if extra:
                for r in conn.execute(f"{base} WHERE i.id IN ({','.join('?' * len(extra))})", list(extra)):
                    scored[r["id"]] = [extra[r["id"]] * 10, r, "image"]

    if use_semantic:
        vectors = embedder.embed(embed_model, [query.text])
        cands = conn.execute(
            f"{base} WHERE i.embedding IS NOT NULL AND i.embed_model = ? AND i.status = 'ok'", [embed_model]
        ).fetchall()
        cands = [c for c in cands if c["id"] in allowed]
        if vectors and cands:
            modes.append("semantic")
            sims = _cosine_scores(vectors[0], [c["embedding"] for c in cands])
            for cand, sim in zip(cands, sims):
                if cand["id"] in scored:
                    scored[cand["id"]][0] += sim
                elif sim >= min_similarity:
                    scored[cand["id"]] = [sim, cand, "semantic"]

    items = list(scored.values())
    if query.terms:
        items.sort(key=lambda x: (-x[0], -(_ts(x[1]["sort_at"])), x[1]["id"]))
    else:
        items.sort(key=lambda x: (-(_ts(x[1]["sort_at"])), -x[1]["id"]))

    page = items[offset:offset + limit]
    expanded = sorted({t for g in groups for t in g[1:]}) if groups else []
    return {
        "total": len(items),
        "mode": "hybrid" if len(modes) > 1 else "keyword",
        "modes": modes,
        "expanded": expanded,
        "query": {"terms": query.terms, "excludes": query.excludes, "filters": query.filters},
        "results": [_to_result(conn, r, sc, m) for sc, r, m in page],
    }


def _ts(value: str | None) -> float:
    if not value:
        return 0.0
    digits = re.sub(r"\D", "", value)[:14]
    return float(digits or 0)


def top_tags(conn: sqlite3.Connection, limit: int = 60) -> list[tuple[str, int]]:
    counts: dict[str, int] = {}
    for row in conn.execute(
        "SELECT tags, user_tags, keywords FROM images WHERE status = 'ok' "
        "AND (tags IS NOT NULL OR user_tags IS NOT NULL OR keywords IS NOT NULL)"
    ):
        seen: set[str] = set()
        for tag in db.json_list(row["tags"]) + db.json_list(row["user_tags"]) + db.json_list(row["keywords"]):
            key = tag.lower()
            if key not in seen:
                seen.add(key)
                counts[tag] = counts.get(tag, 0) + 1
    return sorted(counts.items(), key=lambda x: (-x[1], x[0]))[:limit]


def tag_covers(conn: sqlite3.Connection, tags: list[str]) -> dict[str, int]:
    """每個關鍵字挑一張最新的照片當封面。"""
    covers: dict[str, int] = {}
    for tag in tags:
        row = conn.execute(
            "SELECT id FROM images WHERE status = 'ok' AND thumb_ok = 1 AND (tags LIKE ? OR user_tags LIKE ? OR keywords LIKE ?) "
            "ORDER BY sort_at DESC LIMIT 1",
            (f'%"{tag}"%',) * 3,
        ).fetchone()
        if row:
            covers[tag] = row["id"]
    return covers
