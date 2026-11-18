"""音樂資訊：讀出 MP3、FLAC、M4A 等的曲名、演出者、專輯、年份、長度，放進全文索引（可以用歌名、歌手找）。

只讀檔案開頭與結尾的標籤（mutagen），不讀整首歌，也不修改檔案（核心原則七）。
台灣常見的舊 MP3 標籤是 Big5 卻被當成西歐文字存放（看起來是「¦¶¤ß」這種亂碼），這裡會還原成中文。
存法：和文件文字一樣存在 file_text（source＝music），每一行一個欄位，例如「演出者：周杰倫」。
"""

from __future__ import annotations

from pathlib import Path

MUSIC_EXT = {".mp3", ".flac", ".m4a", ".m4b", ".aac", ".ogg", ".oga", ".opus", ".wma", ".aif", ".aiff", ".ape", ".dsf", ".wav", ".alac"}

FIELDS = (  # (存的名稱, 各種格式的標籤名稱)
    ("曲名", ("title", "TIT2", "\xa9nam", "Title", "WM/Title")),
    ("演出者", ("artist", "TPE1", "\xa9ART", "Author", "WM/AlbumArtist")),
    ("專輯演出者", ("albumartist", "TPE2", "aART", "WM/AlbumArtist")),
    ("專輯", ("album", "TALB", "\xa9alb", "WM/AlbumTitle")),
    ("作曲", ("composer", "TCOM", "\xa9wrt", "WM/Composer")),
    ("類型", ("genre", "TCON", "\xa9gen", "WM/Genre")),
    ("年份", ("date", "year", "TDRC", "TYER", "\xa9day", "WM/Year")),
    ("曲目", ("tracknumber", "TRCK", "trkn", "WM/TrackNumber")),
)


class MusicError(Exception):
    """讀不出標籤，訊息是給使用者看的。"""


def fix_text(s: str) -> str:
    """把被當成西歐文字（Latin-1）的 Big5／GB 標籤還原。只有看起來像亂碼時才動。"""
    if not s or all(ord(c) < 128 for c in s) or any(ord(c) > 255 for c in s):
        return s
    raw = s.encode("latin-1")
    if sum(1 for b in raw if b >= 0x80) < 2:  # 中文至少兩個位元組；只有一個的是真的西歐文字（例如 Röyksopp）
        return s
    for enc in ("utf-8", "cp950", "gb18030"):
        try:
            out = raw.decode(enc)
        except UnicodeDecodeError:
            continue
        if any("一" <= c <= "鿿" for c in out) or enc == "utf-8":
            return out
    return s


def _value(v) -> str:
    if isinstance(v, (list, tuple)):
        v = v[0] if v else ""
    if isinstance(v, tuple):  # MP4 的曲目是 (第幾首, 共幾首)
        v = v[0]
    text = getattr(v, "text", None)
    if text is not None:  # ID3 的欄位
        v = text[0] if text else ""
    return fix_text(str(v).strip())


def tags(path: Path) -> dict:
    """{曲名, 演出者, …, 長度（秒）}。只讀取。"""
    try:
        import mutagen
    except ImportError as exc:  # pragma: no cover
        raise MusicError("這台電腦缺少讀音樂資訊的元件") from exc
    try:
        f = mutagen.File(str(path))
    except Exception as exc:  # noqa: BLE001  壞掉的檔案
        raise MusicError("讀不出這個音樂檔的資訊（檔案可能壞了）") from exc
    if f is None:
        return {}
    out: dict = {}
    t = f.tags or {}
    for label, keys in FIELDS:
        for k in keys:
            try:
                v = t.get(k) if hasattr(t, "get") else None
            except (KeyError, ValueError, TypeError):
                v = None
            if v:
                text = _value(v)
                if text:
                    out[label] = text.split("/")[0] if label == "曲目" else text[:300]
                    break
    if "年份" in out:
        out["年份"] = out["年份"][:4]
    length = getattr(getattr(f, "info", None), "length", None)
    if length:
        out["長度"] = int(round(length))
    return out


def as_text(info: dict) -> str:
    lines = [f"{k}：{v}" for k, v in info.items() if k != "長度"]
    if info.get("長度"):
        m, s = divmod(int(info["長度"]), 60)
        lines.append(f"長度：{m}:{s:02d}")
    return "\n".join(lines)


def parse(text: str) -> dict:
    out = {}
    for line in (text or "").splitlines():
        k, sep, v = line.partition("：")
        if sep:
            out[k] = v
    return out
