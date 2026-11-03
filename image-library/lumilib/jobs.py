"""背景工作佇列：掃描、分析、建立向量、下載模型，依序一次執行一個。"""

from __future__ import annotations

import threading
import traceback
from collections import deque
from datetime import datetime

from . import db
from .analyzer import OllamaClient, OllamaUnavailable, analyze_images, embed_images
from .config import Config
from .media import MediaError
from .scanner import scan_all

LABELS = {
    "scan": "掃描", "analyze": "AI 分析", "index": "掃描並分析", "embed": "建立語意向量", "pull": "下載模型",
    "faces": "人臉辨識", "cluster": "人物分群", "face_model": "下載人臉模型",
    "clip": "建立圖像搜尋索引", "clip_model": "下載圖像搜尋模型",
    "dups": "尋找重複與相似照片", "stacks": "重新計算疊放",
}


def _fmt_bytes(n: int) -> str:
    return f"{n / 1e9:.1f} GB" if n >= 1e9 else f"{n / 1e6:.0f} MB"


class JobRunner:
    def __init__(self, cfg: Config, client_factory=None):
        self.cfg = cfg
        self.client_factory = client_factory or (lambda: OllamaClient(cfg.ollama_url, cfg.request_timeout))
        self.lock = threading.Lock()
        self.wake = threading.Condition(self.lock)
        self.queue: deque[dict] = deque()
        self.stop_event = threading.Event()
        self.closed = False
        self.current: dict | None = None
        self.last: dict | None = None
        self.thread = threading.Thread(target=self._worker, daemon=True, name="lumilib-jobs")
        self.thread.start()

    # ---- public ----
    def submit(self, kind: str, **options) -> dict:
        if kind not in LABELS:
            raise ValueError(f"未知的工作：{kind}")
        job = {"kind": kind, "label": LABELS[kind], "options": options}
        with self.wake:
            # 同樣的工作已在排隊就不重複加入
            if any(j["kind"] == kind and j["options"] == options for j in self.queue):
                return self.snapshot_locked()
            self.queue.append(job)
            self.wake.notify()
            return self.snapshot_locked()

    def stop(self) -> dict:
        with self.lock:
            self.queue.clear()
            if self.current:
                self.stop_event.set()
                self.current["message"] = "停止中…"
            return self.snapshot_locked()

    def snapshot(self) -> dict:
        with self.lock:
            return self.snapshot_locked()

    def snapshot_locked(self) -> dict:
        cur = self.current
        return {
            "running": cur is not None,
            "current": {k: v for k, v in cur.items() if k != "options"} if cur else None,
            "queued": [{"kind": j["kind"], "label": j["label"]} for j in self.queue],
            "last": self.last,
        }

    def close(self) -> None:
        with self.wake:
            self.closed = True
            self.queue.clear()
            self.stop_event.set()
            self.wake.notify_all()

    def wait_idle(self, timeout: float = 30) -> bool:
        """測試用：等到佇列清空。"""
        import time

        end = time.monotonic() + timeout
        while time.monotonic() < end:
            with self.lock:
                if not self.queue and self.current is None:
                    return True
            time.sleep(0.05)
        return False

    # ---- worker ----
    def _update(self, **kw) -> None:
        with self.lock:
            if self.current is not None:
                self.current.update(kw)

    def _worker(self) -> None:
        while True:
            with self.wake:
                while not self.queue and not self.closed:
                    self.wake.wait()
                if self.closed:
                    return
                job = self.queue.popleft()
                self.stop_event.clear()
                self.current = {
                    "kind": job["kind"], "label": job["label"], "options": job["options"],
                    "model": job["options"].get("model"), "message": "準備中…", "done": 0, "total": 0, "error": None,
                    "started_at": datetime.now().isoformat(timespec="seconds"),
                }
            try:
                message = self._run(job["kind"], job["options"])
                error = None
            except (OllamaUnavailable, MediaError) as exc:
                message, error = str(exc), str(exc)
            except Exception as exc:  # 背景工作不能讓服務停掉
                traceback.print_exc()
                message, error = f"發生錯誤：{exc}", str(exc)
            if self.stop_event.is_set() and not error:
                message = f"已停止。{message}"
            with self.lock:
                self.last = {
                    "kind": job["kind"], "label": job["label"], "message": message, "error": error,
                    "finished_at": datetime.now().isoformat(timespec="seconds"),
                }
                self.current = None

    def _faces_ready(self, kind: str) -> bool:
        from .faces import model_installed

        if kind == "faces":
            return True  # 明確要求時，未下載模型會回報錯誤
        return bool(self.cfg.face_enabled) and model_installed(self.cfg, self.cfg.face_model)

    def _clip_ready(self, kind: str) -> bool:
        from .clip import model_installed

        if kind == "clip":
            return True
        return bool(self.cfg.clip_enabled) and model_installed(self.cfg, self.cfg.clip_model)

    def _run(self, kind: str, opts: dict) -> str:
        conn = db.connect(self.cfg.db_path)
        stop = self.stop_event
        try:
            parts: list[str] = []
            if kind in ("scan", "index"):
                results = scan_all(conn, self.cfg, opts.get("roots"), progress=lambda m: self._update(message=m), stop=stop)
                for r in results:
                    if r.offline:
                        parts.append(f"{r.root}：未連接，已略過")
                    else:
                        parts.append(f"{r.root}：新增 {r.added}、更新 {r.updated}、搬移 {r.moved}、遺失 {r.missing}")
                if not results:
                    parts.append("尚未加入任何資料夾")
            if kind in ("faces", "index") and not stop.is_set() and self._faces_ready(kind):
                from .faces import cluster_faces, detect_faces

                res = detect_faces(conn, self.cfg, ids=opts.get("ids"), stop=stop,
                                   progress=lambda i, n, m: self._update(done=i, total=n, message=f"人臉 {i}/{n}　{m}"))
                c = cluster_faces(conn, self.cfg, stop=stop)
                parts.append(f"人臉：處理 {res.scanned} 張、找到 {res.faces} 張臉、新人物 {c.people_new} 位")
            if kind == "cluster":
                from .faces import recluster

                c = recluster(conn, self.cfg, stop=stop)
                parts.append(f"重新分群：新人物 {c.people_new} 位、歸入 {c.assigned} 張臉")
            if kind == "face_model":
                from .faces import download_model

                name = opts["model"]
                download_model(self.cfg, name, lambda st, d, t: self._update(
                    message=f"{name}：{_fmt_bytes(d)} / {_fmt_bytes(t)}" if t else st, done=d, total=t), stop)
                parts.append(f"人臉模型 {name} 下載完成")
            if kind in ("clip", "index") and not stop.is_set() and self._clip_ready(kind):
                from .clip import index_images

                n = index_images(conn, self.cfg, stop=stop,
                                 progress=lambda i, t, m: self._update(done=i, total=t, message=f"圖像索引 {i}/{t}　{m}"))
                parts.append(f"圖像搜尋索引 {n} 張")
            if kind == "clip_model":
                from .clip import download_model as download_clip

                name = opts["model"]
                download_clip(self.cfg, name, lambda st, d, t: self._update(
                    message=f"{st}：{_fmt_bytes(d)} / {_fmt_bytes(t)}" if t else st, done=d, total=t), stop)
                parts.append(f"圖像搜尋模型 {name} 下載完成")
            if kind in ("analyze", "index") and not stop.is_set() and (kind == "analyze" or not opts.get("skip_ai")):
                res = analyze_images(
                    conn, self.cfg, self.client_factory(),
                    redo=bool(opts.get("redo")), retry_failed=bool(opts.get("retry_failed")),
                    ids=opts.get("ids"), folder=opts.get("folder"), root_id=opts.get("root_id"),
                    album_id=opts.get("album_id"),
                    progress=lambda i, n, m: self._update(done=i, total=n, message=f"{i}/{n}　{m}"),
                    stop=stop,
                )
                parts.append(f"分析 {res.analyzed} 個、失敗 {res.failed} 個" + (f"、向量 {res.embedded} 個" if res.embedded else ""))
            if kind == "dups":
                from .organize import find_duplicates

                res = find_duplicates(conn, self.cfg, stop=stop,
                                      progress=lambda i, n, m: self._update(done=i, total=n, message=f"{m} {i}/{n}"))
                parts.append(f"完全相同 {len(res['exact'])} 組、幾乎一樣 {len(res['similar'])} 組")
            if kind == "stacks":
                from .organize import rebuild_stacks

                parts.append(f"疊放 {rebuild_stacks(conn, self.cfg)} 組")
            if kind == "embed":
                n = embed_images(conn, self.cfg, self.client_factory(), stop=stop)
                parts.append(f"建立語意向量 {n} 個")
            if kind == "pull":
                name = opts["model"]

                def report(status: str, done: int, total: int) -> None:
                    text = f"{name}：{status}"
                    if total:
                        text += f"（{_fmt_bytes(done)} / {_fmt_bytes(total)}）"
                    self._update(message=text, done=done, total=total)

                self.client_factory().pull(name, report, stop)
                parts.append(f"{name} 下載完成")
            return "；".join(parts)
        finally:
            conn.close()
