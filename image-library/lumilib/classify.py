"""自動分類：替每個資料夾標上「主題分類」（學校與學習、工作、旅行與活動…），檔案跟著資料夾，也可以單獨改。

三層，由便宜到貴：
1. 規則（不用 AI，掃描完自動跑）：看資料夾名稱（中英文關鍵字）、裡面大多是什麼（音樂、電子書、安裝檔…）；
   子資料夾沿用上層的分類，除非它自己有更明確的特徵。
2. AI（只處理規則分不出來的資料夾）：只交資料夾名稱、路徑、前幾十個檔名、類型比例；
   用這台電腦上的模型時，可以再加幾份文件開頭的一小段。信心低的放進「請你確認」。
3. 本人的修正（核心原則八）：和規則、AI 的結果分開存放，永遠優先，重新分析也不會覆蓋；
   修正會變成「學到的規則」（名稱相近的資料夾照你的習慣分），最近的修正也會當作範例交給 AI。

分類只記在目錄裡，不改硬碟上的檔名或位置（核心原則七）。

存法：
- categories：分類清單（內建的 key 固定，名稱可以改；也可以自己加）。
- category_user：本人設定的（target＝folder:編號／file:編號；category 為 NULL＝不分類）。
- category_ai：AI 的建議（含信心、理由；資料夾內容沒變就不重問）。
- category_learned：從本人修正學到的名稱規則（詞 → 分類）。
- folder_category：每個資料夾「目前算哪一類」（重新計算的結果，查詢、統計用）。
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass

from . import db

BUILTIN = ("school", "work", "travel", "life", "finance", "creative", "hobby", "software", "other")
NAMES = {  # 預設名稱（介面上依語言顯示；本人改過名字就用本人的）
    "school": "學校與學習", "work": "工作", "travel": "旅行與活動", "life": "家人與生活", "finance": "財務與證件",
    "creative": "作品與創作", "hobby": "興趣與收藏", "software": "軟體與系統", "other": "其他",
}

# 資料夾名稱的關鍵字：中文（以及日文漢字）用「包含」比對，英文用整個字比對
KEYWORDS = {
    "school": ("國小", "國中", "高中", "高職", "大學", "研究所", "碩士", "博士", "學校", "作業", "報告", "期中", "期末", "考試", "考卷",
               "講義", "課程", "上課", "筆記", "學期", "社團", "畢業", "論文", "學習", "補習", "自然科", "數學", "英文課",
               "homework", "assignment", "assignments", "school", "university", "college", "course", "courses", "lecture",
               "lectures", "exam", "exams", "thesis", "class", "semester", "study", "notes"),
    "work": ("工作", "公司", "專案", "會議", "簡報", "客戶", "履歷", "求職", "報價", "提案", "業務", "行銷", "企劃", "出差",
             "work", "office", "project", "projects", "meeting", "meetings", "client", "clients", "proposal", "resume", "cv",
             "business", "marketing"),
    "travel": ("旅行", "旅遊", "出遊", "出國", "自由行", "行程", "景點", "畢旅", "露營", "登山",
               "trip", "travel", "travels", "vacation", "holiday", "holidays", "tour", "camping", "hiking"),
    "life": ("家人", "家庭", "小孩", "寶寶", "婚禮", "生日", "聚餐", "朋友", "同學會", "寵物", "生活", "日常", "爸媽", "爺爺", "奶奶",
             "family", "kids", "baby", "wedding", "birthday", "pet", "pets", "party", "friends", "home"),
    "finance": ("發票", "收據", "報稅", "所得稅", "帳單", "銀行", "保險", "合約", "契約", "證件", "身分證", "護照", "存摺", "薪資", "貸款",
                "房貸", "繳費", "invoice", "invoices", "receipt", "receipts", "tax", "taxes", "bank", "insurance", "contract",
                "contracts", "passport", "statement", "statements", "payslip", "loan", "bills"),
    "creative": ("作品", "創作", "設計", "繪畫", "插畫", "剪輯", "作品集", "攝影作品", "影片製作", "混音", "編曲",
                 "portfolio", "design", "designs", "artwork", "drawing", "drawings", "illustration", "render", "renders", "edit"),
    "hobby": ("音樂", "歌曲", "電子書", "小說", "漫畫", "遊戲", "動畫", "電影", "影集", "收藏", "樂譜",
              "music", "songs", "ebook", "ebooks", "books", "novel", "novels", "comic", "comics", "manga", "game", "games",
              "anime", "movie", "movies", "collection"),
    "software": ("安裝", "安裝檔", "軟體", "驅動", "驅動程式", "系統備份", "installer", "installers", "setup", "software", "drivers",
                 "driver", "apps", "programs", "iso"),
}
INSTALLER_EXT = ("dmg", "pkg", "exe", "msi", "iso", "apk", "ipa", "deb", "rpm")
EBOOK_EXT = ("epub", "mobi", "azw", "azw3", "kfx")
CREATIVE_EXT = ("psd", "ai", "indd", "prproj", "aep", "fcpbundle", "blend", "sketch", "fig", "kra", "procreate", "logicx", "als", "ptx")

REVIEW_BELOW = 0.6  # AI 信心低於這個：放進「請你確認」
_CJK = re.compile(r"[぀-ヿ㐀-鿿豈-﫿]+")
_WORD = re.compile(r"[a-z]+")


# ---- 分類清單 ----

def ensure_categories(conn: sqlite3.Connection, commit: bool = True) -> None:
    if conn.execute("SELECT COUNT(*) FROM categories").fetchone()[0]:
        return
    conn.executemany("INSERT OR IGNORE INTO categories (key, name, position, builtin) VALUES (?, NULL, ?, 1)",
                     [(k, i) for i, k in enumerate(BUILTIN)])
    if commit:
        conn.commit()


def categories(conn: sqlite3.Connection, include_merged: bool = False) -> list[dict]:
    """[{key, name（本人改過才有）, builtin, description, examples, merged_into}]，依順序。
    合併掉的分類（merged_into 有值）預設不列。"""
    ensure_categories(conn)
    out = []
    for r in conn.execute("SELECT * FROM categories ORDER BY position, key"):
        if r["merged_into"] and not include_merged:
            continue
        try:
            examples = json.loads(r["examples"]) if r["examples"] else []
        except ValueError:
            examples = []
        out.append({"key": r["key"], "name": r["name"], "builtin": bool(r["builtin"]), "description": r["description"] or "",
                    "examples": examples, "merged_into": r["merged_into"]})
    return out


def valid_keys(conn: sqlite3.Connection) -> set[str]:
    return {c["key"] for c in categories(conn)}


def display_name(c: dict) -> str:
    return c.get("name") or NAMES.get(c["key"], c["key"])


def _resolver(conn: sqlite3.Connection):
    """合併掉的分類 → 合併後的那一類（最多追五層）。"""
    merged = {r["key"]: r["merged_into"] for r in conn.execute("SELECT key, merged_into FROM categories")}

    def resolve(key):
        for _ in range(5):
            nxt = merged.get(key)
            if not nxt:
                return key if key in merged else None
            key = nxt
        return key
    return resolve


def add_category(conn: sqlite3.Connection, name: str, description: str = "", commit: bool = True) -> str:
    name = (name or "").strip()[:40]
    if not name:
        raise ValueError("請輸入分類名稱")
    key = "c" + str(int(conn.execute("SELECT COALESCE(MAX(rowid), 0) + 1 FROM categories").fetchone()[0]))
    pos = conn.execute("SELECT COALESCE(MAX(position), 0) + 1 FROM categories").fetchone()[0]
    conn.execute("INSERT INTO categories (key, name, position, builtin, description) VALUES (?, ?, ?, 0, ?)",
                 (key, name, pos, (description or "").strip()[:300] or None))
    if commit:
        conn.commit()
    return key


def rename_category(conn: sqlite3.Connection, key: str, name: str | None, commit: bool = True) -> None:
    """改名；內建的分類給空白＝改回預設名稱。"""
    row = conn.execute("SELECT builtin FROM categories WHERE key = ?", (key,)).fetchone()
    if row is None:
        raise ValueError("找不到這個分類")
    name = (name or "").strip()[:40] or None
    if name is None and not row["builtin"]:
        raise ValueError("請輸入分類名稱")
    conn.execute("UPDATE categories SET name = ? WHERE key = ?", (name, key))
    if commit:
        conn.commit()


def delete_category(conn: sqlite3.Connection, key: str, commit: bool = True) -> None:
    """只能刪自己加的分類：用到它的資料夾改回「自動」（本人的設定、學到的規則、關鍵字規則拿掉）。"""
    row = conn.execute("SELECT builtin FROM categories WHERE key = ?", (key,)).fetchone()
    if row is None or row["builtin"]:
        raise ValueError("內建的分類不能刪除，可以改名或合併到別的分類")
    for table in ("category_user", "category_learned", "category_rules"):
        conn.execute(f"DELETE FROM {table} WHERE category = ?", (key,))
    conn.execute("DELETE FROM categories WHERE key = ?", (key,))
    if commit:
        conn.commit()
        run_rules(conn)


# ---- 年份 ----

_YEAR = re.compile(r"(?<!\d)(19[5-9]\d|20[0-4]\d)(?!\d)")
_ROC = re.compile(r"(?:民國\s*(\d{2,3}))|(?<!\d)(\d{2,3})\s*(?:學年度|學年|年度|上學期|下學期|學期|年(?!級|班))")


def name_year(name: str) -> int | None:
    """資料夾名稱裡的年份：西元（2015）或民國（105 學年、98 年、民國 98）。看不出來回傳 None。"""
    m = _YEAR.search(name or "")
    if m:
        return int(m.group(1))
    m = _ROC.search(name or "")
    if m:
        n = int(m.group(1) or m.group(2))
        if 50 <= n <= 130:
            return n + 1911
    return None


_STATS_CACHE: dict = {}


def _folder_stats(conn: sqlite3.Connection) -> tuple[dict, dict]:
    """每個資料夾的「內容組成」（安裝檔、電子書、創作檔各幾個）與檔案年份的加總。
    要走過所有檔案一次（一百萬個檔案約 3 秒），所以算好就記著，檔案有變動（掃描過）才重算；
    改分類、看影響範圍時不必再走一次。"""
    path = conn.execute("PRAGMA database_list").fetchone()["file"]
    r = conn.execute("SELECT (SELECT MAX(id) FROM files) AS m, (SELECT COUNT(*) FROM files WHERE status = 'ok') AS n, "
                     "(SELECT MAX(last_scan) FROM roots) AS t, (SELECT COUNT(*) FROM folders) AS f").fetchone()
    sig = (path, r["m"], r["n"], r["t"], r["f"])
    hit = _STATS_CACHE.get(path)
    if hit and hit[0] == sig:
        return hit[1], hit[2]
    inst = ",".join(f"'{e}'" for e in INSTALLER_EXT)
    ebook = ",".join(f"'{e}'" for e in EBOOK_EXT)
    creative = ",".join(f"'{e}'" for e in CREATIVE_EXT)
    groups: dict[int, tuple] = {}
    sums: dict[int, list] = {}
    for x in conn.execute(
            f"SELECT folder_id, COUNT(*) AS n, SUM(ext IN ({inst})) AS a, SUM(ext IN ({ebook})) AS b, SUM(ext IN ({creative})) AS c, "
            "SUM(CASE WHEN mtime > 0 THEN mtime ELSE 0 END) AS ys, SUM(mtime > 0) AS yn FROM files WHERE status = 'ok' GROUP BY folder_id"):
        groups[x["folder_id"]] = (x["n"], x["a"] or 0, x["b"] or 0, x["c"] or 0)
        if x["yn"]:
            sums[x["folder_id"]] = [x["ys"], x["yn"]]
    comp = {}
    for fid, (n, a, b, c) in groups.items():
        for count, cat, reason in ((a, "software", "裡面大多是安裝檔"), (b, "hobby", "裡面大多是電子書"), (c, "creative", "裡面大多是設計、剪輯等創作檔")):
            if count >= 2 and count >= 0.5 * max(1, n):
                comp[fid] = (cat, reason)
                break
    years = _years_from(conn, sums)
    _STATS_CACHE[path] = (sig, comp, years)
    return comp, years


def _years_from(conn: sqlite3.Connection, sums: dict) -> dict[int, int]:
    """由深到淺，把裡面資料夾的加總加到上層，算出每個資料夾（連同裡面）檔案的平均年份。"""
    import time as _time

    sums = {k: list(v) for k, v in sums.items()}
    for r in conn.execute("SELECT id, parent_id FROM folders WHERE status = 'ok' ORDER BY length(path) - length(replace(path, '/', '')) DESC, length(path) DESC"):
        mine = sums.get(r["id"])
        if mine and r["parent_id"]:
            up = sums.setdefault(r["parent_id"], [0, 0])
            up[0] += mine[0]
            up[1] += mine[1]
    out = {}
    for fid, (total, n) in sums.items():
        if n:
            try:
                out[fid] = _time.localtime(total / n).tm_year
            except (OverflowError, ValueError, OSError):
                pass
    return out


def _file_years(conn: sqlite3.Connection) -> dict[int, int]:
    """每個資料夾（連同裡面的資料夾）檔案的修改日期平均是哪一年。複製過的檔案可能是複製當天，所以只在名稱看不出年份時用。"""
    return _folder_stats(conn)[1]


# ---- 規則 ----

def _name_hit(name: str, words: tuple[str, ...]) -> str | None:
    low = name.lower()
    tokens = set(_WORD.findall(low))
    for w in words:
        if (w in tokens) if w.isascii() else (w in low):
            return w
    return None


def _matches(pattern: str, low: str, words: set[str]) -> bool:
    p = pattern.lower()
    return (p in words) if p.isascii() and p.isalnum() else (p in low)


def tokens_of(name: str) -> list[str]:
    """從資料夾名稱取出可以學的詞：中文（日文）連續兩個字以上、英文三個字母以上；純數字、日期不算。"""
    low = (name or "").lower()
    out = [m.group() for m in _CJK.finditer(low) if len(m.group()) >= 2]
    out += [w for w in _WORD.findall(low) if len(w) >= 3]
    return list(dict.fromkeys(out))


def _composition(conn: sqlite3.Connection) -> dict[int, tuple[str, str]]:
    """依裡面的檔案判斷：大多是安裝檔、電子書、創作專案檔 → {資料夾編號: (分類, 理由)}"""
    return _folder_stats(conn)[0]


def rules(conn: sqlite3.Connection) -> list[dict]:
    """我的關鍵字規則（本人定的、助理提出本人確認的），長的詞先比對。"""
    return [dict(r) for r in conn.execute("SELECT * FROM category_rules ORDER BY length(pattern) DESC, id")]


def rule_text(r: dict, names: dict | None = None) -> str:
    years = ""
    if r.get("year_from") and r.get("year_to"):
        years = f"（{r['year_from']}–{r['year_to']} 年）"
    elif r.get("year_from"):
        years = f"（{r['year_from']} 年以後）"
    elif r.get("year_to"):
        years = f"（{r['year_to']} 年以前）"
    return f"「{r['pattern']}」{years}"


def _in_range(r: dict, year: int | None) -> bool:
    return (r["year_from"] is None or year >= r["year_from"]) and (r["year_to"] is None or year <= r["year_to"])


def _pick(cands: list[dict], year: int | None):
    """從符合名稱的規則裡挑一條：有年份就看年份範圍；看不出年份、規則又分成好幾類 → 分不清（放進「請你確認」）。
    回傳 (規則, 分不清時可能的分類) 或 None。"""
    if not cands:
        return None
    ranged = [r for r in cands if r["year_from"] is not None or r["year_to"] is not None]
    plain = [r for r in cands if r not in ranged]
    if year is not None:
        inr = [r for r in ranged if _in_range(r, year)]
        if inr:
            return inr[0], None
        return (plain[0], None) if plain else None
    if plain:
        return plain[0], None
    return ranged[0], list(dict.fromkeys(r["category"] for r in ranged))


@dataclass
class RulesResult:
    folders: int = 0
    by_source: dict | None = None


def run_rules(conn: sqlite3.Connection, commit: bool = True) -> RulesResult:
    """重新算每個資料夾「目前算哪一類」，由高到低：
    本人改過的 > 本人設定的上層 > 我的關鍵字規則（這個資料夾或上層的名稱符合；有年份範圍的看年份）> 學到的習慣
    > 內建的名稱規則 > 內容組成 > AI > 跟著上層。合併掉的分類一律換成合併後的那一類。"""
    ensure_categories(conn, commit=commit)
    resolve = _resolver(conn)
    keys = valid_keys(conn)
    names = {c["key"]: display_name(c) for c in categories(conn, include_merged=True)}
    # 資料夾已經從目錄拿掉了：本人對它的設定也拿掉（避免之後別的資料夾剛好用到同一個編號）
    conn.execute("DELETE FROM category_user WHERE target LIKE 'folder:%' AND CAST(substr(target, 8) AS INTEGER) NOT IN (SELECT id FROM folders)")
    conn.execute("DELETE FROM category_user WHERE target LIKE 'file:%' AND CAST(substr(target, 6) AS INTEGER) NOT IN (SELECT id FROM files)")
    user = {int(r["target"][7:]): r["category"] for r in conn.execute("SELECT target, category FROM category_user WHERE target LIKE 'folder:%'")}
    pending = {}
    for r in conn.execute("SELECT * FROM category_pending"):
        try:
            pending[r["folder_id"]] = (json.loads(r["options"]), r["reason"])
        except ValueError:
            pass
    ai = {r["folder_id"]: r for r in conn.execute("SELECT * FROM category_ai")}
    learned = [(r["token"], r["category"]) for r in conn.execute("SELECT token, category FROM category_learned ORDER BY length(token) DESC")]
    my_rules = [r for r in rules(conn) if resolve(r["category"]) in keys]
    comp = _composition(conn)
    fyears = _file_years(conn)
    rows = conn.execute("SELECT id, parent_id, name, path, main_kind, total_files FROM folders WHERE status = 'ok' "
                        "ORDER BY root_id, length(path) - length(replace(path, '/', '')), path").fetchall()
    eff: dict[int, dict] = {}
    out = []
    by_source: dict[str, int] = {}
    for r in rows:
        fid, parent = r["id"], eff.get(r["parent_id"])
        low = r["name"].lower()
        words = set(_WORD.findall(low))
        # 年份：名稱裡的年份 > 上層名稱裡的年份 > 這個資料夾（連同裡面）檔案的修改日期；都沒有就是看不出來
        own_year = name_year(r["name"]) if r["path"] else None
        name_ctx = own_year or (parent["name_year"] if parent else None)
        year = name_ctx or fyears.get(fid)
        own_rules = [x for x in my_rules if r["path"] and _matches(x["pattern"], low, words)]
        ctx_rules = own_rules + [x for x in (parent["ctx"] if parent else []) if x not in own_rules]
        res = None  # (category, source, confidence, reason, review, from_user)
        ranged_from = False  # 分類來自有年份範圍的規則（裡面的資料夾年份不同時不跟著）
        if fid in user:
            cat = user[fid]
            res = (resolve(cat) if cat else None, "user", 1.0, "你設定的", 0, True)
        elif parent and parent["from_user"]:
            res = (parent["cat"], "user", 1.0, "跟著你設定的上層資料夾", 0, True)
        elif fid in pending:
            opts, reason = pending[fid]
            opts = [resolve(o) for o in opts if resolve(o) in keys]
            if opts:
                res = (opts[0], "pending", 0.5, reason or "請你選一個分類", 1, False)
        if res is None and r["path"]:
            for cands, own in ((own_rules, True), (ctx_rules, False)):
                got = _pick(cands, year)
                if not got:
                    continue
                rule, unsure = got
                who = "你定的規則" if rule["source"] == "user" else "助理加的規則（你確認過）"
                where = "名稱有" if own else "上層資料夾名稱有"
                if unsure and len(unsure) > 1:
                    opts = "或".join(f"「{names.get(resolve(c), c)}」" for c in unsure)
                    res = (resolve(rule["category"]), "my_rule", 0.5, f"{where}「{rule['pattern']}」，但看不出年份：可能是{opts}", 1, False)
                elif unsure:
                    res = (resolve(rule["category"]), "my_rule", 0.5, f"{who}：{where}{rule_text(rule)}，但看不出年份", 1, False)
                else:
                    res = (resolve(rule["category"]), "my_rule", 0.95, f"{who}：{where}{rule_text(rule)}", 0, False)
                ranged_from = rule["year_from"] is not None or rule["year_to"] is not None
                break
        if res is None and r["path"]:
            hit = next(((t, c) for t, c in learned if resolve(c) in keys and ((t in words) if t.isascii() else (t in low))), None)
            if hit:
                res = (resolve(hit[1]), "learned", 0.9, f"你之前把名稱有「{hit[0]}」的資料夾分到這一類", 0, False)
            else:
                for cat, kw in KEYWORDS.items():
                    w = _name_hit(r["name"], kw)
                    if w and resolve(cat) in keys:
                        res = (resolve(cat), "rule", 0.8, f"資料夾名稱有「{w}」", 0, False)
                        break
            if res is None and fid in comp and resolve(comp[fid][0]) in keys:
                cat, reason = comp[fid]
                res = (resolve(cat), "rule", 0.7, reason, 0, False)
            if res is None and r["main_kind"] == "audio" and resolve("hobby") in keys:
                res = (resolve("hobby"), "rule", 0.7, "裡面大多是音樂", 0, False)
            if res is None and fid in ai and resolve(ai[fid]["category"]) in keys:
                a = ai[fid]
                res = (resolve(a["category"]), "ai", a["confidence"], a["reason"] or "AI 建議", 1 if a["confidence"] < REVIEW_BELOW else 0, False)
            # 上層的分類來自有年份範圍的規則、但這個資料夾的年份不在範圍裡（上面已經比對過）：不跟著上層
            if res is None and parent and parent["cat"] and not (parent["ranged"] and ctx_rules and year is not None):
                res = (parent["cat"], "inherit", parent["conf"], "跟著上層資料夾", 0, False)
                ranged_from = parent["ranged"]
        e = {"cat": res[0] if res else None, "conf": res[2] if res else 0, "from_user": bool(res and res[5]), "ranged": ranged_from,
             "year": year, "name_year": name_ctx, "ctx": ctx_rules}
        eff[fid] = e
        if res and (res[0] or res[5]):  # 本人設定「不分類」也記下來（AI 就不會再去問）
            out.append((fid, res[0], res[1], res[2], res[3], res[4], year))
            if res[0]:
                by_source[res[1]] = by_source.get(res[1], 0) + 1
    conn.execute("DELETE FROM folder_category")
    for start in range(0, len(out), 5000):
        conn.executemany("INSERT INTO folder_category (folder_id, category, source, confidence, reason, review, year) VALUES (?, ?, ?, ?, ?, ?, ?)",
                         out[start:start + 5000])
    if commit:
        conn.commit()
    return RulesResult(folders=sum(by_source.values()), by_source=by_source)


# ---- 本人的修正與學習 ----

def set_user(conn: sqlite3.Connection, folder: int | None = None, file: int | None = None, category: str | None = "auto") -> dict:
    """本人設定分類。category：分類的 key／None＝不分類／"auto"＝拿掉本人的設定，回到自動。
    回傳名稱相近、還沒照這樣分的資料夾（介面問「要一起改嗎？」）。"""
    if (folder is None) == (file is None):
        raise ValueError("要指定一個資料夾或檔案")
    if category not in (None, "auto") and category not in valid_keys(conn):
        raise ValueError("沒有這個分類")
    target = f"folder:{int(folder)}" if folder is not None else f"file:{int(file)}"
    if folder is not None:
        conn.execute("DELETE FROM category_pending WHERE folder_id = ?", (int(folder),))
    if category == "auto":
        conn.execute("DELETE FROM category_user WHERE target = ?", (target,))
    else:
        conn.execute("INSERT INTO category_user (target, category, created_at) VALUES (?, ?, ?) "
                     "ON CONFLICT(target) DO UPDATE SET category = excluded.category, created_at = excluded.created_at",
                     (target, category, db.now_iso()))
    conn.commit()
    run_rules(conn)
    if folder is None or category in (None, "auto"):
        return {"similar": [], "tokens": []}
    return similar(conn, int(folder), category)


def similar(conn: sqlite3.Connection, folder: int, category: str, limit: int = 2000) -> dict:
    """名稱和這個資料夾有相同詞、目前不是這一類、也不是本人設定過的資料夾。"""
    row = conn.execute("SELECT name, path, root_id FROM folders WHERE id = ?", (folder,)).fetchone()
    if row is None:
        return {"similar": [], "tokens": []}
    toks = tokens_of(row["name"])
    if not toks:
        return {"similar": [], "tokens": []}
    user = {r[0] for r in conn.execute("SELECT target FROM category_user")}
    out = []
    for r in conn.execute("SELECT d.id, d.name, d.path, d.root_id, c.category FROM folders d LEFT JOIN folder_category c ON c.folder_id = d.id "
                          "WHERE d.status = 'ok' AND d.id != ? AND d.path != '' LIMIT 500000", (folder,)):
        if f"folder:{r['id']}" in user or r["category"] == category:
            continue
        if r["root_id"] == row["root_id"] and r["path"].startswith(row["path"] + "/"):
            continue  # 裡面的資料夾本來就會跟著
        low = r["name"].lower()
        words = set(_WORD.findall(low))
        if any((t in words) if t.isascii() else (t in low) for t in toks):
            out.append({"id": r["id"], "name": r["name"], "path": r["path"], "root_id": r["root_id"]})
            if len(out) >= limit:
                break
    return {"similar": out, "tokens": toks}


def learn(conn: sqlite3.Connection, folder: int, category: str) -> int:
    """本人同意「名稱相近的也照這樣分」：記下學到的詞，重新計算。回傳現在照這樣分的資料夾數。"""
    if category not in valid_keys(conn):
        raise ValueError("沒有這個分類")
    row = conn.execute("SELECT name FROM folders WHERE id = ?", (folder,)).fetchone()
    if row is None:
        raise ValueError("找不到這個資料夾")
    for t in tokens_of(row["name"]):
        conn.execute("INSERT INTO category_learned (token, category, hits, created_at) VALUES (?, ?, 1, ?) "
                     "ON CONFLICT(token) DO UPDATE SET category = excluded.category, hits = hits + 1", (t, category, db.now_iso()))
    conn.commit()
    run_rules(conn)
    return conn.execute("SELECT COUNT(*) FROM folder_category WHERE category = ?", (category,)).fetchone()[0]


def accept(conn: sqlite3.Connection, folders: list[int]) -> int:
    """「請你確認」裡按「對」：把 AI 的建議變成本人的設定（之後不會再被改）。"""
    n = 0
    for fid in folders:
        r = conn.execute("SELECT category FROM folder_category WHERE folder_id = ?", (int(fid),)).fetchone()
        if r is not None:
            conn.execute("INSERT OR REPLACE INTO category_user (target, category, created_at) VALUES (?, ?, ?)",
                         (f"folder:{int(fid)}", r["category"], db.now_iso()))
            conn.execute("DELETE FROM category_pending WHERE folder_id = ?", (int(fid),))
            n += 1
    conn.commit()
    run_rules(conn)
    return n


# ---- 查詢 ----

def of(conn: sqlite3.Connection, folder: int | None = None, file: int | None = None) -> dict:
    """一個資料夾或檔案目前的分類、是誰分的、為什麼。"""
    if file is not None:
        u = conn.execute("SELECT category FROM category_user WHERE target = ?", (f"file:{int(file)}",)).fetchone()
        if u is not None:
            return {"category": u["category"], "source": "user", "reason": "你設定的", "user": True, "confidence": 1.0}
        r = conn.execute("SELECT folder_id FROM files WHERE id = ?", (int(file),)).fetchone()
        if r is None:
            return {"category": None, "source": None, "user": False}
        out = of(conn, folder=r["folder_id"])
        return {**out, "user": False, "from_folder": True}
    r = conn.execute("SELECT * FROM folder_category WHERE folder_id = ?", (int(folder),)).fetchone()
    user = conn.execute("SELECT 1 FROM category_user WHERE target = ?", (f"folder:{int(folder)}",)).fetchone() is not None
    if r is None:
        return {"category": None, "source": "user" if user else None, "user": user}
    return {"category": r["category"], "source": r["source"], "confidence": r["confidence"], "reason": r["reason"],
            "review": bool(r["review"]), "user": user, "year": r["year"]}


def overview(conn: sqlite3.Connection) -> list[dict]:
    """每個分類有幾個資料夾、多少檔案、多大（用資料夾自己的檔案數，不會重複算到裡面別類的資料夾）。"""
    stats = {r["category"]: r for r in conn.execute(
        "SELECT c.category, COUNT(*) AS folders, SUM(d.files) AS files, SUM(d.bytes) AS bytes FROM folder_category c "
        "JOIN folders d ON d.id = c.folder_id WHERE d.status = 'ok' AND c.category IS NOT NULL GROUP BY c.category")}
    out = []
    for c in categories(conn):
        s = stats.get(c["key"])
        top = 0
        if s:  # 分類頁上列幾項（這一類的最上層資料夾＋單獨設定的檔案），側邊欄顯示同一個數字
            fsql, filesql = scope_sql(c["key"])
            top = conn.execute(f"SELECT COUNT(*) FROM ({fsql})", (c["key"],)).fetchone()[0]
        top += conn.execute("SELECT COUNT(*) FROM category_user WHERE target LIKE 'file:%' AND category = ?", (c["key"],)).fetchone()[0]
        out.append({**c, "folders": s["folders"] if s else 0, "files": (s["files"] or 0) if s else 0, "bytes": (s["bytes"] or 0) if s else 0,
                    "top": top})
    return out


def review_list(conn: sqlite3.Connection, limit: int = 200) -> list[dict]:
    rows = conn.execute(
        "SELECT c.folder_id, c.category, c.confidence, c.reason, c.source, c.year, d.name, d.path, d.root_id, d.total_files, d.total_bytes, "
        "r.name AS root "
        "FROM folder_category c JOIN folders d ON d.id = c.folder_id JOIN roots r ON r.id = d.root_id "
        "WHERE c.review = 1 AND d.status = 'ok' ORDER BY d.total_bytes DESC LIMIT ?", (limit,)).fetchall()
    return [dict(r) for r in rows]


def review_count(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) FROM folder_category WHERE review = 1").fetchone()[0]


def scope_sql(category: str) -> tuple[str, str]:
    """分類頁要列的：這一類的「最上層」資料夾（上層不是這一類），以及本人單獨設定成這一類的檔案。"""
    folders = ("SELECT d.* FROM folders d JOIN folder_category c ON c.folder_id = d.id "
               "LEFT JOIN folder_category p ON p.folder_id = d.parent_id "
               "WHERE c.category = ? AND d.status = 'ok' AND d.path != '' AND (p.category IS NULL OR p.category != c.category)")
    files = ("SELECT {cols} FROM category_user u JOIN files f ON u.target = 'file:' || f.id JOIN folders d ON d.id = f.folder_id "
             "WHERE u.category = ? AND f.status = 'ok'")
    return folders, files


# ---- AI ----

def _depth(path: str) -> int:
    return path.count("/") + 1 if path else 0


def ai_candidates(conn: sqlite3.Connection, limit: int | None = None) -> list[sqlite3.Row]:
    """規則分不出來、AI 也還沒看過（或內容變了）的資料夾，淺的、大的先問。"""
    rows = conn.execute(
        "SELECT d.id, d.parent_id, d.name, d.path, d.root_id, d.files, d.total_files, d.total_bytes, r.name AS root "
        "FROM folders d JOIN roots r ON r.id = d.root_id LEFT JOIN folder_category c ON c.folder_id = d.id "
        "LEFT JOIN category_ai a ON a.folder_id = d.id "
        "WHERE d.status = 'ok' AND d.path != '' AND d.total_files > 0 AND (c.folder_id IS NULL OR (c.source = 'ai' AND a.stale = 1)) "
        "AND (a.folder_id IS NULL OR a.stale = 1 OR a.sig != d.name || '|' || d.total_files) "
        "ORDER BY length(d.path) - length(replace(d.path, '/', '')), d.total_bytes DESC").fetchall()
    return rows[:limit] if limit else rows


def ai_todo(conn: sqlite3.Connection) -> int:
    """還有幾個資料夾等 AI 看（只算數量）。"""
    return conn.execute(
        "SELECT COUNT(*) FROM folders d LEFT JOIN folder_category c ON c.folder_id = d.id LEFT JOIN category_ai a ON a.folder_id = d.id "
        "WHERE d.status = 'ok' AND d.path != '' AND d.total_files > 0 AND (c.folder_id IS NULL OR (c.source = 'ai' AND a.stale = 1)) "
        "AND (a.folder_id IS NULL OR a.stale = 1 OR a.sig != d.name || '|' || d.total_files)").fetchone()[0]


def _prompt(conn: sqlite3.Connection, folder: sqlite3.Row, keys: list[tuple[str, str]], read_text: bool) -> str:
    from .textindex import body

    desc = {c["key"]: c["description"] for c in categories(conn) if c["description"]}
    prof = profile(conn)

    kinds = conn.execute("SELECT kind, COUNT(*) AS n FROM files f JOIN folders d ON d.id = f.folder_id "
                         "WHERE f.status = 'ok' AND f.root_id = ? AND (d.id = ? OR d.path LIKE ? ESCAPE '\\') GROUP BY kind ORDER BY n DESC",
                         (folder["root_id"], folder["id"], folder["path"].replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "/%")).fetchall()
    names = [r["name"] for r in conn.execute("SELECT name FROM files WHERE folder_id = ? AND status = 'ok' ORDER BY size DESC LIMIT 30", (folder["id"],))]
    subs = [r["name"] for r in conn.execute("SELECT name FROM folders WHERE parent_id = ? AND status = 'ok' ORDER BY total_bytes DESC LIMIT 15", (folder["id"],))]
    lines = [
        "你是檔案整理助手。根據下面這個資料夾的資訊，判斷它屬於哪一個分類。只能從清單裡選；真的看不出來就回答 unknown。",
        "分類清單：\n" + "\n".join(f"- {k}：{n}" + (f"（{desc.get(k)}）" if desc.get(k) else "") for k, n in keys),
        f"資料夾名稱：{folder['name']}",
        f"位置：{folder['root']} / {folder['path']}",
        "檔案類型：" + "、".join(f"{r['kind']} {r['n']}" for r in kinds),
    ]
    if subs:
        lines.append("裡面的資料夾：" + "、".join(subs))
    if names:
        lines.append("裡面的檔案（部分）：" + "、".join(names))
    if read_text:
        docs = conn.execute("SELECT t.file_id, f.name FROM file_text t JOIN files f ON f.id = t.file_id "
                            "WHERE f.folder_id = ? AND t.status = 'ok' AND f.status = 'ok' ORDER BY t.chars DESC LIMIT 2", (folder["id"],)).fetchall()
        for d in docs:
            text = re.sub(r"\s+", " ", body(conn, d["file_id"]))[:500]
            if text:
                lines.append(f"文件「{d['name']}」開頭：{text}")
    examples = conn.execute("SELECT d.name, u.category FROM category_user u JOIN folders d ON u.target = 'folder:' || d.id "
                            "WHERE u.category IS NOT NULL ORDER BY u.created_at DESC LIMIT 10").fetchall()
    if examples:
        lines.append("這個人之前的分類習慣（請參考）：" + "；".join(f"「{e['name']}」→ {e['category']}" for e in examples))
    if prof.get("identity"):
        lines.append(f"這個人的身分與習慣：{prof['identity'][:300]}")
    if prof.get("teach_start_year"):
        lines.append(f"他大約從 {prof['teach_start_year']} 年開始工作／教書；這之前的資料比較可能是他自己讀書時的。")
    year = name_year(folder["name"])
    if year:
        lines.append(f"資料夾名稱裡的年份：{year}")
    lines.append("請回答 JSON：category（分類的英文代號）、confidence（0 到 1 的信心）、reason（一句中文理由，二十個字以內）。")
    return "\n".join(lines)


@dataclass
class AIResult:
    asked: int = 0
    classified: int = 0
    review: int = 0
    skipped: int = 0
    stopped: bool = False
    error: str = ""


def run_ai(conn: sqlite3.Connection, llm, read_text: bool = True, progress=None, stop=None, wait=None, limit: int | None = None) -> AIResult:
    """把規則分不出來的資料夾交給 AI。上層分好了，裡面的就跟著上層，不再一個一個問。
    wait：每個資料夾之前呼叫（排程不允許時會等；回傳 False＝停止）。"""
    result = AIResult()
    cats = categories(conn)
    keys = [(c["key"], c["name"] or NAMES.get(c["key"], c["key"])) for c in cats]
    valid = {k for k, _ in keys}
    schema = {"type": "object", "properties": {
        "category": {"type": "string", "enum": [*valid, "unknown"]},
        "confidence": {"type": "number"}, "reason": {"type": "string"}}, "required": ["category", "confidence", "reason"]}
    todo = ai_candidates(conn, limit)
    decided: set[int] = set()
    parent_of = {r["id"]: r["parent_id"] for r in conn.execute("SELECT id, parent_id FROM folders")}
    for i, f in enumerate(todo):
        if stop is not None and stop.is_set():
            result.stopped = True
            break
        if wait is not None and not wait():
            result.stopped = True
            break
        # 上層剛被 AI 分好：這一個跟著上層，不用再問
        p, inherited = f["parent_id"], False
        while p:
            if p in decided:
                inherited = True
                break
            p = parent_of.get(p)
        if inherited:
            result.skipped += 1
            continue
        if progress:
            progress(i, len(todo), f["name"])
        try:
            out = llm.plan_json(_prompt(conn, f, keys, read_text), schema)
        except Exception as exc:  # noqa: BLE001  模型沒開、太久沒回應…：先停下來，告訴本人
            result.error = str(exc)
            break
        result.asked += 1
        cat = out.get("category") if isinstance(out, dict) else None
        try:
            conf = max(0.0, min(1.0, float(out.get("confidence") or 0)))
        except (TypeError, ValueError):
            conf = 0.0
        reason = str(out.get("reason") or "")[:60] if isinstance(out, dict) else ""
        cat = cat if cat in valid else None
        conn.execute("INSERT OR REPLACE INTO category_ai (folder_id, category, confidence, reason, sig, model, created_at, stale) "
                     "VALUES (?, ?, ?, ?, ?, ?, ?, 0)", (f["id"], cat, conf, reason, f"{f['name']}|{f['total_files']}",
                                                     getattr(llm, "model", "") or "", db.now_iso()))
        if cat:
            decided.add(f["id"])
            result.classified += 1
            if conf < REVIEW_BELOW:
                result.review += 1
        if result.asked % 20 == 0:
            conn.commit()
            run_rules(conn)
    conn.commit()
    run_rules(conn)
    if progress:
        progress(len(todo), len(todo), "")
    return result


# ---- 本人的身分與習慣（給助理和 AI 參考；只存在這台電腦的目錄裡） ----

PROFILE_KEY = "category_profile"


def profile(conn: sqlite3.Connection) -> dict:
    r = conn.execute("SELECT value FROM settings_kv WHERE key = ?", (PROFILE_KEY,)).fetchone()
    try:
        return json.loads(r["value"]) if r else {}
    except ValueError:
        return {}


def save_profile(conn: sqlite3.Connection, identity: str | None = None, teach_start_year=None, notes: str | None = None) -> dict:
    p = profile(conn)
    if identity is not None:
        p["identity"] = str(identity).strip()[:500]
    if teach_start_year not in (None, ""):
        try:
            y = int(teach_start_year)
            if 1950 <= y <= 2100:
                p["teach_start_year"] = y
        except (TypeError, ValueError):
            pass
    if notes is not None:
        p["notes"] = str(notes).strip()[:500]
    conn.execute("INSERT OR REPLACE INTO settings_kv (key, value) VALUES (?, ?)", (PROFILE_KEY, json.dumps(p, ensure_ascii=False)))
    conn.commit()
    return p


# ---- 整理計畫：一連串的小步驟（新增、改名、說明、合併、拆分、規則、替資料夾改分類），先預覽，本人確認才套用，可以復原 ----

OPS = ("add_category", "rename", "describe", "merge", "split", "rule", "remove_rule", "set_folder", "delete_category")
SNAP_TABLES = ("categories", "category_user", "category_rules", "category_learned", "category_pending")
MAX_OPS = 100


class PlanError(ValueError):
    """計畫裡有一步看不懂，訊息是給使用者看的。"""


def snapshot(conn: sqlite3.Connection) -> dict:
    """分類相關的設定全部記下來（套用前用，復原時照這份還原）。"""
    return {t: [dict(r) for r in conn.execute(f"SELECT * FROM {t}")] for t in SNAP_TABLES}


def restore(conn: sqlite3.Connection, snap: dict) -> None:
    for t in SNAP_TABLES:
        conn.execute(f"DELETE FROM {t}")
        for row in snap.get(t) or []:
            cols = list(row)
            conn.execute(f"INSERT INTO {t} ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})", [row[c] for c in cols])
    conn.commit()
    run_rules(conn)


class _Refs:
    """計畫裡提到分類可以用代號、目前的名稱，或這個計畫裡新增的名稱。"""

    def __init__(self, conn):
        self.conn = conn
        self.reload()

    def reload(self):
        self.cats = categories(self.conn, include_merged=True)

    def find(self, ref) -> str | None:
        if ref is None:
            return None
        ref = str(ref).strip()
        low = ref.lower()
        for c in self.cats:
            if c["key"] == ref:
                return c["key"]
        for c in self.cats:
            if display_name(c).lower() == low or NAMES.get(c["key"], "").lower() == low:
                return c["merged_into"] and _resolver(self.conn)(c["key"]) or c["key"]
        return None

    def need(self, ref, create: bool = False, description: str = "") -> str:
        key = self.find(ref)
        if key:
            return key
        if create and ref and str(ref).strip():
            key = add_category(self.conn, str(ref), description, commit=False)
            self.reload()
            return key
        raise PlanError(f"沒有「{ref}」這個分類")


def _folder_ids(conn, op) -> list[int]:
    ids = [int(x) for x in (op.get("folders") or []) if str(x).isdigit()][:5000]
    pattern = str(op.get("pattern") or "").strip()
    if pattern:
        low = pattern.lower()
        for r in conn.execute("SELECT id, name FROM folders WHERE status = 'ok' AND path != '' AND instr(lower(name), ?) > 0 LIMIT 5000", (low,)):
            ids.append(r["id"])
    return list(dict.fromkeys(ids))


def apply_ops(conn: sqlite3.Connection, ops: list[dict], source: str = "user") -> list[dict]:
    """依序做每一步（不 commit，呼叫的人決定要不要保留）。回傳每一步的結果：{op, ok, text}。"""
    refs = _Refs(conn)
    out = []
    for op in (ops or [])[:MAX_OPS]:
        kind = op.get("op")
        try:
            if kind not in OPS:
                raise PlanError("看不懂這一步")
            if kind == "add_category":
                name = str(op.get("name") or "").strip()
                key = refs.find(name)
                if key:  # 已經有了：只更新說明
                    if op.get("description"):
                        conn.execute("UPDATE categories SET description = ?, merged_into = NULL WHERE key = ?", (str(op["description"])[:300], key))
                else:
                    key = refs.need(name, create=True, description=str(op.get("description") or ""))
                if op.get("examples"):
                    conn.execute("UPDATE categories SET examples = ? WHERE key = ?", (json.dumps([str(x)[:60] for x in op["examples"]][:6], ensure_ascii=False), key))
                text = f"新增分類「{name}」"
            elif kind == "rename":
                key = refs.need(op.get("category"))
                rename_category(conn, key, op.get("name"), commit=False)
                text = f"改名為「{op.get('name')}」"
            elif kind == "describe":
                key = refs.need(op.get("category"))
                conn.execute("UPDATE categories SET description = ? WHERE key = ?", (str(op.get("description") or "")[:300] or None, key))
                if op.get("examples") is not None:
                    conn.execute("UPDATE categories SET examples = ? WHERE key = ?", (json.dumps([str(x)[:60] for x in op["examples"]][:6], ensure_ascii=False), key))
                text = "更新說明"
            elif kind == "merge":
                into = refs.need(op.get("into"), create=True)
                froms = [refs.need(f) for f in (op.get("from") or [])]
                for f in froms:
                    if f == into:
                        continue
                    conn.execute("UPDATE categories SET merged_into = ? WHERE key = ?", (into, f))
                    for table in ("category_user", "category_learned", "category_rules"):  # 本人的設定跟著到合併後的那一類
                        conn.execute(f"UPDATE {table} SET category = ? WHERE category = ?", (into, f))
                text = "合併"
            elif kind == "split":
                src = refs.need(op.get("from"))
                targets = [refs.need(t, create=True) for t in (op.get("into") or [])]
                targets = [t for t in targets if t != src]
                if len(targets) < 2:
                    raise PlanError("拆分要拆成至少兩類")
                conn.execute("UPDATE categories SET merged_into = ? WHERE key = ?", (targets[0], src))
                # 本人原本手動設成這一類的：不知道該跟到哪一類，放進「請你確認」讓本人選（不自己猜）
                moved = conn.execute("SELECT target FROM category_user WHERE category = ? AND target LIKE 'folder:%'", (src,)).fetchall()
                name = display_name(next(c for c in refs.cats if c["key"] == src))
                for row in moved:
                    conn.execute("INSERT OR REPLACE INTO category_pending (folder_id, options, reason) VALUES (?, ?, ?)",
                                 (int(row["target"][7:]), json.dumps(targets), f"你原本把它設成「{name}」，這一類拆開了，請選一個"))
                conn.execute("DELETE FROM category_user WHERE category = ? AND target LIKE 'folder:%'", (src,))
                conn.execute("UPDATE category_learned SET category = ? WHERE category = ?", (targets[0], src))
                text = f"拆分「{name}」"
            elif kind == "rule":
                pattern = str(op.get("pattern") or "").strip()[:40]
                if len(pattern) < 2:
                    raise PlanError("關鍵字太短")
                key = refs.need(op.get("category"), create=bool(op.get("create")))
                yf = int(op["year_from"]) if str(op.get("year_from") or "").isdigit() else None
                yt = int(op["year_to"]) if str(op.get("year_to") or "").isdigit() else None
                conn.execute("DELETE FROM category_rules WHERE pattern = ? AND year_from IS ? AND year_to IS ?", (pattern, yf, yt))
                conn.execute("INSERT INTO category_rules (pattern, category, year_from, year_to, source, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                             (pattern, key, yf, yt, op.get("source") or source, db.now_iso()))
                text = f"規則{rule_text({'pattern': pattern, 'year_from': yf, 'year_to': yt})}"
            elif kind == "remove_rule":
                if op.get("id"):
                    conn.execute("DELETE FROM category_rules WHERE id = ?", (int(op["id"]),))
                else:
                    conn.execute("DELETE FROM category_rules WHERE pattern = ?", (str(op.get("pattern") or ""),))
                text = "拿掉規則"
            elif kind == "set_folder":
                cat = op.get("category")
                key = None if cat in (None, "none") else refs.need(cat, create=bool(op.get("create")))
                ids = _folder_ids(conn, op)
                for fid in ids:
                    conn.execute("INSERT OR REPLACE INTO category_user (target, category, created_at) VALUES (?, ?, ?)",
                                 (f"folder:{fid}", key, db.now_iso()))
                    conn.execute("DELETE FROM category_pending WHERE folder_id = ?", (fid,))
                text = f"{len(ids)} 個資料夾"
            else:  # delete_category
                delete_category(conn, refs.need(op.get("category")), commit=False)
                text = "刪除分類"
            refs.reload()
            out.append({"op": kind, "ok": True, "text": text})
        except (PlanError, ValueError) as exc:
            out.append({"op": kind, "ok": False, "text": str(exc)})
    return out


def _effective(conn) -> dict[int, str | None]:
    return {r["folder_id"]: r["category"] for r in conn.execute("SELECT folder_id, category FROM folder_category")}


def preview(conn: sqlite3.Connection, ops: list[dict], source: str = "user", examples: int = 5) -> dict:
    """先在目錄裡試做一次再全部取消，告訴本人：每一步做不做得到、每一類會有幾個資料夾、哪些資料夾會換分類（附例子）。"""
    ensure_categories(conn)
    conn.commit()
    before = _effective(conn)
    before_counts = {c["key"]: c for c in overview(conn)}
    conn.execute("SAVEPOINT plan_preview")
    try:
        steps = apply_ops(conn, ops, source)
        run_rules(conn, commit=False)
        after = _effective(conn)
        after_cats = overview(conn)
        names = {c["key"]: display_name(c) for c in categories(conn, include_merged=True)}
        review = review_count(conn)
    finally:
        conn.execute("ROLLBACK TO plan_preview")
        conn.execute("RELEASE plan_preview")
    rows = {r["id"]: r for r in conn.execute("SELECT id, name, path, root_id FROM folders WHERE status = 'ok'")}
    moves: dict[tuple, list] = {}
    for fid in set(before) | set(after):
        a, b = before.get(fid), after.get(fid)
        if a != b and fid in rows:
            moves.setdefault((a, b), []).append(fid)
    changes = sorted(({"from": a, "to": b, "from_name": names.get(a) or (NAMES.get(a) if a else None),
                       "to_name": names.get(b) or (NAMES.get(b) if b else None), "count": len(ids),
                       "examples": [{"id": i, "name": rows[i]["name"], "path": rows[i]["path"], "root_id": rows[i]["root_id"]}
                                    for i in sorted(ids, key=lambda i: rows[i]["path"])[:examples]]}
                      for (a, b), ids in moves.items()), key=lambda x: -x["count"])
    return {"steps": steps, "changed": sum(x["count"] for x in changes), "changes": changes[:30], "review": review,
            "categories": [{"key": c["key"], "name": display_name(c), "description": c["description"], "folders": c["folders"], "top": c["top"],
                            "before": (before_counts.get(c["key"]) or {}).get("folders", 0), "new": c["key"] not in before_counts}
                           for c in after_cats],
            "removed": [{"key": k, "name": display_name(v), "folders": v["folders"]} for k, v in before_counts.items()
                        if k not in {c["key"] for c in after_cats}]}


def mark_ai_stale(conn: sqlite3.Connection) -> int:
    """分類的定義改了：AI 之前的建議照新的定義重新判斷（本人改過的不動）。"""
    n = conn.execute("UPDATE category_ai SET stale = 1 WHERE stale = 0").rowcount
    conn.commit()
    return n


def describe_rules(r: RulesResult) -> str:
    s = r.by_source or {}
    parts = [f"分好 {r.folders:,} 個資料夾"]
    if s.get("rule"):
        parts.append(f"規則 {s['rule']:,}")
    if s.get("inherit"):
        parts.append(f"跟著上層 {s['inherit']:,}")
    if s.get("learned"):
        parts.append(f"照你的習慣 {s['learned']:,}")
    if s.get("my_rule"):
        parts.append(f"照你定的規則 {s['my_rule']:,}")
    if s.get("ai"):
        parts.append(f"AI {s['ai']:,}")
    if s.get("user"):
        parts.append(f"你設定的 {s['user']:,}")
    return "自動分類：" + "、".join(parts)


def describe_ai(r: AIResult) -> str:
    if r.error and not r.asked:
        return f"沒辦法用 AI 分類：{r.error}"
    text = f"AI 分類：看了 {r.asked:,} 個資料夾，分好 {r.classified:,} 個"
    if r.review:
        text += f"，其中 {r.review:,} 個沒把握，放在「請你確認」"
    if r.stopped:
        text += "；已暫停，之後會接著做"
    if r.error:
        text += f"；中途停下來：{r.error}"
    return text
