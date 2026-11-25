"""背景工作：分成四個通道同時進行，彼此不會互相卡住。

- scan：建目錄（掃描）。每顆硬碟一個工作，不同硬碟同時掃（最多「同時掃描幾顆硬碟」顆，預設 2）；
  同一顆硬碟裡的資料夾依序掃，讀寫頭才不會來回跳。
- main：讀文件文字、文字辨識、比對內容、照片縮圖、人臉、圖像索引、疊放、找重複（依序執行）
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
    "scan": "掃描", "compare": "比對內容", "retire_verify": "確認副本", "consolidate": "複製到另一顆硬碟", "covers": "做文件封面", "reindex_text": "重建搜尋索引", "extract": "讀取文件文字", "ocr": "文字辨識", "analyze": "AI 分析", "index": "掃描並分析", "embed": "建立語意向量", "pull": "下載模型",
    "faces": "人臉辨識", "cluster": "人物分群", "face_model": "下載人臉模型",
    "clip": "建立圖像搜尋索引", "clip_model": "下載圖像搜尋模型",
    "dups": "尋找重複與相似照片", "stacks": "重新計算疊放", "export": "匯出照片",
    "move_catalog": "搬移目錄", "embed_docs": "建立「用意思找」的索引",
    "photos": "整理照片（拍攝資訊與縮圖）", "backup": "備份目錄", "classify": "自動分類", "classify_ai": "AI 分類", "keywords": "找出常見的詞", "classify_review": "AI 看資料夾並分類",
}
LANES = {"analyze": "ai", "embed": "ai", "embed_docs": "ai", "classify_ai": "ai", "classify_review": "ai", "pull": "download", "face_model": "download", "clip_model": "download",
         "scan": "scan", "backup": "catalog"}
QUEUED_LANES = ("main", "ai", "scan")
SCAN_WORKERS = 4  # 「同時掃描幾顆硬碟」最多 4 顆；實際同時跑幾個看設定
DISK_LANES = ("main", "scan")  # 會讀硬碟的通道
_ids = itertools.count(1)


def _target(options: str | None) -> str | None:
    """工作紀錄裡記的「哪一顆硬碟」"""
    try:
        return (json.loads(options or "{}") or {}).get("target")
    except ValueError:
        return None


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


_CURRENT: list = []


def current_runner():
    """伺服器正在用的背景工作（助理要排工作時用）；還沒啟動就是 None。"""
    return _CURRENT[-1] if _CURRENT else None


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
        _CURRENT.append(self)
        self.threads = [threading.Thread(target=self._worker, args=(lane,), daemon=True, name=f"lumilib-{lane}-{i}")
                        for lane in QUEUED_LANES for i in range(SCAN_WORKERS if lane == "scan" else 1)]
        for t in self.threads:
            t.start()

    # ---- 工作紀錄：寫進資料庫，關掉 App 再開仍然看得到；紀錄失敗不影響工作本身 ----
    LOGGED = ("scan", "index", "compare", "retire_verify", "consolidate", "covers", "extract", "ocr", "analyze", "embed_docs", "photos", "classify_ai", "classify_review")
    RESUMABLE = ("scan", "index", "compare", "retire_verify", "consolidate", "covers", "extract", "ocr", "embed_docs", "photos", "classify_ai", "classify_review")

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
            self._log_sql("UPDATE job_log SET state = 'replaced' WHERE kind = ? AND id < ? AND state IN ('interrupted', 'stopped', 'paused') "
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
                 "target": _target(r["options"]),
                 "resumable": r["state"] in ("interrupted", "stopped", "paused") and r["kind"] in self.RESUMABLE} for r in rows]

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
    def _scan_groups(self, roots) -> list[tuple[str, list[int]]]:
        return [(name, ids) for _key, name, ids in self._scan_groups_keyed(roots)]

    def _scan_groups_keyed(self, roots) -> list[tuple[str, str, list[int]]]:
        """要掃的資料夾來源依「實體硬碟」分組：[(硬碟名稱, [資料夾來源編號…])]。同一顆硬碟的放在同一組（依序掃）。"""
        import os

        conn = db.connect(self.cfg.db_path)
        try:
            rows = conn.execute("SELECT r.id, r.name, r.path, r.drive_id, v.name AS drive FROM roots r "
                                "LEFT JOIN drives v ON v.id = r.drive_id ORDER BY r.id").fetchall()
        finally:
            conn.close()
        if roots:
            wanted = {str(n) for n in roots}
            rows = [r for r in rows if r["name"] in wanted or str(r["id"]) in wanted]
        groups: dict = {}
        for r in rows:
            key = ("drive", r["drive_id"]) if r["drive_id"] is not None else None
            if key is None:
                try:
                    key = ("dev", os.stat(r["path"]).st_dev)  # 還沒記下是哪顆硬碟：用掛載的裝置分
                except OSError:
                    key = ("root", r["id"])
            name, ids = groups.setdefault(key, (r["drive"] or r["name"], []))
            ids.append(r["id"])
        return [(f"{k[0]}:{k[1]}", name, ids) for k, (name, ids) in groups.items()]

    def submit(self, kind: str, **options) -> dict:
        if kind not in LABELS:
            raise ValueError(f"未知的工作：{kind}")
        if kind == "scan" and not options.get("_split"):
            # 掃描：每顆硬碟一個工作，不同硬碟可以同時掃
            try:
                groups = self._scan_groups_keyed(options.get("roots"))
            except Exception:  # noqa: BLE001  分不出來就照舊一起掃
                traceback.print_exc()
                groups = []
            if groups:
                snap = None
                for key, name, ids in groups:
                    snap = self.submit("scan", roots=ids, target=name, _split=True, _drive=key)
                return snap
        options.pop("_split", None)
        drive_key = options.pop("_drive", None)
        lane = lane_of(kind)
        job = {"id": next(_ids), "kind": kind, "label": LABELS[kind], "lane": lane, "options": options,
               "model": options.get("model"), "target": options.get("target"), "message": "排隊中…", "done": 0, "total": 0, "error": None,
               "started_at": None, "stop": threading.Event(), "_drive": drive_key}
        with self.wake:
            if self.closed:
                return self.snapshot_locked()
            same = lambda j: j["kind"] == kind and j["options"] == options  # noqa: E731
            if lane in ("download", "catalog"):  # 下載、備份：馬上開始，不排在掃描後面
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

    def pause(self, job_id: int) -> dict:
        """暫停：停在目前的位置，記成「已暫停」，之後按「繼續」從這裡接著做（關掉 App 再開也一樣）；不接著做後續工作。"""
        with self.lock:
            job = self.active.get(job_id)
            if job and job["kind"] in self.RESUMABLE:
                job["_paused"] = True
                job["stop"].set()
                job["message"] = "暫停中…"
            return self.snapshot_locked()

    def snapshot(self) -> dict:
        with self.lock:
            return self.snapshot_locked()

    def snapshot_locked(self) -> dict:
        active = sorted(self.active.values(), key=lambda j: j["id"])
        # 頂端顯示：優先顯示下載與掃描這類較快結束的工作
        order = {"download": 0, "catalog": 0, "scan": 1, "main": 1, "ai": 2}
        current = min(active, key=lambda j: (order[j["lane"]], j["id"])) if active else None
        return {
            "running": bool(active),
            "current": _public(current) if current else None,
            "active": [_public(j) for j in active],
            "queued": [{"id": j["id"], "kind": j["kind"], "label": j["label"], "lane": j["lane"], "target": j["options"].get("target")}
                       for lane in QUEUED_LANES for j in self.queues[lane]],
            "last": self.last,
            "recent": list(self.recent),
            "confirm": self.confirm,
        }

    def close(self) -> None:
        if self in _CURRENT:
            _CURRENT.remove(self)
        with self.wake:
            self.closed = True
            for q in self.queues.values():
                q.clear()
            for job in self.active.values():
                job["stop"].set()
            self.wake.notify_all()

    def stop_disk_work(self, timeout: float = 60) -> bool:
        """停下會讀硬碟的工作（掃描、比對、讀文字、辨識…，主要通道），並清掉排隊中的；等它們真的停了才回來。
        例如從目錄移除一顆硬碟之前用（避免掃描還在寫入那顆硬碟的紀錄）。"""
        import time

        with self.lock:
            for lane in DISK_LANES:
                self.queues[lane].clear()
            for job in self.active.values():
                if job.get("lane") in DISK_LANES:
                    job["stop"].set()
                    job["message"] = "停止中…"
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            with self.lock:
                if not any(j.get("lane") in DISK_LANES for j in self.active.values()):
                    return True
            time.sleep(0.1)
        return False

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

    def scan_limit(self) -> int:
        try:
            return max(1, min(SCAN_WORKERS, int(self.cfg.scan_parallel)))
        except (TypeError, ValueError, AttributeError):
            return 2

    def _next_index(self, lane: str) -> int | None:
        """排隊中下一個可以開始的工作是第幾個；現在不能開始就回傳 None。"""
        if not self.queues[lane]:
            return None
        if lane != "scan":
            return 0
        running = [j for j in self.active.values() if j["lane"] == "scan"]
        # 同時掃描的硬碟數不超過設定（設定改了立刻生效）
        if len(running) >= self.scan_limit():
            return None
        # 同一顆硬碟已經在掃：先讓別顆硬碟的工作開始（同一顆硬碟同時讀兩個地方反而更慢）
        busy = {j.get("_drive") for j in running if j.get("_drive")}
        for i, j in enumerate(self.queues[lane]):
            if not j.get("_drive") or j["_drive"] not in busy:
                return i
        return None

    def _worker(self, lane: str) -> None:
        while True:
            with self.wake:
                while (index := self._next_index(lane)) is None and not self.closed:
                    self.wake.wait(2)
                if self.closed:
                    return
                job = self.queues[lane][index]
                del self.queues[lane][index]
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
        paused = stopped and job.get("_paused")
        if paused and not error:
            message = f"已暫停，按「繼續」會從這裡接著做。{message}"
        elif stopped and not error:
            message = f"已停止。{message}"
        elif job["kind"] in ("scan", "photos") and not error:
            message = self._follow_up(message, after=job["kind"])
        elif job["kind"] == "pull" and not error:
            message = self._after_pull(job["options"].get("model"), message)
        result = job.get("result") or {}
        self._log_state(job, "error" if error else "interrupted" if result.get("interrupted") else "paused" if paused
                        else "stopped" if stopped else "done", message)
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
            self.wake.notify_all()  # 有空位了：排隊中的掃描可以開始

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

    def _follow_up(self, message: str, after: str = "scan") -> str:
        """掃描完自動接著做：人臉、圖像索引，以及開啟「自動分析」時的 AI 分析（各自需要的模型都準備好才做）。"""
        from .analyzer import ai_status

        try:
            conn = db.connect(self.cfg.db_path)
            try:
                st = db.stats(conn)
            finally:
                conn.close()
            if self.cfg.classify_rules_auto:
                self.submit("classify")  # 自動分類（規則，很快；本人同意過才做）
            self.submit("keywords")  # 檔案分析的關鍵字雲（只讀目錄）
            if self.cfg.auto_extract:
                # 讀取文件文字、文字辨識：掃描完自動接著做（只讀取；排在掃描之後，可以停止，下次接著做）
                from .ocr import available as ocr_available
                from .ocr import ocr_plan
                from .textindex import extract_plan

                conn = db.connect(self.cfg.db_path)
                try:
                    todo = extract_plan(conn)["todo"]["files"]
                finally:
                    conn.close()
                if todo:
                    self.submit("extract")
                    message += f"；接著讀取 {todo:,} 份文件的文字"
            # 先建目錄、照片之後再做：還沒做縮圖的照片與影片，排在讀文件文字之後
            from .scanner import photos_plan

            conn = db.connect(self.cfg.db_path)
            try:
                photos_todo = photos_plan(conn)["todo"]
            finally:
                conn.close()
            if photos_todo and after != "photos":  # 做完照片之後不再排一次（只在雲端的照片一直會算在裡面）
                self.submit("photos")
                message += f"；接著替 {photos_todo:,} 張照片與影片做縮圖"
            # 文件封面（PDF 第一頁、電子書封面…）：只讀硬碟，縮圖存在 Re'memor 的資料目錄
            from .covers import plan as covers_plan

            conn = db.connect(self.cfg.db_path)
            try:
                covers_todo = covers_plan(conn)["todo"]
            finally:
                conn.close()
            if covers_todo and after != "covers":
                self.submit("covers")
            if self.cfg.auto_extract:
                from .ocr import available as ocr_available
                from .ocr import ocr_plan

                conn = db.connect(self.cfg.db_path)
                try:
                    ocr_todo = ocr_plan(conn, self.cfg.ocr_scope)["todo"] if ocr_available() else 0
                finally:
                    conn.close()
                if ocr_todo and ocr_available() and self.cfg.ocr_scope != "off":
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
                    if scan and scan.get("folders_total"):
                        # 依上次掃描時有幾個資料夾估計還要多久（第一次掃描不知道總數，不估）
                        upd(message=m, scan=scan, unit="folders", done=scan["folders_done"],
                            total=max(scan["folders_total"], scan["folders_done"] + 1))
                    else:
                        upd(message=m, scan=scan)

                scan_progress.wants_scan = True  # 側邊欄要顯示「哪一顆硬碟正在掃描、進度多少」
                from .health import held_roots

                upd(message="檢查硬碟的健康狀態")
                # 一般的掃描：先建目錄（檔名、大小、資料夾），照片的拍攝資訊與縮圖之後由「整理照片」補做
                results = scan_all(conn, self.cfg, opts.get("roots"), progress=scan_progress, stop=stop,
                                   hold=held_roots(conn, "scan"), photos=kind != "scan")
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
            if kind == "retire_verify":
                from .health import held_roots
                from .retire import describe as describe_retire, verify as retire_verify

                rid = int(opts["root_id"])
                name = (conn.execute("SELECT name FROM roots WHERE id = ?", (rid,)).fetchone() or {"name": ""})["name"]
                res = retire_verify(conn, rid, stop=stop, hold=held_roots(conn, "read"),
                                    progress=lambda done, total, n: upd(done=done, total=total, message=n))
                job["result"] = {"copies": res.copies, "stopped": res.stopped}
                parts.append(describe_retire(res, name))
            if kind == "reindex_text":
                from .textindex import rebuild_index

                res = rebuild_index(conn, stop=stop, progress=lambda done, total, n: upd(done=done, total=total, message=n))
                job["result"] = res
                parts.append(("已停止，下次會重做" if res["stopped"] else f"依目前的語言包重建了 {res['files']:,} 份文件的搜尋索引"))
            if kind == "covers":
                from . import covers
                from .health import held_roots

                res = covers.run(conn, self.cfg.home, stop=stop, hold=held_roots(conn, "read"),
                                 progress=lambda done, total, n: upd(done=done, total=total, message=n))
                job["result"] = res
                parts.append(covers.describe(res))
            if kind == "consolidate":
                import json as _json

                from . import consolidate
                from .actions import finish_consolidate

                aid = int(opts["action_id"])
                row = conn.execute("SELECT payload, state FROM assistant_actions WHERE id = ?", (aid,)).fetchone()
                if row is None or row["state"] not in ("running", "partial", "failed"):
                    raise RuntimeError("這張整理計畫已經不存在或已經復原了")
                payload = _json.loads(row["payload"])
                res = consolidate.run(conn, aid, payload, stop=stop, progress=lambda done, total, n: upd(done=done, total=total, message=n))
                finish_consolidate(conn, aid, res)
                job["result"] = {"copied": res.copied, "stopped": res.stopped}
                parts.append(consolidate.describe(res, payload))
                if res.error:
                    raise RuntimeError(res.error)
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
            if kind == "backup":
                from pathlib import Path as _Path

                from . import __version__
                from . import backup as bk

                dest = _Path(opts["dest"])
                res = bk.create(self.cfg.db_path, self.cfg.home, dest, auto=bool(opts.get("auto")), version=__version__, stop=stop,
                                progress=lambda done, total, name: upd(done=done, total=total, message=name, unit="bytes"))
                if res.path:
                    self.cfg.save_setting("backup_last", datetime.now().isoformat(timespec="seconds"))
                    removed = bk.prune(dest, int(self.cfg.backup_keep or 4)) if opts.get("auto") else []
                    job["result"] = {"path": str(res.path), "bytes": res.bytes}
                    parts.append(f"已備份到「{res.path.name}」（{res.bytes / 1e6:.0f} MB）"
                                 + (f"；舊的自動備份拿掉 {len(removed)} 份，保留最近 {int(self.cfg.backup_keep or 4)} 份" if removed else ""))
                else:
                    parts.append("已停止備份")
            if kind == "classify":
                from .classify import ai_todo, describe_rules, run_rules

                upd(message="依資料夾名稱與內容分類")
                res = run_rules(conn)
                parts.append(describe_rules(res))
                if self.cfg.classify_ai_auto and not opts.get("no_ai") and ai_todo(conn):
                    self.submit("classify_ai")
            if kind == "classify_review":
                from . import llm as llm_mod
                from .classify import describe_review, run_review

                remote = llm_mod.is_remote(self.cfg)
                if remote and not self.cfg.classify_cloud:
                    raise RuntimeError("讓 AI 看資料夾只用這台電腦上的模型；要用雲端服務，請到「設定 → 分類」打開")
                # 暫停後再繼續：從上次開始的時間算起，已經看過的不再看
                since = opts.get("since") or db.now_iso()
                job["options"]["since"] = since
                res = run_review(conn, llm_mod.make_llm(self.cfg, self.client_factory()), words=opts.get("words"), targets=opts.get("targets"),
                                 only_words=bool(opts.get("only_words")), read_text=bool(self.cfg.classify_read_text) and not remote,
                                 since=since, chat_id=opts.get("chat_id"), stop=stop, only_unclassified=bool(opts.get("only_unclassified")),
                                 progress=lambda done, total, name: upd(done=done, total=total, message=name))
                job["result"] = {"looked": res.looked, "suggested": res.suggested, "action_id": res.action_id, "stopped": res.stopped}
                if res.error and not res.looked:
                    raise RuntimeError(describe_review(res))
                text = describe_review(res)
                parts.append(text)
                if opts.get("chat_id"):  # 在對話裡要求的：看完把結果（和計畫卡）放回那段對話
                    from . import chats

                    if chats.exists(conn, opts["chat_id"]):
                        # 助理的回答要等它講完才存進去：等一下（最多一分鐘），讓結果排在回答後面
                        for _ in range(120):
                            last = conn.execute("SELECT role FROM assistant_messages WHERE chat_id = ? ORDER BY created_at DESC, id DESC LIMIT 1",
                                                (int(opts["chat_id"]),)).fetchone()
                            if last is None or last["role"] != "user" or stop.is_set():
                                break
                            time.sleep(0.5)
                        chats.add_message(conn, opts["chat_id"], "assistant", text + ("。請看下面的計畫卡，勾選後按「確認套用」。" if res.action_id else "。"),
                                          [], [], [res.action_id] if res.action_id else [], "")
            if kind == "keywords":
                from .analysis import build_keywords, describe as describe_keywords

                res = build_keywords(conn, stop=stop, progress=lambda done, total, name: upd(done=done, total=total, message=name))
                parts.append(describe_keywords(res))
            if kind == "classify_ai":
                from . import llm as llm_mod
                from .classify import describe_ai, run_ai

                remote = llm_mod.is_remote(self.cfg)
                if remote and not self.cfg.classify_cloud:
                    raise RuntimeError("AI 分類只用這台電腦上的模型；要用雲端服務，請到「設定 → 分類」打開")
                model = llm_mod.make_llm(self.cfg, self.client_factory())
                read_text = bool(self.cfg.classify_read_text) and not remote  # 用雲端時一律不讀文件內容
                res = run_ai(conn, model, read_text=read_text, stop=stop,
                             wait=None if opts.get("now") else (lambda: self._wait_schedule(job)),
                             progress=lambda done, total, name: upd(done=done, total=total, message=name))
                job["result"] = {"asked": res.asked, "classified": res.classified, "review": res.review, "stopped": res.stopped}
                if res.error and not res.asked:
                    raise RuntimeError(describe_ai(res))
                parts.append(describe_ai(res))
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
            if kind == "photos":
                from .health import held_roots
                from .scanner import describe_photos, process_photos

                res = process_photos(conn, self.cfg, stop=stop, hold=held_roots(conn, "read"),
                                     progress=lambda done, total, name: upd(done=done, total=total, message=name))
                job["result"] = {"done": res.done, "interrupted": res.interrupted, "stopped": res.stopped}
                parts.append(describe_photos(res))
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
