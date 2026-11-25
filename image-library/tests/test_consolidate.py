"""整理計畫：複製到另一顆硬碟、完整比對確認；不覆蓋、不動原本的檔案；可以標記原本那份為待刪除；可以復原。"""

import unittest
from unittest import mock

from lumilib import actions, consolidate, db, retire

from test_retire import RetireTests


class ConsolidateTests(RetireTests):
    def snapshot_old(self):
        return {str(p): (p.stat().st_size, p.stat().st_mtime_ns) for p in self.old.rglob("*")}

    def propose(self, **kw):
        return actions.propose(self.conn, "consolidate", {"source_root": self.rid, "target_root": self.nid, **kw}, 4)

    def run_plan(self, a):
        payload = __import__("json").loads(self.conn.execute("SELECT payload FROM assistant_actions WHERE id = ?", (a["id"],)).fetchone()[0])
        runner = mock.Mock()
        with mock.patch("lumilib.jobs.current_runner", return_value=runner):
            out = actions.run(self.conn, a["id"], 4)
        self.assertEqual(out["state"], "running")
        self.assertEqual(runner.submit.call_args.args[0], "consolidate")
        res = consolidate.run(self.conn, a["id"], payload)
        actions.finish_consolidate(self.conn, a["id"], res)
        return res, actions.get(self.conn, a["id"])

    def test_copy_only_here_and_verify(self):
        before = self.snapshot_old()
        a = self.propose()
        self.assertTrue(a["file_op"])
        self.assertIn("只在這裡.txt", [e["name"] for e in a["examples"]])
        # 「報告.docx」別顆有一樣大小的：還沒確認前算「可能」，不在「只在這顆上」的清單裡
        res, done = self.run_plan(a)
        self.assertEqual(self.snapshot_old(), before, "原本的檔案不能被改到")
        self.assertEqual(done["state"], "done")
        self.assertEqual(res.copied, 1)
        copied = self.new / "Re'memor 集中" / "uuid:old" / "文件" / "只在這裡.txt"
        self.assertEqual(copied.read_bytes(), b"only" * 100)
        self.assertFalse(list(self.new.rglob(consolidate.TMP_PREFIX + "*")), "不能留下暫存檔")
        s = retire.analyze(self.conn, self.rid)
        self.assertEqual(self.states()["只在這裡.txt"], "copy", "複製好的馬上就算別顆有副本")
        self.assertIn("1 個檔案複製並比對確認一模一樣", done["message"])

    def test_never_overwrites_and_undo(self):
        clash = self.new / "Re'memor 集中" / "uuid:old" / "文件" / "只在這裡.txt"
        clash.parent.mkdir(parents=True)
        clash.write_bytes(b"something else")
        a = self.propose(mark_source=True)
        self.run_plan(a)
        self.assertEqual(clash.read_bytes(), b"something else", "同名但內容不同：不能覆蓋")
        other = clash.with_name("只在這裡 (2).txt")
        self.assertEqual(other.read_bytes(), b"only" * 100)
        marks = self.conn.execute("SELECT path FROM delete_marks").fetchall()
        self.assertEqual([m["path"] for m in marks], ["文件/只在這裡.txt"], "原本那份只放進待刪除，沒有刪掉")
        self.assertTrue((self.old / "文件" / "只在這裡.txt").exists())
        trashed = []
        with mock.patch("lumilib.fileops._send_to_trash", side_effect=lambda p: (trashed.append(p), p.unlink())):
            out = actions.undo(self.conn, a["id"])
        self.assertEqual(out["state"], "undone")
        self.assertEqual([p.name for p in trashed], ["只在這裡 (2).txt"], "復原只動這次複製的那份")
        self.assertEqual(clash.read_bytes(), b"something else")
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM delete_marks").fetchone()[0], 0)

    def test_refuses_same_drive_and_read_only(self):
        self.conn.execute("UPDATE drives SET read_only = 1 WHERE key = 'uuid:new'")
        self.conn.commit()
        with self.assertRaisesRegex(actions.ActionError, "唯讀"):
            self.propose()
        with self.assertRaisesRegex(actions.ActionError, "同一顆"):
            actions.propose(self.conn, "consolidate", {"source_root": self.rid, "target_root": self.rid}, 4)
        with self.assertRaisesRegex(actions.ActionError, "權限"):
            actions.propose(self.conn, "consolidate", {"source_root": self.rid, "target_root": self.nid}, 3)

    def test_folder_and_resume(self):
        a = self.propose(folder="照片")
        self.assertEqual(a["examples"][0]["to"], "Re'memor 集中/uuid:old/照片/a.raw")
        payload = __import__("json").loads(self.conn.execute("SELECT payload FROM assistant_actions WHERE id = ?", (a["id"],)).fetchone()[0])
        consolidate.stage(self.conn, a["id"], payload)
        import threading

        stop = threading.Event()
        stop.set()
        self.assertTrue(consolidate.run(self.conn, a["id"], payload, stop=stop).stopped)
        res = consolidate.run(self.conn, a["id"], payload)  # 接著做
        self.assertEqual(res.copied, 2)
        self.assertEqual(consolidate.counts(self.conn, a["id"])["done"], 2)



if __name__ == "__main__":
    unittest.main()
