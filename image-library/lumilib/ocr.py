"""文字辨識（OCR）：用 macOS 內建的辨識引擎（Apple Vision，和「原況文字」相同），完全離線。

辨識的對象（設定「文字辨識範圍」）：
- scans（預設）：沒有文字層的 PDF（掃描檔）與螢幕截圖
- all：再加上所有照片（照片很多時要好幾個小時）
- off：不辨識

辨出來的文字和文件文字放在同一個全文索引裡（file_text，source='ocr'），一樣只讀取檔案、
可以隨時停止或拔掉硬碟、下次從還沒做的繼續；由使用者按下才開始。只有在 Mac 上能用。
"""

from __future__ import annotations

import io
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import textindex

MAX_PDF_PAGES = 200  # 掃描檔最多辨識前 200 頁
PDF_SCALE = 2.0  # 約 144 dpi，文字夠清楚、速度也快
COMMIT_ROWS = 20
COMMIT_SECONDS = 2.0
REPORT_SECONDS = 0.5
SCREENSHOT_WORDS = ["screenshot", "screen shot", "螢幕截圖", "螢幕快照", "截圖", "截屏", "スクリーンショット"]
IMAGE_EXT = ("jpg", "jpeg", "png", "heic", "heif", "tif", "tiff", "webp", "bmp", "gif")
DEFAULT_LANGUAGES = "zh-Hant,zh-Hans,en-US"


class Unavailable(Exception):
    """這台電腦不能做文字辨識（不是 Mac，或系統太舊）。"""


def available() -> bool:
    if sys.platform != "darwin":
        return False
    try:
        import Vision  # noqa: F401
    except Exception:  # noqa: BLE001
        return False
    return True


def _recognize_data(data: bytes, languages: list[str]) -> str:
    """一張圖（PNG、JPEG… 的內容）裡的文字，由上而下、由左而右。"""
    import objc
    import Vision
    from Foundation import NSData

    with objc.autorelease_pool():
        handler = Vision.VNImageRequestHandler.alloc().initWithData_options_(NSData.dataWithBytes_length_(data, len(data)), None)
        req = Vision.VNRecognizeTextRequest.alloc().init()
        req.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
        req.setUsesLanguageCorrection_(True)
        supported, _ = req.supportedRecognitionLanguagesAndReturnError_(None)
        langs = [x for x in languages if not supported or x in supported]
        if langs:
            req.setRecognitionLanguages_(langs)
        ok, err = handler.performRequests_error_([req], None)
        if not ok:
            raise ValueError(str(err) if err else "辨識失敗")
        lines = []
        for obs in req.results() or []:
            cand = obs.topCandidates_(1)
            if cand and len(cand):
                box = obs.boundingBox()
                lines.append((-round(box.origin.y, 2), box.origin.x, str(cand[0].string())))
        lines.sort()
        return "\n".join(t for _, _, t in lines)


def recognize_image(path: Path, languages: list[str]) -> str:
    with open(path, "rb") as fh:
        return _recognize_data(fh.read(), languages)


def recognize_pdf(path: Path, languages: list[str], stop=None) -> str:
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(str(path))
    try:
        out = []
        for i in range(min(len(pdf), MAX_PDF_PAGES)):
            if stop is not None and stop.is_set():
                raise textindex.Stopped
            page = pdf[i]
            image = page.render(scale=PDF_SCALE).to_pil()
            page.close()
            buf = io.BytesIO()
            image.save(buf, format="PNG")
            out.append(recognize(buf.getvalue(), languages))
        return "\n\n".join(out)
    finally:
        pdf.close()


def recognize(data: bytes, languages: list[str]) -> str:
    """測試時可以換掉這個函式（在不是 Mac 的電腦上模擬辨識結果）。"""
    return _recognize_data(data, languages)


def _screenshot_sql() -> str:
    names = " OR ".join(f"lower(f.name) LIKE '%{w}%'" for w in SCREENSHOT_WORDS)
    return f"({names} OR (lower(f.ext) = 'png' AND (i.camera IS NULL OR trim(i.camera) = '')))"


def _candidates_sql(scope: str) -> str | None:
    """要辨識的檔案：還沒辨識過、或辨識之後被改過。"""
    if scope not in ("scans", "all"):
        return None
    exts = ",".join(f"'{e}'" for e in IMAGE_EXT)
    images = f"(f.kind = 'photo' AND lower(f.ext) IN ({exts}) AND {'1' if scope == 'all' else _screenshot_sql()})"
    fresh = "t.size = f.size AND t.mtime = f.mtime"
    # 兩種來源各自用得到索引：像掃描檔的 PDF（讀文字時標記過）、副檔名是圖片的檔案
    return (f"FROM files f JOIN folders d ON d.id = f.folder_id LEFT JOIN file_text t ON t.file_id = f.id "
            f"LEFT JOIN images i ON i.id = f.image_id WHERE f.status = 'ok' AND ("
            f"f.id IN (SELECT file_id FROM file_text WHERE status = 'needs_ocr' "
            f"UNION ALL SELECT id FROM files WHERE status = 'ok' AND lower(ext) IN ({exts}))) AND ("
            f"(t.status = 'needs_ocr' AND {fresh}) OR ({images} AND (t.file_id IS NULL OR NOT ({fresh}))))")


def ocr_plan(conn, scope: str) -> dict:
    sql = _candidates_sql(scope)
    online = {r["id"]: Path(r["path"]).is_dir() for r in conn.execute("SELECT id, path FROM roots")}
    plan = {"todo": 0, "offline": 0}
    if sql:
        for r in conn.execute(f"SELECT f.root_id, COUNT(*) AS n {sql} GROUP BY f.root_id"):
            plan["todo" if online.get(r["root_id"]) else "offline"] += r["n"]
    done = conn.execute("SELECT COUNT(*) FROM file_text WHERE source = 'ocr'").fetchone()[0]
    return {"available": available(), "scope": scope, "todo": plan["todo"], "offline": plan["offline"], "done": done}


@dataclass
class OcrResult:
    read: int = 0
    empty: int = 0
    failed: int = 0
    changed: int = 0
    offline: int = 0
    interrupted: list[str] = field(default_factory=list)
    stopped: bool = False
    held: list[str] = field(default_factory=list)  # 硬碟可能有狀況、等本人決定的（先不碰）
    unavailable: bool = False


def run_ocr(conn, scope: str = "scans", languages: str = DEFAULT_LANGUAGES, progress=None, stop=None, force: bool = False,
            hold: set[int] | None = None) -> OcrResult:
    """辨識還沒辨識的掃描檔與截圖（或所有照片）。force＝不是 Mac 也照做（測試用，會換掉 recognize）。"""
    result = OcrResult()
    sql = _candidates_sql(scope)
    if sql is None:
        return result
    if not force and not available():
        result.unavailable = True
        return result
    langs = [x.strip() for x in (languages or DEFAULT_LANGUAGES).split(",") if x.strip()]
    roots = {r["id"]: r for r in conn.execute("SELECT * FROM roots")}
    online = {rid: Path(r["path"]).is_dir() for rid, r in roots.items()}
    rows = conn.execute(f"SELECT f.id, f.root_id, f.name, f.ext, f.size, f.mtime, d.path AS folder {sql} ORDER BY f.root_id, d.path, f.name").fetchall()
    todo = [r for r in rows if online.get(r["root_id"])]
    result.offline = len(rows) - len(todo)
    if hold:
        result.held = sorted({roots[r["root_id"]]["name"] for r in todo if r["root_id"] in hold})
        todo = [r for r in todo if r["root_id"] not in hold]
    total, done = len(todo), 0
    pending, last_commit, last_report = 0, time.monotonic(), 0.0
    dead: set[int] = set()
    try:
        for r in todo:
            if stop is not None and stop.is_set():
                raise textindex.Stopped
            done += 1
            if r["root_id"] in dead:
                continue
            root = roots[r["root_id"]]
            path = Path(root["path"]).joinpath(*[p for p in r["folder"].split("/") if p], r["name"])
            now = time.monotonic()
            if progress and now - last_report >= REPORT_SECONDS:
                last_report = now
                progress(done, total, f"{root['name']}：{r['name']}")
            try:
                st = path.stat()
                if st.st_size != r["size"] or st.st_mtime != r["mtime"]:
                    result.changed += 1
                    continue
                if (r["ext"] or "").lower() == "pdf":  # 掃描檔：每一頁轉成圖片再辨識
                    text = recognize_pdf(path, langs, stop)
                else:
                    with open(path, "rb") as fh:
                        text = recognize(fh.read(), langs)
                text = textindex.clean(text)
                textindex._store(conn, r["id"], r["size"], r["mtime"], "ocr", text, "ok" if text else "empty")
                if text:
                    result.read += 1
                else:
                    result.empty += 1
            except textindex.Stopped:
                raise
            except OSError as exc:
                if not Path(root["path"]).is_dir():
                    dead.add(r["root_id"])
                    result.interrupted.append(root["name"])
                    continue
                if textindex._health_stop(conn, r["root_id"], exc):  # 讀取錯誤太多：這顆先停，等本人決定
                    dead.add(r["root_id"])
                    result.held.append(root["name"])
                textindex._store(conn, r["id"], r["size"], r["mtime"], "ocr", "", "error", "無法讀取這個檔案")
                result.failed += 1
            except Exception as exc:  # noqa: BLE001
                textindex._store(conn, r["id"], r["size"], r["mtime"], "ocr", "", "error", f"無法辨識：{type(exc).__name__}")
                result.failed += 1
            pending += 1
            if pending >= COMMIT_ROWS or time.monotonic() - last_commit >= COMMIT_SECONDS:
                conn.commit()
                pending, last_commit = 0, time.monotonic()
    except textindex.Stopped:
        result.stopped = True
    conn.commit()
    if progress:
        progress(done, total, "")
    return result


def describe(r: OcrResult) -> str:
    if r.unavailable:
        return "文字辨識只能在 Mac 上使用"
    parts = [f"辨識出 {r.read:,} 個檔案的文字"]
    if r.empty:
        parts.append(f"{r.empty:,} 個沒有找到文字")
    if r.failed:
        parts.append(f"{r.failed:,} 個無法辨識")
    if r.changed:
        parts.append(f"{r.changed:,} 個在掃描後有變動")
    if r.interrupted:
        parts.append("已中斷：" + "、".join(f"「{n}」" for n in r.interrupted) + "，接上後可繼續")
    if r.held:
        parts.append("、".join(f"「{n}」" for n in r.held) + " 可能有狀況，先停下來，等你決定怎麼處理")
    if r.offline:
        parts.append(f"{r.offline:,} 個在沒接上的硬碟")
    return ("已停止。" if r.stopped else "") + "，".join(parts)
