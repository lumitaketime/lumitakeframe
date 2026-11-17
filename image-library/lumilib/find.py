"""搜尋所有硬碟上的檔案：檔名與資料夾路徑、文件內容、文字辨識、照片的 AI 描述，合在同一份結果裡。

查詢語法（以空白分隔，全部條件都要符合；用引號包住完整片語）：
    自然科 報告          同時包含兩個詞
    type:document      類型：video／photo／document／audio／archive／other（也接受中文：文件、照片…）
    ext:pdf            副檔名
    year:2008          修改日期的年份
    root:備份          資料夾來源（或硬碟）名稱包含「備份」
篩選也可以由參數指定（介面上的篩選標籤）：範圍（某個資料夾）、類型、年份、大小、所在硬碟。
只讀資料庫，硬碟沒接上也搜得到。
"""

from __future__ import annotations

import re
import shlex
import sqlite3
import time
from dataclasses import dataclass, field

from . import db, textindex
from .catalog import KIND_GROUPS, _file_item

MAX_HITS = 1000  # 每一種來源最多取這麼多筆，合併後依關聯排序
KIND_NAMES = {"影片": "video", "照片": "photo", "相片": "photo", "文件": "document", "音樂": "audio", "壓縮檔": "archive", "其他": "other"}
SIZE_BUCKETS = {"huge": (1_000_000_000, None), "large": (100_000_000, 1_000_000_000), "medium": (1_000_000, 100_000_000),
                "small": (100_000, 1_000_000), "tiny": (0, 100_000)}


@dataclass
class Query:
    terms: list[str] = field(default_factory=list)
    kind: str | None = None
    ext: str | None = None
    year: int | None = None
    root: str | None = None


def parse(q: str) -> Query:
    try:
        tokens = shlex.split(q or "", posix=True)
    except ValueError:
        tokens = (q or "").split()
    out = Query()
    for tok in tokens:
        key, sep, val = tok.partition(":")
        key = key.lower()
        if sep and val and key in ("type", "kind", "類型"):
            out.kind = KIND_NAMES.get(val, val.lower())
        elif sep and val and key == "ext":
            out.ext = val.lower().lstrip(".")
        elif sep and val and key == "year" and val.isdigit():
            out.year = int(val)
        elif sep and val and key in ("root", "drive", "硬碟"):
            out.root = val
        elif tok.strip():
            out.terms.append(tok.strip())
    return out


def _like(value: str) -> str:
    return "%" + value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def _year_range(year: int) -> tuple[float, float]:
    return time.mktime((year, 1, 1, 0, 0, 0, 0, 0, -1)), time.mktime((year + 1, 1, 1, 0, 0, 0, 0, 0, -1))


def _filters(q: Query, root: int | None, path: str, kind: str | None, year: int | None, size: str | None,
             drive: int | None) -> tuple[str, list]:
    where, args = ["f.status = 'ok'"], []
    kind = kind or q.kind
    if kind:
        kinds = KIND_GROUPS.get(kind, (kind,))
        where.append(f"f.kind IN ({','.join('?' * len(kinds))})")
        args += list(kinds)
    if q.ext:
        where.append("lower(f.ext) = ?")
        args.append(q.ext)
    year = year or q.year
    if year:
        a, b = _year_range(int(year))
        where.append("f.mtime >= ? AND f.mtime < ?")
        args += [a, b]
    if size in SIZE_BUCKETS:
        lo, hi = SIZE_BUCKETS[size]
        where.append("f.size >= ?")
        args.append(lo)
        if hi:
            where.append("f.size < ?")
            args.append(hi)
    if root is not None:
        where.append("f.root_id = ?")
        args.append(int(root))
        path = (path or "").strip("/")
        if path:
            where.append("(d.path = ? OR d.path LIKE ? ESCAPE '\\')")
            args += [path, _like(path + "/")[1:]]  # 「路徑/」開頭
    if drive is not None:
        where.append("r.drive_id = ?")
        args.append(int(drive))
    if q.root:
        where.append("(r.name LIKE ? ESCAPE '\\' OR v.name LIKE ? ESCAPE '\\')")
        args += [_like(q.root), _like(q.root)]
    return " AND ".join(where), args


_BASE = ("FROM files f JOIN folders d ON d.id = f.folder_id JOIN roots r ON r.id = f.root_id "
         "LEFT JOIN drives v ON v.id = r.drive_id")
_COLS = "f.id, f.name, f.kind, f.size, f.mtime, f.root_id, f.image_id, f.label, d.path AS folder_path"


def _text_query(terms: list[str]) -> str | None:
    """全文索引的查詢式：每個詞都要出現。中日韓文字用兩字一組比對；其他文字比對詞的開頭。"""
    parts = []
    for t in terms:
        q = db.fts_query(t)
        if q is None:
            words = re.findall(r"\w+", t.lower())
            if not words:
                continue
            q = '"' + " ".join(words) + '"*'
        parts.append(q)
    return " AND ".join(parts) if parts else None


def find(conn: sqlite3.Connection, q: str, *, root: int | None = None, path: str = "", kind: str | None = None,
         year: int | None = None, size: str | None = None, drive: int | None = None, offset: int = 0, limit: int = 50) -> dict:
    query = parse(q)
    where, args = _filters(query, root, path, kind, year, size, drive)
    terms = query.terms
    order: list[tuple[int, str]] = []  # (檔案, 命中的地方)
    seen: set[int] = set()

    def add(ids, why):
        for i in ids:
            if i not in seen:
                seen.add(i)
                order.append((i, why))

    if terms:
        # 1. 檔名（檔名全都符合的排最前面），再來是資料夾路徑
        name_cond = " AND ".join("f.name LIKE ? ESCAPE '\\'" for _ in terms)
        add([r[0] for r in conn.execute(f"SELECT f.id {_BASE} WHERE {where} AND {name_cond} ORDER BY length(f.name) LIMIT {MAX_HITS}",
                                        args + [_like(t) for t in terms])], "name")
        path_cond = " AND ".join("(f.name LIKE ? ESCAPE '\\' OR d.path LIKE ? ESCAPE '\\')" for _ in terms)
        add([r[0] for r in conn.execute(f"SELECT f.id {_BASE} WHERE {where} AND {path_cond} LIMIT {MAX_HITS}",
                                        args + [x for t in terms for x in (_like(t), _like(t))])], "path")
        # 2. 文件內容與文字辨識（依全文索引的關聯度）
        match = _text_query(terms)
        if match:
            rows = conn.execute(
                f"SELECT f.id, t.source {_BASE} JOIN file_text t ON t.file_id = f.id JOIN "
                f"(SELECT rowid, rank FROM file_fts WHERE file_fts MATCH ? ORDER BY rank LIMIT {MAX_HITS * 3}) m ON m.rowid = f.id "
                f"WHERE {where} AND t.size = f.size AND t.mtime = f.mtime ORDER BY m.rank LIMIT {MAX_HITS}", [match] + args).fetchall()
            for r in rows:
                add([r[0]], "ocr" if r[1] == "ocr" else "text")
        # 3. 照片的 AI 描述、關鍵字、人物、地點（照片圖庫原有的索引）
        pmatch = db.fts_query(" ".join(terms)) or _text_query(terms)
        if pmatch:
            add([r[0] for r in conn.execute(
                f"SELECT f.id {_BASE} JOIN (SELECT rowid FROM search_fts WHERE search_fts MATCH ? LIMIT {MAX_HITS * 3}) s ON s.rowid = f.image_id "
                f"WHERE {where} LIMIT {MAX_HITS}", [pmatch] + args)], "photo")
    else:
        # 只有篩選條件、沒有關鍵字：列出符合篩選的檔案（最近修改的在前）
        add([r[0] for r in conn.execute(f"SELECT f.id {_BASE} WHERE {where} ORDER BY f.mtime DESC LIMIT {MAX_HITS}", args)], "filter")

    page = order[offset:offset + limit]
    rows = {r["id"]: r for r in conn.execute(
        f"SELECT {_COLS}, r.name AS root_name, COALESCE(v.name, r.name) AS drive_name {_BASE} WHERE f.id IN ({','.join('?' * len(page))})",
        [i for i, _ in page])} if page else {}
    items = []
    for fid, why in page:
        r = rows.get(fid)
        if r is None:
            continue
        item = _file_item(r)
        item.update(root=r["root_name"], drive=r["drive_name"], match=why,
                    name_parts=textindex.snippet(r["name"], terms, width=10_000) if terms else [{"text": r["name"], "hit": False}])
        if why in ("text", "ocr"):
            item["snippet"] = textindex.snippet(textindex.body(conn, fid), terms)
        elif why == "photo" and r["image_id"]:
            img = conn.execute("SELECT description, ocr_text, search_text FROM images WHERE id = ?", (r["image_id"],)).fetchone()
            text = " ".join(x for x in (img["description"], img["ocr_text"]) if x) or img["search_text"] if img else ""
            item["snippet"] = textindex.snippet(text or "", terms)
        items.append(item)
    return {"total": len(order), "more": len(order) >= MAX_HITS, "offset": offset, "terms": terms, "items": items}


# ---- 智慧資料夾：儲存起來的搜尋 ----

def smart_folders(conn: sqlite3.Connection) -> list[dict]:
    import json

    return [{"id": r["id"], "name": r["name"], "query": json.loads(r["query"])}
            for r in conn.execute("SELECT * FROM smart_folders ORDER BY position IS NULL, position, name")]


def save_smart_folder(conn: sqlite3.Connection, name: str, query: dict) -> int:
    import json

    name = (name or "").strip()
    if not name:
        raise ValueError("請替智慧資料夾取個名字")
    keep = {k: query[k] for k in ("q", "root", "path", "kind", "year", "size", "drive") if query.get(k) not in (None, "")}
    if not keep:
        raise ValueError("沒有可以儲存的搜尋條件")
    cur = conn.execute("INSERT INTO smart_folders (name, query, created_at) VALUES (?, ?, ?)",
                       (name, json.dumps(keep, ensure_ascii=False), db.now_iso()))
    conn.commit()
    return cur.lastrowid


def delete_smart_folder(conn: sqlite3.Connection, folder_id: int) -> None:
    conn.execute("DELETE FROM smart_folders WHERE id = ?", (int(folder_id),))
    conn.commit()
