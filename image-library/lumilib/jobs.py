"""背景工作：分成三個通道同時進行，彼此不會互相卡住。

- main：掃描、人臉、圖像索引、疊放、找重複（依序執行）
- ai：AI 分析、語意向量（依序執行；可設定只在接電源或夜間進行）
- download：下載模型，每個下載各自進行，可以同時下載好幾個
"""

from __future__ import annotations

import itertools
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
    "pets": "寵物辨識", "pet_cluster": "寵物分群", "pet_model": "下載寵物辨識模型",
    "clip": "建立圖像搜尋索引", "clip_model": "下載圖像搜尋模型",
    "dups": "尋找重複與相似照片", "stacks": "重新計算疊放",
    "quality": "品質檢查（模糊、曝光）", "export": "匯出照片",
    "exif": "修改照片資訊", "exif_undo": "復原照片資訊",
}
LANES = {"analyze": "ai", "embed": "ai", "pull": "download", "face_model": "download", "clip_model": "download", "pet_model": "download"}
QUEUED_LANES = ("main", "ai")
_ids = itertools.count(1)


def lane_of(kind: str) -> str:
    return LANES.get(kind, "main")


def _fmt_bytes(n: int) -> str:
    return f"{n / 1e9:.1f} GB" if n >= 1e9 else f"{n / 1e6:.0f} MB"


def _public(job: dict) -> dict:
    return {k: v for k, v in job.items() if k not in ("options", "stop")}


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
        self.threads = [threading.Thread(target=self._worker, args=(lane,), daemon=True, name=f"lumilib-{lane}")
                        for lane in QUEUED_LANES]
        for t in self.threads:
            t.start()

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
        elif job["kind"] == "pet_model" and not error and self._pets_ready("auto"):
            self.submit("pets")
            message += "；開始辨識寵物"
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
        """掃描完自動接著做：人臉、圖像索引、AI 分析（各自需要的模型都準備好才做）。"""
        from .analyzer import ai_status

        try:
            conn = db.connect(self.cfg.db_path)
            try:
                st = db.stats(conn)
            finally:
                conn.close()
            if st["faces_pending"] and self._faces_ready("auto"):
                self.submit("faces")
            if self._pets_ready("auto"):
                conn = db.connect(self.cfg.db_path)
                try:
                    need_pets = conn.execute(
                        "SELECT 1 FROM images WHERE status = 'ok' AND media_type = 'photo' AND (pets_at IS NULL OR pets_model IS NOT ?) LIMIT 1",
                        (self.cfg.pet_model,),
                    ).fetchone()
                finally:
                    conn.close()
                if need_pets:
                    self.submit("pets")
            if st["images"] > st["clip_done"] and self._clip_ready("auto"):
                self.submit("clip")
            conn = db.connect(self.cfg.db_path)
            try:
                need_quality = conn.execute(
                    "SELECT 1 FROM images WHERE status = 'ok' AND media_type = 'photo' AND quality_at IS NULL LIMIT 1"
                ).fetchone()
            finally:
                conn.close()
            if need_quality:
                self.submit("quality")  # 本機計算，很快
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

    def _after_pull(self, model: str | None, message: str) -> str:
        """剛下載好的就是目前選用的視覺模型：有待分析的照片就直接開始。"""
        from .models import same_model

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

    def _pets_ready(self, kind: str) -> bool:
        from .petid import model_installed

        if kind == "pets":
            return True
        return bool(self.cfg.pet_enabled) and model_installed(self.cfg, self.cfg.pet_model)

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
                results = scan_all(conn, self.cfg, opts.get("roots"), progress=lambda m: upd(message=m), stop=stop)
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
                                   progress=lambda i, n, m: upd(done=i, total=n, message=f"人臉 {i}/{n}　{m}"))
                c = cluster_faces(conn, self.cfg, stop=stop)
                parts.append(f"人臉：處理 {res.scanned} 張、找到 {res.faces} 張臉、新人物 {c.people_new} 位")
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
            if kind in ("pets", "index") and not stop.is_set() and self._pets_ready(kind):
                from .petid import cluster_pets, detect_pets

                res = detect_pets(conn, self.cfg, ids=opts.get("ids"), stop=stop,
                                  progress=lambda i, n, m: upd(done=i, total=n, message=f"寵物 {i}/{n}　{m}"))
                c = cluster_pets(conn, self.cfg, stop=stop)
                parts.append(f"寵物：處理 {res.scanned} 張、找到 {res.animals} 隻貓狗、新寵物 {c.pets_new} 隻")
            if kind == "pet_cluster":
                from .petid import recluster as pet_recluster

                c = pet_recluster(conn, self.cfg, stop=stop)
                parts.append(f"重新分群：新寵物 {c.pets_new} 隻、歸入 {c.assigned} 張")
            if kind == "pet_model":
                from .petid import download_model as download_pets

                name = opts["model"]
                download_pets(self.cfg, name, lambda st, d, t: upd(
                    message=f"{st}：{_fmt_bytes(d)} / {_fmt_bytes(t)}" if t else st, done=d, total=t), stop)
                parts.append("寵物辨識模型下載完成")
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
            if kind == "exif":
                from .exifedit import apply_edits

                res = apply_edits(conn, self.cfg, opts["ids"], opts["changes"], stop=stop,
                                  progress=lambda i, n, m: upd(done=i, total=n, message=f"{i}/{n}　{m}"))
                job["result"] = res
                parts.append(f"已修改 {res['done']} 張" + (f"、{len(res['errors'])} 張失敗" if res["errors"] else "")
                             + (f"、{res['skipped']} 張不用改" if res["skipped"] else ""))
                if res["errors"]:
                    parts.append("；".join(res["errors"][:3]))
            if kind == "exif_undo":
                from .exifedit import undo_batch

                res = undo_batch(conn, self.cfg, int(opts["batch"]), stop=stop,
                                 progress=lambda i, n, m: upd(done=i, total=n, message=f"{i}/{n}"))
                parts.append(f"已復原 {res['done']} 張" + (f"、{len(res['errors'])} 張失敗" if res["errors"] else ""))
            if kind == "dups":
                from .organize import find_duplicates

                res = find_duplicates(conn, self.cfg, stop=stop,
                                      progress=lambda i, n, m: upd(done=i, total=n, message=f"{m} {i}/{n}"))
                parts.append(f"完全相同 {len(res['exact'])} 組、幾乎一樣 {len(res['similar'])} 組")
            if kind == "quality":
                from .quality import check_images

                n = check_images(conn, self.cfg, ids=opts.get("ids"), redo=bool(opts.get("redo")), stop=stop,
                                 progress=lambda i, t, m: upd(done=i, total=t, message=f"品質檢查 {i}/{t}　{m}"))
                parts.append(f"檢查 {n} 張照片的清晰度與曝光")
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
