"""接上硬碟就接著做：只做沒做完的；本人按停止的不動；拔掉再接上才算「剛接上」。主動提醒只提醒、可以先不要提醒。"""

import json
import unittest
from unittest import mock

from lumilib import autopilot, db, reminders, retire
from lumilib.jobs import JobRunner
from lumilib.scanner import scan_all

from test_catalog import CatalogTestCase
from test_dupes import tree


class FakeRunner:
    RESUMABLE = JobRunner.RESUMABLE

    def __init__(self):
        self.submitted = []

    def snapshot(self):
        return {"active": [], "queued": []}

    def submit(self, kind, **opts):
        self.submitted.append((kind, opts))
        return {}

    @property
    def main(self):
        """讀文字、做封面這類後續工作之外的（這些檔案還沒讀過文字，接上時也會接著讀）"""
        return [x for x in self.submitted if x[0] not in ("extract", "covers")]


class AutopilotTests(CatalogTestCase):
    def setUp(self):
        super().setUp()
        self.drive = tree(self.tmp / "備份B", {"a.txt": b"a" * 100, "b/c.txt": b"c" * 50})
        db.add_root(self.conn, self.drive, "備份B")
        scan_all(self.conn, self.cfg)
        self.rid = self.conn.execute("SELECT id FROM roots").fetchone()[0]
        self.runner = FakeRunner()
        self.watch = autopilot.DriveWatcher(self.cfg, self.runner)

    def log(self, kind, state, options):
        self.conn.execute("INSERT INTO job_log (kind, label, options, state, message, created_at) VALUES (?, ?, ?, ?, '', ?)",
                          (kind, kind, json.dumps(options), state, db.now_iso()))
        self.conn.commit()

    def test_finished_drive_is_not_rescanned(self):
        self.watch.tick()
        self.assertEqual([k for k, _ in self.runner.submitted if k == "scan"], [], "已經掃完的不重掃")

    def test_partial_scan_continues_once(self):
        self.conn.execute("UPDATE roots SET scan_state = 'partial'")
        self.log("scan", "interrupted", {"roots": None})
        self.conn.commit()
        self.assertEqual(self.watch.tick(), [("備份B", ["scan"])], "有掃描時，讀文字等掃完再接著做")
        self.assertEqual(self.runner.submitted, [("scan", {"roots": ["備份B"]})])
        self.watch.tick()
        self.assertEqual(len(self.runner.submitted), 1, "還接著的硬碟不會一直重複排")
        self.assertEqual(autopilot.events(self.conn)[0]["did"], ["scan"])
        self.assertIn("接著掃描", reminders.compute(self.conn)[0]["text"])

    def test_user_stop_is_respected(self):
        self.conn.execute("UPDATE roots SET scan_state = 'partial'")
        self.log("scan", "stopped", {"roots": ["備份B"]})
        self.watch.tick()
        self.assertEqual(self.runner.main, [])
        self.assertIn(("extract", {}), self.runner.submitted, "沒讀完的文字照樣接著讀")

    def test_unplug_and_replug_resumes_interrupted_work(self):
        self.watch.tick()
        parked = self.tmp / "拔掉"
        self.drive.rename(parked)
        self.watch.tick()
        self.log("retire_verify", "interrupted", {"root_id": self.rid, "target": f"retire:{self.rid}"})
        self.log("retire_verify", "interrupted", {"root_id": 999, "target": "retire:999"})  # 別顆的不動
        parked.rename(self.drive)
        self.watch.tick()
        self.assertEqual(self.runner.main, [("retire_verify", {"root_id": self.rid, "target": f"retire:{self.rid}"})])

    def test_setting_off(self):
        self.conn.execute("UPDATE roots SET scan_state = 'partial'")
        self.conn.commit()
        with mock.patch.object(self.cfg, "auto_continue", 0):
            self.watch.tick()
        self.assertEqual(self.runner.submitted, [])

    def test_reminders_and_snooze(self):
        self.conn.execute("INSERT INTO drives (key, name, first_seen, last_seen) VALUES ('uuid:x', 'X', ?, ?)", (db.now_iso(), db.now_iso()))
        retire.set_planned(self.conn, self.rid, True)
        retire.analyze(self.conn, self.rid)
        items = reminders.compute(self.conn)
        r = next(x for x in items if x["kind"] == "retire")
        self.assertIn("只在它上面", r["text"])
        reminders.snooze(self.conn, r["key"])
        self.assertFalse(any(x["key"] == r["key"] for x in reminders.compute(self.conn)))
        self.conn.execute("UPDATE roots SET last_scan = '2020-01-01T00:00:00+00:00'")
        self.assertTrue(any(x["kind"] == "stale" for x in reminders.compute(self.conn)))


if __name__ == "__main__":
    unittest.main()
