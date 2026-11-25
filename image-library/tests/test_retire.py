"""硬碟淘汰檢查：只看內容、不看檔名；快速指紋一樣還要完整比對才算副本；同一顆硬碟的另一份不算；全程只讀。"""

import threading
import unittest

from lumilib import db, retire
from lumilib.scanner import scan_all

from test_catalog import CatalogTestCase
from test_dupes import tree

OLD = {
    "照片/a.raw": b"A" * 5000,          # 別顆有（檔名不同）
    "照片/b.raw": b"B" * 7000,          # 別顆有一樣大小、但內容不同
    "文件/報告.docx": b"D" * 300000,    # 別顆有一樣大小、開頭結尾一樣、中間不同
    "文件/只在這裡.txt": b"only" * 100,  # 只有這一顆有
    ".DS_Store": b"x" * 10,             # 系統小檔案
    "空的.txt": b"",
}
MIDDLE = b"D" * 150000 + b"X" + b"D" * 149999  # 和報告.docx 一樣大小、開頭結尾一樣


class RetireTests(CatalogTestCase):
    def setUp(self):
        super().setUp()
        self.old = tree(self.tmp / "老硬碟", OLD)
        self.new = tree(self.tmp / "新硬碟", {"備份/a 的副本.raw": b"A" * 5000, "備份/b.raw": b"C" * 7000, "備份/報告.docx": MIDDLE})
        db.add_root(self.conn, self.old, "老硬碟")
        db.add_root(self.conn, self.new, "新硬碟")
        scan_all(self.conn, self.cfg)
        self.rid = self.conn.execute("SELECT id FROM roots WHERE name = '老硬碟'").fetchone()[0]
        self.nid = self.conn.execute("SELECT id FROM roots WHERE name = '新硬碟'").fetchone()[0]
        # 測試的兩個資料夾其實在同一顆磁碟上：當成兩顆不同的硬碟
        for rid, key in ((self.rid, "uuid:old"), (self.nid, "uuid:new")):
            d = self.conn.execute("INSERT INTO drives (key, name, first_seen, last_seen) VALUES (?, ?, ?, ?)",
                                  (key, key, db.now_iso(), db.now_iso())).lastrowid
            self.conn.execute("UPDATE roots SET drive_id = ? WHERE id = ?", (d, rid))
        self.conn.commit()

    def states(self):
        return {r["name"]: r["state"] for r in self.conn.execute(
            "SELECT f.name, r.state FROM retire_files r JOIN files f ON f.id = r.file_id WHERE r.root_id = ?", (self.rid,))}

    def snapshot(self):
        return {str(p): (p.stat().st_size, p.stat().st_mtime_ns) for p in self.tmp.rglob("*") if "home" not in p.parts}

    def test_catalog_only_first(self):
        s = retire.analyze(self.conn, self.rid)
        # .DS_Store 掃描時就不收進目錄
        self.assertEqual(self.states(), {"a.raw": "maybe", "b.raw": "maybe", "報告.docx": "maybe", "只在這裡.txt": "only", "空的.txt": "junk"})
        self.assertFalse(s["ready"])
        self.assertEqual(s["states"]["only"]["files"], 1)
        self.assertEqual(s["states"]["junk"]["files"], 1)

    def test_verify_reads_only_and_confirms_by_full_content(self):
        before = self.snapshot()
        plan = retire.verify_plan(self.conn, self.rid)
        self.assertEqual(plan["files"], 3)
        self.assertEqual(plan["need"], [])
        r = retire.verify(self.conn, self.rid)
        self.assertEqual(self.snapshot(), before, "確認副本只能讀，不能改到硬碟")
        self.assertEqual((r.copies, r.different), (1, 2))
        st = self.states()
        self.assertEqual(st["a.raw"], "copy")  # 檔名不同也算
        self.assertEqual(st["b.raw"], "only")  # 快速指紋就不一樣
        self.assertEqual(st["報告.docx"], "only")  # 開頭結尾一樣，完整比對才發現不同
        # 快速指紋不同的不必讀完整內容
        b = self.conn.execute("SELECT content_hash, quick_sig FROM files WHERE name = 'b.raw' AND root_id = ?", (self.rid,)).fetchone()
        self.assertIsNone(b["content_hash"])
        self.assertIsNotNone(b["quick_sig"])
        self.assertIn("1 個在別顆硬碟有一模一樣的副本", retire.describe(r))

    def test_same_drive_copy_does_not_count(self):
        drive = self.conn.execute("INSERT INTO drives (key, name, first_seen, last_seen) VALUES ('uuid:1', '同一顆', ?, ?)",
                                  (db.now_iso(), db.now_iso())).lastrowid
        self.conn.execute("UPDATE roots SET drive_id = ?", (drive,))  # 兩個資料夾在同一顆硬碟上
        self.conn.commit()
        retire.analyze(self.conn, self.rid)
        self.assertEqual(self.states()["a.raw"], "only")

    def test_copy_only_on_planned_drive_is_risky(self):
        retire.verify(self.conn, self.rid)
        retire.set_planned(self.conn, self.nid, True)
        s = retire.analyze(self.conn, self.rid)
        self.assertEqual(self.states()["a.raw"], "risky")
        self.assertEqual(s["risky_on"][0]["name"], "uuid:new")
        self.assertIn("也要淘汰", retire.describe_summary(s))

    def test_ready_when_everything_has_copies(self):
        # 只留下別顆有副本的（直接在目錄裡當成沒有這幾個檔案）
        self.conn.execute("UPDATE files SET status = 'missing' WHERE root_id = ? AND name IN ('只在這裡.txt', 'b.raw', '報告.docx')", (self.rid,))
        self.conn.commit()
        retire.verify(self.conn, self.rid)
        s = retire.analyze(self.conn, self.rid)
        self.assertTrue(s["ready"])
        self.assertIn("可以淘汰", retire.describe_summary(s))

    def test_offline_partner_waits(self):
        parked = self.tmp / "拔掉"
        self.new.rename(parked)
        plan = retire.verify_plan(self.conn, self.rid)
        self.assertEqual([n["name"] for n in plan["need"]], ["uuid:new"])
        r = retire.verify(self.conn, self.rid)
        self.assertEqual(r.waiting, 3)
        self.assertEqual(self.states()["a.raw"], "maybe")  # 沒辦法確認：還是「可能」，不會變成「只在這裡」

    def test_stop_and_lists(self):
        stop = threading.Event()
        stop.set()
        self.assertTrue(retire.verify(self.conn, self.rid, stop=stop).stopped)
        f = retire.folders(self.conn, self.rid, "only")
        self.assertEqual(f["folders"][0]["path"], "文件")
        lst = retire.files(self.conn, self.rid, "only")
        self.assertEqual([x["name"] for x in lst["files"]], ["只在這裡.txt"])
        text = retire.export_csv(self.conn, self.rid)
        self.assertIn("只在這裡.txt", text)
        self.assertIn("只有這一顆有", text)

    def test_assistant_tool(self):
        from lumilib import assistant

        out = assistant.tool_retire_check(self.conn, {"drive": "老硬碟"}, assistant.Ctx(level=1))
        self.assertIn("還不能淘汰", out)
        self.assertIn("確認副本", out)
        self.assertIn("找不到", assistant.tool_retire_check(self.conn, {"drive": "不存在"}, assistant.Ctx(level=1)))


if __name__ == "__main__":
    unittest.main()
