"""背景工作：分成三個通道同時進行，彼此不會互相卡住。

- main：掃描、人臉、圖像索引、疊放、找重複（依序執行）
- ai：AI 分析、語意向量（依序執行；可設定只在接電源或夜間進行）
- download：下載模型，每個下載各自進行，可以同時下載好幾個
"""

from __future__ import annotations

import itertools
import json
import threading
import time
import traceback
from collections import deque
from datetime import datetime

from . import db
from .analyzer import OllamaClient, OllamaUnavailable, analyze_images, embed_images
from .config import Config
from .media import MediaError
from .scanner import scan_all

LABELS = {
    "scan": "掃描", "compare": "比對內容", "extract": "讀取文件文字", "ocr": "文字辨識", "analyze": "AI 分析", "index": "掃描並分析", "embed": "建立語意向量", "pull": "下載模型",
    "faces": "人臉辨識", "cluster": "人物分群", "face_model": "下載人臉模型",
    "clip": "建立圖像搜尋索引", "clip_model": "下載圖像搜尋模型",
    "dups": "尋找重複與相似照片", "stacks": "重新計算疊放", "export": "匯出照片",
    "move_catalog": "搬移目錄", "embed_docs": "建立「用意思找」的索引",
}
LANES = {"analyze": "ai", "embed": "ai", "embed_docs": "ai", "pull": "download", "face_model": "download", "clip_model": "download"}
QUEUED_LANES = ("main", "ai")
_ids = itertools.count(1)


def lane_of(kind: str) -> str:
    return LANES.get(kind, "main")


def _fmt_bytes(n: int) -> str:
    return f"{n / 1e9:.1f} GB" if n >= 1e9 else f"{n / 1e6:.0f} MB"


def _public(job: dict) -> dict:
    return {k: v for k, v in job.items() if k not in ("options", "stop") and not k.startswith("_")}


def _estimate(job: dict) -> None:
    """依最近兩分鐘的速度估計還要多久（秒），寫在 job["eta"]；剛開始或沒有進度時不估。"""
    done, total = job.get("done") or 0, job.get("total") or 0
    now = time.monotonic()
    hist = job.get("_hist")
    if hist is None or job.get("_total") != total or (hist and done < hist[-1][1]):
        hist = job["_hist"] = deque(maxlen=400)  # 換了階段（總數變了）就重新計算
        job["_total"] = total
    if not hist or now - hist[-1][0] >= 0.5:
        hist.append((now, done))
    while len(hist) > 2 and now - hist[0][0] > 120:
        hist.popleft()
    t0, d0 = hist[0]
    if total <= 0 or done >= total or now - t0 < 6 or done - d0 < 2:
        job["eta"] = None
        return
    job["eta"] = int((total - done) / ((done - d0) / (now - t0)))


class JobRunner:
    def __init__(self, cfg: Config, client_factory=None):
        self.cfg = cfg
        self.client_factory = client_factory or (lambda: OllamaClient(cfg.ollama_url, cfg.request_timeout))
        self.lock = threading.Lock()
        self.wake = threading.Condition(self.lock)
        self.queues: dict[str, deque] = {lane: deque() for lane in QUEUED_LANES}
        self.active: dict[int, dict] = {}
        self.closed = False
        self.last: dict | None = None
        self.recent: deque = deque(maxlen=8)
        # 「每次先問我」：掃描完有新照片時先記下來，等使用者按「開始」
        self.confirm: dict | None = None
        # 工作結束時要通知的對象（例如清掉伺服器的統計暫存）
        self.on_finish: list = []
        # 上次關掉 App 時還沒做完的工作：標成「已中斷」，使用者可以按「繼續」
        self._log_sql("UPDATE job_log SET state = 'interrupted', message = ?, finished_at = ? WHERE state IN ('queued', 'running')",
                      ("上次關閉 Re'memor 時還沒做完，可以繼續。", db.now_iso()))
        self.threads = [threading.Thread(target=self._worker, args=(lane,), daemon=True, name=f"lumilib-{lane}")
                        for lane in QUEUED_LANES]
        for t in self.threads:
            t.start()

    # ---- 工作紀錄：寫進資料庫，關掉 App 再開仍然看得到；紀錄失敗不影響工作本身 ----
    LOGGED = ("scan", "index", "compare", "extract", "ocr", "analyze", "embed_docs")
    RESUMABLE = ("scan", "index", "compare", "extract", "ocr", "embed_docs")

    def _log_sql(self, sql: str, args: tuple = ()) -> int | None:
        try:
            conn = db.connect(self.cfg.db_path)
            try:
                cur = conn.execute(sql, args)
                conn.commit()
                return cur.lastrowid
            finally:
                conn.close()
        except Exception:  # noqa: BLE001
            traceback.print_exc()
            return None

    def _log_new(self, job: dict) -> None:
        if job["kind"] in self.LOGGED:
            job["_log"] = self._log_sql(
                "INSERT INTO job_log (kind, label, options, state, message, created_at) VALUES (?, ?, ?, 'queued', ?, ?)",
                (job["kind"], job["label"], json.dumps(job["options"], ensure_ascii=False, default=str), job["message"], db.now_iso()))

    def _log_state(self, job: dict, state: str, message: str | None = None) -> None:
        if not job.get("_log"):
            return
        stamp = "started_at" if state == "running" else "finished_at"
        if state in ("running", "done") and job["kind"] in self.RESUMABLE:
            # 這次開始做或做完了：更早之前中斷的同一種工作（範圍相同或這次是全部）會從沒做完的地方接著做，
            # 紀錄裡不再顯示「繼續」，避免一堆重複的待辦
            opts = json.dumps(job["options"], ensure_ascii=False, default=str)
            self._log_sql("UPDATE job_log SET state = 'replaced' WHERE kind = ? AND id < ? AND state IN ('interrupted', 'stopped') "
                          "AND (options = ? OR ? = '{}' OR ? = '{\"roots\": null}')", (job["kind"], job["_log"], opts, opts, opts))
        self._log_sql(f"UPDATE job_log SET state = ?, message = COALESCE(?, message), done = ?, total = ?, {stamp} = ? WHERE id = ?",
                      (state, message, int(job.get("done") or 0), int(job.get("total") or 0), db.now_iso(), job["_log"]))

    def history(self, limit: int = 30) -> list[dict]:
        try:
            conn = db.connect(self.cfg.db_path)
            try:
                rows = conn.execute("SELECT * FROM job_log WHERE state NOT IN ('queued', 'running') ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
            finally:
                conn.close()
        except Exception:  # noqa: BLE001
            return []
        return [{"id": r["id"], "kind": r["kind"], "label": r["label"], "state": r["state"], "message": r["message"],
                 "done": r["done"], "total": r["total"], "started_at": r["started_at"], "finished_at": r["finished_at"],
                 "resumable": r["state"] in ("interrupted", "stopped") and r["kind"] in self.RESUMABLE} for r in rows]

    def resume(self, log_id: int) -> dict:
        """把中斷或停止的掃描、比對重新排進去（它們本來就會從沒做完的地方接著做）。"""
        conn = db.connect(self.cfg.db_path)
        try:
            r = conn.execute("SELECT * FROM job_log WHERE id = ?", (log_id,)).fetchone()
        finally:
            conn.close()
        if r is None or r["kind"] not in self.RESUMABLE:
            raise ValueError("這個工作不能繼續")
        return self.submit(r["kind"], **(json.loads(r["options"] or "{}")))

    # ---- public ----
    def submit(self, kind: str, **options) -> dict:
        if kind not in LABELS:
            raise ValueError(f"未知的工作：{kind}")
        lane = lane_of(kind)
        job = {"id": next(_ids), "kind": kind, "label": LABELS[kind], "lane": lane, "options": options,
               "model": options.get("model"), "message": "排隊中…", "done": 0, "total": 0, "error": None,
               "started_at": None, "stop": threading.Event()}
        with self.wake:
            if self.closed:
                return self.snapshot_locked()
            same = lambda j: j["kind"] == kind and j["options"] == options  # noqa: E731
            if lane == "download":
                # 同一個模型已經在下載就不重複
                if any(same(j) for j in self.active.values()):
                    return self.snapshot_locked()
                job["started_at"] = datetime.now().isoformat(timespec="seconds")
                job["message"] = "準備下載…"
                self.active[job["id"]] = job
                threading.Thread(target=self._execute, args=(job,), daemon=True, name=f"lumilib-dl-{job['id']}").start()
                return self.snapshot_locked()
            # 同樣的工作已在排隊（或 AI 分析已在進行且沒有指定範圍）就不重複加入
            if any(same(j) for j in self.queues[lane]):
                return self.snapshot_locked()
            if kind == "analyze" and not options and any(
                    j["kind"] == "analyze" and not j["options"] for j in self.active.values()):
                return self.snapshot_locked()
            self._log_new(job)  # 先記下來再排進去，工作一開始就找得到自己的紀錄
            self.queues[lane].append(job)
            self.wake.notify_all()
            return self.snapshot_locked()

    def stop(self, job_id: int | None = None) -> dict:
        """停止指定的工作；沒有指定就全部停止並清空排隊。"""
        with self.lock:
            if job_id is not None:
                for q in self.queues.values():
                    for j in list(q):
                        if j["id"] == job_id:
                            q.remove(j)
                job = self.active.get(job_id)
                if job:
                    job["stop"].set()
                    job["message"] = "停止中…"
            else:
                for q in self.queues.values():
                    q.clear()
                for job in self.active.values():
                    job["stop"].set()
                    job["message"] = "停止中…"
            return self.snapshot_locked()

    def snapshot(self) -> dict:
        with self.lock:
            return self.snapshot_locked()

    def snapshot_locked(self) -> dict:
        active = sorted(self.active.values(), key=lambda j: j["id"])
        # 頂端顯示：優先顯示下載與掃描這類較快結束的工作
        order = {"download": 0, "main": 1, "ai": 2}
        current = min(active, key=lambda j: (order[j["lane"]], j["id"])) if active else None
        return {
            "running": bool(active),
            "current": _public(current) if current else None,
            "active": [_public(j) for j in active],
            "queued": [{"id": j["id"], "kind": j["kind"], "label": j["label"], "lane": j["lane"]}
                       for lane in QUEUED_LANES for j in self.queues[lane]],
            "last": self.last,
            "recent": list(self.recent),
            "confirm": self.confirm,
        }

    def close(self) -> None:
        with self.wake:
            self.closed = True
            for q in self.queues.values():
                q.clear()
            for job in self.active.values():
                job["stop"].set()
            self.wake.notify_all()

    def wait_idle(self, timeout: float = 30) -> bool:
        """測試用：等到所有通道都空了。"""
        import time

        end = time.monotonic() + timeout
        while time.monotonic() < end:
            with self.lock:
                if not self.active and not any(self.queues.values()):
                    return True
            time.sleep(0.05)
        return False

    # ---- worker ----
    def _update(self, job: dict, **kw) -> None:
        with self.lock:
            job.update(kw)
            if "done" in kw or "total" in kw:
                _estimate(job)

    def _worker(self, lane: str) -> None:
        while True:
            with self.wake:
                while not self.queues[lane] and not self.closed:
                    self.wake.wait()
                if self.closed:
                    return
                job = self.queues[lane].popleft()
                job["started_at"] = datetime.now().isoformat(timespec="seconds")
                job["message"] = "準備中…"
                self.active[job["id"]] = job
            self._log_state(job, "running")
            self._execute(job)

    def _execute(self, job: dict) -> None:
        error = None
        try:
            message = self._run(job)
        except (OllamaUnavailable, MediaError) as exc:
            message, error = str(exc), str(exc)
        except Exception as exc:  # 背景工作不能讓服務停掉
            traceback.print_exc()
            from .net import describe_error

            message, error = f"發生錯誤：{describe_error(exc)}", describe_error(exc)
        stopped = job["stop"].is_set()
        if stopped and not error:
            message = f"已停止。{message}"
        elif job["kind"] == "scan" and not error:
            message = self._follow_up(message)
        elif job["kind"] == "pull" and not error:
            message = self._after_pull(job["options"].get("model"), message)
        result = job.get("result") or {}
        self._log_state(job, "error" if error else "interrupted" if result.get("interrupted") else "stopped" if stopped else "done", message)
        for fn in list(self.on_finish):
            try:
                fn(job)
            except Exception:  # noqa: BLE001
                traceback.print_exc()
        with self.lock:
            self.last = {
                "id": job["id"], "kind": job["kind"], "label": job["label"], "lane": job["lane"],
                "model": job.get("model"), "message": message, "error": error, "result": job.get("result"),
                "finished_at": datetime.now().isoformat(timespec="seconds"),
            }
            self.recent.appendleft(self.last)
            self.active.pop(job["id"], None)

    def answer_confirm(self, start: bool) -> dict | None:
        """使用者回答「要不要開始分析」：開始就排入分析；稍後就先不問，下次掃描到新照片再問。"""
        with self.lock:
            self.confirm = None
        return self.submit("analyze", confirmed=True) if start else None

    def _wait_schedule(self, job: dict) -> bool:
        """AI 分析每張照片前檢查排程；不在允許的時段就暫停等待。回傳 False 表示要停止。"""
        from .schedule import analysis_allowed

        stop = job["stop"]
        paused = False
        while not stop.is_set():
            ok, reason = analysis_allowed(self.cfg)
            if ok:
                if paused:
                    self._update(job, message="繼續分析…", paused=False)
                return True
            paused = True
            self._update(job, message=f"暫停：{reason}", paused=True)
            stop.wait(30)
        return False

    def _follow_up(self, message: str) -> str:
        """掃描完自動接著做：人臉、圖像索引，以及開啟「自動分析」時的 AI 分析（各自需要的模型都準備好才做）。"""
        from .analyzer import ai_status

        try:
            conn = db.connect(self.cfg.db_path)
            try:
                st = db.stats(conn)
            finally:
                conn.close()
            if self.cfg.auto_extract:
                # 讀取文件文字、文字辨識：掃描完自動接著做（只讀取；排在掃描之後，可以停止，下次接著做）
                from .ocr import available as ocr_available
                from .ocr import ocr_plan
                from .textindex import extract_plan

                conn = db.connect(self.cfg.db_path)
                try:
                    todo = extract_plan(conn)["todo"]["files"]
                    ocr_todo = ocr_plan(conn, self.cfg.ocr_scope)["todo"] if ocr_available() else 0
                finally:
                    conn.close()
                if todo:
                    self.submit("extract")
                    message += f"；接著讀取 {todo:,} 份文件的文字"
                if (todo or ocr_todo) and ocr_available() and self.cfg.ocr_scope != "off":
                    self.submit("ocr")
            if st["faces_pending"] and self._faces_ready("auto"):
                self.submit("faces")
            if st["images"] > st["clip_done"] and self._clip_ready("auto"):
                self.submit("clip")
            if self.cfg.auto_analyze and st["pending"]:
                status = ai_status(self.client_factory(), self.cfg)
                from .schedule import effective

                if status["ready"] and effective(self.cfg)["mode"] == "ask":
                    with self.lock:
                        self.confirm = {"pending": st["pending"], "at": datetime.now().isoformat(timespec="seconds")}
                    message += f"；{st['pending']} 張照片等你確認後開始 AI 分析"
                elif status["ready"]:
                    self.submit("analyze")  # 在 AI 通道執行，不會擋住之後的掃描
                else:
                    message += f"；尚未開始 AI 分析：{status['message']}"
        except Exception as exc:  # noqa: BLE001  後續工作失敗不影響掃描結果
            traceback.print_exc()
            message += f"；無法排入後續工作：{exc}"
        return message

    def _semantic_follow_up(self) -> None:
        """「用意思找文件」開著、模型也在：讀完文字後接著替新的文件建立索引（在 AI 通道，不擋掃描）。"""
        from . import semantic

        if not self.cfg.doc_semantic:
            return
        try:
            model = semantic.model_of(self.cfg)
            if not semantic.model_ready(self.client_factory(), model):
                return
            conn = db.connect(self.cfg.db_path)
            try:
                todo = semantic.plan(conn, model)["todo"]
            finally:
                conn.close()
            if todo:
                self.submit("embed_docs")
        except Exception:  # noqa: BLE001  後續工作失敗不影響讀取結果
            traceback.print_exc()

    def _after_pull(self, model: str | None, message: str) -> str:
        """剛下載好的就是目前選用的視覺模型：有待分析的照片就直接開始。
        剛下載好的是「用意思找文件」的模型：接著建立索引。"""
        from . import semantic
        from .models import same_model

        if model and self.cfg.doc_semantic and same_model(model, semantic.model_of(self.cfg)):
            self._semantic_follow_up()
            return message + "；接著替文件建立「用意思找」的索引"

        if not (model and same_model(model, self.cfg.vision_model) and self.cfg.auto_analyze):
            return message
        try:
            conn = db.connect(self.cfg.db_path)
            try:
                pending = db.stats(conn)["pending"]
            finally:
                conn.close()
            if pending:
                self.submit("analyze")
                message += f"；開始分析 {pending} 個項目"
        except Exception:  # noqa: BLE001
            traceback.print_exc()
        return message

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

    def _run(self, job: dict) -> str:
        kind, opts, stop = job["kind"], job["options"], job["stop"]
        upd = lambda **kw: self._update(job, **kw)  # noqa: E731
        conn = db.connect(self.cfg.db_path)
        try:
            parts: list[str] = []
            if kind == "index":
                opts = {**opts}
            if kind in ("scan", "index"):
                def scan_progress(m, scan=None):
                    upd(message=m, scan=scan)

                scan_progress.wants_scan = True  # 側邊欄要顯示「哪一顆硬碟正在掃描、進度多少」
                from .health import held_roots

                upd(message="檢查硬碟的健康狀態")
                results = scan_all(conn, self.cfg, opts.get("roots"), progress=scan_progress, stop=stop,
                                   hold=held_roots(conn, "scan"))
                upd(scan=None)
                from .scanner import describe

                gone = [r.root for r in results if r.interrupted]
                if gone:  # 掃到一半硬碟被拔掉：不是錯誤，接上後可以繼續
                    job["result"] = {"interrupted": gone}
                for r in results:
                    parts.append(describe(r))
                if not results:
                    parts.append("尚未加入任何資料夾")
            if kind in ("faces", "index") and not stop.is_set() and self._faces_ready(kind):
                from .faces import cluster_faces, detect_faces

                res = detect_faces(conn, self.cfg, ids=opts.get("ids"), stop=stop,
                                   progress=lambda i, n, m: upd(done=i, total=n, message=f"人臉 {i}/{n}　{m}"))
                c = cluster_faces(conn, self.cfg, stop=stop)
                parts.append(f"人臉：處理 {res.scanned} 張、找到 {res.faces} 張臉、新人物 {c.people_new} 位")
            if kind == "compare":
                from .dupes import describe as describe_compare
                from .dupes import run_compare

                from .health import held_roots

                res = run_compare(conn, large=bool(opts.get("large")), stop=stop, hold=held_roots(conn, "read"),
                                  progress=lambda done, total, name: upd(done=done, total=total, message=name, unit="bytes"))
                job["result"] = {"hashed": res.hashed, "interrupted": res.interrupted, "stopped": res.stopped}
                parts.append(describe_compare(res))
            if kind == "move_catalog":
                from pathlib import Path as _Path

                from .location import anchor, describe as describe_move, move_catalog, use_home

                target = _Path(opts["dest"])
                res = move_catalog(self.cfg.db_path, self.cfg.home, target, stop=stop,
                                   progress=lambda done, total, name: upd(done=done, total=total, message=name, unit="bytes"))
                moved = not res.stopped and not res.errors
                if moved:
                    use_home(anchor(), target)
                job["result"] = {"moved": moved, "stopped": res.stopped, "home": str(target)}
                parts.append(describe_move(res, target, self.cfg.home))
            if kind == "extract":
                from .textindex import describe as describe_extract
                from .textindex import run_extract

                from .health import held_roots

                res = run_extract(conn, stop=stop, retry=bool(opts.get("retry_failed")), hold=held_roots(conn, "read"),
                                  progress=lambda done, total, name: upd(done=done, total=total, message=name))
                job["result"] = {"read": res.read, "interrupted": res.interrupted, "stopped": res.stopped}
                parts.append(describe_extract(res))
                if not res.stopped:
                    self._semantic_follow_up()
            if kind == "ocr":
                from .ocr import describe as describe_ocr
                from .ocr import run_ocr

                from .health import held_roots

                res = run_ocr(conn, self.cfg.ocr_scope, self.cfg.ocr_languages, stop=stop, hold=held_roots(conn, "read"),
                              progress=lambda done, total, name: upd(done=done, total=total, message=name))
                job["result"] = {"read": res.read, "interrupted": res.interrupted, "stopped": res.stopped}
                parts.append(describe_ocr(res))
                if not res.stopped and res.read:
                    self._semantic_follow_up()
            if kind == "cluster":
                from .faces import recluster

                c = recluster(conn, self.cfg, stop=stop)
                parts.append(f"重新分群：新人物 {c.people_new} 位、歸入 {c.assigned} 張臉")
            if kind == "face_model":
                from .faces import download_model

                name = opts["model"]
                download_model(self.cfg, name, lambda st, d, t: upd(
                    message=f"{name}：{_fmt_bytes(d)} / {_fmt_bytes(t)}" if t else st, done=d, total=t), stop)
                parts.append(f"人臉模型 {name} 下載完成")
            if kind in ("clip", "index") and not stop.is_set() and self._clip_ready(kind):
                from .clip import index_images

                n = index_images(conn, self.cfg, stop=stop,
                                 progress=lambda i, t, m: upd(done=i, total=t, message=f"圖像索引 {i}/{t}　{m}"))
                parts.append(f"圖像搜尋索引 {n} 張")
            if kind == "clip_model":
                from .clip import download_model as download_clip

                name = opts["model"]
                download_clip(self.cfg, name, lambda st, d, t: upd(
                    message=f"{st}：{_fmt_bytes(d)} / {_fmt_bytes(t)}" if t else st, done=d, total=t), stop)
                parts.append(f"圖像搜尋模型 {name} 下載完成")
            if kind == "index" and not stop.is_set() and not opts.get("skip_ai"):
                self.submit("analyze")  # AI 分析在自己的通道執行，不擋住掃描與人臉
                parts.append("已排入 AI 分析")
            if kind == "analyze" and not stop.is_set():
                res = analyze_images(
                    conn, self.cfg, self.client_factory(),
                    redo=bool(opts.get("redo")), retry_failed=bool(opts.get("retry_failed")),
                    ids=opts.get("ids"), folder=opts.get("folder"), root_id=opts.get("root_id"),
                    album_id=opts.get("album_id"),
                    progress=lambda i, n, m: upd(done=i, total=n, message=f"{i}/{n}　{m}"),
                    stop=stop,
                    wait=lambda: self._wait_schedule(job),
                )
                parts.append(f"分析 {res.analyzed} 個、失敗 {res.failed} 個" + (f"、向量 {res.embedded} 個" if res.embedded else ""))
            if kind == "dups":
                from .organize import find_duplicates

                res = find_duplicates(conn, self.cfg, stop=stop,
                                      progress=lambda i, n, m: upd(done=i, total=n, message=f"{m} {i}/{n}"))
                parts.append(f"完全相同 {len(res['exact'])} 組、幾乎一樣 {len(res['similar'])} 組")
            if kind == "export":
                from .export import export_images

                res = export_images(conn, self.cfg, opts.get("ids") or [], opts.get("export") or {}, stop=stop,
                                    progress=lambda i, t, m: upd(done=i, total=t, message=f"匯出 {i}/{t}　{m}"))
                job["result"] = res
                msg = f"已匯出 {res['exported']} 張到「{res['dest']}」"
                if res.get("raw_copied"):
                    msg += f"（其中 {res['raw_copied']} 個 RAW 原檔）"
                if res["skipped"]:
                    msg += f"；略過 {len(res['skipped'])} 個（{'、'.join(res['skipped'][:3])}）"
                if res["smaller"]:
                    msg += f"；{res['smaller']} 張原圖比指定尺寸小，維持原尺寸"
                parts.append(msg)
            if kind == "stacks":
                from .organize import rebuild_stacks

                parts.append(f"疊放 {rebuild_stacks(conn, self.cfg)} 組")
            if kind == "embed_docs":
                from . import semantic

                res = semantic.run_embed(conn, self.client_factory(), semantic.model_of(self.cfg), stop=stop,
                                         progress=lambda done, total, name: upd(done=done, total=total, message=name))
                job["result"] = {"done": res.done, "stopped": res.stopped}
                if res.error and not res.done:
                    raise RuntimeError(f"沒辦法建立「用意思找」的索引：{res.error}")
                parts.append(semantic.describe(res))
            if kind == "embed":
                n = embed_images(conn, self.cfg, self.client_factory(), stop=stop)
                parts.append(f"建立語意向量 {n} 個")
            if kind == "pull":
                name = opts["model"]

                def report(status: str, done: int, total: int) -> None:
                    text = f"{name}：{status}"
                    if total:
                        text += f"（{_fmt_bytes(done)} / {_fmt_bytes(total)}）"
                    upd(message=text, done=done, total=total)

                self.client_factory().pull(name, report, stop)
                parts.append(f"{name} 下載完成")
            return "；".join(parts)
        finally:
            conn.close()
