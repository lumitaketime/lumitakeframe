"""文件封面縮圖：PDF 的第一頁、電子書的封面、Office／iWork 檔裡附的預覽圖；Mac 上其他文件用系統的 Quick Look 產生。

- 只讀硬碟上的檔案；縮圖存在 Re'memor 的資料目錄（covers 資料夾），不寫到硬碟（核心原則七）。
- 掃描完在背景做，可以停止、下次接著做；硬碟沒接上的先跳過。
- 做不出來的（加密、壞掉、沒有預覽）記下來，不會一直重做；檔案改過才重做。
"""
from __future__ import annotations

import io
import re
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path, PurePosixPath

from . import db

SIZE = 512  # 長邊幾像素
PDF = {"pdf"}
EPUB = {"epub"}
OFFICE = {"docx", "pptx", "xlsx", "docm", "pptm", "xlsm", "odt", "odp", "ods"}
IWORK = {"pages", "key", "numbers"}
QUICKLOOK = {"doc", "ppt", "xls", "rtf", "rtfd", "ai", "psd", "indd", "eps", "svg", "mobi", "azw3"}  # 只有 Mac
MAX_BYTES = 2_000_000_000  # 太大的檔案不做（讀太久）
COMMIT_SECONDS = 2.0


def supported() -> set[str]:
    out = PDF | EPUB | OFFICE | IWORK
    if sys.platform == "darwin" and shutil.which("qlmanage"):
        out |= QUICKLOOK
    return out


def cover_path(home: Path, file_id: int) -> Path:
    return Path(home) / "covers" / f"{int(file_id) % 256:02x}" / f"{int(file_id)}.jpg"


def _save(img, out: Path) -> None:
    from PIL import Image

    img = img.convert("RGB") if img.mode not in ("RGB", "L") else img
    img.thumbnail((SIZE, SIZE), Image.LANCZOS)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    img.save(tmp, "JPEG", quality=82)
    tmp.replace(out)


def _pdf(path: Path):
    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument(str(path))
    try:
        page = doc[0]
        w, h = page.get_size()
        scale = SIZE * 1.5 / max(w, h, 1)
        return page.render(scale=max(0.2, min(scale, 4))).to_pil()
    finally:
        doc.close()


def _image_from_zip(z: zipfile.ZipFile, name: str):
    from PIL import Image

    with z.open(name) as fh:
        img = Image.open(io.BytesIO(fh.read()))
        img.load()
        return img


def _epub(path: Path):
    """電子書的封面：OPF 裡指定的封面圖，沒有就找名字有 cover 的圖。"""
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        opf = None
        try:
            container = z.read("META-INF/container.xml").decode("utf-8", "ignore")
            m = re.search(r'full-path="([^"]+)"', container)
            opf = m.group(1) if m else None
        except KeyError:
            pass
        if opf and opf in names:
            text = z.read(opf).decode("utf-8", "ignore")
            base = PurePosixPath(opf).parent
            cover_id = None
            m = re.search(r'<meta[^>]+name="cover"[^>]+content="([^"]+)"', text) or re.search(r'<meta[^>]+content="([^"]+)"[^>]+name="cover"', text)
            if m:
                cover_id = m.group(1)
            for item in re.finditer(r"<item\b[^>]*>", text):
                tag = item.group(0)
                href = re.search(r'href="([^"]+)"', tag)
                if not href:
                    continue
                is_cover = 'properties="cover-image"' in tag or (cover_id and re.search(rf'id="{re.escape(cover_id)}"', tag))
                if is_cover:
                    target = str(base / href.group(1)) if str(base) != "." else href.group(1)
                    if target in names:
                        return _image_from_zip(z, target)
        imgs = [n for n in names if re.search(r"\.(jpe?g|png|gif)$", n, re.I)]
        for n in sorted(imgs, key=lambda n: ("cover" not in n.lower(), len(n))):
            return _image_from_zip(z, n)
    return None


def _zip_preview(path: Path):
    """Office 與 iWork 檔裡附的預覽圖（存檔時程式自己放進去的）。"""
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        for want in ("docProps/thumbnail.jpeg", "docProps/thumbnail.jpg", "docProps/thumbnail.png", "Thumbnails/thumbnail.png",
                     "QuickLook/Thumbnail.jpg", "QuickLook/Preview.jpg", "preview.jpg", "preview-web.jpg"):
            if want in names:
                return _image_from_zip(z, want)
    return None


def _quicklook(path: Path):
    """Mac 系統內建的預覽（qlmanage）。產生的圖放在暫存資料夾，讀進來後就刪掉。"""
    from PIL import Image

    with tempfile.TemporaryDirectory(prefix="rememor-ql-") as tmp:
        subprocess.run(["qlmanage", "-t", "-s", str(SIZE), "-o", tmp, str(path)], capture_output=True, timeout=60)
        made = list(Path(tmp).glob("*.png"))
        if not made:
            return None
        img = Image.open(made[0])
        img.load()
        return img


def render(path: Path, ext: str):
    ext = (ext or "").lower()
    if ext in PDF:
        return _pdf(path)
    if ext in EPUB:
        return _epub(path)
    if ext in OFFICE or ext in IWORK:
        img = _zip_preview(path)
        if img is None and sys.platform == "darwin" and shutil.which("qlmanage"):
            img = _quicklook(path)
        return img
    if ext in QUICKLOOK and sys.platform == "darwin":
        return _quicklook(path)
    return None


def _todo_sql() -> tuple[str, list]:
    exts = sorted(supported())
    return (f"FROM files f JOIN folders d ON d.id = f.folder_id LEFT JOIN file_covers c ON c.file_id = f.id "
            f"WHERE f.status = 'ok' AND lower(f.ext) IN ({','.join('?' * len(exts))}) AND f.size > 0 AND f.size <= {MAX_BYTES} "
            "AND (c.file_id IS NULL OR c.sig != f.size || '|' || f.mtime)", exts)


def plan(conn) -> dict:
    sql, args = _todo_sql()
    online = {r["id"] for r in conn.execute("SELECT id, path FROM roots") if Path(r["path"]).is_dir()}
    n = 0
    for r in conn.execute(f"SELECT f.root_id, COUNT(*) AS n {sql} GROUP BY f.root_id", args):
        if r["root_id"] in online:
            n += r["n"]
    return {"todo": n}


def run(conn, home: Path, progress=None, stop=None, hold: set[int] | None = None) -> dict:
    """替還沒有封面的文件做封面。只讀硬碟；做好的存在 home/covers。"""
    sql, args = _todo_sql()
    roots = {r["id"]: r for r in conn.execute("SELECT * FROM roots")}
    online = {rid for rid, r in roots.items() if Path(r["path"]).is_dir() and rid not in (hold or set())}
    rows = [r for r in conn.execute(f"SELECT f.id, f.root_id, f.name, f.ext, f.size, f.mtime, d.path AS folder {sql} "
                                    "ORDER BY f.root_id, d.path, f.name", args).fetchall() if r["root_id"] in online]
    made = failed = 0
    last = time.monotonic()
    for i, r in enumerate(rows):
        if stop is not None and stop.is_set():
            break
        if progress:
            progress(i, len(rows), r["name"])
        root = Path(roots[r["root_id"]]["path"])
        if not root.is_dir():
            online.discard(r["root_id"])
            continue
        path = root.joinpath(*[p for p in (r["folder"] or "").split("/") if p], r["name"])
        ok = 0
        try:
            img = render(path, r["ext"])
            if img is not None:
                _save(img, cover_path(home, r["id"]))
                ok = 1
        except Exception:  # noqa: BLE001  壞掉、加密、格式怪的文件：記下來做不出來，不影響其他
            ok = 0
        if not root.is_dir():  # 做的過程中被拔掉：這一個不算，下次再做
            continue
        # 記下這次做的是哪個版本（大小與修改時間；在資料庫裡組字串，和檢查時的寫法一致）
        conn.execute("INSERT OR REPLACE INTO file_covers (file_id, sig, ok, made_at) SELECT id, size || '|' || mtime, ?, ? FROM files WHERE id = ?",
                     (ok, db.now_iso(), r["id"]))
        made += ok
        failed += 1 - ok
        if time.monotonic() - last >= COMMIT_SECONDS:
            conn.commit()
            last = time.monotonic()
    conn.commit()
    if progress:
        progress(len(rows), len(rows), "")
    return {"made": made, "failed": failed, "stopped": bool(stop is not None and stop.is_set())}


def describe(res: dict) -> str:
    text = f"做好 {res['made']:,} 份文件的封面"
    if res["failed"]:
        text += f"，{res['failed']:,} 份沒有預覽可以用（例如加密或沒有封面）"
    if res.get("stopped"):
        text += "；已停止，下次接著做"
    return text
