"""待辦：硬碟狀況、計畫卡、分類請你確認、待刪除、提醒，集中在一起；數字是「幾件事」。"""

import unittest

from lumilib import actions, db, inbox
from lumilib.scanner import scan_all

from test_catalog import CatalogTestCase
from test_dupes import tree


class InboxTests(CatalogTestCase):
    def setUp(self):
        super().setUp()
        tree(self.tmp / "備份B", {"a/x.txt": b"x" * 10, "b/y.txt": b"y" * 20})
        db.add_root(self.conn, self.tmp / "備份B", "備份B")
        scan_all(self.conn, self.cfg)

    def test_empty(self):
        out = inbox.build(self.conn)
        self.assertEqual(out["total"], 0)
        self.assertEqual(inbox.count(self.conn), 0)

    def test_collects_everything(self):
        actions.propose(self.conn, "category_plan", {"ops": [{"op": "add_category", "name": "教學"}]}, 3)
        fid = self.conn.execute("SELECT id FROM folders WHERE path = 'a'").fetchone()[0]
        self.conn.execute("INSERT OR REPLACE INTO folder_category (folder_id, category, source, confidence, review) VALUES (?, 'work', 'ai', 0.4, 1)", (fid,))
        rid = self.conn.execute("SELECT id FROM roots").fetchone()[0]
        self.conn.execute("INSERT INTO delete_marks (kind, item_id, root_id, path, size, sig, marked_at) VALUES ('file', 1, ?, 'a/x.txt', 10, 'h', ?)",
                          (rid, db.now_iso()))
        self.conn.execute("INSERT INTO drive_health (key, name, status, findings, io_errors) VALUES (?, '備份B', 'fail', '[]', 0)",
                          (f"r:{rid}" if self.conn.execute("SELECT drive_id FROM roots").fetchone()[0] is None else
                           f"d:{self.conn.execute('SELECT drive_id FROM roots').fetchone()[0]}",))
        self.conn.commit()
        out = inbox.build(self.conn)
        self.assertEqual(len(out["health"]), 1)
        self.assertEqual(len(out["actions"]), 1)
        self.assertEqual(out["review"]["count"], 1)
        self.assertEqual(out["review"]["examples"][0]["name"], "a")
        self.assertEqual(len(out["pending"]), 1)
        self.assertEqual(out["total"], 4)
        self.assertEqual(inbox.count(self.conn), 4)


if __name__ == "__main__":
    unittest.main()
