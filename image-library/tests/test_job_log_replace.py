"""背景工作紀錄：同一種工作重新開始後，之前中斷的那幾筆不再顯示「繼續」（避免一堆重複的待辦）。"""

import json

from lumilib import db
from lumilib.jobs import JobRunner

from test_catalog import CatalogTestCase


class ReplaceTests(CatalogTestCase):
    def test_old_interrupted_entries_are_replaced(self):
        for kind, opts in (("scan", {"roots": None}), ("scan", {"roots": None}), ("extract", {}), ("scan", {"roots": ["B"]})):
            self.conn.execute("INSERT INTO job_log (kind, label, options, state, created_at) VALUES (?, ?, ?, 'interrupted', ?)",
                              (kind, kind, json.dumps(opts), db.now_iso()))
        self.conn.commit()
        m = JobRunner(self.cfg)
        try:
            job = {"kind": "scan", "label": "掃描", "options": {"roots": None}, "message": ""}
            m._log_new(job)
            m._log_state(job, "running")
            states = [(r["kind"], r["options"], r["state"]) for r in self.conn.execute("SELECT * FROM job_log ORDER BY id")]
        finally:
            m.close()
        self.assertEqual([s for k, o, s in states[:4]], ["replaced", "replaced", "interrupted", "replaced"])
        self.assertEqual(states[4][2], "running")
