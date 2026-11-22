"""檔案分析：類型、年份分布，以及資料夾名稱與檔名裡最常出現的詞（關鍵字雲）。

全部在這台電腦上、只讀目錄資料庫（不讀硬碟、不上傳）。

拆詞不用字典：
- 中文（日文）：名稱裡連續的中文字，取兩到四個字的片段，同時出現在好幾個名稱裡的才算一個詞；
  短的詞幾乎只出現在某個長詞裡（例如「蔦松國」幾乎都在「蔦松國中」裡）就只留長的，反過來也一樣。
  這樣「蔦松」這種專有名詞也找得到。
- 英文：一個字一個字拆（WeddingPhotos → wedding、photos），三個字母以上。
- 濾掉沒意義的：日期與數字、IMG、DSC、新增資料夾、副本、copy、final、副檔名等。

一百萬個檔名也只走兩遍：先用資料夾名稱與一部分檔名找出候選詞，再數每個詞出現在幾個檔名裡。結果存在 keyword_stats。
"""

from __future__ import annotations

import re
import sqlite3
import time
from dataclasses import dataclass

_CJK = re.compile(r"[぀-ヿ㐀-鿿豈-﫿]+")
_LATIN = re.compile(r"[A-Za-z]+")
_CAMEL = re.compile(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])")

STOP_EN = {
    "img", "dsc", "dscn", "dcim", "pic", "pics", "photo", "photos", "image", "images", "screenshot", "screen", "shot", "untitled",
    "new", "folder", "copy", "final", "the", "and", "for", "with", "from", "file", "files", "document", "documents", "doc", "docx",
    "pdf", "jpg", "jpeg", "png", "heic", "mov", "mp4", "mp3", "txt", "zip", "rar", "xls", "xlsx", "ppt", "pptx", "raw", "cr2", "nef",
    "arw", "dng", "psd", "edit", "edited", "version", "ver", "rev", "backup", "bak", "tmp", "temp", "misc", "other", "others", "old",
    "data", "export", "exports", "output", "jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec",
}
STOP_ZH = {
    "新增資料夾", "新增", "資料夾", "未命名", "副本", "複製", "最終", "最終版", "修改", "修改版", "版本", "截圖", "螢幕快照", "螢幕截圖",
    "照片", "相片", "圖片", "影片", "檔案", "文件", "其他", "備份", "暫存", "下載", "整理", "未分類", "雜項", "舊的", "新的",
    "年度", "學年", "學期", "上學期", "下學期", "月份", "日期", "第一", "第二", "第三",
}
STOP_CHARS = set("的和與及之在了是年月日號份個張次版")
MIN_FOLDERS = 2  # 至少出現在幾個資料夾名稱（或對應的檔名數）才算一個詞
TOP = 300
SAMPLE_FILES = 300_000


def _cjk_grams(run: str):
    n = len(run)
    for size in (2, 3, 4):
        for i in range(n - size + 1):
            g = run[i:i + size]
            if g[0] in STOP_CHARS or g[-1] in STOP_CHARS:
                continue
            yield g


_STOP_RE = re.compile("|".join(sorted(map(re.escape, STOP_ZH), key=len, reverse=True)))


def terms(name: str) -> set[str]:
    """一個名稱裡的候選詞（中文片段、英文字）。雜詞（新增資料夾、學年、副本…）先切掉，不會拼成奇怪的片段。"""
    base = name.rsplit(".", 1)[0] if "." in name[-6:] else name
    base = _STOP_RE.sub(" ", base)
    out = set()
    for m in _CJK.finditer(base):
        run = m.group()
        if len(run) <= 4 and len(run) >= 2 and run not in STOP_ZH:
            out.add(run)
        if len(run) > 2:
            out.update(g for g in _cjk_grams(run) if g not in STOP_ZH)
    for m in _LATIN.finditer(base):
        for w in _CAMEL.findall(m.group()):
            w = w.lower()
            if len(w) >= 3 and w not in STOP_EN:
                out.add(w)
    return out


def _prune(counts: dict[str, int]) -> dict[str, int]:
    """中文片段去掉重疊：短詞幾乎只出現在某個長詞裡 → 只留長的；長詞只是短詞偶爾的延伸 → 只留短的。"""
    keep = dict(counts)
    cjk = sorted((w for w in counts if not w.isascii()), key=len, reverse=True)
    for long in cjk:
        if long not in keep:
            continue
        n = keep[long]
        for size in range(2, len(long)):
            for i in range(len(long) - size + 1):
                short = long[i:i + size]
                if short in keep and short != long:
                    if n >= 0.8 * keep[short]:
                        keep.pop(short, None)  # 「蔦松國」幾乎都在「蔦松國中」裡
    # 長詞的每個部分都遠比它常見（例如「國中數」）：拿掉長詞
    for long in [w for w in keep if not w.isascii() and len(w) >= 3]:
        parts = [long[:-1], long[1:]]
        if any(p in counts and counts[p] >= 3 * keep[long] for p in parts) and keep[long] < 3:
            keep.pop(long, None)
    return keep


@dataclass
class KeywordResult:
    words: int = 0
    folders: int = 0
    files: int = 0
    seconds: float = 0


def build_keywords(conn: sqlite3.Connection, progress=None, stop=None) -> KeywordResult:
    t0 = time.monotonic()
    folder_counts: dict[str, int] = {}
    nf = 0
    for r in conn.execute("SELECT name FROM folders WHERE status = 'ok' AND path != ''"):
        nf += 1
        for w in terms(r["name"]):
            folder_counts[w] = folder_counts.get(w, 0) + 1
    total_files = conn.execute("SELECT COUNT(*) FROM files WHERE status = 'ok'").fetchone()[0]
    step = max(1, total_files // SAMPLE_FILES)
    sample: dict[str, int] = {}
    for i, r in enumerate(conn.execute("SELECT name FROM files WHERE status = 'ok'")):
        if i % step:
            continue
        for w in terms(r["name"]):
            sample[w] = sample.get(w, 0) + 1
    if stop is not None and stop.is_set():
        return KeywordResult()
    combined = {w: folder_counts.get(w, 0) * 3 + sample.get(w, 0) * step for w in set(folder_counts) | set(sample)}
    combined = {w: n for w, n in combined.items() if folder_counts.get(w, 0) >= MIN_FOLDERS or sample.get(w, 0) * step >= 3}
    combined = _prune(combined)
    cands = set(sorted(combined, key=lambda w: -combined[w])[:TOP * 2])
    if progress:
        progress(1, 3, "數每個詞出現在幾個檔案")
    file_counts = {w: 0 for w in cands}
    for i, r in enumerate(conn.execute("SELECT name FROM files WHERE status = 'ok'")):
        if stop is not None and i % 50000 == 0 and stop.is_set():
            return KeywordResult()
        for w in terms(r["name"]) & cands:
            file_counts[w] += 1
    scored = sorted(cands, key=lambda w: -(folder_counts.get(w, 0) * 3 + file_counts[w]))[:TOP]
    conn.execute("DELETE FROM keyword_stats")
    conn.executemany("INSERT INTO keyword_stats (word, folders, files) VALUES (?, ?, ?)",
                     [(w, folder_counts.get(w, 0), file_counts[w]) for w in scored])
    conn.execute("INSERT OR REPLACE INTO settings_kv (key, value) VALUES ('keyword_stats_at', ?)", (time.strftime("%Y-%m-%dT%H:%M:%S"),))
    conn.commit()
    if progress:
        progress(3, 3, "")
    return KeywordResult(words=len(scored), folders=nf, files=total_files, seconds=round(time.monotonic() - t0, 1))


def _match_sql(word: str) -> tuple[str, list]:
    return "instr(lower(name), ?) > 0", [word.lower()]


def _word_ok(word: str, name: str) -> bool:
    return word in terms(name) if word.isascii() else word in name.lower()


def keywords(conn: sqlite3.Connection, limit: int = 150) -> dict:
    """關鍵字雲：每個詞出現在幾個資料夾、幾個檔案，以及這些資料夾現在大多在哪一類。"""
    rows = conn.execute("SELECT * FROM keyword_stats ORDER BY folders * 3 + files DESC LIMIT ?", (limit,)).fetchall()
    at = conn.execute("SELECT value FROM settings_kv WHERE key = 'keyword_stats_at'").fetchone()
    words = []
    for r in rows:
        dom = conn.execute(
            "SELECT c.category, COUNT(*) AS n FROM folders d JOIN folder_category c ON c.folder_id = d.id "
            "WHERE d.status = 'ok' AND instr(lower(d.name), ?) > 0 AND c.category IS NOT NULL GROUP BY c.category ORDER BY n DESC LIMIT 1",
            (r["word"].lower(),)).fetchone()
        words.append({"word": r["word"], "folders": r["folders"], "files": r["files"], "category": dom["category"] if dom else None})
    return {"words": words, "updated_at": at["value"] if at else None}


def word_detail(conn: sqlite3.Connection, word: str, limit: int = 50) -> dict:
    """按一個詞：是哪些資料夾、哪些檔案，這些資料夾現在分在哪些類。"""
    w = word.lower()
    folders, cats = [], {}
    for r in conn.execute(
            "SELECT d.id, d.name, d.path, d.root_id, d.total_files, d.total_bytes, r.name AS root, c.category, c.source, c.year "
            "FROM folders d JOIN roots r ON r.id = d.root_id LEFT JOIN folder_category c ON c.folder_id = d.id "
            "WHERE d.status = 'ok' AND d.path != '' AND instr(lower(d.name), ?) > 0 ORDER BY d.total_bytes DESC", (w,)):
        if not _word_ok(word, r["name"]):
            continue
        cats[r["category"]] = cats.get(r["category"], 0) + 1
        if len(folders) < limit:
            folders.append(dict(r))
    files, nfiles = [], 0
    for r in conn.execute("SELECT f.id, f.name, f.kind, f.size, f.root_id, d.path AS folder FROM files f JOIN folders d ON d.id = f.folder_id "
                          "WHERE f.status = 'ok' AND instr(lower(f.name), ?) > 0 LIMIT 5000", (w,)):
        if not _word_ok(word, r["name"]):
            continue
        nfiles += 1
        if len(files) < 30:
            files.append(dict(r))
    return {"word": word, "folders": sum(cats.values()), "files": nfiles, "folder_list": folders, "file_list": files,
            "categories": [{"category": k, "count": n} for k, n in sorted(cats.items(), key=lambda x: -x[1])]}


def file_stats(conn: sqlite3.Connection) -> dict:
    """類型（檔案數、大小）與年份分布（依修改日期）。"""
    kinds = [dict(r) for r in conn.execute(
        "SELECT kind, COUNT(*) AS files, COALESCE(SUM(size), 0) AS bytes FROM files WHERE status = 'ok' GROUP BY kind ORDER BY bytes DESC")]
    years = [dict(r) for r in conn.execute(
        "SELECT CAST(strftime('%Y', mtime, 'unixepoch', 'localtime') AS INTEGER) AS year, COUNT(*) AS files, COALESCE(SUM(size), 0) AS bytes "
        "FROM files WHERE status = 'ok' AND mtime > 0 GROUP BY year ORDER BY year")]
    years = [y for y in years if y["year"] and 1980 <= y["year"] <= 2100]
    exts = [dict(r) for r in conn.execute(
        "SELECT ext, COUNT(*) AS files, COALESCE(SUM(size), 0) AS bytes FROM files WHERE status = 'ok' AND ext != '' "
        "GROUP BY ext ORDER BY files DESC LIMIT 12")]
    return {"kinds": kinds, "years": years, "exts": exts,
            "total": {"files": sum(k["files"] for k in kinds), "bytes": sum(k["bytes"] for k in kinds)}}


def describe(r: KeywordResult) -> str:
    return f"找出 {r.words:,} 個常見的詞（{r.folders:,} 個資料夾、{r.files:,} 個檔案，{r.seconds} 秒）"
