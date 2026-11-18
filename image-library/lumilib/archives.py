"""壓縮檔內容：不解壓縮，只讀出裡面有哪些檔案（ZIP、RAR、7z、tar、ISO）。

只讀取（核心原則第 7 條）：不解開任何檔案、不在硬碟上建立暫存檔；讀出來的檔案清單存在 Re'memor 的資料庫，
和文件文字一起放進全文索引，所以搜尋「報告」也找得到壓縮檔裡的「期末報告.docx」，硬碟拔掉也搜得到。

做法：
- ZIP：Python 內建的 zipfile，只讀檔尾的目錄（再大的 ZIP 也只讀幾 KB）。舊的 Windows 中文 ZIP 檔名不是 UTF-8，
  依序試 UTF-8、Big5（繁體）、GB18030（簡體）、Shift_JIS（日文）。
- tar、tar.gz：Python 內建的 tarfile；壓縮過的 tar 要從頭讀到尾才知道內容，超過 2 GB 的就不讀。
- RAR、7z、ISO：macOS 內建的 bsdtar（libarchive），只列出清單（-t），不解開。
不會往下讀「壓縮檔裡的壓縮檔」。
"""

from __future__ import annotations

import os
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

MAX_ENTRIES = 20_000  # 每個壓縮檔最多記這麼多個檔案
MAX_STREAM = 2_000_000_000  # 壓縮過的 tar 要整個讀過，超過這個大小就不讀
TIMEOUT = 180

ZIP_EXT = {".zip"}
TAR_EXT = {".tar", ".tgz", ".tbz", ".tbz2", ".txz", ".gz", ".bz2", ".xz"}
STREAM_EXT = {".tgz", ".tbz", ".tbz2", ".txz", ".gz", ".bz2", ".xz"}  # 要從頭讀到尾的
BSDTAR_EXT = {".rar", ".7z", ".iso", ".cab", ".lha", ".lzh", ".xar"}
ARCHIVE_EXT = ZIP_EXT | TAR_EXT | BSDTAR_EXT


class ArchiveError(Exception):
    """讀不出清單，訊息是給使用者看的。"""


class NoTool(ArchiveError):
    """這台電腦沒有讀這種壓縮檔的工具。"""


def _zip_name(info: zipfile.ZipInfo) -> str:
    if info.flag_bits & 0x800:  # 檔名標明是 UTF-8
        return info.filename
    try:
        raw = info.filename.encode("cp437")
    except UnicodeEncodeError:
        return info.filename
    for enc in ("utf-8", "cp950", "gb18030", "shift_jis"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return info.filename


def _keep(name: str) -> bool:
    """不記錄資料夾本身與 Mac 壓縮時多出來的隱藏檔（__MACOSX、.DS_Store）。"""
    name = name.replace("\\", "/").strip("/")
    if not name:
        return False
    parts = name.split("/")
    return parts[0] != "__MACOSX" and parts[-1] != ".DS_Store"


def _zip(path: Path) -> list[str]:
    try:
        with zipfile.ZipFile(path) as z:
            return [_zip_name(i).replace("\\", "/") for i in z.infolist() if not i.is_dir()]
    except zipfile.BadZipFile as exc:
        raise ArchiveError("這個 ZIP 檔壞了或不完整") from exc


def _tar(path: Path, stop=None) -> list[str]:
    if path.suffix.lower() in STREAM_EXT and path.stat().st_size > MAX_STREAM:
        raise ArchiveError("壓縮過的 tar 超過 2 GB，要整個讀過才知道內容，所以不讀")
    out = []
    try:
        with tarfile.open(path, mode="r:*") as t:
            for m in t:
                if stop is not None and stop.is_set():
                    break
                if m.isfile():
                    out.append(m.name)
                    if len(out) > MAX_ENTRIES:
                        break
    except tarfile.ReadError as exc:
        if path.suffix.lower() in (".gz", ".bz2", ".xz"):
            return []  # 單一檔案的壓縮（不是 tar）：裡面沒有清單可讀
        raise ArchiveError("這個壓縮檔壞了或不完整") from exc
    except EOFError as exc:
        raise ArchiveError("這個壓縮檔不完整（可能沒有下載或複製完）") from exc
    return out


def bsdtar() -> str | None:
    for p in ("/usr/bin/bsdtar", "/opt/homebrew/bin/bsdtar", "/usr/local/bin/bsdtar"):
        if os.path.exists(p):
            return p
    return None


def _bsdtar(path: Path) -> list[str]:
    tool = bsdtar()
    if tool is None:
        raise NoTool("這台電腦沒有讀 RAR、7z 的工具（Mac 內建有）")
    loc = "en_US.UTF-8" if sys.platform == "darwin" else "C.UTF-8"  # 檔名一律用 UTF-8 輸出
    env = {**os.environ, "LC_ALL": loc, "LANG": loc}
    try:
        proc = subprocess.run([tool, "-tf", str(path)], capture_output=True, timeout=TIMEOUT, env=env)
    except subprocess.TimeoutExpired as exc:
        raise ArchiveError("讀太久了（可能是很大的壓縮檔），先跳過") from exc
    lines = proc.stdout.decode("utf-8", errors="replace").splitlines()
    if proc.returncode != 0 and not lines:
        err = proc.stderr.decode("utf-8", errors="replace").lower()
        if "encrypt" in err or "passphrase" in err or "password" in err:
            raise ArchiveError("有密碼保護，看不到裡面的檔案")
        raise ArchiveError("讀不出這個壓縮檔的內容" + (f"（{err.strip()[:120]}）" if err.strip() else ""))
    return [ln for ln in lines if ln and not ln.endswith("/")]


def _tidy(name: str) -> str:
    name = name.replace("\\", "/")
    while name.startswith("./"):
        name = name[2:]
    return name.lstrip("/")


def entries(path: Path, stop=None) -> tuple[list[str], int]:
    """壓縮檔裡的檔案（路徑），回傳（最多 MAX_ENTRIES 個、總數）。只讀取。"""
    ext = path.suffix.lower()
    if ext in ZIP_EXT:
        names = _zip(path)
    elif ext in TAR_EXT:
        names = _tar(path, stop)
    elif ext in BSDTAR_EXT:
        names = _bsdtar(path)
    else:
        raise ArchiveError("不支援這種壓縮檔")
    names = [_tidy(n) for n in names]
    names = [n for n in names if _keep(n)]
    return names[:MAX_ENTRIES], len(names)


def as_text(names: list[str], total: int) -> str:
    """存進資料庫的樣子：一行一個路徑；太多的話最後註明還有幾個。"""
    text = "\n".join(names)
    if total > len(names):
        text += f"\n…還有 {total - len(names):,} 個檔案"
    return text


def listing(text: str) -> list[dict]:
    """把存起來的清單變回 [{path, name, folder}]（給預覽與搜尋結果用）。"""
    out = []
    for line in (text or "").splitlines():
        if not line or line.startswith("…"):
            continue
        folder, _, name = line.rpartition("/")
        out.append({"path": line, "name": name, "folder": folder})
    return out


def matching(text: str, terms: list[str], limit: int = 3) -> list[str]:
    """清單裡符合搜尋詞的路徑（每個詞都要出現，不分大小寫）；沒有全部符合的，就找符合任一個詞的。"""
    words = [t.lower() for t in terms if t]
    if not words:
        return []
    lines = [ln for ln in (text or "").splitlines() if ln and not ln.startswith("…")]
    low = [ln.lower() for ln in lines]
    hits = [lines[i] for i, ln in enumerate(low) if all(w in ln for w in words)]
    if not hits:
        hits = [lines[i] for i, ln in enumerate(low) if any(w in ln for w in words)]
    return hits[:limit]
