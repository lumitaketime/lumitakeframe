"""檔案管理助理：回答關於你的硬碟與檔案的問題，並在你允許的範圍內提出整理動作。

預設在這台電腦上離線執行（Gemma 4，經由 Ollama，依這台電腦的記憶體挑大小）；也可以改用 Claude、Gemini、OpenAI 或其他服務（llm.py）。

做法（模型不直接碰資料庫或檔案）：
1. 規劃：模型讀問題，選出要用哪些工具。可以分兩三輪：先搜尋，看到結果後再讀文件或提出動作。
2. 查詢：查詢工具都是唯讀的程式，查 Re'memor 的目錄資料庫。
3. 提案：權限允許時，模型可以「提出」整理動作（加標籤、建智慧資料夾、標記待刪除、搬移、改名、移到待刪除資料夾）。
   提案只是一筆紀錄；本人在畫面上看過、按下確認才會執行，而且都可以復原（actions.py）。助理永遠不會刪除檔案（核心原則一）。
4. 回答：模型只根據查到的資料回答，並列出來源檔案讓本人核對。

權限（設定 → AI 助理）：1 只看目錄／2 可以讀文件內容／3 可以在 Re'memor 裡整理／4 可以搬移、改名檔案。
用雲端服務時，除非本人另外允許，文件內容不會送出去，只送檔名與統計（核心原則二）。

「我可以幫忙什麼」的建議卡片不用模型：直接從目錄算出來，快而且不會說錯。
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

from .analyzer import OllamaUnavailable, parse_model_json  # noqa: F401  parse_model_json 給其他模組用
from .llm import (ClaudeLLM, OllamaLLM, OpenAILLM, api_settings, is_local_url, is_remote,  # noqa: F401
                  make_llm, provider_of)

KINDS = ("document", "photo", "video", "audio", "archive", "other")

# 每個工具：說明、需要的權限等級
TOOLS = {
    "search_files": (1, "依檔名、資料夾名稱與文件內容搜尋檔案。args: {\"query\": 關鍵字, \"kind\": 可省略（document/photo/video/audio/archive）, \"year\": 可省略}"),
    "largest_folders": (1, "列出最佔空間的資料夾。args: {\"limit\": 數量（最多 20）}"),
    "drives_overview": (1, "所有硬碟的容量、檔案數、上次掃描時間、各類型佔多少。args: {}"),
    "duplicates": (1, "重複的檔案與資料夾，以及可以釋出多少空間。args: {}"),
    "retire_check": (1, "淘汰檢查：某顆硬碟上的檔案在別顆硬碟有沒有一模一樣的副本、哪些只在這顆上、能不能淘汰。"
                        "使用者問「某顆硬碟可以淘汰／丟掉／不要了嗎」時用這個。args: {\"drive\": 硬碟名稱}"),
    "year_recap": (1, "某一年的回顧：那年留下哪些檔案（各類型、每個月）、最常出現的資料夾、照片在哪裡拍、有哪些文件、分類。"
                      "使用者問「某年我在做什麼／那年有什麼」時用這個。args: {\"year\": 西元年}"),
    "compare_documents": (2, "比較兩份文件的文字差在哪裡（新增、刪掉、改了哪些段落）。args: {\"file_a\": 檔案編號, \"file_b\": 檔案編號}（先用 search_files 找到）"),
    "read_document": (2, "讀一份文件的內容（Re'memor 已經讀好的文字）。args: {\"file_id\": 檔案編號（先用 search_files 找到）}"),
    "catalog_analysis": (1, "檔案分析：類型、年份分布、最常出現的詞（每個詞在幾個資料夾、大多在哪一類），目前的分類清單、規則、使用者的身分。討論分類時先用這個。args: {}"),
    "keyword_folders": (1, "某個詞出現在哪些資料夾（含年份、目前的分類）。args: {\"word\": 詞}"),
    "save_profile": (1, "記下使用者說的身分與習慣、開始工作（例如教書）的年份。args: {\"identity\": 一兩句身分與習慣, \"teach_start_year\": 西元年（可省略）}"),
    "classify_folders": (3, "讓這台電腦上的 AI 真的去看資料夾（名稱、檔名、文件開頭、照片描述），在背景逐一判斷該分到哪一類。"
                            "沒分類的直接分好；原本已經分好、AI 覺得該換的，看完整理成計畫卡讓使用者確認。使用者要你「重新整理、標註、分類」時用這個。"
                            "args: {\"words\": [先看名稱有這些詞的資料夾（可省略）], \"categories\": [只分到這幾類（分類名稱，可省略）], \"only_words\": 只看名稱有這些詞的（true/false）}"),
    "plan_categories": (3, "提出或修改分類的整理計畫（累積在同一張計畫卡上，使用者確認才套用，可以復原）。args: {\"ops\": [步驟]}。"
                           "步驟：{op: add_category, name, description}｜{op: rename, category, name}｜{op: describe, category, description}｜"
                           "{op: merge, from: [分類…], into: 分類}｜{op: split, from: 分類, into: [分類…]}｜"
                           "{op: rule, pattern: 關鍵字, category: 分類, year_from?: 西元年, year_to?: 西元年}｜"
                           "{op: set_folder, pattern: 名稱包含的字（或 folders: [編號]）, category: 分類}｜{op: remove_rule, pattern}｜"
                           "{op: delete_category, category}。分類可以直接寫名稱；新分類先 add_category。"),
    "propose_label": (3, "提出：替檔案或資料夾加上顏色標籤。args: {\"file_ids\": [編號], \"folder_ids\": [編號], \"color\": red/yellow/green/blue/purple/none}"),
    "propose_smart_folder": (3, "提出：把一個搜尋存成智慧資料夾。args: {\"name\": 名稱, \"query\": 搜尋關鍵字, \"kind\": 可省略, \"year\": 可省略}"),
    "propose_mark_delete": (3, "提出：把已確認重複的多餘副本標記為待刪除（只是標記）。args: {\"file_ids\": [編號]}"),
    "propose_move": (4, "提出：把同一個來源裡的檔案搬到某個資料夾（不存在會建立）。args: {\"file_ids\": [編號], \"folder\": 資料夾路徑（和搜尋結果的「資料夾」寫法一樣，相對於同一個來源）}"),
    "propose_rename": (4, "提出：替檔案改名（副檔名不變）。args: {\"renames\": [{\"file_id\": 編號, \"new_name\": 新檔名}]}"),
    "propose_consolidate": (4, "提出整理計畫：把一顆硬碟上的檔案複製到另一顆，逐一比對確認一模一樣（例如淘汰前先備份「只在這顆上」的檔案，或把某個資料夾集中到一顆）。"
                               "不刪除任何原本的檔案；mark_source＝true 時，確認好後把原本那份放進「待刪除」清單。"
                               "args: {\"from\": 來源硬碟名稱, \"to\": 目標硬碟名稱, \"folder\": 只複製這個資料夾（相對路徑，可省略＝只在這顆上的全部檔案）, \"mark_source\": true/false}"),
    "propose_to_pending": (4, "提出：把檔案移到該來源的「Re'memor 待刪除」資料夾（不刪除，隨時可以搬回來）。args: {\"file_ids\": [編號]}"),
}
PLAN_TOOLS = ("catalog_analysis", "keyword_folders", "save_profile", "plan_categories", "classify_folders")
PROPOSE = {"propose_label": "label", "propose_smart_folder": "smart_folder", "propose_mark_delete": "mark_delete",
           "propose_move": "move", "propose_rename": "rename", "propose_to_pending": "to_pending"}

LEVEL_TEXT = {1: "只能查看目錄（檔名、大小、位置），不能讀文件內容，也不能提出整理動作",
              2: "可以查看目錄、讀文件內容；不能提出整理動作",
              3: "可以查看、讀內容，也可以提出在 Re'memor 裡的整理動作（標籤、智慧資料夾、待刪除標記）",
              4: "可以查看、讀內容，也可以提出整理動作，包括搬移、改名、移到待刪除資料夾"}

LANG_NAMES = {"zh-Hant": "繁體中文", "en": "English"}


def _plan_schema(names: list[str]) -> dict:
    return {
        "type": "object",
        "properties": {
            "calls": {"type": "array", "maxItems": 3, "items": {"type": "object", "properties": {
                "tool": {"type": "string", "enum": names}, "args": {"type": "object"}}, "required": ["tool", "args"]}},
        },
        "required": ["calls"],
    }


PLAN_SCHEMA = _plan_schema(list(TOOLS))


class Ctx:
    """這一次問答的狀態：來源、建立的提案、權限、能不能看文件內容。"""

    def __init__(self, level: int = 2, content: bool = True, question: str = "", chat_id: int | None = None):
        self.chat_id = chat_id
        self.level = max(1, min(4, int(level or 2)))
        self.content = content and self.level >= 2
        self.question = question
        self.sources: list[dict] = []
        self.actions: list[dict] = []


def _ctx(ctx) -> Ctx:
    if isinstance(ctx, Ctx):
        return ctx
    c = Ctx()
    if isinstance(ctx, list):  # 舊的寫法：直接給來源清單
        c.sources = ctx
    return c


def allowed_tools(ctx: Ctx) -> list[str]:
    return [name for name, (lv, _) in TOOLS.items() if ctx.level >= lv and (name not in ("read_document", "compare_documents") or ctx.content)]


def _fmt_bytes(n: int) -> str:
    n = float(n or 0)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit in ("B", "KB") else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


# ---- 查詢工具（全部唯讀） ----

def tool_search_files(conn: sqlite3.Connection, args: dict, ctx) -> str:
    from .find import find

    ctx = _ctx(ctx)
    q = str(args.get("query") or "").strip()
    if not q:
        return "（沒有給關鍵字）"
    kind = args.get("kind") or None
    year = args.get("year")
    try:
        year = int(year) if year else None
    except (TypeError, ValueError):
        year = None
    res = find(conn, q, kind=kind if kind in KINDS else None, year=year, limit=10)
    if not res["items"]:
        return f"搜尋「{q}」沒有找到檔案。"
    lines = [f"搜尋「{q}」找到 {res['total']} 個檔案{'（只列前 10 個）' if res['total'] > 10 else ''}："]
    for it in res["items"]:
        n = _source(ctx.sources, it)
        snippet = "".join(p["text"] for p in it.get("snippet") or [])[:160] if ctx.content else ""
        when = time.strftime("%Y-%m-%d", time.localtime(it["mtime"])) if it.get("mtime") else ""
        lines.append(f"[{n}] {it['name']}（編號 {it['id']}，{_fmt_bytes(it['size'])}，{when}，硬碟「{it['drive']}」，"
                     f"資料夾 {it['folder'] or '最上層'}）" + (f"\n    內容：{snippet}" if snippet else ""))
    return "\n".join(lines)


def tool_largest_folders(conn: sqlite3.Connection, args: dict, ctx) -> str:
    ctx = _ctx(ctx)
    try:
        limit = max(1, min(20, int(args.get("limit") or 10)))
    except (TypeError, ValueError):
        limit = 10
    rows = conn.execute(
        "SELECT d.id, d.root_id, d.name, d.path, d.total_bytes, d.total_files, r.name AS root, COALESCE(v.name, r.name) AS drive "
        "FROM folders d JOIN roots r ON r.id = d.root_id LEFT JOIN drives v ON v.id = r.drive_id "
        "WHERE d.status = 'ok' AND d.path != '' AND instr(d.path, '/') = 0 ORDER BY d.total_bytes DESC LIMIT ?", (limit * 3,)).fetchall()
    # 每個來源最上面一層的資料夾；不夠的話再看第二層
    if len(rows) < limit:
        rows = conn.execute(
            "SELECT d.id, d.root_id, d.name, d.path, d.total_bytes, d.total_files, r.name AS root, COALESCE(v.name, r.name) AS drive "
            "FROM folders d JOIN roots r ON r.id = d.root_id LEFT JOIN drives v ON v.id = r.drive_id "
            "WHERE d.status = 'ok' AND d.path != '' ORDER BY d.total_bytes DESC LIMIT ?", (limit,)).fetchall()
    lines = ["最佔空間的資料夾："]
    for r in rows[:limit]:
        n = _source(ctx.sources, {"type": "folder", "id": r["id"], "root_id": r["root_id"], "name": r["name"], "path": r["path"],
                                  "drive": r["drive"], "size": r["total_bytes"]})
        lines.append(f"[{n}] {r['name']}（資料夾編號 {r['id']}，{_fmt_bytes(r['total_bytes'])}，{r['total_files']:,} 個檔案，"
                     f"硬碟「{r['drive']}」，路徑 {r['path']}）")
    return "\n".join(lines)


def tool_drives_overview(conn: sqlite3.Connection, args: dict, ctx) -> str:
    from .catalog import drives_overview, kinds_overview

    lines = ["硬碟："]
    for d in drives_overview(conn):
        when = (d.get("last_scan") or "")[:10] or "還沒掃描"
        lines.append(f"- {d['name']}：{d['files']:,} 個檔案，{_fmt_bytes(d['bytes'])}"
                     + (f"，容量 {_fmt_bytes(d['capacity'])}" if d.get("capacity") else "")
                     + f"，{'已接上' if d.get('online') else '沒接上'}，上次掃描 {when}{'（沒有掃完）' if not d.get('complete', True) else ''}")
    kinds = kinds_overview(conn)
    if kinds:
        lines.append("各類型：" + "、".join(f"{k['kind']} {k['files']:,} 個（{_fmt_bytes(k['bytes'])}）" for k in kinds))
    return "\n".join(lines)


def tool_duplicates(conn: sqlite3.Connection, args: dict, ctx) -> str:
    from .dupes import compare_plan, duplicate_files, duplicate_folders

    folders = duplicate_folders(conn, limit=5)
    files = duplicate_files(conn, limit=5)
    plan_ = compare_plan(conn)
    lines = [f"重複資料夾：{folders['confirmed']} 組已確認，可釋出 {_fmt_bytes(folders['releasable'])}。",
             f"重複檔案：{files['total']} 組已確認，可釋出 {_fmt_bytes(files['releasable'])}。",
             f"還沒比對內容的檔案：{plan_['small']['files'] + plan_['large']['files']:,} 個（比對後才能確定是不是真的一樣）。"]
    for g in (folders.get("groups") or [])[:3] + (files.get("groups") or [])[:3]:
        items = g.get("items") or []
        if items:
            lines.append(f"- 「{items[0]['name']}」有 {len(items)} 份：" + "；".join(
                f"{i.get('drive')}／{i.get('path')}" + (f"（檔案編號 {i['id']}）" if i.get("id") and g in (files.get("groups") or []) else "")
                for i in items[:4]))
    lines.append("（要刪除時請到「重複項目」頁由本人選擇保留哪一份。）")
    return "\n".join(lines)


def _find_root(conn: sqlite3.Connection, name: str):
    name = str(name or "").strip()
    rows = conn.execute("SELECT r.*, COALESCE(v.name, r.name) AS label FROM roots r LEFT JOIN drives v ON v.id = r.drive_id").fetchall()
    for test in (lambda r: r["name"] == name or r["label"] == name, lambda r: name and (name in r["name"] or name in (r["label"] or ""))):
        hit = [r for r in rows if test(r)]
        if hit:
            return hit[0], rows
    return None, rows


def tool_retire_check(conn: sqlite3.Connection, args: dict, ctx) -> str:
    from . import retire

    root, rows = _find_root(conn, args.get("drive"))
    if root is None:
        return "（找不到這顆硬碟。目前的硬碟有：" + "、".join(r["label"] for r in rows) + "）"
    s = retire.analyze(conn, root["id"])
    lines = [retire.describe_summary(s)]
    top = retire.folders(conn, root["id"], "only", 0, 5)["folders"]
    if top:
        lines.append("只在這顆上、最大的幾個資料夾：" + "；".join(f"{f['path'] or '（最上層）'}（{f['files']:,} 個，{_fmt_bytes(f['bytes'])}）" for f in top))
    if s["states"]["maybe"]["files"]:
        plan_ = retire.verify_plan(conn, root["id"])
        need = "、".join(f"「{n['name']}」" for n in plan_["need"])
        lines.append(f"還有 {plan_['files']:,} 個要完整比對才能確定（大約要讀 {_fmt_bytes(plan_['bytes'])}）"
                     + (f"，需要接上 {need}" if need else "") + "。請到「硬碟」頁這顆硬碟的「淘汰檢查」按「確認副本」。")
    lines.append("（淘汰檢查只讀不寫；要不要淘汰、怎麼處理，由使用者自己決定。）")
    return "\n".join(lines)


def tool_propose_consolidate(conn: sqlite3.Connection, args: dict, ctx) -> str:
    from .actions import ActionError, propose

    ctx = _ctx(ctx)
    src, rows = _find_root(conn, args.get("from"))
    dst, _ = _find_root(conn, args.get("to"))
    if src is None or dst is None:
        return "（找不到硬碟。目前的硬碟有：" + "、".join(r["label"] for r in rows) + "）"
    try:
        action = propose(conn, "consolidate", {"source_root": src["id"], "target_root": dst["id"], "folder": args.get("folder"),
                                               "mark_source": bool(args.get("mark_source"))}, ctx.level, ctx.question)
    except ActionError as exc:
        return f"（沒有建立提案：{exc}）"
    ctx.actions.append(action)
    return (f"已建立整理計畫 #{action['id']}：{action['summary']}。這只是提案，要等使用者在畫面上看過並按下「執行」才會開始複製；"
            "複製在背景進行，可以暫停；原本的檔案不會被刪除。")


def tool_year_recap(conn: sqlite3.Connection, args: dict, ctx) -> str:
    from .insight import describe_year, year_recap

    try:
        year = int(str(args.get("year") or "").strip()[:4])
    except ValueError:
        return "（沒有給年份）"
    if not 1950 <= year <= 2100:
        return "（年份看起來不對）"
    ctx = _ctx(ctx)
    r = year_recap(conn, year)
    text = describe_year(r)
    for f in r["folders"][:5]:
        n = _source(ctx.sources, {"type": "folder", "id": f["id"], "root_id": f["root_id"], "name": f["name"] or f["drive"], "path": f["path"],
                                  "drive": f["drive"]})
        text += f"\n[{n}] 資料夾 {f['drive']}／{f['path'] or '（最上層）'}"
    return text


def tool_compare_documents(conn: sqlite3.Connection, args: dict, ctx) -> str:
    from .insight import compare_texts, describe_compare
    from .textindex import body

    ctx = _ctx(ctx)
    if not ctx.content:
        return "（目前的設定不允許讀文件內容）"
    try:
        a, b = int(args.get("file_a")), int(args.get("file_b"))
    except (TypeError, ValueError):
        return "（要給兩個檔案編號）"
    rows = {r["id"]: r for r in conn.execute(
        "SELECT f.id, f.name, f.size, f.root_id, d.path AS folder, COALESCE(v.name, r.name) AS drive FROM files f JOIN folders d ON d.id = f.folder_id "
        "JOIN roots r ON r.id = f.root_id LEFT JOIN drives v ON v.id = r.drive_id WHERE f.id IN (?, ?)", (a, b))}
    if a not in rows or b not in rows:
        return "（找不到其中一個檔案）"
    ta, tb = body(conn, a), body(conn, b)
    if not ta or not tb:
        return "（其中一份 Re'memor 還沒讀到文字，沒辦法比較）"
    for i in (a, b):
        r = rows[i]
        _source(ctx.sources, {"type": "file", "id": r["id"], "root_id": r["root_id"], "name": r["name"], "folder": r["folder"],
                              "path": f"{r['folder']}/{r['name']}" if r["folder"] else r["name"], "drive": r["drive"], "size": r["size"]})
    return describe_compare(rows[a]["name"], rows[b]["name"], compare_texts(ta, tb))


def tool_read_document(conn: sqlite3.Connection, args: dict, ctx) -> str:
    from .textindex import body

    ctx = _ctx(ctx)
    if not ctx.content:
        return "（目前的設定不允許讀文件內容）"
    try:
        fid = int(args.get("file_id"))
    except (TypeError, ValueError):
        return "（沒有給檔案編號）"
    r = conn.execute("SELECT f.id, f.name, f.size, f.mtime, f.root_id, d.path AS folder, COALESCE(v.name, r.name) AS drive "
                     "FROM files f JOIN folders d ON d.id = f.folder_id JOIN roots r ON r.id = f.root_id "
                     "LEFT JOIN drives v ON v.id = r.drive_id WHERE f.id = ?", (fid,)).fetchone()
    if r is None:
        return f"找不到編號 {fid} 的檔案。"
    text = body(conn, fid)
    n = _source(ctx.sources, {"type": "file", "id": r["id"], "root_id": r["root_id"], "name": r["name"], "folder": r["folder"],
                              "path": f"{r['folder']}/{r['name']}" if r["folder"] else r["name"], "drive": r["drive"], "size": r["size"]})
    if not text:
        return f"[{n}] {r['name']}：Re'memor 還沒讀到這份文件的文字（可能還沒讀取，或是掃描檔）。"
    return f"[{n}] {r['name']} 的內容（前 3000 字）：\n{text[:3000]}"


def _proposer(kind: str):
    def tool(conn: sqlite3.Connection, args: dict, ctx) -> str:
        from .actions import ActionError, propose

        ctx = _ctx(ctx)
        try:
            action = propose(conn, kind, args, ctx.level, ctx.question)
        except ActionError as exc:
            return f"（沒有建立提案：{exc}）"
        ctx.actions.append(action)
        return f"已建立提案 #{action['id']}：{action['summary']}。這只是提案，要等使用者在畫面上看過並按下「執行」才會做。"
    return tool


def tool_catalog_analysis(conn: sqlite3.Connection, args: dict, ctx) -> str:
    from . import analysis, classify

    st = analysis.file_stats(conn)
    kw = analysis.keywords(conn, 40)["words"]
    names = {c["key"]: classify.display_name(c) for c in classify.categories(conn, include_merged=True)}
    lines = ["類型：" + "、".join(f"{k['kind']} {k['files']:,} 個 {_fmt_bytes(k['bytes'])}" for k in st["kinds"][:8])]
    years = st["years"]
    if years:
        lines.append("年份（檔案修改日期）：" + "、".join(f"{y['year']}:{y['files']:,}" for y in years[-25:]))
    if kw:
        lines.append("最常出現的詞（資料夾數／檔案數／目前大多在哪一類）：" + "、".join(
            f"{w['word']}({w['folders']}/{w['files']}/{names.get(w['category'], '未分類')})" for w in kw))
    else:
        lines.append("（還沒有找出常見的詞）")
    cats = classify.overview(conn)
    lines.append("目前的分類：" + "；".join(f"{classify.display_name(c)}（{c['folders']} 個資料夾）"
                                          + (f"：{c['description']}" if c["description"] else "") for c in cats))
    rs = classify.rules(conn)
    if rs:
        lines.append("已經有的關鍵字規則：" + "；".join(f"{classify.rule_text(r)}→{names.get(r['category'], r['category'])}" for r in rs[:30]))
    prof = classify.profile(conn)
    if prof:
        lines.append(f"使用者說過的身分：{prof.get('identity') or '（無）'}；開始工作的年份：{prof.get('teach_start_year') or '（還沒問）'}")
    return "\n".join(lines)


def tool_keyword_folders(conn: sqlite3.Connection, args: dict, ctx) -> str:
    from . import analysis, classify

    word = str(args.get("word") or "").strip()[:40]
    if not word:
        return "（沒有指定詞）"
    d = analysis.word_detail(conn, word, limit=25)
    names = {c["key"]: classify.display_name(c) for c in classify.categories(conn, include_merged=True)}
    lines = [f"「{word}」出現在 {d['folders']:,} 個資料夾、{d['files']:,} 個檔案。目前的分類：" + "、".join(
        f"{names.get(x['category'], '未分類')} {x['count']}" for x in d["categories"])]
    for f in d["folder_list"]:
        lines.append(f"- [資料夾 {f['id']}] {f['root']}/{f['path']}（年份 {f['year'] or '不明'}，目前：{names.get(f['category'], '未分類')}）")
    return "\n".join(lines)


def tool_save_profile(conn: sqlite3.Connection, args: dict, ctx) -> str:
    from . import classify

    p = classify.save_profile(conn, args.get("identity"), args.get("teach_start_year"))
    return f"已記下：身分「{p.get('identity') or ''}」，開始工作的年份 {p.get('teach_start_year') or '（未說）'}。"


def tool_classify_folders(conn: sqlite3.Connection, args: dict, ctx) -> str:
    """開始「AI 看資料夾」的背景工作：先估計要看幾個、大約多久，再排進去（看完會把結果放回這段對話）。"""
    from . import classify
    from . import jobs as jobs_mod

    ctx = _ctx(ctx)
    words = [str(w).strip() for w in (args.get("words") or []) if str(w).strip()][:10]
    targets = [str(c).strip() for c in (args.get("categories") or []) if str(c).strip()][:20]
    only = bool(args.get("only_words")) and bool(words)
    n = len(classify.review_candidates(conn, words, only))
    if not n:
        return "（沒有需要看的資料夾：都是使用者自己設定過的，或目錄裡還沒有資料夾）"
    secs = classify.review_estimate(conn, n)
    runner = jobs_mod.current_runner()
    if runner is None:
        return "（現在沒辦法在背景開始，請到「設定 → 分類」按「讓 AI 看資料夾」）"
    runner.submit("classify_review", words=words or None, targets=targets or None, only_words=only or None, chat_id=ctx.chat_id)
    mins = max(1, round(secs / 60))
    return (f"已經開始在背景看 {n:,} 個資料夾，大約 {mins} 分鐘（上層看過、有結論的，裡面的會跟著，實際會更快）。"
            "進度在「掃描進度」，可以暫停。看完會把結果和計畫卡放回這段對話；沒分類的會直接分好，原本已分好、AI 覺得該換的要使用者確認。")


def tool_plan_categories(conn: sqlite3.Connection, args: dict, ctx) -> str:
    from .actions import ActionError, propose

    ctx = _ctx(ctx)
    ops = args.get("ops") if isinstance(args.get("ops"), list) else []
    try:
        action = propose(conn, "category_plan", {"ops": ops, "chat_id": ctx.chat_id, "replace": bool(args.get("replace"))},
                         ctx.level, ctx.question)
    except ActionError as exc:
        return f"（沒有更新計畫：{exc}）"
    if not any(a["id"] == action["id"] for a in ctx.actions):
        ctx.actions.append(action)
    else:
        ctx.actions = [action if a["id"] == action["id"] else a for a in ctx.actions]
    prev = action.get("preview") or {}
    bad = [it for it in action["items"] if it.get("ok") is False]
    cats = "、".join(f"{c['name']} {c['folders']}" for c in prev.get("categories") or [])
    return (f"計畫卡 #{action['id']} 已更新（共 {len(action['items'])} 步），套用後會改變 {prev.get('changed', 0):,} 個資料夾，"
            f"{prev.get('review', 0)} 個要使用者確認。各類資料夾數：{cats}。"
            + (f"有 {len(bad)} 步做不到：" + "；".join(f"{b['name']}（{b['reason']}）" for b in bad) if bad else "")
            + "這還只是計畫，要使用者在畫面上勾選、按確認才會套用。")


RUN = {"search_files": tool_search_files, "largest_folders": tool_largest_folders, "drives_overview": tool_drives_overview,
       "duplicates": tool_duplicates, "read_document": tool_read_document, "retire_check": tool_retire_check, "propose_consolidate": tool_propose_consolidate,
       "year_recap": tool_year_recap, "compare_documents": tool_compare_documents,
       "catalog_analysis": tool_catalog_analysis, "keyword_folders": tool_keyword_folders, "save_profile": tool_save_profile,
       "plan_categories": tool_plan_categories, "classify_folders": tool_classify_folders,
       **{name: _proposer(kind) for name, kind in PROPOSE.items()}}


def _source(sources: list, item: dict) -> int:
    """把查到的檔案或資料夾記成來源，回傳編號（1 起算）；同一個只記一次。"""
    key = (item.get("type"), item.get("id"))
    for i, s in enumerate(sources):
        if (s.get("type"), s.get("id")) == key:
            return i + 1
    sources.append({k: item.get(k) for k in ("type", "id", "root_id", "name", "path", "folder", "drive", "size")})
    return len(sources)


# ---- 規劃與回答 ----

def plan(llm, question: str, history: list[dict], context: str, ctx: Ctx | None = None, results: list[str] | None = None) -> list[dict]:
    ctx = ctx or Ctx()
    names = allowed_tools(ctx)
    tools = "\n".join(f"- {name}：{TOOLS[name][1]}" for name in names)
    recent = "\n".join(f"{m['role']}: {m['content'][:300]}" for m in history[-4:])
    found = "\n\n".join(results or [])
    if len(found) > 6000:
        found = found[:6000] + "\n…（後面省略）"
    can_act = ctx.level >= 3
    prompt = (f"你是 Re'memor 的檔案管理助理，正在幫使用者查他的硬碟目錄。使用者給你的權限：{LEVEL_TEXT[ctx.level]}。\n"
              f"決定接下來要用哪些工具（最多 3 個）。\n可以用的工具：\n{tools}\n\n"
              f"使用者目前在：{context or '（沒有特定位置）'}\n最近的對話：\n{recent or '（無）'}\n\n"
              f"使用者的問題：{question}\n\n"
              + (f"已經查到的資料：\n{found}\n\n資料已經夠回答的話，就給空陣列。\n" if found else "")
              + "只輸出 JSON：{\"calls\": [{\"tool\": 工具名稱, \"args\": {...}}]}。打招呼或不需要查資料的問題就給空陣列。"
              "搜尋關鍵字要用檔名或文件裡可能出現的詞，短一點（例如「預算」而不是整句話）。"
              + ("只有使用者要求整理（例如歸類、改名、搬移、標記）時才用 propose_ 開頭的工具；檔案編號一定要來自查到的資料，不要猜。"
                 if can_act else "")
              + "\n使用者在談自己的身分、習慣，或想怎麼分類時：先用 catalog_analysis 看資料；他說了身分或開始工作的年份就用 save_profile 記下來；"
              + ("要新增、改名、合併、拆分分類，或加關鍵字規則、替資料夾改分類，就用 plan_categories（一次只放這次要改的步驟）。"
                 "同一個詞可能屬於兩類（例如學校名稱可能是讀過也教過）時，年份能分就用有 year_from／year_to 的規則；"
                 "還不知道他哪一年開始工作，就先不要猜，在回答裡問他。"
                 "使用者要你「重新整理、標註、把相關的分到某幾類」時，用 classify_folders 讓 AI 真的去看資料夾（可以指定 words 與 categories）。" if can_act else "需要改分類時，請使用者到設定 → AI 助理把權限調到「可以幫你整理」。"))
    try:
        data = llm.plan_json(prompt, _plan_schema(names))
    except Exception:  # noqa: BLE001  規劃失敗就直接回答（不查資料）
        return []
    calls = data.get("calls") if isinstance(data, dict) else None
    return [c for c in (calls or []) if isinstance(c, dict) and c.get("tool") in names][:3]


def ask(conn: sqlite3.Connection, llm, question: str, history: list[dict] | None = None, context: str = "", lang: str = "zh-Hant",
        level: int = 2, cloud_content: bool = False, chat_id: int | None = None):
    """回答一個問題，逐步產生事件（給介面即時顯示）：
    {"type": "step", "tool", "args"}、{"type": "action", "action"}（提案）、{"type": "token", "text"}、
    {"type": "done", "sources": [...]}、{"type": "error", "message"}。"""
    history = history or []
    remote = bool(getattr(llm, "remote", False))
    ctx = Ctx(level, content=(not remote) or bool(cloud_content), question=question, chat_id=chat_id)
    results: list[str] = []
    done_calls: set[str] = set()
    rounds = 3 if ctx.level >= 3 else 2
    for _ in range(rounds):
        calls = plan(llm, question, history, context, ctx, results)
        fresh = []
        for c in calls:
            key = json.dumps([c["tool"], c.get("args") or {}], ensure_ascii=False, sort_keys=True)
            if key not in done_calls:
                done_calls.add(key)
                fresh.append(c)
        if not fresh:
            break
        for call in fresh:
            args = call.get("args") if isinstance(call.get("args"), dict) else {}
            yield {"type": "step", "tool": call["tool"], "args": args}
            before = len(ctx.actions)
            try:
                results.append(f"### {call['tool']}\n" + RUN[call["tool"]](conn, args, ctx))
            except Exception as exc:  # noqa: BLE001  單一工具失敗不影響回答
                results.append(f"### {call['tool']}\n（查詢失敗：{exc}）")
            for action in ctx.actions[before:]:
                yield {"type": "action", "action": action}
            if call["tool"] == "plan_categories" and len(ctx.actions) == before:  # 同一張計畫卡更新了：再送一次給介面
                for action in ctx.actions:
                    if action["kind"] == "category_plan":
                        yield {"type": "action", "action": action}
    language = LANG_NAMES.get(lang, "繁體中文")
    where = "透過使用者自己選擇的服務執行" if remote else "在使用者自己的電腦上離線執行"
    system = (f"你是 Re'memor 的檔案管理助理，{where}。用{language}回答，語氣親切、白話、簡潔。\n"
              f"使用者給你的權限：{LEVEL_TEXT[ctx.level]}。\n"
              "規則：\n- 只根據「查到的資料」回答；資料裡沒有的，就說查不到，並建議可以怎麼找，不要編造檔名或路徑。\n"
              "- 提到檔案或資料夾時，在後面標上來源編號，例如 [1]。\n"
              "- 你自己不能刪除、搬移或修改任何檔案。"
              + ("你建立的整理提案（或分類的計畫卡）會列在回答下面，要等使用者檢查後勾選、按確認才會做；不要說已經做好了。"
                 "回答時用一兩句話說明這次改了什麼，以及還有什麼需要使用者決定（例如哪一年開始工作）。"
                 if ctx.actions else
                 "需要整理時，提出具體建議，並說明要在 Re'memor 的哪個頁面由使用者自己確認（例如「重複項目」頁、「待刪除」頁）"
                 + ("；或請使用者到設定 → AI 助理提高權限，讓你直接提出整理動作。" if ctx.level < 3 else "。"))
              + "\n- 不要提到工具名稱、JSON，或分類的內部代號（例如 c10），一律用分類名稱。"
              + "\n- 只有提到「查到的資料」裡有編號的檔案或資料夾時才標 [編號]；統計、分析的數字不要標。"
              + "\n- 你可以讓這台電腦上的 AI 在背景真的去看資料夾並分類；已經開始的話，告訴使用者進度在「掃描進度」，看完結果會回到這段對話。")
    data = "\n\n".join(results) if results else "（這個問題沒有查資料）"
    messages = [{"role": "system", "content": system}]
    for m in history[-6:]:
        if m.get("role") in ("user", "assistant") and m.get("content"):
            messages.append({"role": m["role"], "content": str(m["content"])[:2000]})
    messages.append({"role": "user", "content": f"使用者目前在：{context or '（沒有特定位置）'}\n\n查到的資料：\n{data}\n\n問題：{question}"})
    try:
        for text in llm.stream(messages):
            yield {"type": "token", "text": text}
    except OllamaUnavailable as exc:
        yield {"type": "error", "message": str(exc)}
        return
    except Exception as exc:  # noqa: BLE001
        yield {"type": "error", "message": f"助理沒有回應：{exc}"}
        return
    yield {"type": "done", "sources": ctx.sources, "actions": [a["id"] for a in ctx.actions]}


# ---- 狀態與建議 ----

PROVIDER_NAMES = {"claude": "Claude", "gemini": "Gemini", "openai": "OpenAI", "custom": ""}


def status(cfg, client) -> dict:
    """助理能不能用。這台電腦（Ollama）：有沒有開、模型下載了沒。其他服務：網址、模型、金鑰填了沒（不在打開頁面時連到外面）。
    remote＝問題與檔名會送到這台電腦以外的服務。"""
    from .analyzer import ollama_installed
    from .models import assistant_model, same_model

    p = provider_of(cfg)
    level = max(1, min(4, int(getattr(cfg, "assistant_permission", 2) or 2)))
    base = {"provider": p, "permission": level, "cloud_content": bool(getattr(cfg, "assistant_cloud_content", 0))}
    if p != "ollama":
        s = api_settings(cfg, p)
        out = {**base, "model": s["model"], "url": s["url"], "remote": is_remote(cfg), "service": PROVIDER_NAMES.get(p) or "",
               "ollama": True, "installed": True, "model_ready": False, "message": ""}
        if p == "custom" and (not s["url"] or not s["model"]):
            out["message"] = "請到設定 → AI 助理填寫服務網址與模型名稱。"
        elif p != "custom" and not s["key"]:
            out["message"] = f"請到設定 → AI 助理填寫 {PROVIDER_NAMES[p]} 的 API 金鑰。"
        elif not s["model"]:
            out["message"] = "請到設定 → AI 助理選擇模型。"
        else:
            out["model_ready"] = True  # 真的連不連得到，問的時候或按「測試連線」才知道
        return out
    model = assistant_model(cfg)
    out = {**base, "model": model, "remote": False, "service": "", "ollama": False, "installed": False, "model_ready": False, "message": ""}
    try:
        names = client.list_models()
    except OllamaUnavailable:
        out["installed"] = ollama_installed()["installed"]
        out["message"] = "Ollama 已安裝但沒有開啟。" if out["installed"] else "還沒有安裝 Ollama。"
        return out
    out["ollama"] = out["installed"] = True
    out["model_ready"] = any(same_model(model, n) for n in names)
    if not out["model_ready"]:
        out["message"] = f"還沒下載助理用的模型（{model}）。"
    return out


def suggestions(conn: sqlite3.Connection, ocr_scope: str = "scans") -> list[dict]:
    """「我可以幫忙什麼」：直接從目錄算出來的建議（不用模型）。每張卡片：
    {key, title 參數, href 或 ask（問助理的話）}；文字由介面依語言組成。"""
    from .dupes import compare_plan, duplicate_files, duplicate_folders
    from .textindex import extract_plan

    out = []
    try:
        folders = duplicate_folders(conn, limit=0)
        files = duplicate_files(conn, limit=0)
        free = (folders.get("releasable") or 0) + (files.get("releasable") or 0)
        if free > 200_000_000:
            out.append({"key": "dupes", "bytes": free, "groups": (folders.get("confirmed") or 0) + (files.get("total") or 0), "href": "/duplicates"})
        plan_ = compare_plan(conn)
        waiting = plan_["small"]["files"] + plan_["large"]["files"]
        if waiting > 100:
            out.append({"key": "compare", "files": waiting, "bytes": plan_["small"]["bytes"] + plan_["large"]["bytes"], "href": "/duplicates"})
    except Exception:  # noqa: BLE001
        pass
    pending = conn.execute("SELECT COUNT(*) FROM delete_marks").fetchone()[0]
    if pending:
        out.append({"key": "pending", "count": pending, "href": "/pending"})
    try:
        text = extract_plan(conn)
        if text["todo"]["files"]:
            out.append({"key": "unread", "files": text["todo"]["files"], "href": "/settings/text"})
        if text["errors"] > 20:
            out.append({"key": "failed", "files": text["errors"], "href": "/settings/text"})
    except Exception:  # noqa: BLE001
        pass
    now = time.time()
    for r in conn.execute("SELECT r.id, r.name, r.path, r.last_scan, r.scan_state FROM roots r"):
        online = Path(r["path"]).is_dir()
        if r["scan_state"] == "partial" and online:
            out.append({"key": "incomplete", "name": r["name"], "root": r["id"], "href": "/drives"})
        elif r["last_scan"]:
            try:
                age = (now - time.mktime(time.strptime(r["last_scan"][:19], "%Y-%m-%dT%H:%M:%S"))) / 86400
            except ValueError:
                age = 0
            if age > 180:
                out.append({"key": "stale", "name": r["name"], "days": int(age), "online": online, "href": "/drives"})
    big = conn.execute("SELECT COUNT(*), COALESCE(SUM(size), 0) FROM files INDEXED BY idx_files_all_size "
                       "WHERE status = 'ok' AND size >= 4000000000").fetchone()
    if big[0]:
        out.append({"key": "big", "count": big[0], "bytes": big[1], "ask": "big"})
    out.append({"key": "ask_find", "ask": "find"})
    return out


__all__ = ["ask", "status", "suggestions", "make_llm", "OllamaLLM", "OpenAILLM", "ClaudeLLM", "TOOLS", "RUN", "Ctx", "allowed_tools"]
