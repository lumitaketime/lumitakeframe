"""文件文字與全文索引：讀出 PDF、Word、PowerPoint、Excel、電子書、純文字裡的文字，放進全文索引。

安全原則（核心原則第 7 條）：只讀取檔案，讀出來的文字存在 Re'memor 的資料庫，不在硬碟上建立任何東西。
做成背景工作：分批寫入，可以隨時停止或拔掉硬碟，下次從還沒讀的繼續（由使用者按下才開始）。

存法：每個檔案最多存 1,000,000 個字（壓縮後存放），用來顯示命中的段落；
索引用 FTS5（中日韓文字拆成單字與兩字一組，和照片搜尋相同的斷詞）。索引表不另存原文，省空間。
"""

from __future__ import annotations

import html
import io
import re
import sqlite3
import subprocess
import sys
import time
import zipfile
import zlib
from dataclasses import dataclass, field
from pathlib import Path

from . import db

MAX_CHARS = 1_000_000  # 每個檔案最多存這麼多字
MAX_FILE = 300_000_000  # 超過 300 MB 的文件不讀（多半是掃描檔，之後交給 OCR）
MAX_TEXT_FILE = 20_000_000  # 純文字檔最多讀 20 MB
MAX_ZIP_ENTRY = 50_000_000  # Office、EPUB 裡單一部分解開後最多 50 MB（避免惡意的壓縮炸彈）
MAX_PDF_PAGES = 3000
COMMIT_ROWS = 50
COMMIT_SECONDS = 2.0
REPORT_SECONDS = 0.5

TEXT_EXT = {".txt", ".md", ".markdown", ".csv", ".tsv", ".log", ".json", ".xml", ".srt", ".vtt", ".tex", ".yml", ".yaml", ".ini", ".conf"}
HTML_EXT = {".html", ".htm", ".xhtml"}
OOXML_EXT = {".docx", ".docm", ".dotx", ".pptx", ".pptm", ".ppsx", ".xlsx", ".xlsm"}
ODF_EXT = {".odt", ".odp", ".ods"}
MAC_TEXTUTIL_EXT = {".doc", ".rtf", ".rtfd", ".wordml", ".webarchive"}
SUPPORTED = TEXT_EXT | HTML_EXT | OOXML_EXT | ODF_EXT | MAC_TEXTUTIL_EXT | {".pdf", ".epub"}


class Unsupported(Exception):
    """這台電腦讀不了這種檔案（例如在 Mac 以外讀舊版 Word）。"""


class Stopped(Exception):
    pass


# ---- 各種格式 ----

def _decode(raw: bytes) -> str:
    bom16 = raw[:2] in (b"\xff\xfe", b"\xfe\xff")
    for enc in (("utf-16",) if bom16 else ()) + ("utf-8-sig", "big5", "gb18030"):
        try:
            return raw.decode(enc)
        except UnicodeError:
            continue
    return raw.decode("utf-8", errors="replace")


_TAG = re.compile(r"<[^>]+>")
_BLOCK = re.compile(r"</(p|div|h[1-6]|li|tr|br|w:p|a:p|text:p|text:h|table:table-row)\s*>|<(br|w:br|w:tab|a:br)\s*/?>", re.I)
_SCRIPT = re.compile(r"<(script|style)\b.*?</\1>", re.I | re.S)


def _xml_text(xml: str) -> str:
    """XML 或 HTML → 純文字：段落換行、去掉標籤、還原 &amp; 之類的符號。"""
    xml = _SCRIPT.sub(" ", xml)
    xml = _BLOCK.sub("\n", xml)
    return html.unescape(_TAG.sub("", xml))


def _zip_parts(path: Path, pick) -> str:
    """從 Office、ODF、EPUB（都是壓縮包）讀出要的部分。pick(names) 回傳要讀的部分（依順序）。"""
    out = []
    with zipfile.ZipFile(path) as z:
        for name in pick(z.namelist()):
            info = z.getinfo(name)
            if info.file_size > MAX_ZIP_ENTRY:
                continue
            out.append(_xml_text(z.read(name).decode("utf-8", errors="replace")))
            if sum(len(x) for x in out) > MAX_CHARS:
                break
    return "\n".join(out)


def _num(name: str) -> int:
    m = re.search(r"(\d+)\.xml$", name)
    return int(m.group(1)) if m else 0


def _ooxml_parts(names: list[str]) -> list[str]:
    word = [n for n in names if re.match(r"word/(document|header\d*|footer\d*|footnotes|endnotes)\.xml$", n)]
    slides = sorted((n for n in names if re.match(r"ppt/slides/slide\d+\.xml$", n)), key=_num)
    notes = sorted((n for n in names if re.match(r"ppt/notesSlides/notesSlide\d+\.xml$", n)), key=_num)
    sheets = [n for n in names if n == "xl/sharedStrings.xml"] + sorted(
        (n for n in names if re.match(r"xl/worksheets/sheet\d+\.xml$", n)), key=_num)
    return sorted(word, key=lambda n: (not n.startswith("word/document"), n)) + slides + notes + sheets


def _epub_parts(names: list[str]) -> list[str]:
    return sorted(n for n in names if n.lower().endswith((".xhtml", ".html", ".htm")))


def _pdf(path: Path, stop=None) -> tuple[str, bool]:
    """PDF 的文字層。回傳（文字、是否像掃描檔：大部分頁面沒有文字，之後交給 OCR）。"""
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(str(path))
    try:
        pages = min(len(pdf), MAX_PDF_PAGES)
        parts, empty, total = [], 0, 0
        for i in range(pages):
            if stop is not None and stop.is_set():
                raise Stopped
            page = pdf[i]
            tp = page.get_textpage()
            text = tp.get_text_range()
            tp.close()
            page.close()
            if len(text.strip()) < 20:
                empty += 1
            parts.append(text)
            total += len(text)
            if total > MAX_CHARS:
                break
        return "\n".join(parts), pages > 0 and empty / pages > 0.6
    finally:
        pdf.close()


def _textutil(path: Path) -> str:
    if sys.platform != "darwin":
        raise Unsupported("只有在 Mac 上才能讀這種檔案")
    proc = subprocess.run(["/usr/bin/textutil", "-convert", "txt", "-stdout", str(path)], capture_output=True, timeout=120)
    if proc.returncode != 0:
        raise ValueError(proc.stderr.decode("utf-8", errors="replace").strip() or "無法讀取")
    return _decode(proc.stdout)


def extract(path: Path, stop=None) -> tuple[str, bool]:
    """讀出一個檔案的文字。回傳（文字、是否需要 OCR）。只讀取。"""
    ext = path.suffix.lower()
    if path.is_dir() and ext == ".rtfd":
        return _textutil(path), False
    if ext in TEXT_EXT or ext in HTML_EXT:
        with open(path, "rb") as fh:
            raw = fh.read(MAX_TEXT_FILE)
        text = _decode(raw)
        return (_xml_text(text) if ext in HTML_EXT else text), False
    if ext in OOXML_EXT:
        return _zip_parts(path, _ooxml_parts), False
    if ext in ODF_EXT:
        return _zip_parts(path, lambda names: [n for n in names if n == "content.xml"]), False
    if ext == ".epub":
        return _zip_parts(path, _epub_parts), False
    if ext == ".pdf":
        return _pdf(path, stop)
    if ext in MAC_TEXTUTIL_EXT:
        return _textutil(path), False
    raise Unsupported("不支援這種檔案")


def clean(text: str) -> str:
    """把多餘的空白收起來，最多留 MAX_CHARS 個字。"""
    text = re.sub(r"[ \t 　]+", " ", text.replace("\r", "\n"))
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    return text.strip()[:MAX_CHARS]


# ---- 索引 ----

def _store(conn: sqlite3.Connection, file_id: int, size: int, mtime: float, source: str, text: str, status: str,
           error: str | None = None) -> None:
    """寫入（或換掉）一個檔案的文字與索引。"""
    old = conn.execute("SELECT body FROM file_text WHERE file_id = ?", (file_id,)).fetchone()
    if old and old["body"]:
        conn.execute("INSERT INTO file_fts(file_fts, rowid, tokens) VALUES ('delete', ?, ?)",
                     (file_id, db.fts_tokens(zlib.decompress(old["body"]).decode("utf-8"))))
    body = zlib.compress(text.encode("utf-8"), 6) if text else None
    conn.execute(
        "INSERT OR REPLACE INTO file_text (file_id, source, status, body, chars, size, mtime, extracted_at, error) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (file_id, source, status, body, len(text), size, mtime, db.now_iso(), error))
    if text:
        conn.execute("INSERT INTO file_fts(rowid, tokens) VALUES (?, ?)", (file_id, db.fts_tokens(text)))


def index_bytes(conn: sqlite3.Connection) -> int:
    """文件文字（壓縮後）加上全文索引大約佔多少空間。"""
    body = conn.execute("SELECT COALESCE(SUM(length(body)), 0) FROM file_text").fetchone()[0]
    fts = conn.execute("SELECT COALESCE(SUM(length(block)), 0) FROM file_fts_data").fetchone()[0]
    return int(body + fts)


def reset(conn: sqlite3.Connection, ocr_only: bool = False) -> int:
    """清除讀過的文字與索引，之後重新讀取（只動 Re'memor 自己的資料庫，不碰硬碟上的檔案）。
    ocr_only＝只清文字辨識的結果。回傳清掉幾個檔案。"""
    if not ocr_only:
        n = conn.execute("SELECT COUNT(*) FROM file_text").fetchone()[0]
        conn.execute("DELETE FROM file_text")
        conn.execute("INSERT INTO file_fts(file_fts) VALUES ('delete-all')")
        conn.commit()
        return n
    rows = conn.execute("SELECT file_id, body FROM file_text WHERE source = 'ocr'").fetchall()
    for r in rows:
        if r["body"]:
            conn.execute("INSERT INTO file_fts(file_fts, rowid, tokens) VALUES ('delete', ?, ?)",
                         (r["file_id"], db.fts_tokens(zlib.decompress(r["body"]).decode("utf-8"))))
    conn.execute("DELETE FROM file_text WHERE source = 'ocr'")
    conn.commit()
    return len(rows)


def _exts_sql() -> str:
    return ",".join(f"'{e.lstrip('.')}'" for e in sorted(SUPPORTED))  # 目錄裡存的副檔名不含點


def _candidates_sql(extra: str = "", retry: bool = False, cloud: bool = False) -> str:
    """要讀文字的檔案：支援的類型、大小在上限內、還沒讀過或讀過之後被改過；
    在雲端還沒下載的每次都再看一次；retry＝連之前讀不了的也再試一次。"""
    retry_sql = ("OR t.status = 'error' " if retry else "") + ("OR t.status = 'cloud'" if cloud else "")
    return (f"FROM files f JOIN folders d ON d.id = f.folder_id LEFT JOIN file_text t ON t.file_id = f.id "
            f"WHERE f.status = 'ok' AND lower(f.ext) IN ({_exts_sql()}) AND f.size <= {MAX_FILE} "
            f"AND (t.file_id IS NULL OR t.size != f.size OR t.mtime != f.mtime {retry_sql}) {extra}")


def extract_plan(conn: sqlite3.Connection) -> dict:
    """還要讀幾個文件（硬碟接著的、沒接上的），已經讀好幾個、讀不了幾個、像掃描檔要 OCR 的有幾個。"""
    online = {r["id"]: Path(r["path"]).is_dir() for r in conn.execute("SELECT id, path FROM roots")}
    plan = {"todo": [0, 0], "offline": [0, 0]}
    for r in conn.execute(f"SELECT f.root_id, COUNT(*) AS n, COALESCE(SUM(f.size), 0) AS b {_candidates_sql()} GROUP BY f.root_id"):
        slot = plan["todo"] if online.get(r["root_id"]) else plan["offline"]
        slot[0] += r["n"]
        slot[1] += r["b"]
    stats = {r["status"]: r["n"] for r in conn.execute(
        # 從文件文字這邊數（只讀狀態的索引，不碰壓縮的內文），再對回檔案
        "SELECT t.status, COUNT(*) AS n FROM file_text t INDEXED BY idx_file_text_state CROSS JOIN files f ON f.id = t.file_id AND f.status = 'ok' "
        "AND t.size = f.size AND t.mtime = f.mtime GROUP BY t.status")}
    return {"todo": {"files": plan["todo"][0], "bytes": plan["todo"][1]}, "offline": {"files": plan["offline"][0], "bytes": plan["offline"][1]},
            "done": stats.get("ok", 0) + stats.get("empty", 0), "failed": stats.get("error", 0) + stats.get("unsupported", 0),
            "needs_ocr": stats.get("needs_ocr", 0), "cloud": stats.get("cloud", 0), "errors": stats.get("error", 0)}


@dataclass
class ExtractResult:
    read: int = 0
    chars: int = 0
    empty: int = 0
    needs_ocr: int = 0
    failed: int = 0
    changed: int = 0
    offline: int = 0
    cloud: int = 0
    interrupted: list[str] = field(default_factory=list)
    stopped: bool = False


SF_DATALESS = 0x40000000  # macOS：檔案只是雲端的佔位，內容還沒下載到這台電腦


def run_extract(conn: sqlite3.Connection, progress=None, stop=None, retry: bool = False) -> ExtractResult:
    """讀出還沒讀的文件文字。progress(done, total, 正在讀的檔案)。可以隨時停止，下次接著做。"""
    result = ExtractResult()
    roots = {r["id"]: r for r in conn.execute("SELECT * FROM roots")}
    online = {rid: Path(r["path"]).is_dir() for rid, r in roots.items()}
    rows = conn.execute(f"SELECT f.id, f.root_id, f.name, f.size, f.mtime, d.path AS folder {_candidates_sql(retry=retry, cloud=True)} "
                        "ORDER BY f.root_id, d.path, f.name").fetchall()
    todo = [r for r in rows if online.get(r["root_id"])]
    result.offline = len(rows) - len(todo)
    total, done = len(todo), 0
    pending, last_commit, last_report = 0, time.monotonic(), 0.0
    dead: set[int] = set()

    def report(name: str, force: bool = False) -> None:
        nonlocal last_report
        now = time.monotonic()
        if progress and (force or now - last_report >= REPORT_SECONDS):
            last_report = now
            progress(done, total, name)

    try:
        for r in todo:
            if stop is not None and stop.is_set():
                raise Stopped
            done += 1
            if r["root_id"] in dead:
                continue
            root = roots[r["root_id"]]
            path = Path(root["path"]).joinpath(*[p for p in r["folder"].split("/") if p], r["name"])
            report(f"{root['name']}：{r['name']}")
            try:
                st = path.stat()
                if st.st_size != r["size"] or st.st_mtime != r["mtime"]:
                    result.changed += 1  # 掃描之後被改過：重新掃描後再讀
                    continue
                if getattr(st, "st_flags", 0) & SF_DATALESS:
                    # iCloud、Google 雲端硬碟、OneDrive 只在雲端的檔案：讀它會從網路下載，不讀（資料不出家門）；
                    # 等你自己把它下載到這台電腦，下次就會讀到
                    _store(conn, r["id"], r["size"], r["mtime"], "text", "", "cloud", "在雲端，還沒下載到這台電腦")
                    result.cloud += 1
                    continue
                text, scanned = extract(path, stop)
                text = clean(text)
                if scanned and len(text) < 200:
                    _store(conn, r["id"], r["size"], r["mtime"], "text", text, "needs_ocr")
                    result.needs_ocr += 1
                else:
                    _store(conn, r["id"], r["size"], r["mtime"], "text", text, "ok" if text else "empty")
                    result.read += 1 if text else 0
                    result.empty += 0 if text else 1
                    result.chars += len(text)
            except Stopped:
                raise
            except Unsupported as exc:
                _store(conn, r["id"], r["size"], r["mtime"], "text", "", "unsupported", str(exc))
                result.failed += 1
            except OSError:
                if not Path(root["path"]).is_dir():  # 硬碟被拔掉：這顆先停，其他硬碟繼續；不算錯誤
                    dead.add(r["root_id"])
                    result.interrupted.append(root["name"])
                    continue
                _store(conn, r["id"], r["size"], r["mtime"], "text", "", "error", "無法讀取這個檔案")
                result.failed += 1
            except Exception as exc:  # noqa: BLE001  壞掉的檔案不能讓整個工作停下來
                _store(conn, r["id"], r["size"], r["mtime"], "text", "", "error", f"檔案格式有問題：{type(exc).__name__}: {exc}"[:300])
                result.failed += 1
            pending += 1
            if pending >= COMMIT_ROWS or time.monotonic() - last_commit >= COMMIT_SECONDS:
                conn.commit()
                pending, last_commit = 0, time.monotonic()
    except Stopped:
        result.stopped = True
    conn.commit()
    report("", force=True)
    return result


def describe(r: ExtractResult) -> str:
    parts = [f"讀出 {r.read:,} 份文件的文字"]
    if r.needs_ocr:
        parts.append(f"{r.needs_ocr:,} 份像掃描檔，之後可以用文字辨識")
    if r.empty:
        parts.append(f"{r.empty:,} 份沒有文字")
    if r.failed:
        parts.append(f"{r.failed:,} 份無法讀取")
    if r.cloud:
        parts.append(f"{r.cloud:,} 份只在雲端、還沒下載到這台電腦（不會替你下載）")
    if r.changed:
        parts.append(f"{r.changed:,} 份在掃描後有變動（重新掃描後再讀）")
    if r.interrupted:
        parts.append("已中斷：" + "、".join(f"「{n}」" for n in r.interrupted) + "，接上後可繼續")
    if r.offline:
        parts.append(f"{r.offline:,} 份在沒接上的硬碟")
    return ("已停止。" if r.stopped else "") + "，".join(parts)


# ---- 搜尋 ----

def body(conn: sqlite3.Connection, file_id: int) -> str:
    r = conn.execute("SELECT body FROM file_text WHERE file_id = ?", (file_id,)).fetchone()
    return zlib.decompress(r["body"]).decode("utf-8") if r and r["body"] else ""


def snippet(text: str, terms: list[str], width: int = 70) -> list[dict]:
    """命中的那一段：[{text, hit}]，hit 的部分由介面用粗體顯示（不是只靠顏色）。找不到時回傳開頭一段。"""
    low = text.lower()
    hits = sorted((low.find(t.lower()), t) for t in terms if t and low.find(t.lower()) >= 0)
    if not hits:
        return [{"text": text[:width * 2].replace("\n", " "), "hit": False}] if text else []
    at = hits[0][0]
    start = max(0, at - width)
    end = min(len(text), at + width)
    piece = text[start:end].replace("\n", " ")
    marks = []
    plow = piece.lower()
    for t in terms:
        i = plow.find(t.lower()) if t else -1
        while i >= 0:
            marks.append((i, i + len(t)))
            i = plow.find(t.lower(), i + len(t))
    marks.sort()
    out, pos = [], 0
    for a, b in marks:
        if a < pos:
            continue
        if a > pos:
            out.append({"text": piece[pos:a], "hit": False})
        out.append({"text": piece[a:b], "hit": True})
        pos = b
    if pos < len(piece):
        out.append({"text": piece[pos:], "hit": False})
    if start > 0:
        out.insert(0, {"text": "…", "hit": False})
    if end < len(text):
        out.append({"text": "…", "hit": False})
    return out


def text_matches(conn: sqlite3.Connection, query: str, limit: int = 200) -> list[int]:
    """全文索引裡符合的檔案（只算文字還是最新的，也就是檔案在讀過之後沒有被改過）。"""
    match = db.fts_query(query)
    if not match:
        return []
    return [r[0] for r in conn.execute(
        "SELECT t.file_id FROM file_fts JOIN file_text t ON t.file_id = file_fts.rowid JOIN files f ON f.id = t.file_id "
        "WHERE file_fts MATCH ? AND f.status = 'ok' AND t.size = f.size AND t.mtime = f.mtime ORDER BY file_fts.rank LIMIT ?",
        (match, limit))]
