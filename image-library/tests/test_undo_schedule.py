"""合併可以復原（人物、寵物）、分析排程（星期、時段、條件）、每次先問我。"""

import shutil
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

import numpy as np
from PIL import Image

from lumilib import db, schedule
from lumilib.config import load_config
from lumilib.scanner import scan_all


class UndoMergeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        photos = self.tmp / "p"
        photos.mkdir()
        for i in range(4):
            Image.new("RGB", (64, 48), (i * 40, 80, 120)).save(photos / f"{i}.jpg")
        self.cfg = load_config(self.tmp / "home")
        self.conn = db.connect(self.cfg.db_path)
        db.add_root(self.conn, photos)
        scan_all(self.conn, self.cfg)
        ids = [r[0] for r in self.conn.execute("SELECT id FROM images ORDER BY id")]
        now = db.now_iso()
        vec = np.ones(512, dtype=np.float32).tobytes()
        self.p1 = self.conn.execute("INSERT INTO persons (name, created_at, updated_at) VALUES ('廖添丁', ?, ?)", (now, now)).lastrowid
        self.p2 = self.conn.execute("INSERT INTO persons (name, groups, created_at, updated_at) VALUES ('阿明', '[\"客戶\"]', ?, ?)", (now, now)).lastrowid
        for i, pid in ((ids[0], self.p1), (ids[1], self.p1), (ids[2], self.p2), (ids[3], self.p2)):
            self.conn.execute("INSERT INTO faces (image_id, person_id, embedding, model, manual, created_at) VALUES (?, ?, ?, 'm', ?, ?)",
                              (i, pid, vec, 1 if i == ids[3] else 0, now))
        self.conn.commit()

    def tearDown(self):
        self.conn.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_api_merge_and_undo(self):
        from fastapi.testclient import TestClient

        from lumilib.server import create_app

        app = create_app(self.cfg, start_jobs_on_boot=False)
        with TestClient(app, base_url="http://127.0.0.1:8766", client=("127.0.0.1", 50000)) as client:
            res = client.post("/api/people/merge", json={"target": self.p1, "sources": [self.p2]}).json()
            self.assertTrue(res["undo"])
            people = client.get("/api/people").json()
            self.assertEqual([(p["name"], p["count"]) for p in people], [("廖添丁", 4)])
            self.assertEqual(client.get("/api/search", params={"q": "阿明", "smart": 0}).json()["total"], 0)
            back = client.post("/api/people/unmerge", json={"undo": res["undo"]}).json()
            self.assertEqual(back["restored"], [self.p2])
            people = {p["name"]: p for p in client.get("/api/people").json()}
            self.assertEqual(people["阿明"]["count"], 2)
            self.assertEqual(people["阿明"]["groups"], ["客戶"])
            self.assertEqual(people["廖添丁"]["count"], 2)
            manual = self.conn.execute("SELECT manual FROM faces WHERE person_id = ? ORDER BY id", (self.p2,)).fetchall()
            self.assertEqual([m[0] for m in manual], [0, 1])
            self.assertEqual(client.get("/api/search", params={"q": "阿明", "smart": 0}).json()["total"], 2)
            # 同一個代碼不能用兩次
            self.assertEqual(client.post("/api/people/unmerge", json={"undo": res["undo"]}).status_code, 410)


class ScheduleTests(unittest.TestCase):
    def setUp(self):
        self.cfg = load_config(Path(tempfile.mkdtemp()))
        schedule._cache.clear()

    def at(self, text):
        return datetime.fromisoformat(text)

    def test_days_and_overnight_window(self):
        c = self.cfg
        c.analyze_schedule, c.schedule_days, c.schedule_start, c.schedule_end, c.schedule_ac = "schedule", "12345", "22:00", "07:00", 0
        self.assertTrue(schedule.analysis_allowed(c, self.at("2026-11-02T23:00"))[0])   # 週一晚上
        self.assertTrue(schedule.analysis_allowed(c, self.at("2026-11-07T03:00"))[0])   # 週五晚上延續到週六清晨
        self.assertFalse(schedule.analysis_allowed(c, self.at("2026-11-07T23:00"))[0])  # 週六晚上
        self.assertFalse(schedule.analysis_allowed(c, self.at("2026-11-03T12:00"))[0])  # 白天
        self.assertEqual(schedule.describe(schedule.effective(c)), "週一至週五 22:00–07:00")

    def test_conditions(self):
        c = self.cfg
        c.analyze_schedule, c.schedule_start, c.schedule_end = "schedule", "00:00", "00:00"
        c.schedule_ac, c.schedule_idle, c.schedule_battery = 1, 10, 0
        noon = self.at("2026-11-03T12:00")
        with mock.patch.object(schedule, "on_ac_power", return_value=False):
            ok, why = schedule.analysis_allowed(c, noon)
            self.assertFalse(ok)
            self.assertIn("電池", why)
        with mock.patch.object(schedule, "on_ac_power", return_value=True), mock.patch.object(schedule, "idle_minutes", return_value=2.0):
            ok, why = schedule.analysis_allowed(c, noon)
            self.assertFalse(ok)
            self.assertIn("閒置", why)
        with mock.patch.object(schedule, "on_ac_power", return_value=True), mock.patch.object(schedule, "idle_minutes", return_value=30.0):
            self.assertTrue(schedule.analysis_allowed(c, noon)[0])
        c.schedule_ac, c.schedule_idle, c.schedule_battery = 0, 0, 50
        with mock.patch.object(schedule, "on_ac_power", return_value=False), mock.patch.object(schedule, "battery_percent", return_value=30):
            self.assertFalse(schedule.analysis_allowed(c, noon)[0])
        self.assertIn("全天", schedule.describe(schedule.effective(c)))

    def test_legacy_modes(self):
        c = self.cfg
        c.analyze_schedule, c.night_start, c.night_end = "ac_night", 23, 6
        s = schedule.effective(c)
        self.assertEqual((s["mode"], s["start"], s["end"], s["ac"]), ("schedule", "23:00", "06:00", True))
        c.analyze_schedule = "always"
        self.assertTrue(schedule.analysis_allowed(c, self.at("2026-11-03T12:00"))[0])

    def test_ask_mode_waits_for_answer(self):
        from lumilib.jobs import JobRunner

        c = self.cfg
        c.analyze_schedule, c.auto_analyze = "ask", 1
        runner = JobRunner(c)
        try:
            with mock.patch("lumilib.analyzer.ai_status", return_value={"ready": True, "message": ""}), \
                 mock.patch.object(db, "stats", return_value={"faces_pending": 0, "images": 0, "clip_done": 0, "pending": 5}), \
                 mock.patch.object(runner, "submit") as submit:
                msg = runner._follow_up("掃描完成")
                self.assertIn("確認", msg)
                self.assertEqual(runner.snapshot()["confirm"]["pending"], 5)
                self.assertFalse(any(call.args[0] == "analyze" for call in submit.call_args_list))
                runner.answer_confirm(True)
                self.assertIsNone(runner.snapshot()["confirm"])
                submit.assert_called_with("analyze", confirmed=True)
        finally:
            runner.close()


if __name__ == "__main__":
    unittest.main()
