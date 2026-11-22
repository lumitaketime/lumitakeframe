"""本機圖庫服務（FastAPI）：提供 PWA 介面與 API。

- 在這台 Mac 上用 127.0.0.1 開啟不需要登入。
- 開啟「手機連線」後綁定區網，其他裝置一律需要密碼登入。
- 檢查 Host / Origin，避免其他網站透過瀏覽器呼叫這個服務。
"""

from __future__ import annotations

import ipaddress
import json
import mimetypes
import os
import shutil
import socket
import sqlite3
import sys
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import quote, urlparse

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response

from . import __version__, db, fileops
from .analyzer import OllamaClient, OllamaUnavailable
from .net import ca_file
from .auth import COOKIE, SESSION_DAYS, Auth
from .config import CONFIG_KEYS, Config
from .jobs import JobRunner
from .media import BROWSER_VIDEO, MediaError, encode, exiftool, load_image, thumb_path, tool_status, write_thumbnail
from .models import annotated, machine_info, recommend, recommend_assistant, same_model
from .search import STACK_COUNT_SQL, search, summarize, tag_covers, top_tags

WEB_DIR = Path(__file__).parent / "web"


_BUILD: str | None = None


def build_id() -> str:
    """這一份程式的建置代號：介面或引擎任何一個檔案改了就不一樣（版本號碼不一定會變）。
    用來分辨「正在執行的 Re'memor」是不是剛更新的這一份。"""
    global _BUILD
    if _BUILD is None:
        import hashlib

        here = Path(__file__).parent
        packed = here / "BUILD_ID"  # Mac App 內打包的版本：打包時算好的
        if packed.is_file():
            _BUILD = packed.read_text().strip()
            return _BUILD
        h = hashlib.sha1()
        for path in [WEB_DIR / "index.html", *sorted(here.glob("*.py"))]:
            try:
                h.update(path.name.encode())
                h.update(path.read_bytes())
            except OSError:
                pass
        _BUILD = h.hexdigest()[:12]
    return _BUILD
PUBLIC_API = {"/api/auth/status", "/api/auth/login", "/api/auth/logout"}
LOCAL_ONLY_API = {"/api/pick-folder", "/api/restart", "/api/shutdown", "/api/catalog/move", "/api/catalog/location/check", "/api/lan", "/api/open-url", "/api/ollama/start", "/api/storage/reveal", "/api/reveal-path", "/api/items/open", "/api/pending/trash", "/api/pending/export",
                  "/api/assistant/actions/run", "/api/assistant/actions/undo", "/api/health/decide", "/api/health/check", "/api/spotlight/report", "/api/spotlight/ack", "/api/spotlight/rebuild"}
SETTING_KEYS = {
    "vision_model", "embed_model", "language", "analyze_max_side", "scan_on_start", "ollama_url",
    "face_enabled", "face_model", "face_similarity", "face_min_faces",
    "query_rewrite", "clip_enabled", "clip_model",
    "keep_awake", "stack_enabled", "burst_seconds",
    "auto_analyze", "dup_threshold", "screen_png_rule", "large_files_limit", "album_sort", "folder_sort", "open_action", "ocr_scope", "ocr_languages", "start_page", "auto_extract", "assistant_model", "assistant_provider", "assistant_api_url", "assistant_api_model", "assistant_api_key", "assistant_claude_model", "assistant_claude_key", "assistant_gemini_model", "assistant_gemini_key", "assistant_openai_model", "assistant_openai_key", "assistant_permission", "assistant_cloud_content", "doc_semantic", "doc_embed_model", "spotlight", "spotlight_internal", "analysis_detail", "analyze_schedule", "night_start", "night_end", "schedule_days", "schedule_start", "schedule_end", "schedule_ac", "schedule_idle", "schedule_battery", "viewer_rating_bar", "nav_hidden", "pinned_tools", "grid_style", "onboarded",
    "text_model", "analysis_prompt", "clip_custom_repo", "face_custom_url", "face_custom_det", "face_custom_rec",
}
SECRET_KEYS = ("assistant_api_key", "assistant_claude_key", "assistant_gemini_key", "assistant_openai_key")
MAX_IDS = 5000


def _is_loopback(host: str) -> bool:
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host == "localhost"


def _host_only(host_header: str) -> str:
    host = host_header.strip().lower()
    if host.startswith("["):
        return host[1:].split("]")[0]
    return host.rsplit(":", 1)[0] if host.count(":") == 1 else host


def lan_addresses(port: int) -> list[str]:
    urls = []
    name = socket.gethostname()
    if name:
        urls.append(f"http://{name if '.' in name else name + '.local'}:{port}")
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("192.0.2.1", 80))  # 不會真的送出封包，只用來取得本機區網 IP
            ip = s.getsockname()[0]
        if not ip.startswith("127."):
            urls.append(f"http://{ip}:{port}")
    except OSError:
        pass
    return urls


def qr_svg(text: str) -> str:
    import qrcode
    import qrcode.image.svg

    img = qrcode.make(text, image_factory=qrcode.image.svg.SvgPathImage, box_size=10, border=2)
    return img.to_string(encoding="unicode")


def create_app(cfg: Config, bound_host: str = "127.0.0.1", client_factory=None, start_jobs_on_boot: bool = True,
               trash=None, warm_background: bool | None = None) -> FastAPI:
    auth = Auth(cfg.auth_file)
    client_factory = client_factory or (lambda: OllamaClient(cfg.ollama_url, cfg.request_timeout))
    state: dict = {}
    if warm_background is None:
        warm_background = start_jobs_on_boot

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        conn = db.connect(cfg.db_path)
        has_roots = bool(db.list_roots(conn))
        from .analyzer import reset_server_errors

        reset_server_errors(conn)  # 修正後重新開啟，之前因模型設定失敗的照片會重新分析
        conn.close()
        state["jobs"] = JobRunner(cfg, client_factory)
        state["jobs"].on_finish.append(lambda _job: app.state.clear_memo())

        # 開機時與掃描、讀取文字之後，在背景更新資料庫的估計，查詢才不會走到很慢的路
        def refresh_stats(job=None):
            if job is not None and job.get("kind") not in ("scan", "index", "extract", "ocr", "compare"):
                return

            def run():
                try:
                    c = db.connect(cfg.db_path)
                    try:
                        db.refresh_stats(c)
                    finally:
                        c.close()
                except sqlite3.Error:
                    pass  # 資料庫正忙：下次再更新

            threading.Thread(target=run, daemon=True).start()

        state["jobs"].on_finish.append(refresh_stats)
        state["jobs"].on_finish.append(lambda _job: __import__("lumilib.spotlight", fromlist=["changed"]).changed())
        # 目錄搬好了：重新啟動，改用新位置
        state["jobs"].on_finish.append(
            lambda job: job.get("kind") == "move_catalog" and (job.get("result") or {}).get("moved") and app.state.restart_later(2.0))
        refresh_stats()
        if start_jobs_on_boot and cfg.scan_on_start and has_roots:
            state["jobs"].submit("scan")
        app.state.schedule_warm(4.0)  # 開機後在背景先把探索、整理工具等統計算好
        yield
        app.state.stop_warm()
        state["jobs"].close()
        exiftool().close()

    app = FastAPI(title="Re'memor", version=__version__, lifespan=lifespan, docs_url=None, redoc_url=None)

    def jobs() -> JobRunner:
        return state["jobs"]

    def conn() -> sqlite3.Connection:
        return db.connect(cfg.db_path)

    def is_local(request: Request) -> bool:
        client = request.client.host if request.client else ""
        return _is_loopback(client) and _is_loopback(_host_only(request.headers.get("host", "")))

    # ---- 保護 ----
    # 較重的統計頁（探索、整理工具、關鍵字、人物…）的結果暫存起來；
    # 使用者做了任何修改（非 GET 請求）或背景工作完成時立刻清掉，畫面不會看到舊資料。
    # 資料只會經由這兩條路改變，所以可以放心存久一點（10 分鐘，「回憶」也跟著日期換）。
    import functools
    import threading as _threading

    memo_store: dict = {}
    memo_lock = _threading.Lock()
    key_locks: dict = {}
    # 清掉快取後，在背景把使用者最近打開過的統計頁重新算好（stale 期間不必在點下去時才等）
    warm_calls: dict = {}  # fn 名稱 → (wrapper, 最近一次的參數)
    warm_timer = [None]

    def memo(ttl: float = 30.0, warm: bool = False):
        def deco(fn):
            import inspect

            @functools.wraps(fn)
            def wrapper(*args, **kwargs):
                key = (fn.__name__, tuple(sorted(kwargs.items())))
                if warm:
                    warm_calls[fn.__name__] = (wrapper, dict(kwargs))
                with memo_lock:
                    hit = memo_store.get(key)
                    lock = key_locks.setdefault(key, _threading.Lock())
                if hit and time.monotonic() - hit[0] < ttl:
                    return hit[1]
                # 同一個頁面同時被要兩次（例如背景預先計算時使用者剛好點進來）只算一次
                with lock:
                    with memo_lock:
                        hit = memo_store.get(key)
                    if hit and time.monotonic() - hit[0] < ttl:
                        return hit[1]
                    value = fn(*args, **kwargs)
                    with memo_lock:
                        memo_store[key] = (time.monotonic(), value)
                    return value
            if warm:
                # 先用預設參數登記，開機後就能預先算好（FastAPI 呼叫時也會把預設值帶進來，快取的鍵一致）
                defaults = {k: v.default for k, v in inspect.signature(fn).parameters.items() if v.default is not inspect.Parameter.empty}
                warm_calls[fn.__name__] = (wrapper, defaults)
            return wrapper
        return deco

    def warm_now() -> None:
        for name, (wrapper, kwargs) in list(warm_calls.items()):
            if warm_timer[0] is False:
                return
            try:
                wrapper(**kwargs)
            except Exception as exc:  # noqa: BLE001  預先計算失敗不影響使用者，下次打開時再算
                print(f"預先計算 {name} 失敗：{exc}", flush=True)

    def schedule_warm(delay: float = 1.5) -> None:
        if not warm_background or warm_timer[0] is False:
            return
        if warm_timer[0]:
            warm_timer[0].cancel()
        t = _threading.Timer(delay, warm_now)  # 連續修改時只在停下來後算一次
        t.daemon = True
        warm_timer[0] = t
        t.start()

    def stop_warm() -> None:
        if warm_timer[0]:
            warm_timer[0].cancel()
        warm_timer[0] = False

    def clear_memo() -> None:
        with memo_lock:
            memo_store.clear()
        schedule_warm()

    app.state.warm_now = warm_now
    app.state.schedule_warm = schedule_warm
    app.state.stop_warm = stop_warm
    app.state.clear_memo = clear_memo

    @app.middleware("http")
    async def guard(request: Request, call_next):
        path = request.url.path
        local = is_local(request)
        request.state.local = local
        if not local and not (cfg.lan and bound_host != "127.0.0.1"):
            return JSONResponse({"error": "只允許本機連線"}, status_code=403)
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            origin = request.headers.get("origin")
            if origin and urlparse(origin).netloc.lower() != request.headers.get("host", "").lower():
                return JSONResponse({"error": "來源不符"}, status_code=403)
            if request.method in ("POST", "PUT", "PATCH") and "application/json" not in request.headers.get("content-type", ""):
                return JSONResponse({"error": "需要 JSON"}, status_code=415)
        if path.startswith("/api/"):
            if path in LOCAL_ONLY_API and not local and request.method != "GET":
                return JSONResponse({"error": "這個操作只能在 Mac 本機進行"}, status_code=403)
            if path not in PUBLIC_API and not local and not auth.verify(request.cookies.get(COOKIE)):
                return JSONResponse({"error": "請先登入"}, status_code=401)
        response = await call_next(request)
        if request.method not in ("GET", "HEAD", "OPTIONS") and path.startswith("/api/"):
            clear_memo()
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        return response

    @app.exception_handler(ValueError)
    async def value_error(request: Request, exc: ValueError):
        return JSONResponse({"error": str(exc)}, status_code=400)

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        return JSONResponse({"error": exc.detail}, status_code=exc.status_code)

    # ---- auth ----
    @app.get("/api/auth/status")
    def auth_status(request: Request):
        local = request.state.local
        return {
            "local": local,
            "required": not local,
            "authenticated": local or auth.verify(request.cookies.get(COOKIE)),
            "has_password": auth.has_password,
        }

    @app.post("/api/auth/login")
    def login(request: Request, body: dict = Body(...)):
        if not auth.check_password(str(body.get("password", ""))):
            raise HTTPException(401, "密碼不正確")
        resp = JSONResponse({"ok": True})
        resp.set_cookie(COOKIE, auth.issue(), max_age=SESSION_DAYS * 86400, httponly=True, samesite="lax")
        return resp

    @app.post("/api/auth/logout")
    def logout(body: dict = Body(default={})):
        resp = JSONResponse({"ok": True})
        resp.delete_cookie(COOKIE)
        return resp

    # ---- 伺服器狀態 ----
    @app.get("/api/server")
    def server_info(request: Request):
        c = conn()
        try:
            roots = [_root_dict(c, r) for r in db.list_roots(c)]
            return {
                "version": __version__,
                "build": build_id(),
                "stats": db.stats(c),
                "roots": roots,
                "jobs": jobs().snapshot(),
                "health_alerts": health_alerts(c),
                "models": {"vision": cfg.vision_model, "embed": cfg.embed_model, "language": cfg.language},
                "tools": tool_status(),
                "ssl_ca": bool(ca_file()),
                "ai": cached_ai_status(),
                "ui": {"viewer_rating_bar": cfg.viewer_rating_bar, "nav_hidden": cfg.nav_hidden, "pinned_tools": cfg.pinned_tools,
                       "grid_style": cfg.grid_style, "onboarded": cfg.onboarded,
                       "album_sort": cfg.album_sort, "folder_sort": cfg.folder_sort, "open_action": cfg.open_action,
                       "start_page": cfg.start_page},
                "favorites": favorites(c),
                "local": request.state.local,
                "platform": sys.platform,
                "home": str(cfg.home) if request.state.local else None,
            }
        finally:
            c.close()

    def health_alerts(c) -> list[dict]:
        from .health import alerts

        try:
            return alerts(c)
        except sqlite3.Error:
            return []

    # ---- 硬碟健康：有狀況先停下來問本人 ----
    @app.get("/api/health")
    def health_list(check: bool = True):
        """每顆接著的硬碟的健康狀態（最近看過的直接用上次的結果；只讀取）。"""
        from . import health

        c = conn()
        try:
            out, seen = [], set()
            for r in db.list_roots(c):
                key = health.key_of(r)
                online = Path(r["path"]).is_dir()
                if key in seen:
                    continue
                seen.add(key)
                h = health.check(c, r) if (online and check) else None
                if h is None:
                    row = c.execute("SELECT * FROM drive_health WHERE key = ?", (key,)).fetchone()
                    h = health.public(row) if row else {"key": key, "name": r["name"], "status": "unknown", "findings": [],
                                                         "io_errors": 0, "needs_decision": False, "decision": None, "smart": None}
                same = [x for x in db.list_roots(c) if health.key_of(x) == key]
                out.append({**h, "online": online, "roots": [x["name"] for x in same], "root_ids": [x["id"] for x in same], "root_id": r["id"]})
            return out
        finally:
            c.close()

    @app.post("/api/health/check")
    def health_check(body: dict = Body(default={})):
        """重新看一次某顆硬碟的自我檢測（使用者按下「重新檢查」）。"""
        from . import health

        c = conn()
        try:
            root = c.execute("SELECT * FROM roots WHERE id = ?", (int(body.get("root_id") or 0),)).fetchone()
            if root is None:
                raise HTTPException(404, "找不到這個資料夾來源")
            if not Path(root["path"]).is_dir():
                raise HTTPException(400, "這顆硬碟沒有接上")
            return health.check(c, root, force=True)
        finally:
            c.close()

    @app.post("/api/health/decide")
    def health_decide(body: dict = Body(...)):
        """本人選擇怎麼處理有狀況的硬碟：pause（先暫停）／light（只記錄檔名、不讀內容）／continue（照常進行）。"""
        from . import health

        c = conn()
        try:
            return health.decide(c, str(body.get("key") or ""), str(body.get("decision") or ""))
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        finally:
            c.close()

    def folder_cover(c, root_id: int, path: str) -> int | None:
        """使用者自訂的資料夾封面（照片還在才算）。"""
        row = c.execute(
            "SELECT fc.image_id FROM folder_covers fc JOIN images i ON i.id = fc.image_id "
            "WHERE fc.root_id = ? AND fc.path = ? AND i.status = 'ok'", (root_id, path)).fetchone()
        return row[0] if row else None

    def folder_pref(c, root_id: int, path: str) -> tuple[bool, int | None]:
        row = c.execute("SELECT favorite, position FROM folder_prefs WHERE root_id = ? AND path = ?", (root_id, path)).fetchone()
        return (bool(row["favorite"]), row["position"]) if row else (False, None)

    def favorites(c) -> list[dict]:
        """側邊欄的「喜好項目」：收藏的相簿，以及釘選的資料夾、檔案、側邊欄捷徑（後三種依拖曳排好的順序）。"""
        out = [{"kind": "album", "id": r["id"], "name": r["name"], "href": f"/albums/{r['id']}"}  # noqa: E501
               for r in c.execute("SELECT id, name FROM albums WHERE favorite = 1 ORDER BY position IS NULL, position, name")]
        pins = []
        for r in c.execute("SELECT p.root_id, p.path, p.position, r.name AS root_name FROM folder_prefs p JOIN roots r ON r.id = p.root_id "
                           "WHERE p.favorite = 1"):
            name = r["path"].rsplit("/", 1)[-1] if r["path"] else r["root_name"]
            href = f"/folders/{r['root_id']}" + (f"?path={quote(r['path'], safe='')}" if r["path"] else "")
            pins.append({"kind": "folder", "name": name, "href": href, "root_id": r["root_id"], "path": r["path"], "position": r["position"]})
        for r in c.execute("SELECT href, kind, ref, name, icon, position FROM sidebar_links"):
            pins.append({"kind": r["kind"], "name": r["name"], "href": r["href"], "ref": r["ref"], "icon": r["icon"], "position": r["position"]})
        pins.sort(key=lambda p: (p["position"] is None, p["position"] or 0, p["name"]))
        return out + pins

    def _root_dict(c, r) -> dict:
        from .catalog import root_summary

        custom = folder_cover(c, r["id"], "")
        cover = {"id": custom} if custom else c.execute(
            "SELECT id FROM images WHERE root_id = ? AND status = 'ok' AND thumb_ok = 1 ORDER BY sort_at DESC LIMIT 1",
            (r["id"],),
        ).fetchone()
        return {
            "id": r["id"], "name": r["name"], "path": r["path"], "online": Path(r["path"]).is_dir(),
            "count": r["image_count"] if "image_count" in r.keys() else c.execute(
                "SELECT COUNT(*) FROM images WHERE root_id = ? AND status = 'ok'", (r["id"],)).fetchone()[0],
            "last_scan": r["last_scan"], "cover": cover["id"] if cover else None, "cover_custom": bool(custom),
            "favorite": folder_pref(c, r["id"], "")[0], "position": folder_pref(c, r["id"], "")[1],
            "catalog": root_summary(c, r),
        }

    # ---- 時間軸 ----
    def scope_sql(params: dict) -> tuple[str, list]:
        where, args = ["i.status = 'ok'"], []
        if params.get("album") is None:
            where.append("i.stack_top = 1")  # 疊放只顯示封面
        if params.get("fav") == "1":
            where.append("i.favorite = 1")
        if params.get("type") in ("photo", "video"):
            where.append("i.media_type = ?")
            args.append(params["type"])
        if params.get("type") == "raw":
            where.append("i.is_raw = 1")
        if str(params.get("album", "")).isdigit():
            where.append("i.id IN (SELECT image_id FROM album_items WHERE album_id = ?)")
            args.append(int(params["album"]))
        if params.get("missing") == "1":
            where[0] = "i.status = 'missing'"
        # 快速篩選：星等、顏色標籤、檔案類型
        rating = str(params.get("rating", ""))
        if rating.lstrip("-").isdigit() and int(rating) != 0:
            where.append("i.rating = -1" if int(rating) < 0 else "i.rating >= ?")
            if int(rating) > 0:
                args.append(int(rating))
        if params.get("label"):
            where.append("i.label = ?")
            args.append(str(params["label"]))
        kind = params.get("kind")
        if kind in ("raw", "jpeg", "video"):
            if "i.stack_top = 1" in where:
                where.remove("i.stack_top = 1")  # 疊放裡的 RAW 或 JPEG 也要找得到
            if kind == "raw":
                where.append("i.is_raw = 1")
            elif kind == "video":
                where.append("i.media_type = 'video'")
            else:
                where.append("i.media_type = 'photo' AND i.is_raw = 0 AND "
                             "(lower(i.rel_path) LIKE '%.jpg' OR lower(i.rel_path) LIKE '%.jpeg')")
        return " AND ".join(where), args

    @app.get("/api/timeline/buckets")
    def buckets(request: Request):
        where, args = scope_sql(dict(request.query_params))
        c = conn()
        try:
            rows = c.execute(
                f"SELECT substr(i.sort_at, 1, 7) AS month, COUNT(*) AS count FROM images i WHERE {where} "
                "GROUP BY month ORDER BY month DESC",
                args,
            ).fetchall()
            return [{"month": r["month"] or "0000-00", "count": r["count"]} for r in rows]
        finally:
            c.close()

    @app.get("/api/timeline/bucket")
    def bucket(request: Request, month: str):
        where, args = scope_sql(dict(request.query_params))
        c = conn()
        try:
            if month == "0000-00":
                rows = c.execute(f"SELECT i.*, {STACK_COUNT_SQL} FROM images i WHERE {where} AND i.sort_at IS NULL", args).fetchall()
            else:
                rows = c.execute(
                    f"SELECT i.*, {STACK_COUNT_SQL} FROM images i WHERE {where} AND substr(i.sort_at, 1, 7) = ? ORDER BY i.sort_at DESC, i.id DESC",
                    args + [month],
                ).fetchall()
            return [summarize(r) for r in rows]
        finally:
            c.close()

    # ---- 單一檔案 ----
    def get_image_or_404(c, image_id: int):
        image = db.get_image(c, image_id)
        if image is None:
            raise HTTPException(404, "找不到這個檔案")
        return image

    def detail(c, image) -> dict:
        path = db.absolute_path(c, image)
        root = db.get_root(c, image["root_id"])
        # 向量等二進位欄位（例如圖像搜尋索引）不能放進 JSON
        data = {k: image[k] for k in image.keys()
                if k not in ("embedding", "search_text", "clip") and not isinstance(image[k], (bytes, bytearray, memoryview))}
        for key in ("tags", "objects", "user_tags", "keywords"):
            data[key] = db.json_list(image[key])
        albums = c.execute(
            "SELECT a.id, a.name FROM albums a JOIN album_items ai ON ai.album_id = a.id WHERE ai.image_id = ? ORDER BY a.name",
            (image["id"],),
        ).fetchall()
        faces = c.execute(
            "SELECT f.id, f.person_id, f.x1, f.y1, f.x2, f.y2, p.name FROM faces f LEFT JOIN persons p ON p.id = f.person_id "
            "WHERE f.image_id = ? AND f.excluded = 0 ORDER BY f.x1",
            (image["id"],),
        ).fetchall()
        from .organize import stack_members
        from .places import country_names

        data["stack"] = [summarize(m) for m in stack_members(c, image["stack_id"])] if image["stack_id"] else []
        data["country_name"] = country_names(image["country"])[0] if image["country"] else ""
        data.update(
            faces=[{"id": f["id"], "person_id": f["person_id"], "name": f["name"],
                    "box": [f["x1"], f["y1"], f["x2"], f["y2"]]} for f in faces],
            summary=summarize(image),
            root=root["name"], root_path=root["path"], path=str(path), exists=path.exists(),
            filename=image["rel_path"].rsplit("/", 1)[-1],
            albums=[dict(a) for a in albums],
            playable=image["media_type"] == "video" and Path(image["rel_path"]).suffix.lower() in BROWSER_VIDEO,
            sidecars=[p.name for p in fileops.sidecars(path)] if path.exists() else [],
        )
        return data

    @app.get("/api/assets/{image_id:int}")
    def asset(image_id: int):
        c = conn()
        try:
            return detail(c, get_image_or_404(c, image_id))
        finally:
            c.close()

    @app.post("/api/assets/{image_id:int}")
    def update_asset(image_id: int, body: dict = Body(...)):
        c = conn()
        try:
            get_image_or_404(c, image_id)
            tags = body.get("user_tags")
            if isinstance(tags, str):
                tags = tags.replace("，", ",").replace("、", ",").split(",")
            db.set_user_fields(c, image_id, user_tags=tags, note=body.get("note"), favorite=body.get("favorite"))
            return detail(c, db.get_image(c, image_id))
        finally:
            c.close()

    def _render(image, path: Path, max_side: int):
        return load_image(path, image["media_type"], bool(image["is_raw"]), max_side, image["duration"], image["orientation"])

    @app.post("/api/assets/{image_id:int}/marks")
    def set_marks(image_id: int, body: dict = Body(...)):
        """星等（-1 拒絕～5）、顏色標籤、關鍵字；只存在圖庫裡，不寫入檔案。"""
        from . import ratings

        c = conn()
        try:
            get_image_or_404(c, image_id)
            kws = body.get("keywords")
            if isinstance(kws, str):
                kws = kws.replace("，", ",").replace("、", ",").split(",")
            try:
                ratings.update(c, image_id, rating=body.get("rating"), label=body.get("label"), keywords=kws)
            except ValueError as exc:
                raise HTTPException(400, str(exc))
            return detail(c, db.get_image(c, image_id))
        finally:
            c.close()

    @app.get("/api/assets/{image_id:int}/thumb")
    def thumb(image_id: int):
        c = conn()
        try:
            image = get_image_or_404(c, image_id)
            path = db.absolute_path(c, image)
        finally:
            c.close()
        target = thumb_path(cfg.thumbs_dir, image["fingerprint"])
        if not target.exists():
            if not path.exists():
                raise HTTPException(404, "檔案目前無法存取")
            try:
                write_thumbnail(_render(image, path, cfg.thumb_size * 2), cfg.thumbs_dir, image["fingerprint"], cfg.thumb_size)
            except MediaError as exc:
                raise HTTPException(415, str(exc))
        return FileResponse(target, media_type="image/webp", headers={"Cache-Control": "private, max-age=31536000, immutable"})

    @app.get("/api/assets/{image_id:int}/preview")
    def preview(image_id: int, size: int = 2048):
        size = max(256, min(size, 4096))
        c = conn()
        try:
            image = get_image_or_404(c, image_id)
            path = db.absolute_path(c, image)
        finally:
            c.close()
        if not path.exists():
            target = thumb_path(cfg.thumbs_dir, image["fingerprint"])
            if target.exists():  # 硬碟沒接上時退回縮圖
                return FileResponse(target, media_type="image/webp", headers={"Cache-Control": "no-store"})
            raise HTTPException(404, "檔案目前無法存取")
        if Path(image["rel_path"]).suffix.lower() == ".gif":
            return FileResponse(path, media_type="image/gif")
        try:
            body = encode(_render(image, path, size), size, "JPEG", 88)
        except MediaError as exc:
            raise HTTPException(415, str(exc))
        return Response(body, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=86400"})

    @app.get("/api/assets/{image_id:int}/original")
    def original(image_id: int, download: int = 0):
        c = conn()
        try:
            image = get_image_or_404(c, image_id)
            path = db.absolute_path(c, image)
        finally:
            c.close()
        if not path.exists():
            raise HTTPException(404, "檔案目前無法存取（硬碟可能未連接）")
        ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if path.suffix.lower() in (".mov",):
            ctype = "video/quicktime"
        return FileResponse(
            path, media_type=ctype, filename=path.name if download else None,
            content_disposition_type="attachment" if download else "inline",
            headers={"Cache-Control": "private, max-age=3600"},
        )

    @app.post("/api/assets/{image_id:int}/reveal")
    def reveal(image_id: int, body: dict = Body(default={})):
        c = conn()
        try:
            path = db.absolute_path(c, get_image_or_404(c, image_id))
        finally:
            c.close()
        if not path.exists():
            raise HTTPException(404, "檔案不在原位置，可能硬碟未連接或已被移動")
        fileops.reveal(path, select=body.get("mode") != "open")
        return {"ok": True}

    @app.post("/api/assets/bulk")
    def bulk(body: dict = Body(...)):
        ids = [int(i) for i in body.get("ids") or []][:MAX_IDS]
        action = body.get("action")
        if not ids:
            raise HTTPException(400, "沒有選取任何項目")
        c = conn()
        try:
            if action in ("favorite", "unfavorite"):
                c.executemany("UPDATE images SET favorite = ? WHERE id = ?", [(1 if action == "favorite" else 0, i) for i in ids])
                c.commit()
                return {"done": len(ids)}
            if action == "trash":
                res = fileops.trash_images(c, ids, **({"trash": trash} if trash else {}))
                return {"done": len(res.done), "ids": res.done, "errors": res.errors}
            if action in ("rating", "label"):
                from . import ratings

                value = body.get("value")
                errors = []
                for i in ids:
                    try:
                        ratings.update(c, i, **({"rating": int(value or 0)} if action == "rating" else {"label": value or ""}))
                    except ValueError as exc:  # 個別項目失敗不影響其他
                        errors.append(str(exc))
                return {"done": len(ids), "errors": errors[:5]}
            if action in ("add_tags", "remove_tags"):
                # 批次加上或移除我的關鍵字（#標籤）；只存在圖庫裡
                from . import ratings

                tags = [str(t).strip().lstrip("#").strip() for t in (body.get("tags") or []) if str(t).strip().lstrip("#").strip()]
                if not tags:
                    raise HTTPException(400, "請輸入至少一個標籤")
                lower = {t.lower() for t in tags}
                errors, changed = [], 0
                for i in ids:
                    row = db.get_image(c, i)
                    if row is None:
                        continue
                    current = list(dict.fromkeys(db.json_list(row["keywords"]) + db.json_list(row["user_tags"])))
                    if action == "add_tags":
                        new = current + [t for t in tags if t.lower() not in {x.lower() for x in current}]
                    else:
                        new = [t for t in current if t.lower() not in lower]
                    if new == current:
                        continue
                    try:
                        ratings.update(c, i, keywords=new)
                        changed += 1
                    except ValueError as exc:  # 個別項目失敗不影響其他
                        errors.append(str(exc))
                return {"done": changed, "errors": errors[:5]}
            if action == "stack":
                from .organize import make_stack

                return {"stack_id": make_stack(c, ids)}
            if action == "add_to_album":
                album_id = body.get("album_id")
                if not album_id:
                    album_id = db.create_album(c, str(body.get("name") or ""))
                db.add_to_album(c, int(album_id), ids)
                return {"done": len(ids), "album_id": int(album_id)}
            if action == "remove_from_album":
                db.remove_from_album(c, int(body["album_id"]), ids)
                return {"done": len(ids)}
            if action == "analyze":
                return {"jobs": jobs().submit("analyze", ids=ids, redo=bool(body.get("redo")))}
            raise HTTPException(400, f"未知的動作：{action}")
        finally:
            c.close()

    # ---- 疊放 ----
    @app.post("/api/assets/{image_id:int}/stack")
    def stack_action(image_id: int, body: dict = Body(...)):
        from .organize import set_cover, unstack

        c = conn()
        try:
            image = get_image_or_404(c, image_id)
            if body.get("action") == "unstack" and image["stack_id"]:
                unstack(c, image["stack_id"])
            elif body.get("action") == "cover":
                set_cover(c, image_id)
            return detail(c, db.get_image(c, image_id))
        finally:
            c.close()

    # ---- 重複與相似 ----
    @app.get("/api/duplicates")
    def duplicates():
        from .organize import load_duplicates, suggest_keep

        c = conn()
        try:
            data = load_duplicates(c, cfg)
            if data is None:
                return {"computed_at": None, "exact": [], "similar": []}

            def expand(group):
                rows = c.execute(f"SELECT * FROM images WHERE id IN ({','.join('?' * len(group))})", group).fetchall()
                keep = suggest_keep(rows)
                return {
                    "keep": keep,
                    "items": [{**summarize(r), "path": str(db.absolute_path(c, r)), "size": r["size"],
                               "width": r["width"], "height": r["height"], "folder": r["folder"]} for r in rows],
                }

            return {
                "computed_at": data["computed_at"],
                "exact": [expand(g) for g in data["exact"][:300]],
                "similar": [expand(g) for g in data["similar"][:300]],
                "total_exact": len(data["exact"]),
                "total_similar": len(data["similar"]),
            }
        finally:
            c.close()

    @app.post("/api/duplicates/ignore")
    def ignore_duplicates(body: dict = Body(...)):
        from .organize import ignore_group

        c = conn()
        try:
            ignore_group(c, [int(i) for i in body.get("ids") or []])
            return {"ok": True}
        finally:
            c.close()

    # ---- 智慧相簿 ----
    @app.get("/api/smart-albums")
    def smart_albums():
        from .organize import list_smart

        c = conn()
        try:
            return list_smart(c)
        finally:
            c.close()

    @app.post("/api/smart-albums")
    def save_smart_album(body: dict = Body(...)):
        from .organize import save_smart

        c = conn()
        try:
            return {"id": save_smart(c, str(body.get("name", "")), str(body.get("query", "")), body.get("id"))}
        finally:
            c.close()

    @app.get("/api/smart-albums/{smart_id:int}")
    def smart_album(smart_id: int):
        c = conn()
        try:
            row = c.execute("SELECT * FROM smart_albums WHERE id = ?", (smart_id,)).fetchone()
            if row is None:
                raise HTTPException(404, "找不到智慧相簿")
            res = search(c, row["query"], limit=2000)
            return {**dict(row), "count": res["total"], "assets": res["results"]}
        finally:
            c.close()

    @app.delete("/api/smart-albums/{smart_id:int}")
    def delete_smart_album(smart_id: int):
        c = conn()
        try:
            c.execute("DELETE FROM smart_albums WHERE id = ?", (smart_id,))
            c.commit()
            return {"ok": True}
        finally:
            c.close()

    # ---- 那年今日 ----
    @app.get("/api/memories")
    @memo(600, warm=True)
    def get_memories():
        from .organize import memories

        c = conn()
        try:
            return [
                {"year": m["year"], "years_ago": m["years_ago"], "count": m["count"],
                 "assets": [summarize(r) for r in m["rows"]]}
                for m in memories(c)
            ]
        finally:
            c.close()

    # ---- 關鍵字 ----
    @app.get("/api/keywords")
    @memo(600, warm=True)
    def keywords(source: str = "all", year: str | None = None, limit: int = 300):
        from . import keywords as kw

        c = conn()
        try:
            return {"keywords": kw.keyword_counts(c, source, year, max(10, min(limit, 1000))), "years": kw.years(c)}
        finally:
            c.close()

    @app.get("/api/people/groups")
    def people_groups():
        from .faces import all_groups

        c = conn()
        try:
            return all_groups(c)
        finally:
            c.close()

    @app.post("/api/people/groups")
    def assign_groups(body: dict = Body(...)):
        from .faces import set_groups

        c = conn()
        try:
            ids = [int(i) for i in body.get("ids") or []]
            set_groups(c, ids, add=body.get("add"), remove=body.get("remove"), replace=body.get("replace"))
            return {"ok": True}
        finally:
            c.close()

    ai_cache: dict = {"at": 0.0, "value": None}

    def cached_ai_status(force: bool = False) -> dict:
        import time

        from .analyzer import ai_status

        now = time.monotonic()
        if force or ai_cache["value"] is None or now - ai_cache["at"] > 15:
            ai_cache["value"] = ai_status(client_factory(), cfg)
            ai_cache["at"] = now
        return ai_cache["value"]

    @app.get("/api/ai/status")
    def ai_state():
        return cached_ai_status(force=True)

    @app.post("/api/ai/test")
    def ai_test(body: dict = Body(default={})):
        """用一張照片實際跑一次分析，回傳花費時間、結果或完整錯誤（不寫入圖庫）。"""
        import time

        from .analyzer import build_prompt, normalize_result
        from .media import analysis_images

        c = conn()
        try:
            image_id = body.get("id")
            if image_id:
                image = db.get_image(c, int(image_id))
            else:
                image = c.execute(
                    "SELECT * FROM images WHERE status = 'ok' AND media_type = 'photo' ORDER BY sort_at DESC LIMIT 1"
                ).fetchone()
            if image is None:
                raise HTTPException(404, "圖庫裡還沒有照片")
            model = str(body.get("model") or cfg.vision_model)
            out = {"id": image["id"], "name": image["rel_path"].rsplit("/", 1)[-1], "model": model, "ok": False}
            t0 = time.monotonic()
            try:
                path = db.absolute_path(c, image)
                images = analysis_images(path, image["media_type"], bool(image["is_raw"]), cfg.analyze_max_side,
                                         image["duration"], image["orientation"])
                out["prepare_seconds"] = round(time.monotonic() - t0, 1)
                t1 = time.monotonic()
                raw = client_factory().describe(model, build_prompt(cfg, image, len(images)), images)
                out["seconds"] = round(time.monotonic() - t1, 1)
                out["result"] = normalize_result(raw)
                out["ok"] = bool(out["result"]["description"] or out["result"]["tags"])
                if not out["ok"]:
                    out["error"] = "模型回傳空白結果"
            except Exception as exc:  # noqa: BLE001  診斷用：把任何錯誤原封不動回報
                out["seconds"] = round(time.monotonic() - t0, 1)
                out["error"] = f"{type(exc).__name__}：{exc}"
            return out
        finally:
            c.close()

    @app.post("/api/ollama/start")
    def ollama_start(body: dict = Body(default={})):
        """設定引導用：打開已安裝的 Ollama（Mac 上就是開啟 Ollama App）。"""
        from .analyzer import ollama_installed

        info = ollama_installed()
        if not info["installed"]:
            raise HTTPException(400, "還沒有安裝 Ollama")
        import subprocess

        try:
            if sys.platform == "darwin" and info.get("app"):
                subprocess.Popen(["open", "-a", info["app"]])
            else:
                subprocess.Popen([info["cli"], "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 start_new_session=True)
        except OSError as exc:
            raise HTTPException(500, f"無法啟動 Ollama：{exc}") from exc
        ai_cache["at"] = 0.0
        return {"ok": True}

    @app.post("/api/ollama/test")
    def ollama_test(body: dict = Body(...)):
        url = str(body.get("url") or cfg.ollama_url).strip().rstrip("/")
        try:
            models = OllamaClient(url, 8).installed()
            return {"ok": True, "count": len(models)}
        except OllamaUnavailable as exc:
            return {"ok": False, "error": str(exc)}

    # ---- 人物（人臉辨識） ----
    @app.get("/api/people")
    @memo(600, warm=True)
    def people(all: int = 0):
        from .faces import list_persons

        c = conn()
        try:
            return list_persons(c, include_hidden=bool(all))
        finally:
            c.close()

    @app.get("/api/people/{person_id:int}")
    def person(person_id: int):
        from .faces import list_persons

        c = conn()
        try:
            info = next((p for p in list_persons(c, include_hidden=True) if p["id"] == person_id), None)
            if info is None:
                raise HTTPException(404, "找不到這個人物")
            rows = c.execute(
                "SELECT DISTINCT i.* FROM images i JOIN faces f ON f.image_id = i.id "
                "WHERE f.person_id = ? AND i.status = 'ok' ORDER BY i.sort_at DESC, i.id DESC",
                (person_id,),
            ).fetchall()
            return {**info, "assets": [summarize(r) for r in rows]}
        finally:
            c.close()

    @app.get("/api/people/{person_id:int}/faces")
    def person_faces(person_id: int, limit: int = 600):
        """選封面用：這個人物的每一張臉（清楚的排前面）。"""
        c = conn()
        try:
            rows = c.execute(
                "SELECT f.id, f.image_id, f.score, i.sort_at FROM faces f JOIN images i ON i.id = f.image_id "
                "WHERE f.person_id = ? AND i.status = 'ok' ORDER BY f.score DESC, i.sort_at DESC LIMIT ?",
                (person_id, max(1, min(limit, 3000))),
            ).fetchall()
            return [{"id": r["id"], "image_id": r["image_id"], "score": r["score"], "at": r["sort_at"]} for r in rows]
        finally:
            c.close()

    @app.post("/api/people/{person_id:int}")
    def edit_person(person_id: int, body: dict = Body(...)):
        from .faces import rename_person

        c = conn()
        try:
            if c.execute("SELECT 1 FROM persons WHERE id = ?", (person_id,)).fetchone() is None:
                raise HTTPException(404, "找不到這個人物")
            if "name" in body:
                rename_person(c, person_id, str(body["name"] or ""))
            if "hidden" in body:
                c.execute("UPDATE persons SET hidden = ? WHERE id = ?", (1 if body["hidden"] else 0, person_id))
            if isinstance(body.get("groups"), list):
                from .faces import set_groups

                set_groups(c, [person_id], replace=[str(g) for g in body["groups"]])
            if body.get("cover_face_id"):
                face = c.execute("SELECT 1 FROM faces WHERE id = ? AND person_id = ?", (int(body["cover_face_id"]), person_id)).fetchone()
                if face is None:
                    raise HTTPException(400, "這張臉不屬於這個人物")
                c.execute("UPDATE persons SET cover_face_id = ? WHERE id = ?", (int(body["cover_face_id"]), person_id))
            c.commit()
            return {"ok": True}
        finally:
            c.close()

    # 合併可以復原：記下合併前的樣子，給前端一個代碼（只保留最近 30 次）
    import secrets
    from collections import OrderedDict

    undo_store: "OrderedDict[str, tuple[str, dict]]" = OrderedDict()

    def keep_undo(kind: str, snap: dict) -> str:
        token = secrets.token_urlsafe(9)
        undo_store[token] = (kind, snap)
        while len(undo_store) > 30:
            undo_store.popitem(last=False)
        return token

    def take_undo(kind: str, token: str) -> dict:
        item = undo_store.pop(str(token or ""), None)
        if item is None or item[0] != kind:
            raise HTTPException(410, "已經無法復原（可能已經復原過，或程式重新啟動過）")
        return item[1]

    @app.post("/api/people/merge")
    def merge_people(body: dict = Body(...)):
        from .faces import merge_persons, merge_snapshot

        target, sources = int(body["target"]), [int(x) for x in body.get("sources") or [] if int(x) != int(body["target"])]
        c = conn()
        try:
            snap = merge_snapshot(c, target, sources)
            merge_persons(c, target, sources)
            return {"ok": True, "undo": keep_undo("people", snap)}
        finally:
            c.close()

    @app.post("/api/people/unmerge")
    def unmerge_people(body: dict = Body(...)):
        from .faces import unmerge_persons

        snap = take_undo("people", body.get("undo"))
        c = conn()
        try:
            return {"restored": unmerge_persons(c, snap)}
        finally:
            c.close()

    @app.post("/api/people/{person_id:int}/move")
    def move_person_images(person_id: int, body: dict = Body(...)):
        """選取的照片移到另一個人物（to），或拆成新人物（name，可以是空字串＝未命名）。可以復原。"""
        from .faces import move_images

        c = conn()
        try:
            to = body.get("to")
            name = body.get("name")
            try:
                res = move_images(c, person_id, [int(i) for i in body.get("ids") or []][:MAX_IDS],
                                  to_person=int(to) if to else None, new_name=str(name) if name is not None else None)
            except ValueError as exc:
                raise HTTPException(400, str(exc))
            return {"person_id": res["person_id"], "moved": res["moved"],
                    "undo": keep_undo("move", res["snapshot"]) if res["snapshot"] else None}
        finally:
            c.close()

    @app.post("/api/people/move/undo")
    def undo_person_move(body: dict = Body(...)):
        from .faces import undo_move

        snap = take_undo("move", body.get("undo"))
        c = conn()
        try:
            undo_move(c, snap)
            return {"ok": True}
        finally:
            c.close()

    @app.post("/api/people/{person_id:int}/remove")
    def remove_from_person(person_id: int, body: dict = Body(...)):
        from .faces import remove_images_from_person

        c = conn()
        try:
            return {"removed": remove_images_from_person(c, person_id, [int(i) for i in body.get("ids") or []])}
        finally:
            c.close()

    @app.get("/api/faces/{face_id:int}/thumb")
    def face_thumb(face_id: int):
        from .faces import face_thumb_path

        target = face_thumb_path(cfg, face_id)
        if not target.exists():
            raise HTTPException(404, "找不到臉部縮圖")
        return FileResponse(target, media_type="image/webp", headers={"Cache-Control": "private, max-age=31536000, immutable"})

    @app.post("/api/faces/{face_id:int}")
    def edit_face(face_id: int, body: dict = Body(...)):
        from .faces import assign_face

        c = conn()
        try:
            pid = body.get("person_id")
            person_id = assign_face(c, face_id, int(pid) if pid else None, body.get("name") or None)
            return {"person_id": person_id}
        finally:
            c.close()

    @app.get("/api/clip/models")
    def clip_models():
        from .clip import CLIP_MODELS, model_installed

        items = [
            {"name": k, **v, "installed": model_installed(cfg, k), "active": k == cfg.clip_model}
            for k, v in CLIP_MODELS.items()
        ]
        items.append({
            "name": "custom", "repo": cfg.clip_custom_repo, "label": "自訂模型（Hugging Face）",
            "multilingual": None, "note": cfg.clip_custom_repo or "在下方輸入 Immich 格式的儲存庫名稱",
            "installed": model_installed(cfg, "custom"), "active": cfg.clip_model == "custom", "custom": True,
        })
        return items

    @app.post("/api/clip/models/delete")
    def delete_clip_model(body: dict = Body(...)):
        from .clip import CLIP_MODELS, delete_model

        if body.get("name") not in CLIP_MODELS and body.get("name") != "custom":
            raise HTTPException(400, "未知的模型")
        delete_model(cfg, body["name"])
        return {"ok": True}

    @app.get("/api/faces/models")
    def face_models():
        from .faces import FACE_MODELS, model_info, model_installed

        items = [
            {"name": k, **v, "installed": model_installed(cfg, k), "active": k == cfg.face_model}
            for k, v in FACE_MODELS.items()
        ]
        custom = model_info(cfg, "custom") or {"label": "自訂模型", "note": "在下方輸入 InsightFace 格式 zip 的網址與檔名"}
        items.append({"name": "custom", **custom, "installed": model_installed(cfg, "custom"),
                      "active": cfg.face_model == "custom", "custom": True})
        return items

    @app.post("/api/faces/models/delete")
    def delete_face_model(body: dict = Body(...)):
        from .faces import FACE_MODELS, delete_model

        if body.get("name") not in FACE_MODELS and body.get("name") != "custom":
            raise HTTPException(400, "未知的人臉模型")
        delete_model(cfg, body["name"])
        return {"ok": True}

    @app.post("/api/faces/clear")
    def clear_faces(body: dict = Body(default={})):
        from .faces import clear_all

        c = conn()
        try:
            return {"removed": clear_all(c, cfg)}
        finally:
            c.close()

    # ---- 搜尋與探索 ----
    @app.post("/api/analysis/confirm")
    def analysis_confirm(body: dict = Body(default={})):
        """「每次先問我」的回答：start=true 開始分析，false 稍後再說。"""
        jobs().answer_confirm(bool(body.get("start")))
        return jobs().snapshot()

    @app.get("/api/analysis/schedule")
    def analysis_schedule_status():
        """排程說明與現在能不能分析（設定頁顯示用）。"""
        from .schedule import analysis_allowed, battery_percent, describe, effective, idle_minutes, on_ac_power

        s = effective(cfg)
        ok, reason = analysis_allowed(cfg)
        idle = idle_minutes()
        return {**s, "summary": describe(s), "ok": ok, "reason": reason, "on_ac": on_ac_power(),
                "battery_now": battery_percent(), "idle_now": round(idle, 1) if idle is not None else None}

    @app.get("/api/analysis/errors")
    def analysis_errors():
        """分析失敗的原因統計（依錯誤訊息分組）。"""
        c = conn()
        try:
            rows = c.execute(
                "SELECT substr(error, 1, 160) AS reason, COUNT(*) AS count FROM images "
                "WHERE status = 'ok' AND analyzed_at IS NULL AND error IS NOT NULL GROUP BY reason ORDER BY count DESC LIMIT 8"
            ).fetchall()
            return [{"reason": r["reason"], "count": r["count"]} for r in rows]
        finally:
            c.close()

    @app.get("/api/search/suggest")
    def search_suggest(q: str = ""):
        from .search import suggest

        c = conn()
        try:
            return suggest(c, q[:60])
        finally:
            c.close()

    def resolve_scope(c, scope: str):
        """搜尋範圍字串 → (SQL 條件, 參數, 顯示名稱, 附加查詢)。看不懂的範圍就當作全部圖庫。"""
        kind, _, rest = (scope or "").partition(":")
        try:
            if kind == "album":
                aid = int(rest)
                row = c.execute("SELECT name FROM albums WHERE id = ?", (aid,)).fetchone()
                if row:
                    return ("i.id IN (SELECT image_id FROM album_items WHERE album_id = ?)", [aid], f"相簿「{row['name']}」", "")
            elif kind == "smart":
                row = c.execute("SELECT name, query FROM smart_albums WHERE id = ?", (int(rest),)).fetchone()
                if row:
                    return ("1", [], f"智慧相簿「{row['name']}」", row["query"] or "")
            elif kind == "folder":
                rid, _, path = rest.partition(":")
                root = c.execute("SELECT name FROM roots WHERE id = ?", (int(rid),)).fetchone()
                if root:
                    path = path.strip("/")
                    if not path:
                        return ("i.root_id = ?", [int(rid)], f"資料夾「{root['name']}」", "")
                    esc = path.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                    return ("i.root_id = ? AND i.rel_path LIKE ? ESCAPE '\\'", [int(rid), esc + "/%"],
                            f"資料夾「{path.rsplit('/', 1)[-1]}」", "")
            elif kind == "person":
                pid = int(rest)
                row = c.execute("SELECT name FROM persons WHERE id = ?", (pid,)).fetchone()
                if row:
                    return ("i.id IN (SELECT image_id FROM faces WHERE person_id = ?)", [pid], f"「{row['name'] or '未命名人物'}」的照片", "")
            elif kind == "favorites":
                return ("i.favorite = 1", [], "我的最愛", "")
            elif kind == "videos":
                return ("i.media_type = 'video'", [], "影片", "")
            elif kind == "tool":
                from .tools import screens_and_documents

                if rest == "screens":
                    ids, label = [r["id"] for r, _ in screens_and_documents(c, png_rule=bool(cfg.screen_png_rule))], "截圖與文件"
                else:
                    ids, label = None, ""
                if ids is not None:
                    # 用 json_each 帶入一大串 id，不受 SQL 參數數量上限影響
                    return ("i.id IN (SELECT value FROM json_each(?))", [json.dumps(ids)], label, "")
        except (ValueError, sqlite3.Error):
            pass
        return None

    @app.get("/api/search")
    @memo(20)
    def do_search(q: str = "", limit: int = 200, offset: int = 0, semantic: int = 0, smart: int = 1, scope: str = ""):
        from .analyzer import rewrite_query
        from .search import parse_query

        limit = max(1, min(limit, 1000))
        c = conn()
        warnings = []
        try:
            sc = resolve_scope(c, scope) if scope else None
            scope_label = ""
            if sc:
                scope_sql, scope_params, scope_label, extra_q = sc
                if extra_q:
                    q = f"{extra_q} {q}".strip()
                sc = (scope_sql, scope_params)
            terms = parse_query(q).terms
            groups, english = None, ""
            if smart and cfg.query_rewrite and terms:
                try:
                    rw = rewrite_query(client_factory(), cfg.search_model, terms)
                    groups, english = rw["groups"], rw["english"]
                except Exception as exc:  # noqa: BLE001  改寫失敗就只用原本的關鍵字，不打擾使用者
                    print(f"查詢改寫失敗，改用原始關鍵字：{exc}", flush=True)
            clip_rank = None
            if smart and cfg.clip_enabled and terms:
                from . import clip as clipmod

                if clipmod.model_installed(cfg, cfg.clip_model):
                    multi = clipmod.is_multilingual(cfg.clip_model, cfg)
                    texts = [q if multi else (english or q)]
                    if english and multi:
                        texts.append(english)

                    def clip_rank(_texts, allowed, _c=c, _t=texts):
                        return clipmod.rank(_c, cfg, _t, allowed)
            use_sem = bool(semantic and cfg.embed_model)
            try:
                result = search(c, q, limit=limit, offset=max(0, offset), semantic=use_sem,
                                embedder=client_factory() if use_sem else None, embed_model=cfg.embed_model,
                                groups=groups, clip_rank=clip_rank, scope=sc)
            except (OllamaUnavailable, MediaError) as exc:
                warnings.append(str(exc))
                result = search(c, q, limit=limit, offset=max(0, offset), groups=groups, scope=sc)
            if warnings:
                result["warning"] = "；".join(warnings)
            result["english"] = english
            result["scope"] = {"key": scope, "label": scope_label} if scope_label else None
            return result
        finally:
            c.close()

    @app.post("/api/assets/{image_id:int}/translate")
    def translate(image_id: int, body: dict = Body(default={})):
        from .analyzer import translate_analysis

        c = conn()
        try:
            image = get_image_or_404(c, image_id)
        finally:
            c.close()
        if not image["description"]:
            raise HTTPException(400, "這張還沒有 AI 描述")
        try:
            return translate_analysis(client_factory(), cfg.search_model, image["description"],
                                      db.json_list(image["tags"]), body.get("language") or cfg.language)
        except OllamaUnavailable as exc:
            raise HTTPException(503, str(exc))

    @app.get("/api/explore")
    @memo(600, warm=True)
    def explore():
        c = conn()
        try:
            tags = top_tags(c, 40)
            covers = tag_covers(c, [t for t, _ in tags])

            def grouped(column: str, limit: int = 20):
                rows = c.execute(
                    f"SELECT {column} AS value, COUNT(*) AS count, id FROM images WHERE status = 'ok' AND thumb_ok = 1 "
                    f"AND {column} IS NOT NULL AND {column} != '' GROUP BY {column} ORDER BY count DESC LIMIT ?",
                    (limit,),
                ).fetchall()
                return [{"value": r["value"], "count": r["count"], "cover": r["id"]} for r in rows]

            years = c.execute(
                "SELECT substr(sort_at, 1, 4) AS value, COUNT(*) AS count, MAX(id) AS id FROM images "
                "WHERE status = 'ok' AND sort_at IS NOT NULL GROUP BY value ORDER BY value DESC"
            ).fetchall()
            from .faces import list_persons

            places = c.execute(
                "SELECT place AS value, COUNT(*) AS count, MAX(id) AS id FROM images "
                "WHERE status = 'ok' AND thumb_ok = 1 AND place IS NOT NULL AND place != '' "
                "GROUP BY place ORDER BY count DESC LIMIT 30"
            ).fetchall()
            return {
                "places": [{"value": r["value"], "count": r["count"], "cover": r["id"]} for r in places],
                "people": list_persons(c)[:24],
                "tags": [{"value": t, "count": n, "cover": covers.get(t)} for t, n in tags if covers.get(t)],
                "scenes": grouped("scene", 16),
                "years": [{"value": r["value"], "count": r["count"], "cover": r["id"]} for r in years],
            }
        finally:
            c.close()

    # ---- 資料夾 ----
    @app.get("/api/drives")
    def drives_api(request: Request, detail: bool = False):
        """側邊欄：所有硬碟與各類型的統計。只讀資料庫，硬碟沒接上也回傳。
        detail＝硬碟總覽頁：加上每顆硬碟各類型佔多少，以及已接上但還沒加入目錄的硬碟（只限本機）。"""
        from .catalog import drives_overview, kinds_overview, labels_overview, new_volumes

        c = conn()
        try:
            snap = jobs().snapshot()
            current = snap.get("current") or {}
            out = {"drives": drives_overview(c, current.get("scan"), detail=detail), "kinds": kinds_overview(c),
                   "labels": labels_overview(c),
                   "pending": c.execute("SELECT COUNT(*) FROM delete_marks").fetchone()[0]}
            if detail:
                out["new"] = new_volumes(c) if request.state.local else []
                out["scan_job"] = current.get("id") if current.get("kind") in ("scan", "index") else None
                out["queued"] = [j["id"] for j in snap.get("queued", []) if j["kind"] in ("scan", "index")]
            return out
        finally:
            c.close()

    @app.get("/api/items/position")
    def items_position(root: int, path: str = "", name: str = "", sort: str = "name", desc: bool = False, group: str | None = None):
        """某個名稱的項目在這個資料夾清單上是第幾個（打開資料夾並選好它用）。"""
        from .catalog import item_position

        c = conn()
        try:
            return {"index": item_position(c, root, path, name, sort, desc, group)}
        finally:
            c.close()

    @app.get("/api/items")
    def items_api(root: int | None = None, path: str = "", kind: str | None = None, label: str | None = None,
                  offset: int = 0, limit: int = 200, sort: str = "name", desc: bool = False, group: str | None = None):
        """列表與圖像檢視：只回傳要求的那一段與總數。只讀資料庫，硬碟沒接上也能看。"""
        from .catalog import items_page

        if root is None and kind is None and label is None:
            raise HTTPException(400, "請指定要看的資料夾、類型或標籤")
        c = conn()
        try:
            page = items_page(c, root_id=root, path=path, kind=kind, label=label, offset=offset, limit=limit, sort=sort, desc=desc, group=group)
            if page is None:
                raise HTTPException(404, "找不到這個位置")
            return page
        finally:
            c.close()

    @app.post("/api/items/open")
    def open_item(body: dict = Body(...)):
        """用 Mac 預設的 App 打開檔案，或在 Finder 中顯示（只限本機、硬碟要接著）。只讀取，不修改檔案。"""
        action = "reveal" if body.get("action") == "reveal" else "open"
        c = conn()
        try:
            r = db.get_root(c, int(body["root_id"]))
        finally:
            c.close()
        if r is None:
            raise HTTPException(404, "找不到這個位置")
        try:
            target = fileops.safe_folder(Path(r["path"]), str(body.get("path", "")))
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        if not target.exists():
            raise HTTPException(409, f"請接上「{r['name']}」以開啟這個項目。")
        try:
            fileops.reveal(target, select=action == "reveal")
        except OSError as e:  # 這台電腦沒有可以開啟檔案的程式（例如在沒有桌面的系統上執行）
            raise HTTPException(500, "無法在這台電腦上開啟檔案。") from e
        return {"ok": True}

    # 快速預覽（空白鍵）：只讀取，硬碟要接著。可以直接播放或顯示的類型才送出原檔，文字檔只讀開頭一段
    PREVIEW_MEDIA = {".mp3", ".m4a", ".aac", ".wav", ".flac", ".ogg", ".pdf", ".mp4", ".mov", ".m4v", ".webm",
                     ".jpg", ".jpeg", ".png", ".gif", ".webp"}
    PREVIEW_TEXT = {".txt", ".md", ".csv", ".tsv", ".json", ".log", ".xml", ".html", ".htm", ".css", ".js", ".py", ".srt",
                    ".yml", ".yaml", ".ini", ".conf", ".sh", ".tex"}
    PREVIEW_TEXT_BYTES = 200_000

    def _preview_target(root: int, path: str) -> Path:
        c = conn()
        try:
            r = db.get_root(c, root)
        finally:
            c.close()
        if r is None:
            raise HTTPException(404, "找不到這個位置")
        try:
            target = fileops.safe_folder(Path(r["path"]), path)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        if not target.is_file():
            raise HTTPException(409, f"請接上「{r['name']}」以預覽這個檔案。")
        return target

    @app.get("/api/items/photo")
    def item_photo(root: int, path: str, size: int = 2048):
        """直接從硬碟讀一張照片做成預覽（還沒進照片圖庫、或從佔比圖打開時用）。只讀取，不在硬碟上留下任何東西。
        HEIC、TIFF、RAW（內嵌預覽）也可以；長邊縮到 size。"""
        from .media import PHOTO_EXTENSIONS, RAW_EXTENSIONS, MediaError, encode, load_image

        target = _preview_target(root, path)
        ext = target.suffix.lower()
        if ext not in PHOTO_EXTENSIONS and ext not in RAW_EXTENSIONS:
            raise HTTPException(415, "這不是照片")
        side = max(256, min(int(size), 4096))
        try:
            img = load_image(target, "photo", ext in RAW_EXTENSIONS, side)
            data = encode(img, side, quality=85)
        except MediaError as e:
            raise HTTPException(422, str(e)) from e
        return Response(data, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=300"})

    @app.get("/api/items/raw")
    def item_raw(root: int, path: str):
        target = _preview_target(root, path)
        if target.suffix.lower() not in PREVIEW_MEDIA:
            raise HTTPException(415, "這種檔案無法直接預覽")
        return FileResponse(target, media_type=mimetypes.guess_type(target.name)[0] or "application/octet-stream",
                            headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, max-age=60"})

    @app.get("/api/items/text")
    def item_text(root: int, path: str):
        target = _preview_target(root, path)
        if target.suffix.lower() not in PREVIEW_TEXT:
            raise HTTPException(415, "這種檔案無法直接預覽")
        with open(target, "rb") as f:
            raw = f.read(PREVIEW_TEXT_BYTES + 1)
        truncated = len(raw) > PREVIEW_TEXT_BYTES
        raw = raw[:PREVIEW_TEXT_BYTES]
        # UTF-16 幾乎任何內容都「解得開」，所以開頭有它的標記才用；其餘依序試常見的中文編碼
        bom16 = raw[:2] in (b"\xff\xfe", b"\xfe\xff")
        for enc in (("utf-16",) if bom16 else ()) + ("utf-8-sig", "big5", "gb18030"):
            try:
                text = raw.decode(enc)
                break
            except UnicodeError:
                continue
        else:
            text = raw.decode("utf-8", errors="replace")
        return {"text": text, "truncated": truncated}

    @app.get("/api/spotlight/items")
    def spotlight_items():
        """Mac App 要放進 Spotlight 的項目（硬碟、智慧資料夾）。索引只存在這台 Mac。"""
        from .spotlight import payload

        c = conn()
        try:
            return payload(c, bool(cfg.spotlight))
        finally:
            c.close()

    spotlight_state: dict = {}

    @app.post("/api/spotlight/report")
    def spotlight_report(body: dict = Body(...)):
        """Mac App 回報放進 Spotlight 的結果（設定頁顯示，方便知道狀況）。"""
        probe = body.get("probe")
        spotlight_state.update(ok=bool(body.get("ok")), count=int(body.get("count") or 0),
                               error=str(body.get("error") or "")[:300], at=db.now_iso(),
                               # 自我檢查：Spotlight 自己找不找得到 Re'memor 放進去的項目（None＝沒有檢查）
                               probe=int(probe) if isinstance(probe, (int, float)) else None,
                               probe_error=str(body.get("probe_error") or "")[:300], running=bool(body.get("running")))
        return {"ok": True}

    @app.get("/api/spotlight/changes")
    def spotlight_changes(cursor: str = "", limit: int = 500):
        """Mac App 分批來拿：要放進 Spotlight（或拿掉）的項目，只有新增、改過、不在了的。"""
        from . import spotlight

        c = conn()
        try:
            return spotlight.changes(c, cursor, max(50, min(limit, 2000)), bool(cfg.spotlight), bool(cfg.spotlight_internal))
        except ValueError as e:
            raise HTTPException(400, "cursor 不對") from e
        finally:
            c.close()

    @app.post("/api/spotlight/ack")
    def spotlight_ack(body: dict = Body(...)):
        """Mac App 放好了：記下來，之後只送有變動的。"""
        from . import spotlight

        c = conn()
        try:
            return {"saved": spotlight.ack(c, body.get("done") or [], body.get("deleted") or [])}
        finally:
            c.close()

    @app.post("/api/spotlight/rebuild")
    def spotlight_rebuild(body: dict = Body(default={})):
        """重新建立 Spotlight 裡 Re'memor 的項目（清掉再全部放一次）。"""
        from . import spotlight

        spotlight.request_reset()
        return {"ok": True}

    @app.get("/api/spotlight/status")
    def spotlight_status():
        c = conn()
        try:
            from . import spotlight

            n = c.execute("SELECT COUNT(*) FROM spotlight_sync").fetchone()[0]
            total = spotlight.total(c, bool(cfg.spotlight_internal)) if cfg.spotlight else 0
        finally:
            c.close()
        return {"enabled": bool(cfg.spotlight), "items": n, "total": total, "report": spotlight_state or None}

    @app.get("/api/music")
    def music_info(file: int):
        """音樂的曲名、演出者、專輯（讀文件文字時記下的標籤；硬碟沒接上也看得到）。"""
        from . import music
        from .textindex import body

        c = conn()
        try:
            row = c.execute("SELECT t.status FROM file_text t JOIN files f ON f.id = t.file_id WHERE t.file_id = ? AND t.source = 'music' "
                            "AND t.size = f.size AND t.mtime = f.mtime", (int(file),)).fetchone()
            return {"status": row["status"] if row else "todo", "tags": music.parse(body(c, int(file))) if row else {}}
        finally:
            c.close()

    @app.get("/api/archive")
    def archive_listing(file: int, limit: int = 2000):
        """壓縮檔裡有哪些檔案（掃描後記在目錄裡的清單，硬碟沒接上也看得到；沒有解開壓縮檔）。"""
        from . import archives

        c = conn()
        try:
            row = c.execute("SELECT t.status, t.error, t.body, t.size = f.size AND t.mtime = f.mtime AS fresh FROM files f "
                            "LEFT JOIN file_text t ON t.file_id = f.id WHERE f.id = ?", (int(file),)).fetchone()
        finally:
            c.close()
        if row is None:
            raise HTTPException(404, "找不到這個檔案")
        if row["status"] is None or not row["fresh"]:
            return {"status": "todo", "entries": [], "total": 0}
        if row["status"] != "ok":
            return {"status": row["status"], "message": row["error"] or "", "entries": [], "total": 0}
        import zlib

        text = zlib.decompress(row["body"]).decode("utf-8") if row["body"] else ""
        items = archives.listing(text)
        more = text.rsplit("\n", 1)[-1] if text.endswith("個檔案") else ""
        return {"status": "ok", "entries": items[:max(1, min(limit, 20_000))], "total": len(items), "more": more}

    @app.post("/api/items/label")
    def label_items(body: dict = Body(...)):
        """替檔案與資料夾加上或拿掉顏色標籤。只改目錄資料庫，不寫到硬碟。"""
        from .catalog import set_labels

        files, folders = body.get("files") or [], body.get("folders") or []
        if len(files) + len(folders) > MAX_IDS:
            raise HTTPException(400, f"一次最多 {MAX_IDS} 個項目")
        c = conn()
        try:
            return {"changed": set_labels(c, files, folders, body.get("label"))}
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        finally:
            c.close()

    # ---- 重複項目：內容完全相同的檔案與資料夾（這裡只查詢，不刪除任何東西）----
    @app.get("/api/dupes/summary")
    def dupes_summary():
        from .dupes import compare_plan, duplicate_files, duplicate_folders

        c = conn()
        try:
            folders = duplicate_folders(c, limit=0)
            files = duplicate_files(c, limit=0)
            waiting = duplicate_files(c, limit=0, pending=True)
            return {
                "plan": compare_plan(c),
                "folders": {"total": folders["total"], "confirmed": folders["confirmed"], "releasable": folders["releasable"]},
                "files": {"confirmed": files["total"], "releasable": files["releasable"],
                          "pending": waiting["total"], "pending_releasable": waiting["pending_releasable"]},
            }
        finally:
            c.close()

    @app.get("/api/dupes/folders")
    def dupes_folders(offset: int = 0, limit: int = 100):
        from .dupes import duplicate_folders

        c = conn()
        try:
            return duplicate_folders(c, max(0, offset), max(1, min(200, limit)))
        finally:
            c.close()

    @app.get("/api/dupes/files")
    def dupes_files(offset: int = 0, limit: int = 100, pending: bool = False):
        from .dupes import duplicate_files

        c = conn()
        try:
            return duplicate_files(c, max(0, offset), max(1, min(200, limit)), pending=pending)
        finally:
            c.close()

    # ---- 待刪除：標記只寫資料庫；清理只在使用者按下確認後執行，而且只限這台 Mac ----
    @app.post("/api/dupes/mark")
    def dupes_mark(body: dict = Body(...)):
        from . import pending

        c = conn()
        try:
            return {"marked": pending.mark(c, str(body.get("kind")), body.get("keep") or [], body.get("remove") or [])}
        except pending.MarkError as e:
            raise HTTPException(400, str(e)) from e
        finally:
            c.close()

    @app.post("/api/dupes/unmark")
    def dupes_unmark(body: dict = Body(...)):
        from . import pending

        c = conn()
        try:
            return {"unmarked": pending.unmark(c, body.get("ids") or [])}
        finally:
            c.close()

    @app.get("/api/pending")
    def pending_list():
        from . import pending

        c = conn()
        try:
            return pending.listing(c)
        finally:
            c.close()

    @app.post("/api/pending/trash")
    def pending_trash(body: dict = Body(...)):
        """把標記的項目移到垃圾桶。只有使用者在介面上確認時才會呼叫；逐項再驗證一次，不符的跳過。"""
        from . import pending

        if body.get("confirm") is not True:
            raise HTTPException(400, "需要本人確認")
        c = conn()
        try:
            return pending.clean(c, body.get("ids") or [])
        finally:
            c.close()

    @app.post("/api/pending/export")
    def pending_export(body: dict = Body(...)):
        from . import pending

        c = conn()
        try:
            out = pending.export_list(c, cfg.home, str(body.get("drive") or ""))
        except pending.MarkError as e:
            raise HTTPException(400, str(e)) from e
        finally:
            c.close()
        try:
            fileops.reveal(out, select=True)
        except OSError:
            pass
        return {"path": str(out)}

    # ---- 掃描進度：進行中的工作與存在資料庫裡的紀錄 ----
    @app.get("/api/activity")
    def activity():
        snap = jobs().snapshot()
        return {"active": [j for j in [snap.get("current"), *[a for a in snap.get("active", []) if a.get("id") != (snap.get("current") or {}).get("id")]] if j],
                "queued": snap.get("queued", []), "history": jobs().history()}

    @app.post("/api/activity/resume")
    def activity_resume(body: dict = Body(...)):
        try:
            jobs().resume(int(body.get("id") or 0))
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        return {"ok": True}

    # ---- 搜尋所有硬碟上的檔案（檔名、內容、文字辨識、照片描述）與智慧資料夾 ----
    @app.get("/api/find")
    def find_api(q: str = "", root: int | None = None, path: str = "", kind: str | None = None, year: int | None = None,
                 size: str | None = None, drive: int | None = None, offset: int = 0, limit: int = 50):
        from .find import find

        c = conn()
        try:
            meaning = None
            if cfg.doc_semantic:
                from . import semantic

                client, model = client_factory(), semantic.model_of(cfg)
                meaning = lambda text: semantic.nearest(c, client, model, text)  # noqa: E731
            return find(c, q, root=root, path=path, kind=kind or None, year=year, size=size or None, drive=drive,
                        offset=max(0, offset), limit=max(1, min(200, limit)), meaning=meaning)
        finally:
            c.close()

    @app.get("/api/semantic/status")
    def semantic_status():
        """用意思找文件：開了沒、模型下載了沒、還有幾份文件要建立索引。"""
        from . import semantic

        model = semantic.model_of(cfg)
        c = conn()
        try:
            p = semantic.plan(c, model)
        finally:
            c.close()
        client = client_factory()
        try:
            names = client.list_models()
            ollama_ok = True
        except Exception:  # noqa: BLE001
            names, ollama_ok = [], False
        info = next((m for m in annotated(machine_info()["ram_gb"], names) if same_model(m["name"], model)), None)
        return {"enabled": bool(cfg.doc_semantic), "model": model, "ollama": ollama_ok,
                "model_ready": any(same_model(model, n) for n in names), "size_gb": info["size_gb"] if info else None, **p}

    @app.post("/api/semantic/reset")
    def semantic_reset(body: dict = Body(default={})):
        from . import semantic

        c = conn()
        try:
            return {"removed": semantic.reset(c)}
        finally:
            c.close()

    @app.get("/api/text/status")
    def text_status():
        """還有多少文件要讀、多少要辨識（搜尋頁與設定頁顯示）。"""
        from .ocr import ocr_plan
        from .textindex import extract_plan

        c = conn()
        try:
            from .textindex import index_bytes

            return {"extract": extract_plan(c), "ocr": ocr_plan(c, cfg.ocr_scope), "bytes": index_bytes(c),
                    "languages": cfg.ocr_languages}
        finally:
            c.close()

    @app.post("/api/text/reset")
    def text_reset(body: dict = Body(default={})):
        """清除 Re'memor 自己存的文件文字與索引（不碰硬碟上的檔案），之後按「讀取文件文字」重新讀。"""
        from .textindex import reset

        if not body.get("confirm"):
            raise HTTPException(400, "需要確認")
        if jobs().snapshot()["active"] and any(j["kind"] in ("extract", "ocr") for j in jobs().snapshot()["active"]):
            raise HTTPException(409, "正在讀取文件文字，請先停止再重新讀取")
        c = conn()
        try:
            return {"cleared": reset(c, ocr_only=bool(body.get("ocr_only")))}
        finally:
            c.close()

    @app.get("/api/smart-folders")
    def smart_list():
        from .find import smart_folders

        c = conn()
        try:
            return smart_folders(c)
        finally:
            c.close()

    @app.post("/api/smart-folders")
    def smart_save(body: dict = Body(...)):
        from .find import save_smart_folder

        c = conn()
        try:
            return {"id": save_smart_folder(c, str(body.get("name") or ""), body.get("query") or {})}
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        finally:
            c.close()

    @app.delete("/api/smart-folders/{folder_id:int}")
    def smart_delete(folder_id: int):
        from .find import delete_smart_folder

        c = conn()
        try:
            delete_smart_folder(c, folder_id)
            return {"ok": True}
        finally:
            c.close()

    @app.get("/api/usage")
    def usage_api(root: int, path: str = ""):
        """佔比圖（方塊圖、環狀圖）：目前層與下一層的大小。只讀資料庫。"""
        from .catalog import usage_map

        c = conn()
        try:
            data = usage_map(c, root, path)
            if data is None:
                raise HTTPException(404, "找不到這個資料夾")
            return data
        finally:
            c.close()

    # ---- 檔案管理助理（在這台電腦上執行的語言模型；只查詢、只建議，不改任何檔案） ----
    @app.get("/api/assistant/status")
    def assistant_status():
        from .assistant import status

        return status(cfg, client_factory())

    @app.post("/api/assistant/test")
    def assistant_test(body: dict = Body(default={})):
        """試一下現在的設定：請模型回一句話（不送任何檔案資料）。"""
        from .assistant import make_llm

        try:
            reply = make_llm(cfg, client_factory()).complete("請只回答兩個字：可以", max_tokens=20)
            return {"ok": True, "reply": reply[:80]}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)[:300]}

    @app.post("/api/assistant/models")
    def assistant_models(body: dict = Body(default={})):
        """向服務取得可以用的模型清單（使用者按下按鈕才連線，只送金鑰，不送任何檔案資料）。"""
        from .llm import PROVIDERS, list_models

        provider = str(body.get("provider") or "")
        if provider not in PROVIDERS or provider == "ollama":
            raise HTTPException(400, "不認得的服務")
        try:
            return {"ok": True, "models": list_models(cfg, provider)[:300]}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)[:300], "models": []}

    @app.get("/api/assistant/suggestions")
    def assistant_suggestions():
        from .assistant import suggestions

        c = conn()
        try:
            return suggestions(c, cfg.ocr_scope)
        finally:
            c.close()

    @app.post("/api/assistant/ask")
    def assistant_ask(body: dict = Body(...)):
        """回答一個問題：一行一個 JSON 事件（查詢步驟、提案、逐字的回答、來源）。"""
        from fastapi.responses import StreamingResponse

        from .assistant import ask, make_llm

        from . import chats

        question = str(body.get("question") or "").strip()[:2000]
        if not question:
            raise HTTPException(400, "請輸入問題")
        history = [m for m in (body.get("history") or []) if isinstance(m, dict)][-8:]

        def events():
            c = conn()
            try:
                # 對話紀錄：沒有指定對話（或已經刪掉）就開一段新的；問題先存，回答在結束時一起存
                chat_id = body.get("chat_id")
                if not (isinstance(chat_id, int) and chats.exists(c, chat_id)):
                    chat_id = chats.create(c, question)
                chats.add_message(c, chat_id, "user", question)
                yield json.dumps({"type": "chat", "id": chat_id}, ensure_ascii=False) + "\n"
                text, steps, sources, acts, error = [], [], [], [], ""
                try:
                    for ev in ask(c, make_llm(cfg, client_factory()), question, history,
                                  str(body.get("context") or "")[:300], str(body.get("lang") or "zh-Hant"),
                                  level=cfg.assistant_permission, cloud_content=bool(cfg.assistant_cloud_content)):
                        kind = ev.get("type")
                        if kind == "token":
                            text.append(ev["text"])
                        elif kind == "step":
                            steps.append(ev)
                        elif kind == "action":
                            acts.append(ev["action"]["id"])
                        elif kind == "done":
                            sources = ev.get("sources") or []
                        elif kind == "error":
                            error = ev.get("message") or ""
                        yield json.dumps(ev, ensure_ascii=False) + "\n"
                finally:
                    # 使用者中途按停止也存下已經回答的部分
                    chats.add_message(c, chat_id, "assistant", "".join(text), steps, sources, acts, error)
            finally:
                c.close()

        return StreamingResponse(events(), media_type="application/x-ndjson")

    # ---- 助理的對話紀錄（只存在這台電腦）----
    @app.get("/api/assistant/chats")
    def assistant_chats():
        from . import chats

        c = conn()
        try:
            return chats.listing(c)
        finally:
            c.close()

    @app.get("/api/assistant/chats/{chat_id:int}")
    def assistant_chat(chat_id: int):
        from . import chats

        c = conn()
        try:
            data = chats.load(c, chat_id)
        finally:
            c.close()
        if data is None:
            raise HTTPException(404, "找不到這段對話")
        return data

    @app.post("/api/assistant/chats/delete")
    def assistant_chats_delete(body: dict = Body(...)):
        """刪除對話紀錄（可以一次好幾段）。只刪 Re'memor 存的對話，不動任何檔案、也不影響已經執行的動作。"""
        from . import chats

        c = conn()
        try:
            return {"deleted": chats.delete(c, body.get("ids") or [])}
        finally:
            c.close()

    @app.post("/api/assistant/chats/rename")
    def assistant_chats_rename(body: dict = Body(...)):
        from . import chats

        c = conn()
        try:
            chats.rename(c, int(body.get("id") or 0), str(body.get("title") or ""))
            return {"ok": True}
        finally:
            c.close()

    # ---- 助理提出的動作：本人確認後才執行，都可以復原 ----
    @app.get("/api/assistant/actions")
    def assistant_actions(limit: int = 30):
        from .actions import history

        c = conn()
        try:
            return history(c, limit)
        finally:
            c.close()

    @app.get("/api/assistant/actions/{action_id:int}")
    def assistant_action(action_id: int):
        from .actions import ActionError, get

        c = conn()
        try:
            return get(c, action_id)
        except ActionError as e:
            raise HTTPException(404, str(e)) from e
        finally:
            c.close()

    def _action_call(body: dict, fn):
        from .actions import ActionError

        if body.get("confirm") is not True:
            raise HTTPException(400, "需要本人確認")
        c = conn()
        try:
            return fn(c, int(body.get("id")))
        except (TypeError, ValueError) as e:
            if isinstance(e, ActionError):
                raise HTTPException(400, str(e)) from e
            raise HTTPException(400, "動作編號不對") from e
        finally:
            c.close()

    @app.post("/api/assistant/actions/run")
    def assistant_action_run(body: dict = Body(...)):
        """執行助理的提案。只有使用者在畫面上按下確認時才會呼叫（confirm=true），而且只限這台 Mac。"""
        from .actions import run

        only = body.get("only")
        only = [int(i) for i in only] if isinstance(only, list) else None
        return _action_call(body, lambda c, i: run(c, i, cfg.assistant_permission, only))

    @app.post("/api/assistant/actions/undo")
    def assistant_action_undo(body: dict = Body(...)):
        from .actions import undo

        return _action_call(body, undo)

    @app.post("/api/assistant/actions/dismiss")
    def assistant_action_dismiss(body: dict = Body(...)):
        from .actions import dismiss

        return _action_call({**body, "confirm": True}, dismiss)

    @app.get("/api/usage/tree")
    def usage_tree_api(root: int, path: str = "", px: int = 1_000_000, max_nodes: int = 30_000, depth: int = 64):
        """佔比圖與連線圖：一路拆到每個資料夾與檔案（小到畫不出來的合併成「其他」）。只讀資料庫。"""
        from .usage import usage_tree

        c = conn()
        try:
            data = usage_tree(c, root, path, px=max(10_000, min(px, 20_000_000)), max_nodes=max(50, min(max_nodes, 60_000)),
                              depth=max(1, min(depth, 64)))
            if data is None:
                raise HTTPException(404, "找不到這個資料夾")
            return data
        finally:
            c.close()

    @app.get("/api/usage/rest")
    def usage_rest_api(folder: int, below: int, offset: int = 0, limit: int = 200):
        """「其他」裡面有哪些項目（由大到小）。"""
        from .usage import usage_rest

        c = conn()
        try:
            return usage_rest(c, folder, below, max(0, offset), max(1, min(500, limit)))
        finally:
            c.close()

    @app.get("/api/location/kinds")
    def location_kinds_api(root: int, path: str = ""):
        """資訊欄：這個資料夾（含子資料夾）裡各類型佔多少。"""
        from .catalog import subtree_kinds

        c = conn()
        try:
            kinds = subtree_kinds(c, root, path)
            if kinds is None:
                raise HTTPException(404, "找不到這個資料夾")
            return {"kinds": kinds}
        finally:
            c.close()

    @app.get("/api/items/groups")
    def items_groups_api(group: str, root: int | None = None, path: str = "", kind: str | None = None, label: str | None = None):
        """分組的標題與每組的數量（列表與圖像檢視用來畫出每一段的標題）。"""
        from .catalog import item_groups

        c = conn()
        try:
            data = item_groups(c, group, root_id=root, path=path, kind=kind, label=label)
            if data is None:
                raise HTTPException(404, "找不到這個位置或分組方式")
            return data
        finally:
            c.close()

    @app.get("/api/location")
    def location_api(root: int, path: str = ""):
        from .catalog import location_info

        c = conn()
        try:
            info = location_info(c, root, path)
            if info is None:
                raise HTTPException(404, "找不到這個資料夾")
            return info
        finally:
            c.close()

    @app.get("/api/folders")
    @memo(20)
    def folders(root: int | None = None, path: str = ""):
        c = conn()
        try:
            if root is None:
                return {"roots": [_root_dict(c, r) for r in db.list_roots(c)]}
            r = db.get_root(c, root)
            if r is None:
                raise HTTPException(404, "找不到資料夾")
            path = path.strip("/")
            prefix = f"{path}/" if path else ""
            esc = prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            rows = c.execute(
                "SELECT folder, COUNT(*) AS count, MAX(sort_at) AS latest, id FROM images "
                "WHERE root_id = ? AND status = 'ok' AND folder LIKE ? ESCAPE '\\' GROUP BY folder",
                (r["id"], esc + "%"),
            ).fetchall()
            children: dict[str, dict] = {}
            for row in rows:
                if row["folder"] == path:
                    continue
                name = row["folder"][len(prefix):].split("/")[0]
                child = children.setdefault(name, {"name": name, "path": prefix + name, "count": 0, "cover": None, "latest": "", "cover_custom": False})
                child["count"] += row["count"]
                if (row["latest"] or "") >= child["latest"]:
                    child["latest"], child["cover"] = row["latest"] or "", row["id"]
            # 硬碟目錄：所有子資料夾（含沒有照片的、空的）與總大小；硬碟拔掉時也看得到
            from .catalog import folder_listing

            listing = folder_listing(c, r["id"], path)
            if listing:
                for sf in listing["subfolders"]:
                    if sf["status"] != "ok":
                        continue
                    child = children.setdefault(sf["name"], {"name": sf["name"], "path": sf["path"], "count": 0, "cover": None,
                                                             "latest": "", "cover_custom": False})
                    child.update(files=sf["files"], bytes=sf["bytes"], subfolders=sf["subfolders"])
            # 使用者自訂的封面優先
            for child in children.values():
                custom = folder_cover(c, r["id"], child["path"])
                if custom:
                    child["cover"], child["cover_custom"] = custom, True
                child["favorite"], child["position"] = folder_pref(c, r["id"], child["path"])
            here_custom = folder_cover(c, r["id"], path) if path else None
            assets = c.execute(
                f"SELECT i.*, {STACK_COUNT_SQL} FROM images i WHERE i.root_id = ? AND i.folder = ? AND i.status = 'ok' "
                "AND i.stack_top = 1 ORDER BY i.sort_at DESC, i.id DESC",
                (r["id"], path),
            ).fetchall()
            crumbs, acc = [], []
            for part in [p for p in path.split("/") if p]:
                acc.append(part)
                crumbs.append({"name": part, "path": "/".join(acc)})
            root_info = _root_dict(c, r)
            return {
                "root": root_info,
                "path": path,
                "abs_path": str(Path(r["path"]).joinpath(*[p for p in path.split("/") if p])),
                "crumbs": crumbs,
                "folders": sorted(children.values(), key=lambda x: x["name"].lower()),
                "assets": [summarize(a) for a in assets],
                "cover": here_custom if path else root_info["cover"],
                "cover_custom": bool(here_custom) if path else root_info["cover_custom"],
                "catalog": catalog_payload(listing),
            }
        finally:
            c.close()

    OTHER_FILES_LIMIT = 20000

    def catalog_payload(listing: dict | None) -> dict | None:
        """資料夾的目錄資料：總數、各類型佔多少、照片以外的檔案（精簡格式：[id, 名稱, 類型, 大小, 修改時間]）。"""
        if listing is None:
            return None
        media = ("photo", "raw", "video")
        others = [f for f in listing["files"] if f["status"] == "ok" and not (f["kind"] in media and f["image_id"])]
        return {
            "total_files": listing["total_files"], "total_bytes": listing["total_bytes"],
            "files_here": listing["files_here"], "bytes_here": listing["bytes_here"],
            "kinds": listing["kinds"],
            "files": [[f["id"], f["name"], f["kind"], f["size"], f["mtime"]] for f in others[:OTHER_FILES_LIMIT]],
            "files_total": len(others),
            "missing": [f["name"] for f in listing["files"] if f["status"] != "ok"][:200],
        }

    @app.post("/api/folders/prefs")
    def set_folder_prefs(body: dict = Body(...)):
        """收藏資料夾（只影響顯示）。"""
        c = conn()
        try:
            root_id, path = int(body.get("root_id") or 0), str(body.get("path") or "").strip("/")
            if db.get_root(c, root_id) is None:
                raise HTTPException(404, "找不到資料夾")
            c.execute("INSERT OR IGNORE INTO folder_prefs (root_id, path) VALUES (?, ?)", (root_id, path))
            if "favorite" in body:
                c.execute("UPDATE folder_prefs SET favorite = ? WHERE root_id = ? AND path = ?", (1 if body["favorite"] else 0, root_id, path))
            c.commit()
            return {"ok": True}
        finally:
            c.close()

    @app.post("/api/folders/order")
    def set_folder_order(body: dict = Body(...)):
        """拖曳排好的顯示順序：items 是 [{root_id, path}]，依序存成 0、1、2…（不會動到硬碟上的檔案）。"""
        c = conn()
        try:
            for pos, it in enumerate(body.get("items") or []):
                root_id, path = int(it.get("root_id") or 0), str(it.get("path") or "").strip("/")
                c.execute("INSERT OR IGNORE INTO folder_prefs (root_id, path) VALUES (?, ?)", (root_id, path))
                c.execute("UPDATE folder_prefs SET position = ? WHERE root_id = ? AND path = ?", (pos, root_id, path))
            c.commit()
            return {"ok": True}
        finally:
            c.close()

    @app.post("/api/favorites/link")
    def set_favorite_link(body: dict = Body(...)):
        """把檔案或側邊欄的項目釘到「喜好項目」（on＝false 就拿掉）。只記在目錄裡，不動硬碟上的檔案。"""
        href = str(body.get("href") or "")
        kind = str(body.get("kind") or "")
        # 只接受 Re'memor 自己的頁面（不能是外部網址）
        if not href.startswith("/") or href.startswith("//") or len(href) > 2000 or kind not in ("file", "link"):
            raise HTTPException(400, "這個項目不能放進喜好項目")
        c = conn()
        try:
            if body.get("on", True):
                name = str(body.get("name") or "").strip()[:200] or href
                top = c.execute("SELECT MAX(m) FROM (SELECT MAX(position) AS m FROM folder_prefs WHERE favorite = 1 "
                                "UNION ALL SELECT MAX(position) FROM sidebar_links)").fetchone()[0]
                c.execute("INSERT INTO sidebar_links (href, kind, ref, name, icon, position, created_at) VALUES (?, ?, ?, ?, ?, ?, ?) "
                          "ON CONFLICT(href) DO UPDATE SET name = excluded.name, ref = excluded.ref, icon = excluded.icon",
                          (href, kind, str(body.get("ref") or "")[:200] or None, name, str(body.get("icon") or "")[:40] or None,
                           (top if top is not None else -1) + 1, db.now_iso()))
            else:
                c.execute("DELETE FROM sidebar_links WHERE href = ?", (href,))
            c.commit()
            return {"ok": True}
        finally:
            c.close()

    @app.post("/api/favorites/order")
    def set_favorites_order(body: dict = Body(...)):
        """拖曳排好的「喜好項目」順序：items 是 [{kind: folder, root_id, path} 或 {kind: file／link, href}]，依序存成 0、1、2…"""
        c = conn()
        try:
            for pos, it in enumerate(body.get("items") or []):
                if not isinstance(it, dict):
                    continue
                if it.get("kind") == "folder":
                    root_id, path = int(it.get("root_id") or 0), str(it.get("path") or "").strip("/")
                    c.execute("UPDATE folder_prefs SET position = ? WHERE root_id = ? AND path = ?", (pos, root_id, path))
                else:
                    c.execute("UPDATE sidebar_links SET position = ? WHERE href = ?", (pos, str(it.get("href") or "")))
            c.commit()
            return {"ok": True}
        finally:
            c.close()

    @app.post("/api/folders/cover")
    def set_folder_cover(body: dict = Body(...)):
        """資料夾（或資料夾來源本身，path 為空）的封面；image_id 為空＝改回自動（最新的照片）。"""
        c = conn()
        try:
            root_id = int(body.get("root_id") or 0)
            path = str(body.get("path") or "").strip("/")
            if db.get_root(c, root_id) is None:
                raise HTTPException(404, "找不到資料夾")
            image_id = body.get("image_id")
            if image_id:
                c.execute("INSERT OR REPLACE INTO folder_covers (root_id, path, image_id) VALUES (?, ?, ?)", (root_id, path, int(image_id)))
            else:
                c.execute("DELETE FROM folder_covers WHERE root_id = ? AND path = ?", (root_id, path))
            c.commit()
            return {"ok": True}
        finally:
            c.close()

    @app.post("/api/folders/reveal")
    def reveal_folder(body: dict = Body(...)):
        c = conn()
        try:
            r = db.get_root(c, int(body["root_id"]))
        finally:
            c.close()
        if r is None:
            raise HTTPException(404, "找不到資料夾")
        target = fileops.safe_folder(Path(r["path"]), str(body.get("path", "")))
        if not target.exists():
            raise HTTPException(404, "資料夾不存在或硬碟未連接")
        fileops.reveal(target, select=False)
        return {"ok": True}

    # ---- 相簿 ----
    @app.get("/api/albums")
    def albums():
        c = conn()
        try:
            return db.list_albums(c)
        finally:
            c.close()

    @app.post("/api/albums")
    def new_album(body: dict = Body(...)):
        c = conn()
        try:
            album_id = db.create_album(c, str(body.get("name", "")), [int(i) for i in body.get("ids") or []])
            return db.get_album(c, album_id)
        finally:
            c.close()

    @app.get("/api/albums/{album_id:int}")
    def album(album_id: int):
        c = conn()
        try:
            a = db.get_album(c, album_id)
            if a is None:
                raise HTTPException(404, "找不到相簿")
            rows = c.execute(
                "SELECT i.* FROM images i JOIN album_items ai ON ai.image_id = i.id WHERE ai.album_id = ? "
                "ORDER BY i.sort_at DESC, i.id DESC",
                (album_id,),
            ).fetchall()
            return {**a, "assets": [summarize(r) for r in rows]}
        finally:
            c.close()

    @app.post("/api/albums/{album_id:int}")
    def edit_album(album_id: int, body: dict = Body(...)):
        c = conn()
        try:
            if db.get_album(c, album_id) is None:
                raise HTTPException(404, "找不到相簿")
            db.update_album(c, album_id, name=body.get("name"), description=body.get("description"),
                            cover_id=body.get("cover_id"), favorite=body.get("favorite"))
            return db.get_album(c, album_id)
        finally:
            c.close()

    @app.post("/api/albums/order")
    def set_album_order(body: dict = Body(...)):
        """拖曳排好的相簿順序：ids 依序存成 0、1、2…"""
        c = conn()
        try:
            c.executemany("UPDATE albums SET position = ? WHERE id = ?", [(i, int(a)) for i, a in enumerate(body.get("ids") or [])])
            c.commit()
            return {"ok": True}
        finally:
            c.close()

    @app.delete("/api/albums/{album_id:int}")
    def remove_album(album_id: int):
        c = conn()
        try:
            db.delete_album(c, album_id)
            return {"ok": True}
        finally:
            c.close()

    # ---- 圖庫資料夾（根目錄） ----
    @app.get("/api/roots")
    def roots():
        c = conn()
        try:
            return [_root_dict(c, r) for r in db.list_roots(c)]
        finally:
            c.close()

    @app.post("/api/roots")
    def add_root(body: dict = Body(...)):
        c = conn()
        try:
            r = db.add_root(c, str(body.get("path", "")), body.get("name") or None)
            jobs().submit("scan", roots=[r["name"]])
            return _root_dict(c, r)
        finally:
            c.close()

    @app.post("/api/roots/{root_id:int}")
    def relocate(root_id: int, body: dict = Body(...)):
        c = conn()
        try:
            r = db.relocate_root(c, root_id, str(body.get("path", "")))
            jobs().submit("scan", roots=[r["name"]])
            return _root_dict(c, r)
        finally:
            c.close()

    @app.delete("/api/roots/{root_id:int}")
    def delete_root(root_id: int):
        """移除資料夾：連同縮圖、人臉與分析資料一起清掉（照片檔案不受影響）。"""
        from .storage import remove_root

        # 正在掃描或讀這顆硬碟：先停下來（做完的部分保留），再移除，避免掃描還在寫它的紀錄
        if not jobs().stop_disk_work(timeout=60):
            raise HTTPException(409, "掃描還在停止中，請過幾秒再試一次。")
        c = conn()
        try:
            return remove_root(c, cfg, root_id)
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc
        finally:
            c.close()

    # ---- 整理工具 ----
    @app.get("/api/tools/summary")
    @memo(600, warm=True)
    def tools_summary():
        from .tools import screens_and_documents

        c = conn()
        try:
            from .organize import load_duplicates

            dups = load_duplicates(c, cfg)
            return {
                "screens": len(screens_and_documents(c, png_rule=bool(cfg.screen_png_rule))),
                "biggest": c.execute("SELECT COALESCE(SUM(size), 0) FROM images WHERE status = 'ok'").fetchone()[0],
                "videos_bytes": c.execute("SELECT COALESCE(SUM(size), 0) FROM images WHERE status = 'ok' AND media_type = 'video'").fetchone()[0],
                "dups": (len(dups["exact"]) + len(dups["similar"])) if dups else None,
            }
        finally:
            c.close()

    @app.get("/api/tools/screens")
    @memo(600, warm=True)
    def tools_screens():
        from .tools import screens_and_documents

        c = conn()
        try:
            return [{**summarize(r), "reason": reason} for r, reason in screens_and_documents(c, png_rule=bool(cfg.screen_png_rule))]
        finally:
            c.close()

    @app.get("/api/tools/large")
    def tools_large(kind: str = "all", sort: str = "size"):
        from .tools import large_files

        c = conn()
        try:
            return [{**summarize(r), "size": r["size"], "rel_path": r["rel_path"], "root_id": r["root_id"]}
                    for r in large_files(c, kind, limit=max(50, min(int(cfg.large_files_limit or 200), 2000)), sort=sort)]
        finally:
            c.close()

    @app.get("/api/tools/size-by-kind")
    def tools_size_by_kind():
        from .tools import size_by_kind

        c = conn()
        try:
            return size_by_kind(c)
        finally:
            c.close()

    @app.get("/api/tools/folder-tree")
    def tools_folder_tree(root_id: int | None = None, path: str = ""):
        from .tools import folder_children

        c = conn()
        try:
            out = folder_children(c, root_id, path)
            if root_id is not None:
                root = db.get_root(c, root_id)
                out["root_name"] = root["name"] if root else ""
            return out
        finally:
            c.close()

    @app.get("/api/tools/large-folders")
    def tools_large_folders():
        from .tools import large_folders

        c = conn()
        try:
            return large_folders(c)
        finally:
            c.close()

    @app.get("/api/export/defaults")
    def export_defaults():
        from .export import default_dest

        return {"dest": str(default_dest().parent)}

    @app.post("/api/export/inspect")
    def export_inspect(body: dict = Body(...)):
        """匯出前先看選了什麼：幾張 RAW、幾張一般照片、幾部影片（影片不匯出）。"""
        ids = [int(i) for i in body.get("ids", [])][:20000]
        out = {"total": len(ids), "raw": 0, "photo": 0, "video": 0}
        c = conn()
        try:
            for start in range(0, len(ids), 500):
                chunk = ids[start:start + 500]
                marks = ",".join("?" * len(chunk))
                for r in c.execute(f"SELECT media_type, is_raw FROM images WHERE id IN ({marks})", chunk):
                    if r["media_type"] == "video":
                        out["video"] += 1
                    elif r["is_raw"]:
                        out["raw"] += 1
                    else:
                        out["photo"] += 1
            return out
        finally:
            c.close()

    @app.post("/api/reveal-path")
    def reveal_path(body: dict = Body(...)):
        """在 Finder 顯示匯出的資料夾（只限本機）。"""
        target = Path(str(body.get("path", ""))).expanduser()
        if not target.exists():
            raise HTTPException(404, "找不到這個資料夾")
        fileops.reveal(target, select=False)
        return {"ok": True}

    # ---- 儲存空間與模型管理 ----
    @app.get("/api/storage")
    def storage_usage():
        from .storage import usage

        try:
            ollama = client_factory().installed()
            ollama_ok = True
        except Exception:  # noqa: BLE001
            ollama, ollama_ok = [], False
        c = conn()
        try:
            return {**usage(c, cfg, ollama), "ollama_ok": ollama_ok}
        finally:
            c.close()

    @app.post("/api/storage/clean")
    def storage_clean(body: dict = Body(default={})):
        from .storage import clean_orphans

        c = conn()
        try:
            return clean_orphans(c, cfg)
        finally:
            c.close()

    @app.post("/api/storage/clear-analysis")
    def storage_clear_analysis(body: dict = Body(default={})):
        from .storage import clear_analysis

        root_id = body.get("root_id")
        c = conn()
        try:
            return {"cleared": clear_analysis(c, int(root_id) if root_id is not None else None)}
        finally:
            c.close()

    @app.post("/api/storage/models/delete")
    def storage_delete_model(body: dict = Body(...)):
        """刪除任何一種模型：Ollama（視覺、語意、翻譯）、人臉、圖像搜尋。"""
        from .storage import delete_model_files

        kind, name = str(body.get("kind", "")), str(body.get("name", ""))
        if kind == "ollama":
            client_factory().delete(name)
            return {"ok": True}
        if kind in ("face", "clip"):
            try:
                return {"ok": True, "freed": delete_model_files(cfg, kind, name)}
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from exc
        raise HTTPException(400, "未知的模型類型")

    @app.post("/api/storage/reveal")
    def storage_reveal(body: dict = Body(default={})):
        fileops.reveal(cfg.home, select=False)
        return {"ok": True}

    @app.post("/api/pick-folder")
    def pick(body: dict = Body(default={})):
        path = fileops.pick_folder(str(body.get("purpose") or "add"))
        return {"path": path}

    # ---- 工作 ----
    @app.get("/api/jobs")
    def job_state():
        return jobs().snapshot()

    @app.post("/api/jobs")
    def start_job(body: dict = Body(...)):
        kind = body.get("kind")
        opts = {k: body[k] for k in ("roots", "folder", "root_id", "album_id", "redo", "retry_failed", "large") if body.get(k) is not None}
        if kind in ("pull", "face_model", "clip_model"):
            opts = {"model": str(body["model"])}
        if kind == "export":
            ids = [int(i) for i in body.get("ids") or []][:MAX_IDS]
            if not ids:
                raise HTTPException(400, "沒有選取照片")
            opts = {"ids": ids, "export": dict(body.get("options") or {})}
        return jobs().submit(kind, **opts)

    @app.post("/api/jobs/stop")
    def stop_job(body: dict = Body(default={})):
        job_id = body.get("id")
        return jobs().stop(int(job_id) if job_id is not None else None)

    # ---- 模型與設定 ----
    @app.get("/api/models")
    def models():
        try:
            installed = client_factory().installed()
            error = None
        except OllamaUnavailable as exc:
            installed, error = [], str(exc)
        names = [m["name"] for m in installed]
        machine = machine_info()
        ai_cache["at"] = 0.0  # 模型清單變了，下次重新檢查
        return {
            "ollama_ok": error is None,
            "error": error,
            "installed": installed,
            "machine": machine,
            "picks": recommend(machine["ram_gb"]),
            "recommended": annotated(machine["ram_gb"], names),
            "assistant_pick": recommend_assistant(machine["ram_gb"]),
            "active": {"vision": cfg.vision_model, "embed": cfg.embed_model, "text": cfg.text_model},
            "ollama_url": cfg.ollama_url,
        }

    @app.post("/api/models/delete")
    def delete_model(body: dict = Body(...)):
        client_factory().delete(str(body["name"]))
        return {"ok": True}

    @app.get("/api/settings")
    def settings():
        from .analyzer import PROMPTS

        return {**public_settings(), "default_prompt": PROMPTS.get(cfg.language, PROMPTS["zh-TW"])}

    @app.post("/api/settings")
    def save_settings(body: dict = Body(...)):
        if "face_model" in body and body["face_model"] != cfg.face_model:
            from .faces import FACE_MODELS, clear_all

            if body["face_model"] not in FACE_MODELS and body["face_model"] != "custom":
                raise HTTPException(400, "未知的人臉模型")
            c = conn()
            try:
                clear_all(c, cfg)
            finally:
                c.close()
        for key, value in body.items():
            if key in SECRET_KEYS and not value and not body.get("clear_" + key):
                continue  # 空白＝沒有改金鑰（介面不會拿到原本的金鑰）
            if key == "assistant_permission":
                try:
                    value = max(1, min(4, int(value)))
                except (TypeError, ValueError):
                    continue
            if key in SETTING_KEYS:
                cfg.save_setting(key, value)
        if "spotlight" in body or "spotlight_internal" in body:
            from . import spotlight

            spotlight.changed()  # 打開或關掉：下一次同步時放進去或全部拿掉
        return public_settings()

    def public_settings() -> dict:
        """設定值；API 金鑰不回傳，只說有沒有設定。"""
        out = {k: getattr(cfg, k) for k in CONFIG_KEYS if k not in SECRET_KEYS}
        for k in SECRET_KEYS:
            out[k + "_set"] = bool(getattr(cfg, k))
        from .models import assistant_model

        out["assistant_model_effective"] = assistant_model(cfg)
        return out

    # ---- 手機連線 ----
    @app.get("/api/lan")
    def lan(request: Request):
        urls = lan_addresses(cfg.port)
        active = bound_host != "127.0.0.1"
        return {
            "enabled": bool(cfg.lan),
            "active": active,
            "needs_restart": bool(cfg.lan) != active,
            "has_password": auth.has_password,
            "urls": urls,
            "qr": qr_svg(urls[-1]) if urls else None,
            "local": request.state.local,
        }

    @app.post("/api/lan")
    def set_lan(body: dict = Body(...)):
        if body.get("password"):
            auth.set_password(str(body["password"]))
        if "enabled" in body:
            if body["enabled"] and not auth.has_password:
                raise HTTPException(400, "開啟手機連線前請先設定密碼")
            cfg.save_setting("lan", 1 if body["enabled"] else 0)
        return {"enabled": bool(cfg.lan), "has_password": auth.has_password}

    @app.post("/api/open-url")
    def open_url(body: dict = Body(...)):
        """App 視窗裡的外部連結（例如 Ollama 下載頁）改用預設瀏覽器開啟。"""
        url = str(body.get("url", ""))
        if not url.startswith(("https://", "http://")):
            raise HTTPException(400, "只能開啟網址")
        import webbrowser

        webbrowser.open(url)
        return {"ok": True}

    @app.post("/api/shutdown")
    def shutdown(body: dict = Body(default={})):
        """結束這個 Re'memor（只接受這台電腦自己的請求）：更新後啟動新版時，請舊版讓出連接埠。
        背景工作會先停下並記錄，下次可以接著做。"""
        import signal

        def later():
            time.sleep(0.3)
            os.kill(os.getpid(), signal.SIGTERM)

        threading.Thread(target=later, daemon=True).start()
        return {"ok": True}

    def restart_later(delay: float = 0.6):
        def later():
            import time

            time.sleep(delay)
            jobs().close()
            exiftool().close()
            if getattr(sys, "frozen", False):  # Mac App 內打包的執行檔
                os.execv(sys.executable, [sys.executable, *sys.argv[1:]])
            os.execv(sys.executable, [sys.executable, "-m", "lumilib", *sys.argv[1:]])

        threading.Thread(target=later, daemon=True).start()

    app.state.restart_later = restart_later

    @app.post("/api/restart")
    def restart(body: dict = Body(default={})):
        restart_later()
        return {"ok": True}

    # ---- 目錄放在哪裡 ----
    @app.get("/api/catalog/location")
    def catalog_location():
        from .location import anchor, folder_size, pointed

        size, files = folder_size(cfg.home)
        base = anchor()
        old = base if pointed(base) is not None and (base / "library.db").exists() else None
        if old is None and base.is_dir():  # 搬回來時收起來的那份
            stashed = sorted(p for p in base.iterdir() if p.is_dir() and p.name.startswith("舊的目錄 "))
            old = stashed[-1] if stashed else None
        return {"home": str(cfg.home), "default": str(base), "moved": pointed(base) is not None, "bytes": size, "files": files,
                "free": shutil.disk_usage(cfg.home).free, "old_copy": str(old) if old else None}

    def _move_target(path: str):
        from .location import check_target

        c = conn()
        try:
            roots = [r["path"] for r in db.list_roots(c)]
        finally:
            c.close()
        return check_target(path, cfg.home, roots)

    @app.post("/api/catalog/location/check")
    def catalog_check(body: dict = Body(...)):
        target, error = _move_target(str(body.get("path") or ""))
        return {"target": str(target) if target else None, "error": error}

    @app.post("/api/catalog/move")
    def catalog_move(body: dict = Body(...)):
        """把目錄搬到另一個位置（複製、確認完整後才改用；原本那份不刪除）。搬好後自動重新啟動。"""
        if jobs().snapshot()["active"]:
            raise HTTPException(409, "有工作正在進行。請等它完成或停止後再搬移目錄。")
        target, error = _move_target(str(body.get("path") or ""))
        if error:
            raise HTTPException(400, error)
        return jobs().submit("move_catalog", dest=str(target))

    # ---- 前端（PWA） ----
    @app.get("/{full_path:path}")
    def spa(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(404, "not found")
        index = WEB_DIR / "index.html"
        if full_path:
            target = (WEB_DIR / full_path).resolve()
            if WEB_DIR.resolve() in target.parents and target.is_file():
                cache = "public, max-age=31536000, immutable" if "/assets/" in f"/{full_path}" else "no-cache"
                return FileResponse(target, headers={"Cache-Control": cache})
        if not index.exists():
            return Response("前端尚未建置：請在 image-library/web 執行 pnpm install && pnpm build", media_type="text/plain; charset=utf-8")
        return FileResponse(index, headers={"Cache-Control": "no-cache"})

    return app


def serve(cfg: Config, host: str | None = None, port: int | None = None, open_browser: bool = False) -> None:
    import uvicorn

    host = host or ("0.0.0.0" if cfg.lan else "127.0.0.1")
    port = port or cfg.port
    cfg.port = port
    db.connect(cfg.db_path).close()
    if host != "127.0.0.1" and not Auth(cfg.auth_file).has_password:
        print("尚未設定手機連線密碼，改為只允許本機。請在設定頁設定密碼。")
        host = "127.0.0.1"
    url = f"http://127.0.0.1:{port}/"
    if not _take_port(port, url, open_browser):
        return
    app = create_app(cfg, bound_host=host)
    print(f"Re'memor：{url}（按 Ctrl+C 結束）")
    if host != "127.0.0.1":
        for u in lan_addresses(port):
            print(f"  手機／平板（同一個 Wi-Fi）：{u}")
    if cfg.keep_awake and sys.platform == "darwin":
        import subprocess

        # 程式結束時 caffeinate 會跟著結束（-w 監看本程序）
        subprocess.Popen(["caffeinate", "-i", "-s", "-w", str(os.getpid())],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if open_browser:
        import webbrowser

        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    uvicorn.run(app, host=host, port=port, log_level="warning")


def _running(port: int) -> dict | None:
    """這個連接埠上正在執行的 Re'memor（回傳它的版本資訊）；沒有東西或不是 Re'memor 回傳 None。"""
    import urllib.request

    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/server", timeout=2) as r:
            data = json.loads(r.read().decode("utf-8"))
            return data if isinstance(data, dict) and "version" in data else None
    except Exception:  # noqa: BLE001
        return None


def _port_busy(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def _stop_other(port: int) -> None:
    """請舊的 Re'memor 結束：新版有「結束」的請求；更舊的版本在 Mac 上找出程序後請它結束。"""
    import signal
    import subprocess
    import urllib.request

    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/api/shutdown", data=b"{}", method="POST",
                                     headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=2).close()
        return
    except Exception:  # noqa: BLE001
        pass
    if sys.platform != "darwin":
        return
    try:
        pids = subprocess.run(["/usr/sbin/lsof", "-nP", "-t", f"-iTCP:{port}", "-sTCP:LISTEN"],
                              capture_output=True, text=True, timeout=5).stdout.split()
    except (OSError, subprocess.SubprocessError):
        return
    for pid in pids:
        try:
            cmd = subprocess.run(["/bin/ps", "-p", pid, "-o", "command="], capture_output=True, text=True, timeout=5).stdout
        except (OSError, subprocess.SubprocessError):
            continue
        if "lumilib" in cmd or "rememor" in cmd.lower():
            try:
                os.kill(int(pid), signal.SIGTERM)
            except (OSError, ValueError):
                pass


def _take_port(port: int, url: str, open_browser: bool) -> bool:
    """啟動前先看看連接埠：已經有同一份 Re'memor 在跑就直接打開它；是舊的就請它讓位，改用這一份。
    回傳 True＝可以啟動。"""
    if not _port_busy(port):
        return True
    other = _running(port)
    if other is None:
        print(f"連接埠 {port} 被其他程式佔用，Re'memor 無法啟動。請關閉那個程式後再試一次。")
        return False
    if other.get("build") and other.get("build") == build_id():
        print(f"Re'memor 已經在執行（同一個版本），直接打開：{url}")
        if open_browser:
            import webbrowser

            webbrowser.open(url)
        return False
    print("發現另一個舊版的 Re'memor 正在執行（可能是之前開的 App 或終端機視窗），正在關閉它，改用剛更新的這一版…")
    _stop_other(port)
    deadline = time.monotonic() + 15
    while _port_busy(port) and time.monotonic() < deadline:
        time.sleep(0.3)
    if _port_busy(port):
        print("無法自動關閉舊版。請先結束 Re'memor App（選單列的 Re'memor 圖示 → 結束），"
              "或關閉另一個正在執行 Re'memor 的終端機視窗，再執行一次這個指令。")
        return False
    return True


_UNAVAILABLE_PAGE = """<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Re'memor</title><style>
:root { color-scheme: light dark; --bg: #f5f5f7; --card: #fff; --text: #1d1d1f; --sub: #6e6e73; --accent: #0071e3; }
@media (prefers-color-scheme: dark) { :root { --bg: #1c1c1e; --card: #2c2c2e; --text: #f5f5f7; --sub: #a1a1a6; --accent: #0a84ff; } }
body { margin: 0; min-height: 100vh; display: flex; align-items: center; justify-content: center; background: var(--bg); color: var(--text);
  font: 14px/1.5 -apple-system, BlinkMacSystemFont, "PingFang TC", sans-serif; }
main { max-width: 460px; margin: 24px; padding: 28px; border-radius: 16px; background: var(--card); text-align: center; }
h1 { font-size: 20px; margin: 12px 0 8px; } p { color: var(--sub); margin: 0 0 12px; } code { word-break: break-all; color: var(--text); }
button { font: inherit; border: 0; border-radius: 999px; padding: 8px 18px; margin: 6px; cursor: pointer; }
.main { background: var(--accent); color: #fff; } .alt { background: transparent; color: var(--accent); box-shadow: inset 0 0 0 1px var(--accent); }
#msg { min-height: 1.5em; }
</style></head><body><main>
<img src="/icon.png" width="56" height="56" alt="">
<h1>請接上放目錄的磁碟</h1>
<p>Re'memor 的目錄放在 <code>__TARGET__</code>，那顆磁碟現在沒有接上。接上後按「再試一次」。</p>
<p>The catalog is on a disk that isn't connected. Connect it and click Try Again.</p>
<button class="main" onclick="go('retry')">再試一次</button>
__LOCAL__
<p id="msg"></p></main>
<script>
async function go(what) {
  document.getElementById('msg').textContent = '…';
  const r = await fetch('/api/catalog/' + what, { method: 'POST' }).then((x) => x.json()).catch(() => ({ error: '沒有回應' }));
  if (r.error) { document.getElementById('msg').textContent = r.error; return; }
  document.getElementById('msg').textContent = '正在重新開啟…';
  setTimeout(() => location.replace('/'), 2500);
}
</script></body></html>"""


def serve_unavailable(err, port: int, open_browser: bool) -> None:
    """目錄所在的磁碟沒接上：只開一個說明頁，不在空的位置另開新目錄（也不碰任何硬碟）。"""
    import html

    import uvicorn

    from .location import use_home

    url = f"http://127.0.0.1:{port}/"
    print(str(err))
    if not _take_port(port, url, open_browser):
        return
    has_local = (err.anchor / "library.db").exists()
    local_btn = (f'<button class="alt" onclick="go(\'use-local\')">改用這台 Mac 上的舊目錄</button>'
                 f'<p>（{html.escape(str(err.anchor))} 裡還有搬走前的那份，可能比較舊）</p>') if has_local else ""
    page = _UNAVAILABLE_PAGE.replace("__TARGET__", html.escape(str(err.target))).replace("__LOCAL__", local_btn)
    app = FastAPI()

    def restart():
        def later():
            time.sleep(0.5)
            if getattr(sys, "frozen", False):
                os.execv(sys.executable, [sys.executable, *sys.argv[1:]])
            os.execv(sys.executable, [sys.executable, "-m", "lumilib", *sys.argv[1:]])

        threading.Thread(target=later, daemon=True).start()

    @app.get("/api/server")
    def info():
        return {"version": __version__, "build": build_id(), "unavailable": str(err.target)}

    @app.get("/api/auth/status")
    def auth_status():
        return {"authenticated": True, "local": True}

    @app.post("/api/catalog/retry")
    def retry():
        if not (err.target / "library.db").exists():
            return {"error": "還是找不到。請確認磁碟接上了，Finder 裡看得到它。"}
        restart()
        return {"ok": True}

    @app.post("/api/catalog/use-local")
    def use_local():
        if not has_local:
            return {"error": "這台 Mac 上沒有舊的目錄。"}
        use_home(err.anchor, err.anchor)
        restart()
        return {"ok": True}

    @app.post("/api/shutdown")
    def shutdown():
        import signal

        threading.Thread(target=lambda: (time.sleep(0.3), os.kill(os.getpid(), signal.SIGTERM)), daemon=True).start()
        return {"ok": True}

    @app.get("/icon.png")
    def icon():
        return FileResponse(WEB_DIR / "icon.png")

    @app.get("/{full_path:path}")
    def page_(full_path: str):
        return Response(page, media_type="text/html; charset=utf-8", headers={"Cache-Control": "no-cache"})

    if open_browser:
        import webbrowser

        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")

