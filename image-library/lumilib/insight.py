"""助理更聰明：一年的回顧、兩份文件的差異、文件的關鍵字與摘要、這週的摘要。

全部只讀目錄（文件內容用 Re'memor 已經讀好的文字，不再讀硬碟）。
文件摘要用 AI：預設用這台電腦上的模型；設定成雲端服務而且沒有允許傳文件內容時，不送出（核心原則二）。
"""
from __future__ import annotations

import difflib
import json
import re
import sqlite3
from collections import Counter
from datetime import datetime, timedelta, timezone

from . import db

GROUP = {"raw": "photo", "package": "other"}
KIND_ZH = {"photo": "照片", "video": "影片", "document": "文件", "audio": "音樂", "archive": "壓縮檔", "other": "其他"}


def _bytes(n: int) -> str:
    for unit, size in (("TB", 1e12), ("GB", 1e9), ("MB", 1e6), ("KB", 1e3)):
        if n >= size:
            return f"{n / size:.1f} {unit}"
    return f"{n} B"


def _drive_names(conn) -> dict:
    return {r["id"]: r["label"] for r in conn.execute(
        "SELECT r.id, COALESCE(v.name, r.name) AS label FROM roots r LEFT JOIN drives v ON v.id = r.drive_id")}


# ---- 一年的回顧（「2015 年我在做什麼？」） ----

def year_recap(conn: sqlite3.Connection, year: int) -> dict:
    """這一年留下的檔案：各類型多少、每個月多少、最常出現的資料夾、照片在哪裡拍、有哪些文件。
    年份用檔案的修改時間（照片用拍攝時間）；複製過的檔案修改時間可能是複製當天。"""
    year = int(year)
    start = datetime(year, 1, 1).timestamp()
    end = datetime(year + 1, 1, 1).timestamp()
    kinds: dict = {}
    for r in conn.execute("SELECT kind, COUNT(*) AS n, COALESCE(SUM(size), 0) AS b FROM files WHERE status = 'ok' AND mtime >= ? AND mtime < ? "
                          "GROUP BY kind", (start, end)):
        g = GROUP.get(r["kind"], r["kind"])
        k = kinds.setdefault(g, {"kind": g, "files": 0, "bytes": 0})
        k["files"] += r["n"]
        k["bytes"] += r["b"]
    months = [0] * 12
    for r in conn.execute("SELECT CAST(strftime('%m', mtime, 'unixepoch', 'localtime') AS INTEGER) AS m, COUNT(*) AS n FROM files "
                          "WHERE status = 'ok' AND mtime >= ? AND mtime < ? GROUP BY m", (start, end)):
        if r["m"]:
            months[r["m"] - 1] = r["n"]
    names = _drive_names(conn)
    folders = [{"id": r["id"], "root_id": r["root_id"], "path": r["path"], "name": r["name"], "files": r["n"], "drive": names.get(r["root_id"], "")}
               for r in conn.execute(
                   "SELECT d.id, d.root_id, d.path, d.name, COUNT(*) AS n FROM files f JOIN folders d ON d.id = f.folder_id "
                   "WHERE f.status = 'ok' AND f.mtime >= ? AND f.mtime < ? GROUP BY d.id ORDER BY n DESC LIMIT 8", (start, end))]
    places, cameras, photos = [], [], 0
    try:
        y = str(year)
        photos = conn.execute("SELECT COUNT(*) FROM images WHERE status = 'ok' AND substr(taken_at, 1, 4) = ?", (y,)).fetchone()[0]
        places = [{"place": r["place"], "n": r["n"]} for r in conn.execute(
            "SELECT place, COUNT(*) AS n FROM images WHERE status = 'ok' AND substr(taken_at, 1, 4) = ? AND place IS NOT NULL AND place != '' "
            "GROUP BY place ORDER BY n DESC LIMIT 6", (y,))]
        cameras = [r["camera"] for r in conn.execute(
            "SELECT camera, COUNT(*) AS n FROM images WHERE status = 'ok' AND substr(taken_at, 1, 4) = ? AND camera IS NOT NULL AND camera != '' "
            "GROUP BY camera ORDER BY n DESC LIMIT 3", (y,))]
    except sqlite3.Error:
        pass
    docs = [{"id": r["id"], "root_id": r["root_id"], "name": r["name"], "folder": r["folder"], "drive": names.get(r["root_id"], "")}
            for r in conn.execute(
                "SELECT f.id, f.root_id, f.name, d.path AS folder FROM files f JOIN folders d ON d.id = f.folder_id "
                "WHERE f.status = 'ok' AND f.kind = 'document' AND f.mtime >= ? AND f.mtime < ? ORDER BY f.size DESC LIMIT 10", (start, end))]
    cats = []
    try:
        from .classify import categories, display_name

        label = {c["key"]: display_name(c) for c in categories(conn, include_merged=True)}
        cats = [{"name": label.get(r["category"], r["category"]), "files": r["n"]} for r in conn.execute(
            "SELECT c.category, COUNT(*) AS n FROM files f JOIN folder_category c ON c.folder_id = f.folder_id "
            "WHERE f.status = 'ok' AND f.mtime >= ? AND f.mtime < ? AND c.category IS NOT NULL GROUP BY c.category ORDER BY n DESC LIMIT 6",
            (start, end))]
    except sqlite3.Error:
        pass
    return {"year": year, "kinds": sorted(kinds.values(), key=lambda k: -k["bytes"]), "months": months, "folders": folders,
            "photos": photos, "places": places, "cameras": cameras, "documents": docs, "categories": cats,
            "files": sum(k["files"] for k in kinds.values()), "bytes": sum(k["bytes"] for k in kinds.values())}


def describe_year(r: dict) -> str:
    if not r["files"] and not r["photos"]:
        return f"{r['year']} 年沒有找到檔案（依檔案的修改時間與照片的拍攝時間）。"
    lines = [f"{r['year']} 年留下 {r['files']:,} 個檔案（{_bytes(r['bytes'])}）："
             + "、".join(f"{KIND_ZH.get(k['kind'], k['kind'])} {k['files']:,} 個" for k in r["kinds"])]
    busy = [f"{i + 1} 月 {n:,}" for i, n in sorted(enumerate(r["months"]), key=lambda x: -x[1])[:3] if n]
    if busy:
        lines.append("檔案最多的月份：" + "、".join(busy))
    if r["categories"]:
        lines.append("分類：" + "、".join(f"{c['name']} {c['files']:,} 個" for c in r["categories"]))
    if r["folders"]:
        lines.append("最常出現的資料夾：" + "；".join(f"{f['drive']}／{f['path'] or '（最上層）'}（{f['files']:,} 個）" for f in r["folders"][:6]))
    if r["photos"]:
        lines.append(f"那年拍的照片 {r['photos']:,} 張" + ("，地點：" + "、".join(f"{p['place']}（{p['n']}）" for p in r["places"]) if r["places"] else "")
                     + ("，相機：" + "、".join(r["cameras"]) if r["cameras"] else ""))
    if r["documents"]:
        lines.append("那年的文件（部分）：" + "、".join(d["name"] for d in r["documents"][:8]))
    lines.append("（年份依檔案的修改時間；複製過的檔案可能是複製當天的日期。）")
    return "\n".join(lines)


# ---- 兩份文件的差異 ----

def compare_texts(a: str, b: str, max_changes: int = 15) -> dict:
    la = [x.strip() for x in a.splitlines() if x.strip()][:5000]
    lb = [x.strip() for x in b.splitlines() if x.strip()][:5000]
    sm = difflib.SequenceMatcher(None, la, lb, autojunk=False)
    added = removed = changed = 0
    changes = []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            continue
        if op == "insert":
            added += j2 - j1
        elif op == "delete":
            removed += i2 - i1
        else:
            changed += max(i2 - i1, j2 - j1)
        if len(changes) < max_changes:
            changes.append({"op": op, "before": " / ".join(la[i1:i2])[:300], "after": " / ".join(lb[j1:j2])[:300]})
    return {"similarity": round(sm.ratio(), 3), "added": added, "removed": removed, "changed": changed, "lines": [len(la), len(lb)],
            "changes": changes}


def describe_compare(name_a: str, name_b: str, d: dict) -> str:
    if d["similarity"] >= 0.999:
        return f"「{name_a}」和「{name_b}」的文字一模一樣。"
    lines = [f"「{name_a}」（{d['lines'][0]:,} 行）和「{name_b}」（{d['lines'][1]:,} 行）相似度 {d['similarity'] * 100:.0f}%："
             f"新增 {d['added']:,} 行、刪掉 {d['removed']:,} 行、改了 {d['changed']:,} 行。"]
    word = {"insert": "新增", "delete": "刪掉", "replace": "改成"}
    for c in d["changes"]:
        if c["op"] == "insert":
            lines.append(f"- 新增：{c['after']}")
        elif c["op"] == "delete":
            lines.append(f"- 刪掉：{c['before']}")
        else:
            lines.append(f"- 原本：{c['before']} → {word['replace']}：{c['after']}")
    return "\n".join(lines)


# ---- 文件的關鍵字與摘要（資訊欄） ----

_STOP_EN = {"the", "and", "for", "with", "that", "this", "from", "are", "was", "were", "you", "your", "have", "has", "not", "but", "all",
            "can", "will", "our", "their", "they", "his", "her", "its", "into", "than", "then", "there", "these", "those", "also", "been"}


def keywords(text: str, n: int = 8) -> list[str]:
    """文件裡最常出現的詞（中文用常一起出現的字，英文用單字）。"""
    from .analysis import terms

    count: Counter = Counter()
    for line in text[:200_000].splitlines()[:4000]:
        line = line.strip()
        if not line:
            continue
        for w in terms(line[:300]):
            if w.lower() in _STOP_EN or len(w) < 2 or w.isdigit():
                continue
            count[w] += 1
    cand = [(w, c) for w, c in count.most_common(n * 6) if c >= 2]
    # 長詞優先：「一次函數」出現的次數和「一次函」「函數」差不多時，只留長的那個
    keep = [w for w, c in cand if not any(len(o) > len(w) and w in o and co >= c * 0.6 for o, co in cand)]
    out: list[str] = []
    for w in keep:
        if any(w in o or o in w for o in out):
            continue
        out.append(w)
        if len(out) >= n:
            break
    return out


SUMMARY_SCHEMA = """
CREATE TABLE IF NOT EXISTS file_summaries (
    file_id INTEGER PRIMARY KEY REFERENCES files(id) ON DELETE CASCADE,
    sig TEXT NOT NULL,
    summary TEXT NOT NULL,
    model TEXT,
    created_at TEXT NOT NULL
);
"""


def _sig(conn, file_id: int) -> str | None:
    r = conn.execute("SELECT size || '|' || mtime FROM files WHERE id = ?", (file_id,)).fetchone()
    return r[0] if r else None


def insight(conn: sqlite3.Connection, file_id: int) -> dict:
    """資訊欄用：有沒有讀過文字、關鍵字、AI 摘要（做過的）、別顆硬碟上的副本（完整比對過的）。"""
    from .textindex import body

    f = conn.execute("SELECT id, root_id, name, size, content_hash FROM files WHERE id = ?", (int(file_id),)).fetchone()
    if f is None:
        raise ValueError("找不到這個檔案")
    text = body(conn, f["id"])
    s = conn.execute("SELECT summary, sig, model FROM file_summaries WHERE file_id = ?", (f["id"],)).fetchone()
    summary = s["summary"] if s and s["sig"] == _sig(conn, f["id"]) else None
    copies = []
    if f["content_hash"]:
        names = _drive_names(conn)
        my = conn.execute("SELECT drive_id FROM roots WHERE id = ?", (f["root_id"],)).fetchone()
        for r in conn.execute("SELECT g.root_id, g.name, d.path FROM files g JOIN folders d ON d.id = g.folder_id JOIN roots r ON r.id = g.root_id "
                              "WHERE g.content_hash = ? AND g.status = 'ok' AND g.id != ? LIMIT 6", (f["content_hash"], f["id"])):
            copies.append({"root_id": r["root_id"], "drive": names.get(r["root_id"], ""), "path": "/".join(p for p in (r["path"], r["name"]) if p)})
    return {"file_id": f["id"], "has_text": bool(text), "chars": len(text), "keywords": keywords(text) if text else [],
            "summary": summary, "copies": copies, "hashed": bool(f["content_hash"])}


def summarize(conn: sqlite3.Connection, llm, file_id: int, lang: str = "zh-Hant") -> str:
    """請 AI 寫兩三句摘要（用已經讀好的文字的前一段），記起來；檔案改過才重寫。"""
    from .textindex import body

    text = body(conn, int(file_id))
    if not text:
        raise ValueError("Re'memor 還沒讀到這份文件的文字，沒辦法寫摘要")
    name = conn.execute("SELECT name FROM files WHERE id = ?", (int(file_id),)).fetchone()["name"]
    lang_name = "English" if lang.startswith("en") else "繁體中文"
    head = re.sub(r"[ \t]+", " ", text)[:4000]
    prompt = (f"請用{lang_name}替下面這份文件寫兩到三句摘要：說明它是什麼、重點是什麼。不要加入文件裡沒有的內容。\n"
              f"檔名：{name}\n內容（開頭一部分）：\n{head}\n請回答 JSON：summary。")
    out = llm.plan_json(prompt, {"type": "object", "properties": {"summary": {"type": "string"}}, "required": ["summary"]})
    summary = str((out or {}).get("summary") or "").strip()[:600] if isinstance(out, dict) else ""
    if not summary:
        raise ValueError("AI 沒有回答，請再試一次")
    conn.execute("INSERT OR REPLACE INTO file_summaries (file_id, sig, summary, model, created_at) VALUES (?, ?, ?, ?, ?)",
                 (int(file_id), _sig(conn, int(file_id)), summary, getattr(llm, "model", "") or "", db.now_iso()))
    conn.commit()
    return summary


# ---- 這週的摘要（總覽頁） ----

def week_report(conn: sqlite3.Connection, days: int = 7) -> dict:
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")
    kinds: dict = {}
    for r in conn.execute("SELECT kind, COUNT(*) AS n, COALESCE(SUM(size), 0) AS b FROM files WHERE status = 'ok' AND first_seen >= ? GROUP BY kind",
                          (since,)):
        g = GROUP.get(r["kind"], r["kind"])
        k = kinds.setdefault(g, {"kind": g, "files": 0, "bytes": 0})
        k["files"] += r["n"]
        k["bytes"] += r["b"]
    scans = [r["label"] for r in conn.execute(
        "SELECT DISTINCT COALESCE(json_extract(options, '$.target'), '') AS label FROM job_log WHERE kind IN ('scan', 'index') AND state = 'done' "
        "AND finished_at >= ?", (since,)) if r["label"]]
    hashed = conn.execute("SELECT COUNT(*) FROM files WHERE hashed_at >= ?", (since,)).fetchone()[0]
    acts = conn.execute("SELECT COUNT(*) FROM assistant_actions WHERE state IN ('done', 'partial') AND done_at >= ?", (since,)).fetchone()[0]
    docs = conn.execute("SELECT COUNT(*) FROM file_text WHERE extracted_at >= ? AND body IS NOT NULL", (since,)).fetchone()[0]
    return {"days": days, "kinds": sorted(kinds.values(), key=lambda k: -k["bytes"]), "files": sum(k["files"] for k in kinds.values()),
            "bytes": sum(k["bytes"] for k in kinds.values()), "scans": scans, "hashed": hashed, "actions": acts, "docs": docs}


__all__ = ["year_recap", "describe_year", "compare_texts", "describe_compare", "keywords", "insight", "summarize", "week_report",
           "SUMMARY_SCHEMA", "json"]
