"""本機圖庫服務（FastAPI）：提供 PWA 介面與 API。

- 在這台 Mac 上用 127.0.0.1 開啟不需要登入。
- 開啟「手機連線」後綁定區網，其他裝置一律需要密碼登入。
- 檢查 Host / Origin，避免其他網站透過瀏覽器呼叫這個服務。
"""

from __future__ import annotations

import ipaddress
import mimetypes
import os
import socket
import sqlite3
import sys
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response

from . import __version__, db, fileops
from .analyzer import OllamaClient, OllamaUnavailable
from .net import ca_file
from .auth import COOKIE, SESSION_DAYS, Auth
from .config import CONFIG_KEYS, Config
from .jobs import JobRunner
from .media import BROWSER_VIDEO, MediaError, encode, exiftool, load_image, thumb_path, tool_status, write_thumbnail
from .models import annotated, machine_info, recommend, same_model
from .search import STACK_COUNT_SQL, search, summarize, tag_covers, top_tags

WEB_DIR = Path(__file__).parent / "web"
PUBLIC_API = {"/api/auth/status", "/api/auth/login", "/api/auth/logout"}
LOCAL_ONLY_API = {"/api/pick-folder", "/api/restart", "/api/lan", "/api/open-url", "/api/ollama/start", "/api/storage/reveal", "/api/reveal-path"}
SETTING_KEYS = {
    "vision_model", "embed_model", "language", "analyze_max_side", "scan_on_start", "ollama_url",
    "face_enabled", "face_model", "face_similarity", "face_min_faces",
    "pet_enabled", "pet_model", "pet_similarity", "pet_min_photos", "query_rewrite", "clip_enabled", "clip_model",
    "keep_awake", "xmp_sync", "xmp_embed", "stack_enabled", "burst_seconds",
    "auto_analyze", "blur_threshold", "under_luma", "over_percent", "analysis_detail", "analyze_schedule", "night_start", "night_end", "viewer_rating_bar", "nav_hidden", "pinned_tools", "grid_style", "onboarded",
    "text_model", "analysis_prompt", "clip_custom_repo", "face_custom_url", "face_custom_det", "face_custom_rec",
}
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
               trash=None) -> FastAPI:
    auth = Auth(cfg.auth_file)
    client_factory = client_factory or (lambda: OllamaClient(cfg.ollama_url, cfg.request_timeout))
    state: dict = {}

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        conn = db.connect(cfg.db_path)
        has_roots = bool(db.list_roots(conn))
        from .analyzer import reset_server_errors

        reset_server_errors(conn)  # 修正後重新開啟，之前因模型設定失敗的照片會重新分析
        conn.close()
        state["jobs"] = JobRunner(cfg, client_factory)
        if start_jobs_on_boot and cfg.scan_on_start and has_roots:
            state["jobs"].submit("scan")
        yield
        state["jobs"].close()
        exiftool().close()

    app = FastAPI(title="Lumitake Library", version=__version__, lifespan=lifespan, docs_url=None, redoc_url=None)

    def jobs() -> JobRunner:
        return state["jobs"]

    def conn() -> sqlite3.Connection:
        return db.connect(cfg.db_path)

    def is_local(request: Request) -> bool:
        client = request.client.host if request.client else ""
        return _is_loopback(client) and _is_loopback(_host_only(request.headers.get("host", "")))

    # ---- 保護 ----
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
                "stats": db.stats(c),
                "roots": roots,
                "jobs": jobs().snapshot(),
                "models": {"vision": cfg.vision_model, "embed": cfg.embed_model, "language": cfg.language},
                "tools": tool_status(),
                "ssl_ca": bool(ca_file()),
                "ai": cached_ai_status(),
                "ui": {"viewer_rating_bar": cfg.viewer_rating_bar, "nav_hidden": cfg.nav_hidden, "pinned_tools": cfg.pinned_tools,
                       "grid_style": cfg.grid_style, "onboarded": cfg.onboarded},
                "local": request.state.local,
                "platform": sys.platform,
                "home": str(cfg.home) if request.state.local else None,
            }
        finally:
            c.close()

    def _root_dict(c, r) -> dict:
        cover = c.execute(
            "SELECT id FROM images WHERE root_id = ? AND status = 'ok' AND thumb_ok = 1 ORDER BY sort_at DESC LIMIT 1",
            (r["id"],),
        ).fetchone()
        return {
            "id": r["id"], "name": r["name"], "path": r["path"], "online": Path(r["path"]).is_dir(),
            "count": r["image_count"] if "image_count" in r.keys() else c.execute(
                "SELECT COUNT(*) FROM images WHERE root_id = ? AND status = 'ok'", (r["id"],)).fetchone()[0],
            "last_scan": r["last_scan"], "cover": cover["id"] if cover else None,
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

        from .petid import image_pets

        data["stack"] = [summarize(m) for m in stack_members(c, image["stack_id"])] if image["stack_id"] else []
        data["pets"] = [p for p in image_pets(c, image["id"]) if p["pet_id"]]
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

    @app.post("/api/assets/{image_id:int}/xmp")
    def set_xmp(image_id: int, body: dict = Body(...)):
        """星等（-1 拒絕～5）、顏色標籤、關鍵字；依設定寫回 Lightroom 的 .xmp。"""
        from .xmp import write

        c = conn()
        try:
            get_image_or_404(c, image_id)
            kws = body.get("keywords")
            if isinstance(kws, str):
                kws = kws.replace("，", ",").replace("、", ",").split(",")
            try:
                where = write(c, cfg, image_id, rating=body.get("rating"), label=body.get("label"), keywords=kws)
            except (RuntimeError, MediaError) as exc:
                raise HTTPException(500, f"已更新圖庫，但寫回檔案失敗：{exc}")
            data = detail(c, db.get_image(c, image_id))
            data["written_to"] = where
            return data
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
            if action == "move":
                res = fileops.move_images(c, ids, int(body["root_id"]), str(body.get("folder", "")))
                return {"done": len(res.done), "ids": res.done, "errors": res.errors}
            if action in ("rating", "label"):
                from .xmp import write

                value = body.get("value")
                errors = []
                for i in ids:
                    try:
                        write(c, cfg, i, **({"rating": int(value or 0)} if action == "rating" else {"label": value or ""}))
                    except Exception as exc:  # 個別檔案寫回失敗不影響其他
                        errors.append(str(exc))
                return {"done": len(ids), "errors": errors[:5]}
            if action in ("add_tags", "remove_tags"):
                # 批次加上或移除我的關鍵字（#標籤）；RAW 會寫入 .xmp，和 Lightroom 同步
                from .xmp import write

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
                        write(c, cfg, i, keywords=new)
                        changed += 1
                    except Exception as exc:  # 個別檔案寫回失敗不影響其他
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

    # ---- 器材與關鍵字 ----
    @app.get("/api/gear")
    def gear_stats():
        from . import gear

        c = conn()
        try:
            return gear.stats(c)
        finally:
            c.close()

    @app.get("/api/gear/assets")
    def gear_assets(camera: str | None = None, lens: str | None = None, focal: str | None = None,
                    aperture: str | None = None, iso: str | None = None):
        from . import gear

        c = conn()
        try:
            rows = gear.assets(c, camera=camera, lens=lens, focal=focal, aperture=aperture, iso=iso)
            return {"count": len(rows), "assets": [summarize(r) for r in rows]}
        finally:
            c.close()

    @app.get("/api/keywords")
    def keywords(source: str = "all", year: str | None = None, limit: int = 300):
        from . import gear

        c = conn()
        try:
            return {"keywords": gear.keyword_counts(c, source, year, max(10, min(limit, 1000))), "years": gear.years(c)}
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
                c.execute("UPDATE persons SET cover_face_id = ? WHERE id = ?", (int(body["cover_face_id"]), person_id))
            c.commit()
            return {"ok": True}
        finally:
            c.close()

    @app.post("/api/people/merge")
    def merge_people(body: dict = Body(...)):
        from .faces import merge_persons

        c = conn()
        try:
            merge_persons(c, int(body["target"]), [int(x) for x in body.get("sources") or []])
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

    @app.get("/api/search")
    def do_search(q: str = "", limit: int = 200, offset: int = 0, semantic: int = 0, smart: int = 1):
        from .analyzer import rewrite_query
        from .search import parse_query

        limit = max(1, min(limit, 1000))
        c = conn()
        warnings = []
        try:
            terms = parse_query(q).terms
            groups, english = None, ""
            if smart and cfg.query_rewrite and terms:
                try:
                    rw = rewrite_query(client_factory(), cfg.search_model, terms)
                    groups, english = rw["groups"], rw["english"]
                except Exception as exc:  # 改寫失敗不能讓搜尋失敗
                    warnings.append(f"智慧搜尋暫時無法使用（{exc}），只用原始關鍵字")
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
                                groups=groups, clip_rank=clip_rank)
            except (OllamaUnavailable, MediaError) as exc:
                warnings.append(str(exc))
                result = search(c, q, limit=limit, offset=max(0, offset), groups=groups)
            if warnings:
                result["warning"] = "；".join(warnings)
            result["english"] = english
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
                "cameras": grouped("camera"),
                "lenses": grouped("lens"),
                "years": [{"value": r["value"], "count": r["count"], "cover": r["id"]} for r in years],
                "gps": c.execute("SELECT COUNT(*) FROM images WHERE status = 'ok' AND lat IS NOT NULL").fetchone()[0],
            }
        finally:
            c.close()

    @app.get("/api/map")
    def map_points():
        """地圖用：[[id, lat, lon], ...]，資料量小，十萬筆也能一次載入。"""
        c = conn()
        try:
            rows = c.execute(
                "SELECT id, lat, lon FROM images WHERE status = 'ok' AND lat IS NOT NULL ORDER BY sort_at DESC"
            ).fetchall()
            return [[r["id"], r["lat"], r["lon"]] for r in rows]
        finally:
            c.close()

    # ---- 資料夾 ----
    @app.get("/api/folders")
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
                child = children.setdefault(name, {"name": name, "path": prefix + name, "count": 0, "cover": None, "latest": ""})
                child["count"] += row["count"]
                if (row["latest"] or "") >= child["latest"]:
                    child["latest"], child["cover"] = row["latest"] or "", row["id"]
            assets = c.execute(
                f"SELECT i.*, {STACK_COUNT_SQL} FROM images i WHERE i.root_id = ? AND i.folder = ? AND i.status = 'ok' "
                "AND i.stack_top = 1 ORDER BY i.sort_at DESC, i.id DESC",
                (r["id"], path),
            ).fetchall()
            crumbs, acc = [], []
            for part in [p for p in path.split("/") if p]:
                acc.append(part)
                crumbs.append({"name": part, "path": "/".join(acc)})
            return {
                "root": _root_dict(c, r),
                "path": path,
                "abs_path": str(Path(r["path"]).joinpath(*[p for p in path.split("/") if p])),
                "crumbs": crumbs,
                "folders": sorted(children.values(), key=lambda x: x["name"].lower()),
                "assets": [summarize(a) for a in assets],
            }
        finally:
            c.close()

    @app.get("/api/fs/dirs")
    def fs_dirs(root: int, path: str = ""):
        """搬移時選擇目的地：列出硬碟上真實存在的子資料夾（包含還沒有照片的）。"""
        c = conn()
        try:
            r = db.get_root(c, root)
        finally:
            c.close()
        if r is None:
            raise HTTPException(404, "找不到資料夾")
        base = fileops.safe_folder(Path(r["path"]), path)
        if not base.is_dir():
            raise HTTPException(404, "資料夾不存在或硬碟未連接")
        names = sorted(
            (p.name for p in base.iterdir() if p.is_dir() and not p.name.startswith(".")), key=str.lower
        )
        return {"root": r["id"], "path": path.strip("/"), "dirs": names}

    @app.post("/api/folders")
    def make_folder(body: dict = Body(...)):
        c = conn()
        try:
            return {"path": fileops.create_folder(c, int(body["root_id"]), str(body.get("path", "")))}
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
                            cover_id=body.get("cover_id"))
            return db.get_album(c, album_id)
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

        c = conn()
        try:
            return remove_root(c, cfg, root_id)
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc
        finally:
            c.close()

    # ---- 整理工具 ----
    @app.get("/api/tools/summary")
    def tools_summary():
        from .quality import blurry, exposure_problems
        from .tools import screens_and_documents

        c = conn()
        try:
            q = c.execute(
                "SELECT COUNT(*), SUM(quality_at IS NOT NULL) FROM images WHERE status = 'ok' AND media_type = 'photo'"
            ).fetchone()
            from .organize import load_duplicates

            dups = load_duplicates(c, cfg)
            return {
                "photos": q[0] or 0, "quality_done": q[1] or 0,
                "blurry": len(blurry(c, float(cfg.blur_threshold))),
                "exposure": len(exposure_problems(c, under_luma=cfg.under_luma, over_frac=cfg.over_percent / 100)),
                "screens": len(screens_and_documents(c)),
                "biggest": c.execute("SELECT COALESCE(SUM(size), 0) FROM images WHERE status = 'ok'").fetchone()[0],
                "videos_bytes": c.execute("SELECT COALESCE(SUM(size), 0) FROM images WHERE status = 'ok' AND media_type = 'video'").fetchone()[0],
                "dups": (len(dups["exact"]) + len(dups["similar"])) if dups else None,
            }
        finally:
            c.close()

    @app.get("/api/tools/blurry")
    def tools_blurry(threshold: float | None = None):
        from .quality import blurry

        c = conn()
        try:
            t = float(threshold) if threshold is not None else float(cfg.blur_threshold)
            return [{**summarize(r), "sharpness": r["sharpness"]} for r in blurry(c, t)]
        finally:
            c.close()

    @app.get("/api/tools/exposure")
    def tools_exposure():
        from .quality import EXPOSURE_LABELS, exposure_problems

        c = conn()
        try:
            return [{**summarize(r), "flag": flag, "reason": EXPOSURE_LABELS[flag]}
                    for r, flag in exposure_problems(c, under_luma=cfg.under_luma, over_frac=cfg.over_percent / 100)]
        finally:
            c.close()

    @app.get("/api/tools/screens")
    def tools_screens():
        from .tools import screens_and_documents

        c = conn()
        try:
            return [{**summarize(r), "reason": reason} for r, reason in screens_and_documents(c)]
        finally:
            c.close()

    @app.get("/api/tools/large")
    def tools_large(kind: str = "all", sort: str = "size"):
        from .tools import large_files

        c = conn()
        try:
            return [{**summarize(r), "size": r["size"], "rel_path": r["rel_path"], "root_id": r["root_id"]}
                    for r in large_files(c, kind, sort=sort)]
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

    @app.get("/api/pets")
    def pets_list():
        from .petid import list_pets, model_installed
        from .tools import pets

        c = conn()
        try:
            pending = c.execute(
                "SELECT COUNT(*) FROM images WHERE status = 'ok' AND media_type = 'photo' AND (pets_at IS NULL OR pets_model IS NOT ?)",
                (cfg.pet_model,),
            ).fetchone()[0]
            return {
                "kinds": pets(c),
                "pets": list_pets(c),
                "hidden": sum(1 for p in list_pets(c, include_hidden=True) if p["hidden"]),
                "enabled": bool(cfg.pet_enabled),
                "installed": model_installed(cfg, cfg.pet_model),
                "model": cfg.pet_model,
                "pending": pending,
            }
        finally:
            c.close()

    @app.get("/api/pets/models")
    def pet_models():
        from .petid import models_status

        return models_status(cfg)

    @app.post("/api/pets/models/delete")
    def delete_pet_model(body: dict = Body(...)):
        from .petid import PET_MODELS, delete_model

        if body.get("name") not in PET_MODELS:
            raise HTTPException(400, "未知的寵物模型")
        delete_model(cfg, body["name"])
        return {"ok": True}

    @app.post("/api/pets/clear")
    def clear_pets_data():
        from .petid import clear_all

        c = conn()
        try:
            return {"cleared": clear_all(c, cfg)}
        finally:
            c.close()

    @app.get("/api/pet-thumbs/{det_id:int}")
    def pet_thumb(det_id: int):
        from .petid import thumb_path

        target = thumb_path(cfg, det_id)
        if not target.exists():
            raise HTTPException(404, "找不到寵物縮圖")
        return FileResponse(target, media_type="image/webp", headers={"Cache-Control": "private, max-age=31536000, immutable"})

    @app.get("/api/petid/all")
    def pets_all():
        from .petid import list_pets

        c = conn()
        try:
            return list_pets(c, include_hidden=True)
        finally:
            c.close()

    @app.get("/api/petid/{pet_id:int}")
    def pet_detail(pet_id: int):
        from .petid import KIND_LABELS, pet_image_ids

        c = conn()
        try:
            pet = c.execute("SELECT * FROM pets WHERE id = ?", (pet_id,)).fetchone()
            if pet is None:
                raise HTTPException(404, "找不到這隻寵物")
            ids = pet_image_ids(c, pet_id)
            rows = []
            for start in range(0, len(ids), 500):
                chunk = ids[start:start + 500]
                rows += c.execute(
                    f"SELECT * FROM images WHERE id IN ({','.join('?' * len(chunk))}) AND status = 'ok'", chunk
                ).fetchall()
            rows.sort(key=lambda r: r["sort_at"] or "", reverse=True)
            return {"id": pet["id"], "name": pet["name"] or "", "kind": pet["kind"], "kind_label": KIND_LABELS.get(pet["kind"], ""),
                    "cover": pet["cover_id"], "hidden": bool(pet["hidden"]), "assets": [summarize(r) for r in rows]}
        finally:
            c.close()

    @app.post("/api/petid/{pet_id:int}")
    def edit_pet(pet_id: int, body: dict = Body(...)):
        """改名（同名的另一隻會合併）、隱藏、把照片移出。"""
        from .petid import merge_pets, remove_images, rename_pet, set_hidden

        c = conn()
        try:
            pet = c.execute("SELECT * FROM pets WHERE id = ?", (pet_id,)).fetchone()
            if pet is None:
                raise HTTPException(404, "找不到這隻寵物")
            out: dict = {"id": pet_id}
            if "name" in body:
                name = str(body["name"] or "").strip()[:60]
                same = c.execute("SELECT id FROM pets WHERE name = ? AND id != ? AND kind = ?", (name, pet_id, pet["kind"])).fetchone() if name else None
                if same:
                    merge_pets(c, same["id"], [pet_id])
                    out = {"id": same["id"], "merged": True}
                else:
                    rename_pet(c, pet_id, name)
            if "hidden" in body:
                set_hidden(c, pet_id, bool(body["hidden"]))
            if body.get("remove"):
                out["removed"] = remove_images(c, pet_id, [int(i) for i in body["remove"]][:MAX_IDS])
            return out
        finally:
            c.close()

    @app.post("/api/petid/merge")
    def merge_pet_ids(body: dict = Body(...)):
        from .petid import merge_pets

        c = conn()
        try:
            merge_pets(c, int(body["target"]), [int(i) for i in body.get("sources") or []])
            return {"ok": True}
        finally:
            c.close()

    @app.get("/api/pets/{key}")
    def pets_kind(key: str):
        from .tools import PET_KINDS, pet_images

        label = next((lbl for k, lbl, _ in PET_KINDS if k == key), None)
        if label is None:
            raise HTTPException(404, "找不到這個分類")
        c = conn()
        try:
            return {"key": key, "label": label, "assets": [summarize(r) for r in pet_images(c, key)]}
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
        out = {"total": len(ids), "raw": 0, "photo": 0, "video": 0, "raw_xmp": 0}
        c = conn()
        try:
            for start in range(0, len(ids), 500):
                chunk = ids[start:start + 500]
                marks = ",".join("?" * len(chunk))
                for r in c.execute(f"SELECT media_type, is_raw, xmp_mtime FROM images WHERE id IN ({marks})", chunk):
                    if r["media_type"] == "video":
                        out["video"] += 1
                    elif r["is_raw"]:
                        out["raw"] += 1
                        out["raw_xmp"] += 1 if r["xmp_mtime"] else 0
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
        if kind in ("face", "clip", "pet"):
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
        path = fileops.pick_folder()
        return {"path": path}

    # ---- 工作 ----
    @app.get("/api/jobs")
    def job_state():
        return jobs().snapshot()

    @app.post("/api/jobs")
    def start_job(body: dict = Body(...)):
        kind = body.get("kind")
        opts = {k: body[k] for k in ("roots", "folder", "root_id", "album_id", "redo", "retry_failed") if body.get(k) is not None}
        if kind in ("pull", "face_model", "clip_model", "pet_model"):
            opts = {"model": str(body["model"])}
        if kind == "export":
            ids = [int(i) for i in body.get("ids") or []][:MAX_IDS]
            if not ids:
                raise HTTPException(400, "沒有選取照片")
            opts = {"ids": ids, "export": dict(body.get("options") or {})}
        if kind == "quality" and body.get("redo"):
            opts = {"redo": True}
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

        return {**{k: getattr(cfg, k) for k in CONFIG_KEYS},
                "default_prompt": PROMPTS.get(cfg.language, PROMPTS["zh-TW"])}

    @app.post("/api/settings")
    def save_settings(body: dict = Body(...)):
        if "pet_model" in body and body["pet_model"] != cfg.pet_model:
            from .petid import PET_MODELS
            from .petid import clear_all as clear_pets

            if body["pet_model"] not in PET_MODELS:
                raise HTTPException(400, "未知的寵物模型")
            c = conn()
            try:
                clear_pets(c, cfg)  # 不同模型的特徵無法比較，換模型就重新辨識
            finally:
                c.close()
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
            if key in SETTING_KEYS:
                cfg.save_setting(key, value)
        return {k: getattr(cfg, k) for k in CONFIG_KEYS}

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

    @app.post("/api/restart")
    def restart(body: dict = Body(default={})):
        def later():
            import time

            time.sleep(0.6)
            jobs().close()
            exiftool().close()
            if getattr(sys, "frozen", False):  # Mac App 內打包的執行檔
                os.execv(sys.executable, [sys.executable, *sys.argv[1:]])
            os.execv(sys.executable, [sys.executable, "-m", "lumilib", *sys.argv[1:]])

        threading.Thread(target=later, daemon=True).start()
        return {"ok": True}

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
    app = create_app(cfg, bound_host=host)
    url = f"http://127.0.0.1:{port}/"
    print(f"Lumitake Library：{url}（按 Ctrl+C 結束）")
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
