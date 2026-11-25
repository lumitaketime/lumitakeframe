"""語言包：中文、英文內建；日文、韓文、德文、法文可以在設定裡加入。

語言包決定兩件事：
1. 文字辨識（OCR）認得哪些語言（Apple Vision 的語言代碼）。
2. 搜尋怎麼處理詞形變化：英文一定處理（搜 report 也找得到 reports）；加入德文、法文後也處理那兩種語言。
   中文、日文、韓文都是一個字一個字加上兩字一組，不必另外斷詞。

全文索引存的是「詞根」（reports → report），搜尋時也換成詞根再找，兩邊一致。
每份文字先看比較像哪一種語言（英文、德文、法文），整份用那一種的規則；搜尋時每一種都試。
"""
from __future__ import annotations

import re
from functools import lru_cache

PACKS = {
    "ja": {"ocr": ["ja-JP"], "stem": None},
    "ko": {"ocr": ["ko-KR"], "stem": None},
    "de": {"ocr": ["de-DE"], "stem": "german"},
    "fr": {"ocr": ["fr-FR"], "stem": "french"},
}
BASE_OCR = ["zh-Hant", "zh-Hans", "en-US"]
VERSION = 1  # 斷詞規則改了就加一（目錄會在背景重建索引）

# 用來猜語言的常見字（每種語言二十來個）
_STOP = {
    "english": {"the", "and", "of", "to", "in", "is", "that", "for", "with", "on", "as", "are", "this", "be", "by", "from", "it", "or", "was", "an"},
    "german": {"der", "die", "und", "das", "ist", "nicht", "mit", "den", "von", "zu", "ein", "eine", "auf", "für", "im", "sich", "des", "dem", "auch", "werden"},
    "french": {"le", "la", "les", "et", "des", "est", "une", "un", "du", "dans", "que", "pour", "pas", "qui", "sur", "au", "avec", "il", "sont", "ce"},
}
_LATIN = re.compile(r"[^\W\d_]+")

_state = {"langs": ("english",)}  # 目前有哪些詞形規則


def configure(packs) -> tuple[str, ...]:
    """套用目前加入的語言包（程式啟動、本人改設定時）。回傳啟用的詞形規則。"""
    langs = ["english"] + [PACKS[p]["stem"] for p in sorted(set(packs or [])) if p in PACKS and PACKS[p]["stem"]]
    _state["langs"] = tuple(langs)
    return _state["langs"]


def parse(value) -> list[str]:
    if isinstance(value, (list, tuple)):
        items = value
    else:
        items = str(value or "").replace(" ", "").split(",")
    return [p for p in dict.fromkeys(items) if p in PACKS]


def ocr_languages(packs) -> str:
    codes = list(BASE_OCR)
    for p in parse(packs):
        codes += PACKS[p]["ocr"]
    return ",".join(dict.fromkeys(codes))


def signature() -> str:
    """索引用的是哪一套規則（變了就要重建）。"""
    return f"{VERSION}:" + ",".join(_state["langs"])


@lru_cache(maxsize=8)
def _stemmer(lang: str):
    try:
        import snowballstemmer
    except ImportError:  # 還沒裝好：先不處理詞形變化
        return None
    return snowballstemmer.stemmer(lang)


@lru_cache(maxsize=200_000)
def stem(word: str, lang: str) -> str:
    s = _stemmer(lang)
    if s is None or len(word) < 3:
        return word
    return s.stemWord(word) or word


def guess(text: str) -> str:
    """這段文字比較像哪一種（只在啟用的規則裡挑）。看不出來就用英文。"""
    langs = _state["langs"]
    if len(langs) == 1:
        return langs[0]
    words = _LATIN.findall(text[:20000])
    best, score = "english", 0
    for lang in langs:
        stop = _STOP.get(lang, set())
        n = sum(1 for w in words if w in stop)
        if n > score:
            best, score = lang, n
    return best


def stem_text(text: str, lang: str | None = None) -> str:
    """把拉丁字母的詞換成詞根（已經是小寫）。數字與中日韓文字不動。"""
    lang = lang or guess(text)
    return _LATIN.sub(lambda m: stem(m.group(), lang), text)


def variants(word: str) -> list[str]:
    """搜尋時一個詞的各種詞根（每一種啟用的規則各一個），去掉重複。"""
    return list(dict.fromkeys(stem(word, lang) for lang in _state["langs"]))
