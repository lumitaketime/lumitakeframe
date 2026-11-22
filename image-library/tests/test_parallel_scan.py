"""同時掃描好幾顆硬碟：每顆硬碟一個工作，同時進行的不超過設定的顆數；可以暫停、之後接著做。"""

import threading
import time
from unittest import mock

from lumilib import db, jobs as jobs_mod
from lumilib.jobs import JobRunner
from lumilib.scanner import scan_all

from test_catalog import CatalogTestCase


class ParallelScanTests(CatalogTestCase):
    def setUp(self):
        super().setUp()
        for name in ("碟A", "碟B", "碟C"):
            d = self.tmp / name
            (d / "資料夾").mkdir(parents=True)
            for i in range(3):
                (d / "資料夾" / f"{name}-{i}.txt").write_text(name, encoding="utf-8")
            db.add_root(self.conn, d, name)
        self.roots = [(r["id"], r["name"]) for r in self.conn.execute("SELECT id, name FROM roots ORDER BY id")]
        self.running = 0
        self.peak = 0
        self.lock = threading.Lock()

    def slow_scan(self, delay=0.4, until_stopped=False):
        real = scan_all

        def wrapper(conn, cfg, roots=None, **kw):
            with self.lock:
                self.running += 1
                self.peak = max(self.peak, self.running)
            try:
                if until_stopped:
                    kw["stop"].wait(10)
                else:
                    time.sleep(delay)
                return real(conn, cfg, roots, **kw)
            finally:
                with self.lock:
                    self.running -= 1
        return mock.patch.object(jobs_mod, "scan_all", side_effect=wrapper)

    def separate_drives(self, same=()):
        """測試時三個資料夾在同一顆磁碟上：當成三顆不同的硬碟（same 裡的編號當成同一顆）"""
        groups = [("drive:0" if i in same else f"drive:{i}", f"硬碟{i}", [rid]) for i, (rid, _) in enumerate(self.roots)]
        return mock.patch.object(JobRunner, "_scan_groups_keyed", lambda _self, roots: [g for g in groups if not roots or
                                 any(str(x) in (str(g[2][0]), dict(self.roots)[g[2][0]]) for x in roots)])

    def run_all(self, parallel):
        self.cfg.scan_parallel = parallel
        self.cfg.auto_extract = 0
        m = JobRunner(self.cfg)
        try:
            with self.slow_scan(), self.separate_drives():
                snap = m.submit("scan")
                self.assertEqual(sorted(j.get("target") for j in snap["queued"] + snap["active"] if j["kind"] == "scan"),
                                 ["硬碟0", "硬碟1", "硬碟2"])  # 每顆硬碟一個工作
                self.assertTrue(m.wait_idle(30))
        finally:
            m.close()

    def test_two_drives_at_a_time(self):
        self.run_all(2)
        self.assertEqual(self.peak, 2)  # 同時兩顆，不超過設定
        n = self.conn.execute("SELECT COUNT(*) FROM files WHERE status = 'ok'").fetchone()[0]
        self.assertEqual(n, 9)  # 三顆硬碟的檔案都進了目錄，資料庫沒有被同時寫壞
        self.assertEqual(self.conn.execute("PRAGMA integrity_check").fetchone()[0], "ok")

    def test_one_at_a_time_when_set_to_one(self):
        self.run_all(1)
        self.assertEqual(self.peak, 1)

    def test_same_drive_waits_for_its_turn(self):
        """同一顆硬碟上分開加入的兩個資料夾：不同時掃，讓別顆硬碟先開始"""
        self.cfg.scan_parallel = 3
        self.cfg.auto_extract = 0
        m = JobRunner(self.cfg)
        try:
            with self.slow_scan(), self.separate_drives(same=(0, 1)):
                for name in ("碟A", "碟B", "碟C"):
                    m.submit("scan", roots=[name])
                self.assertTrue(m.wait_idle(30))
        finally:
            m.close()
        self.assertEqual(self.peak, 2)  # 設定 3 顆，但其中兩個在同一顆硬碟上

    def test_same_drive_stays_in_one_job(self):
        ids = [rid for rid, _ in self.roots]
        for i, rid in enumerate(ids):
            cur = self.conn.execute("INSERT INTO drives (key, name, last_seen, first_seen) VALUES (?, ?, ?, ?)",
                                    (f"test-{i}", f"硬碟{i}", db.now_iso(), db.now_iso()))
            self.conn.execute("UPDATE roots SET drive_id = ? WHERE id = ?", (cur.lastrowid, rid))
        drive = self.conn.execute("SELECT drive_id FROM roots WHERE id = ?", (ids[0],)).fetchone()[0]
        self.conn.execute("UPDATE roots SET drive_id = ? WHERE id = ?", (drive, ids[1]))  # 前兩個在同一顆硬碟
        self.conn.commit()
        m = JobRunner(self.cfg)
        try:
            groups = m._scan_groups(None)
        finally:
            m.close()
        self.assertEqual(sorted(len(g[1]) for g in groups), [1, 2])

    def test_pause_and_resume(self):
        self.cfg.auto_extract = 0
        m = JobRunner(self.cfg)
        try:
            with self.slow_scan(until_stopped=True), self.separate_drives():
                m.submit("scan", roots=["碟A"])
                for _ in range(100):
                    active = m.snapshot()["active"]
                    if active:
                        break
                    time.sleep(0.05)
                m.pause(active[0]["id"])
                self.assertTrue(m.wait_idle(10))
            hist = m.history()
            self.assertEqual(hist[0]["state"], "paused")
            self.assertTrue(hist[0]["resumable"])
            self.assertEqual(hist[0]["target"], "硬碟0")
            with self.separate_drives():
                m.resume(hist[0]["id"])  # 繼續：從這裡接著做
                self.assertTrue(m.wait_idle(10))
            states = [h["state"] for h in m.history()]
        finally:
            m.close()
        self.assertEqual(states[:2], ["done", "replaced"])  # 做完了，暫停那一筆不再顯示「繼續」
        self.assertIn("碟A-0.txt", [r["name"] for r in self.conn.execute("SELECT name FROM files")])

    def test_api(self):
        from fastapi.testclient import TestClient

        from lumilib.server import create_app

        with TestClient(create_app(self.cfg, start_jobs_on_boot=False), base_url="http://127.0.0.1:8766", client=("127.0.0.1", 1)) as c:
            self.assertEqual(c.post("/api/settings", json={"scan_parallel": 9}).json()["scan_parallel"], 4)  # 最多 4 顆
            self.assertEqual(c.post("/api/settings", json={"scan_parallel": 2}).json()["scan_parallel"], 2)
            act = c.get("/api/activity").json()
            self.assertEqual((act["paused"], act["scan_parallel"]), ([], 2))
            self.assertEqual(c.post("/api/jobs/pause", json={"id": 999}).status_code, 200)  # 沒有這個工作：不出錯
