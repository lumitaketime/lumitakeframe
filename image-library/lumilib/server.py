"""本機網頁介面：搜尋、瀏覽、編輯標籤、在檔案總管中顯示原檔。

只綁定 127.0.0.1，並檢查 Host / Origin，避免其他網站透過瀏覽器呼叫這個服務。
"""

from __future__ import annotations

import json
import mimetypes
import os
import subprocess
import sys
import threading
import traceback
from contextlib import contextmanager
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import __version__, db
from .analyzer import OllamaClient, OllamaUnavailable, analyze_images, embed_images
from .config import Config
from .imaging import ImageReadError, ensure_thumbnail, make_jpeg, open_image, thumb_path
from .scanner import scan_all
from .search import search, top_tags

STATIC_DIR = Path(__file__).parent / "static"


class JobRunner:
    """同一時間只跑一個背景工作（掃描或分析）。"""

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None
        self.state: dict = {"kind": None, "running": False, "message": "", "done": 0, "total": 0}

    def snapshot(self) -> dict:
        with self.lock:
            return dict(self.state)

    def _update(self, **kw) -> None:
        with self.lock:
            self.state.update(kw)

    def start(self, kind: str, **options) -> bool:
        with self.lock:
            if self.state["running"]:
                return False
            self.stop_event.clear()
            self.state = {
                "kind": kind, "running": True, "message": "準備中…", "done": 0, "total": 0,
                "started_at": datetime.now().isoformat(timespec="seconds"), "error": None,
            }
        self.thread = threading.Thread(target=self._run, args=(kind, options), daemon=True)
        self.thread.start()
        return True

    def stop(self) -> None:
        self.stop_event.set()
        self._update(message="停止中…")

    def _run(self, kind: str, options: dict) -> None:
        conn = db.connect(self.cfg.db_path)
        try:
            if kind in ("scan", "index"):
                results = scan_all(conn, self.cfg, progress=lambda m: self._update(message=m))
                parts = []
                for r in results:
                    if r.offline:
                        parts.append(f"{r.root}：未連接，已略過")
                    else:
                        parts.append(f"{r.root}：新增 {r.added}、更新 {r.updated}、搬移 {r.moved}、遺失 {r.missing}")
                self._update(message="；".join(parts) or "尚未加入任何資料夾")
            if kind in ("analyze", "index") and not self.stop_event.is_set():
                client = OllamaClient(self.cfg.ollama_url, self.cfg.request_timeout)
                res = analyze_images(
                    conn, self.cfg, client,
                    retry_failed=bool(options.get("retry_failed")),
                    progress=lambda i, n, m: self._update(done=i, total=n, message=f"分析中 {i}/{n}：{m}"),
                    stop=self.stop_event,
                )
                self._update(message=f"完成：分析 {res.analyzed} 張、失敗 {res.failed} 張、建立向量 {res.embedded} 張")
            if kind == "embed":
                client = OllamaClient(self.cfg.ollama_url, self.cfg.request_timeout)
                n = embed_images(conn, self.cfg, client, stop=self.stop_event)
                self._update(message=f"完成：建立向量 {n} 張")
        except OllamaUnavailable as exc:
            self._update(error=str(exc), message=str(exc))
        except Exception as exc:  # 背景工作不能讓伺服器掛掉
            traceback.print_exc()
            self._update(error=str(exc), message=f"發生錯誤：{exc}")
        finally:
            conn.close()
            if self.stop_event.is_set():
                self._update(message="已停止")
            self._update(running=False, finished_at=datetime.now().isoformat(timespec="seconds"))


def reveal_in_file_manager(path: Path, select: bool = True) -> None:
    if sys.platform.startswith("win"):
        if select:
            subprocess.Popen(["explorer", f"/select,{path}"])
        else:
            os.startfile(str(path))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", "-R", str(path)] if select else ["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path.parent if select else path)])


def make_handler(cfg: Config, jobs: JobRunner, allowed_hosts: set[str]):
    class Handler(BaseHTTPRequestHandler):
        server_version = f"lumilib/{__version__}"

        def log_message(self, fmt, *args):  # 安靜一點，只記錄錯誤
            if args and str(args[1] if len(args) > 1 else "").startswith(("4", "5")):
                super().log_message(fmt, *args)

        # ---- helpers ----
        @contextmanager
        def _conn(self):
            conn = db.connect(cfg.db_path)
            try:
                yield conn
                conn.commit()
            finally:
                conn.close()

        def _send(self, status: int, body: bytes, ctype: str, cache: str = "no-store") -> None:
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", cache)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _json(self, data, status: int = 200) -> None:
            self._send(status, json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

        def _error(self, status: int, message: str) -> None:
            self._json({"error": message}, status)

        def _host_ok(self) -> bool:
            host = (self.headers.get("Host") or "").lower()
            if host not in allowed_hosts:
                return False
            origin = self.headers.get("Origin")
            if origin and urlparse(origin).netloc.lower() not in allowed_hosts:
                return False
            return True

        def _read_json(self) -> dict:
            length = int(self.headers.get("Content-Length") or 0)
            if length > 1_000_000:
                raise ValueError("request too large")
            raw = self.rfile.read(length) if length else b"{}"
            data = json.loads(raw.decode("utf-8") or "{}")
            if not isinstance(data, dict):
                raise ValueError("JSON object expected")
            return data

        def _image_or_404(self, conn, image_id: str):
            if not image_id.isdigit():
                return None
            return db.get_image(conn, int(image_id))

        # ---- routes ----
        def do_HEAD(self):
            self.do_GET()

        def do_GET(self):
            if not self._host_ok():
                return self._error(HTTPStatus.FORBIDDEN, "forbidden host")
            url = urlparse(self.path)
            parts = [p for p in url.path.split("/") if p]
            qs = {k: v[-1] for k, v in parse_qs(url.query).items()}
            try:
                if not parts:
                    return self._static("index.html")
                if parts[0] == "static" and len(parts) == 2:
                    return self._static(parts[1])
                if parts == ["api", "stats"]:
                    return self._stats()
                if parts == ["api", "search"]:
                    return self._search(qs)
                if parts == ["api", "tags"]:
                    with self._conn() as conn:
                        return self._json([{"tag": t, "count": c} for t, c in top_tags(conn, 80)])
                if len(parts) == 3 and parts[:2] == ["api", "image"]:
                    return self._detail(parts[2])
                if len(parts) == 2 and parts[0] in ("thumb", "preview"):
                    return self._picture(parts[1], parts[0] == "preview")
            except Exception as exc:
                traceback.print_exc()
                return self._error(500, str(exc))
            self._error(404, "not found")

        def do_POST(self):
            if not self._host_ok():
                return self._error(HTTPStatus.FORBIDDEN, "forbidden host")
            if "application/json" not in (self.headers.get("Content-Type") or ""):
                return self._error(415, "JSON required")
            parts = [p for p in urlparse(self.path).path.split("/") if p]
            try:
                body = self._read_json()
                if len(parts) == 3 and parts[:2] == ["api", "image"]:
                    with self._conn() as conn:
                        image = self._image_or_404(conn, parts[2])
                        if image is None:
                            return self._error(404, "not found")
                        tags = body.get("user_tags")
                        if isinstance(tags, str):
                            tags = [t for t in tags.replace("，", ",").split(",")]
                        db.set_user_fields(conn, image["id"], user_tags=tags, note=body.get("note"))
                    return self._detail(parts[2])
                if len(parts) == 3 and parts[:2] == ["api", "open"]:
                    with self._conn() as conn:
                        image = self._image_or_404(conn, parts[2])
                        if image is None:
                            return self._error(404, "not found")
                        path = db.absolute_path(conn, image)
                    if not path.exists():
                        return self._error(404, "檔案不在原位置，可能是硬碟未連接或已被移動")
                    reveal_in_file_manager(path, select=body.get("mode") != "open")
                    return self._json({"ok": True})
                if len(parts) == 3 and parts[:2] == ["api", "jobs"]:
                    action = parts[2]
                    if action == "stop":
                        jobs.stop()
                        return self._json(jobs.snapshot())
                    if action in ("scan", "analyze", "index", "embed"):
                        if not jobs.start(action, retry_failed=body.get("retry_failed")):
                            return self._error(409, "已有工作在執行")
                        return self._json(jobs.snapshot())
            except (ValueError, json.JSONDecodeError) as exc:
                return self._error(400, str(exc))
            except Exception as exc:
                traceback.print_exc()
                return self._error(500, str(exc))
            self._error(404, "not found")

        # ---- handlers ----
        def _static(self, name: str):
            target = (STATIC_DIR / name).resolve()
            if target.parent != STATIC_DIR.resolve() or not target.is_file():
                return self._error(404, "not found")
            ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            if ctype.startswith("text/") or ctype.endswith("javascript"):
                ctype += "; charset=utf-8"
            self._send(200, target.read_bytes(), ctype)

        def _stats(self):
            with self._conn() as conn:
                roots = [
                    {
                        "id": r["id"], "name": r["name"], "path": r["path"],
                        "online": Path(r["path"]).is_dir(), "images": r["image_count"],
                        "last_scan": r["last_scan"],
                    }
                    for r in db.list_roots(conn)
                ]
                data = {
                    "version": __version__,
                    "stats": db.stats(conn),
                    "roots": roots,
                    "job": jobs.snapshot(),
                    "models": {"vision": cfg.vision_model, "embed": cfg.embed_model, "ollama": cfg.ollama_url},
                }
            self._json(data)

        def _search(self, qs: dict):
            limit = max(1, min(int(qs.get("limit", 120)), 500))
            offset = max(0, int(qs.get("offset", 0)))
            semantic = qs.get("semantic") == "1" and bool(cfg.embed_model)
            embedder = OllamaClient(cfg.ollama_url, 60) if semantic else None
            with self._conn() as conn:
                try:
                    result = search(
                        conn, qs.get("q", ""), limit=limit, offset=offset,
                        semantic=semantic, embedder=embedder, embed_model=cfg.embed_model,
                    )
                except OllamaUnavailable as exc:
                    result = search(conn, qs.get("q", ""), limit=limit, offset=offset)
                    result["warning"] = str(exc)
            self._json(result)

        def _detail(self, image_id: str):
            with self._conn() as conn:
                image = self._image_or_404(conn, image_id)
                if image is None:
                    return self._error(404, "not found")
                root = db.get_root(conn, image["root_id"])
                path = db.absolute_path(conn, image)
                data = {k: image[k] for k in image.keys() if k not in ("embedding", "search_text")}
                for key in ("tags", "objects", "user_tags"):
                    data[key] = db.json_list(image[key])
                data.update(
                    root=root["name"], path=str(path), exists=path.exists(),
                    filename=image["rel_path"].rsplit("/", 1)[-1], has_embedding=image["embedding"] is not None,
                )
            self._json(data)

        def _picture(self, image_id: str, preview: bool):
            with self._conn() as conn:
                image = self._image_or_404(conn, image_id)
                if image is None:
                    return self._error(404, "not found")
                path = db.absolute_path(conn, image)
            thumb = thumb_path(cfg.thumbs_dir, image["fingerprint"])
            if not preview and thumb.exists():
                return self._send(200, thumb.read_bytes(), "image/jpeg", "private, max-age=86400")
            if not path.exists():
                if thumb.exists():  # 硬碟沒接上時，大圖退回縮圖
                    return self._send(200, thumb.read_bytes(), "image/jpeg", "no-store")
                return self._error(404, "檔案目前無法存取")
            try:
                img, _ = open_image(path, draft_side=3200 if preview else cfg.thumb_size * 2)
                with img:
                    if preview:
                        body = make_jpeg(img, 1600, quality=88)
                    else:
                        body = ensure_thumbnail(img, cfg.thumbs_dir, image["fingerprint"], cfg.thumb_size).read_bytes()
            except ImageReadError as exc:
                return self._error(415, str(exc))
            self._send(200, body, "image/jpeg", "private, max-age=3600")

    return Handler


def serve(cfg: Config, host: str = "127.0.0.1", port: int = 8765, open_browser: bool = False) -> None:
    db.connect(cfg.db_path).close()
    jobs = JobRunner(cfg)
    allowed = {f"{h}:{port}" for h in ("127.0.0.1", "localhost", host)}
    httpd = ThreadingHTTPServer((host, port), make_handler(cfg, jobs, allowed))
    url = f"http://{'127.0.0.1' if host in ('0.0.0.0', '') else host}:{port}/"
    print(f"圖庫介面：{url}（按 Ctrl+C 結束）")
    if open_browser:
        import webbrowser

        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已關閉")
    finally:
        jobs.stop()
        httpd.server_close()
