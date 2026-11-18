"""檔案管理助理：在這台電腦上執行的語言模型（預設 Gemma 4 E4B，經由 Ollama），回答關於你的硬碟與檔案的問題。

做法（模型不直接碰資料庫或檔案）：
1. 規劃：模型讀問題，選出要用哪些「查詢工具」（搜尋檔案、最大的資料夾、硬碟概況、重複檔案、讀一份文件的內容）。
2. 查詢：這些工具都是唯讀的程式，查 Re'memor 的目錄資料庫。
3. 回答：模型只根據查到的資料回答，並列出來源檔案讓本人核對。

助理不會刪除、搬移或修改任何檔案（核心原則一）；它只能「建議」，動手一律由本人在介面上確認。
問題、檔案內容與回答都留在這台電腦，不會送到任何外部服務（核心原則二）。

「我可以幫忙什麼」的建議卡片不用模型：直接從目錄算出來，快而且不會說錯。
"""

from __future__ import annotations

import json
import sqlite3
import time
import urllib.error
import urllib.request
from pathlib import Path

from .analyzer import OllamaUnavailable, parse_model_json

TOOLS = {
    "search_files": "依檔名、資料夾名稱與文件內容搜尋檔案。args: {\"query\": 關鍵字, \"kind\": 可省略（document/photo/video/audio/archive）, \"year\": 可省略}",
    "largest_folders": "列出最佔空間的資料夾。args: {\"limit\": 數量（最多 20）}",
    "drives_overview": "所有硬碟的容量、檔案數、上次掃描時間、各類型佔多少。args: {}",
    "duplicates": "重複的檔案與資料夾，以及可以釋出多少空間。args: {}",
    "read_document": "讀一份文件的內容（只讀 Re'memor 已經讀好的文字）。args: {\"file_id\": 檔案編號（先用 search_files 找到）}",
}

PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "calls": {"type": "array", "maxItems": 3, "items": {"type": "object", "properties": {
            "tool": {"type": "string", "enum": list(TOOLS)}, "args": {"type": "object"}}, "required": ["tool", "args"]}},
    },
    "required": ["calls"],
}

LANG_NAMES = {"zh-Hant": "繁體中文", "en": "English"}


def _fmt_bytes(n: int) -> str:
    n = float(n or 0)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit in ("B", "KB") else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


# ---- 查詢工具（全部唯讀） ----

def tool_search_files(conn: sqlite3.Connection, args: dict, sources: list) -> str:
    from .find import find

    q = str(args.get("query") or "").strip()
    if not q:
        return "（沒有給關鍵字）"
    kind = args.get("kind") or None
    year = args.get("year")
    try:
        year = int(year) if year else None
    except (TypeError, ValueError):
        year = None
    res = find(conn, q, kind=kind if kind in ("document", "photo", "video", "audio", "archive", "other") else None, year=year, limit=10)
    if not res["items"]:
        return f"搜尋「{q}」沒有找到檔案。"
    lines = [f"搜尋「{q}」找到 {res['total']} 個檔案{'（只列前 10 個）' if res['total'] > 10 else ''}："]
    for it in res["items"]:
        n = _source(sources, it)
        snippet = "".join(p["text"] for p in it.get("snippet") or [])[:160]
        when = time.strftime("%Y-%m-%d", time.localtime(it["mtime"])) if it.get("mtime") else ""
        lines.append(f"[{n}] {it['name']}（編號 {it['id']}，{_fmt_bytes(it['size'])}，{when}，硬碟「{it['drive']}」，"
                     f"資料夾 {it['folder'] or '最上層'}）" + (f"\n    內容：{snippet}" if snippet else ""))
    return "\n".join(lines)


def tool_largest_folders(conn: sqlite3.Connection, args: dict, sources: list) -> str:
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
        n = _source(sources, {"type": "folder", "id": r["id"], "root_id": r["root_id"], "name": r["name"], "path": r["path"],
                              "drive": r["drive"], "size": r["total_bytes"]})
        lines.append(f"[{n}] {r['name']}（{_fmt_bytes(r['total_bytes'])}，{r['total_files']:,} 個檔案，硬碟「{r['drive']}」，路徑 {r['path']}）")
    return "\n".join(lines)


def tool_drives_overview(conn: sqlite3.Connection, args: dict, sources: list) -> str:
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


def tool_duplicates(conn: sqlite3.Connection, args: dict, sources: list) -> str:
    from .dupes import compare_plan, duplicate_files, duplicate_folders

    folders = duplicate_folders(conn, limit=5)
    files = duplicate_files(conn, limit=5)
    plan = compare_plan(conn)
    lines = [f"重複資料夾：{folders['confirmed']} 組已確認，可釋出 {_fmt_bytes(folders['releasable'])}。",
             f"重複檔案：{files['total']} 組已確認，可釋出 {_fmt_bytes(files['releasable'])}。",
             f"還沒比對內容的檔案：{plan['small']['files'] + plan['large']['files']:,} 個（比對後才能確定是不是真的一樣）。"]
    for g in (folders.get("groups") or [])[:3] + (files.get("groups") or [])[:3]:
        items = g.get("items") or []
        if items:
            lines.append(f"- 「{items[0]['name']}」有 {len(items)} 份：" + "；".join(f"{i.get('drive')}／{i.get('path')}" for i in items[:4]))
    lines.append("（助理只提供建議；要刪除時請到「重複項目」頁由本人選擇保留哪一份。）")
    return "\n".join(lines)


def tool_read_document(conn: sqlite3.Connection, args: dict, sources: list) -> str:
    from .textindex import body

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
    n = _source(sources, {"type": "file", "id": r["id"], "root_id": r["root_id"], "name": r["name"], "folder": r["folder"],
                          "path": f"{r['folder']}/{r['name']}" if r["folder"] else r["name"], "drive": r["drive"], "size": r["size"]})
    if not text:
        return f"[{n}] {r['name']}：Re'memor 還沒讀到這份文件的文字（可能還沒讀取，或是掃描檔）。"
    return f"[{n}] {r['name']} 的內容（前 3000 字）：\n{text[:3000]}"


RUN = {"search_files": tool_search_files, "largest_folders": tool_largest_folders, "drives_overview": tool_drives_overview,
       "duplicates": tool_duplicates, "read_document": tool_read_document}


def _source(sources: list, item: dict) -> int:
    """把查到的檔案或資料夾記成來源，回傳編號（1 起算）；同一個只記一次。"""
    key = (item.get("type"), item.get("id"))
    for i, s in enumerate(sources):
        if (s.get("type"), s.get("id")) == key:
            return i + 1
    sources.append({k: item.get(k) for k in ("type", "id", "root_id", "name", "path", "folder", "drive", "size")})
    return len(sources)


# ---- 和模型對話：這台電腦的 Ollama，或 OpenAI 相容的 API（本機的 LM Studio、llama.cpp，或雲端服務） ----

def is_local_url(url: str) -> bool:
    """網址是不是這台電腦（資料不會離開）。"""
    from urllib.parse import urlparse

    host = (urlparse(url).hostname or "").lower()
    return host in ("127.0.0.1", "localhost", "::1") or host.endswith(".local")


class OllamaLLM:
    """這台電腦上的 Ollama。"""

    def __init__(self, client, base_url: str, model: str):
        self.client, self.base_url, self.model = client, base_url, model
        self.remote = False

    def plan_json(self, prompt: str, schema: dict) -> dict:
        return self.client.chat_json(self.model, prompt, schema, timeout=120, num_predict=300)

    def stream(self, messages: list[dict]):
        payload = {"model": self.model, "messages": messages, "stream": True, "keep_alive": "15m", "think": False,
                   "options": {"temperature": 0.3, "num_ctx": 8192, "num_predict": 1200}}
        for event in _post_stream(self.base_url, payload):
            if event.get("error"):
                raise RuntimeError(str(event["error"]))
            text = (event.get("message") or {}).get("content") or ""
            if text:
                yield text

    def complete(self, prompt: str, max_tokens: int = 50) -> str:
        return "".join(self.stream([{"role": "user", "content": prompt}]))[:500]


class OpenAILLM:
    """OpenAI 相容的 API（/chat/completions）：本機的 LM Studio、llama.cpp server，或雲端服務。"""

    def __init__(self, base_url: str, model: str, key: str = ""):
        self.base_url, self.model, self.key = base_url.rstrip("/"), model, key
        self.remote = not is_local_url(base_url)

    def _request(self, payload: dict, timeout: int = 120):
        headers = {"Content-Type": "application/json"}
        if self.key:
            headers["Authorization"] = f"Bearer {self.key}"
        req = urllib.request.Request(self.base_url + "/chat/completions", data=json.dumps(payload).encode("utf-8"),
                                     headers=headers, method="POST")
        try:
            return urllib.request.urlopen(req, timeout=timeout)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "ignore")[:200]
            if exc.code in (401, 403):
                raise RuntimeError("API 金鑰不對或沒有權限。請到設定 → AI 助理檢查。") from exc
            if exc.code == 404:
                raise RuntimeError(f"找不到這個服務或模型（{self.model}）。請檢查網址與模型名稱。") from exc
            raise RuntimeError(f"服務回應 {exc.code}：{body}") from exc
        except (urllib.error.URLError, ConnectionError, TimeoutError) as exc:
            raise OllamaUnavailable(f"連不到 {self.base_url}。請確認服務有開啟、網址正確。") from exc

    def plan_json(self, prompt: str, schema: dict) -> dict:
        payload = {"model": self.model, "messages": [{"role": "user", "content": prompt + "\n只輸出 JSON，不要其他文字。"}],
                   "temperature": 0.1, "max_tokens": 300}
        with self._request(payload) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        content = ((data.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
        return parse_model_json(content)

    def stream(self, messages: list[dict]):
        payload = {"model": self.model, "messages": messages, "stream": True, "temperature": 0.3, "max_tokens": 1200}
        with self._request(payload, timeout=300) as resp:
            for raw in resp:
                line = raw.decode("utf-8").strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    return
                try:
                    event = json.loads(data)
                except ValueError:
                    continue
                text = ((event.get("choices") or [{}])[0].get("delta") or {}).get("content") or ""
                if text:
                    yield text

    def complete(self, prompt: str, max_tokens: int = 50) -> str:
        payload = {"model": self.model, "messages": [{"role": "user", "content": prompt}], "temperature": 0, "max_tokens": max_tokens}
        with self._request(payload, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return ((data.get("choices") or [{}])[0].get("message") or {}).get("content") or ""


def make_llm(cfg, client):
    """依設定選擇：這台電腦的 Ollama（預設），或 OpenAI 相容的 API。"""
    if cfg.assistant_provider == "openai" and cfg.assistant_api_url:
        return OpenAILLM(cfg.assistant_api_url, cfg.assistant_api_model, cfg.assistant_api_key)
    return OllamaLLM(client, cfg.ollama_url, cfg.assistant_model)


def _post_stream(base_url: str, payload: dict, timeout: int = 300):
    req = urllib.request.Request(base_url.rstrip("/") + "/api/chat", data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "ignore")
        if exc.code == 404:
            raise OllamaUnavailable(f"模型「{payload.get('model')}」還沒下載。") from exc
        raise RuntimeError(f"Ollama 回應 {exc.code}：{body[:200]}") from exc
    except (urllib.error.URLError, ConnectionError) as exc:
        raise OllamaUnavailable("沒有連到 Ollama。請打開 Ollama 後再試一次。") from exc
    with resp:
        for line in resp:
            if line.strip():
                yield json.loads(line.decode("utf-8"))


def plan(llm, question: str, history: list[dict], context: str) -> list[dict]:
    tools = "\n".join(f"- {name}：{desc}" for name, desc in TOOLS.items())
    recent = "\n".join(f"{m['role']}: {m['content'][:300]}" for m in history[-4:])
    prompt = (f"你是 Re'memor 的檔案管理助理，正在幫使用者查他的硬碟目錄。先決定要用哪些查詢工具（最多 3 個）。\n"
              f"可以用的工具：\n{tools}\n\n"
              f"使用者目前在：{context or '（沒有特定位置）'}\n最近的對話：\n{recent or '（無）'}\n\n"
              f"使用者的問題：{question}\n\n"
              "只輸出 JSON：{\"calls\": [{\"tool\": 工具名稱, \"args\": {...}}]}。打招呼或不需要查資料的問題就給空陣列。"
              "搜尋關鍵字要用檔名或文件裡可能出現的詞，短一點（例如「預算」而不是整句話）。")
    try:
        data = llm.plan_json(prompt, PLAN_SCHEMA)
    except Exception:  # noqa: BLE001  規劃失敗就直接回答（不查資料）
        return []
    calls = data.get("calls") if isinstance(data, dict) else None
    return [c for c in (calls or []) if isinstance(c, dict) and c.get("tool") in RUN][:3]


def ask(conn: sqlite3.Connection, llm, question: str, history: list[dict] | None = None, context: str = "", lang: str = "zh-Hant"):
    """回答一個問題，逐步產生事件（給介面即時顯示）：
    {"type": "step", "tool", "args"}、{"type": "token", "text"}、{"type": "done", "sources": [...]}、{"type": "error", "message"}。"""
    history = history or []
    sources: list[dict] = []
    results = []
    for call in plan(llm, question, history, context):
        yield {"type": "step", "tool": call["tool"], "args": call.get("args") or {}}
        try:
            results.append(f"### {call['tool']}\n" + RUN[call["tool"]](conn, call.get("args") or {}, sources))
        except Exception as exc:  # noqa: BLE001  單一工具失敗不影響回答
            results.append(f"### {call['tool']}\n（查詢失敗：{exc}）")
    language = LANG_NAMES.get(lang, "繁體中文")
    where = "透過使用者自己選擇的服務執行" if getattr(llm, "remote", False) else "在使用者自己的電腦上離線執行"
    system = (f"你是 Re'memor 的檔案管理助理，{where}。用{language}回答，語氣親切、白話、簡潔。\n"
              "規則：\n- 只根據「查到的資料」回答；資料裡沒有的，就說查不到，並建議可以怎麼找，不要編造檔名或路徑。\n"
              "- 提到檔案或資料夾時，在後面標上來源編號，例如 [1]。\n"
              "- 你不能刪除、搬移或修改任何檔案。需要整理時，提出具體建議，並說明要在 Re'memor 的哪個頁面由使用者自己確認"
              "（例如「重複項目」頁、「待刪除」頁）。\n- 不要提到工具名稱或 JSON。")
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
    yield {"type": "done", "sources": sources}


# ---- 狀態與建議 ----

def status(cfg, client) -> dict:
    """助理能不能用。這台電腦（Ollama）：有沒有開、模型下載了沒。API：網址與模型填了沒、連不連得到。
    remote＝問題與檔案片段會送到這台電腦以外的服務。"""
    from .analyzer import ollama_installed
    from .models import same_model

    if cfg.assistant_provider == "openai":
        url, model = cfg.assistant_api_url, cfg.assistant_api_model
        out = {"provider": "openai", "model": model, "url": url, "remote": bool(url) and not is_local_url(url),
               "ollama": True, "installed": True, "model_ready": False, "message": ""}
        if not url or not model:
            out["message"] = "請到設定 → AI 助理填寫服務網址與模型名稱。"
            return out
        out["model_ready"] = True  # 真的連不連得到，問的時候或按「測試連線」才知道（不在每次打開頁面時連到外面）
        return out
    model = cfg.assistant_model
    out = {"provider": "ollama", "model": model, "remote": False, "ollama": False, "installed": False, "model_ready": False, "message": ""}
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


__all__ = ["ask", "status", "suggestions", "make_llm", "OllamaLLM", "OpenAILLM", "TOOLS", "parse_model_json"]
