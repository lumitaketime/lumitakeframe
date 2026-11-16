"""重複項目：完整內容比對、重複資料夾、可中斷接續。這些測試守住「不會把不一樣的東西當成重複」。"""

import shutil
import threading
import unittest
from pathlib import Path

from lumilib import db, dupes
from lumilib.scanner import scan_all

from test_catalog import CatalogTestCase


def tree(base: Path, files: dict[str, bytes]) -> Path:
    for rel, data in files.items():
        p = base / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    return base


PHOTOS = {"旅行/a.raw": b"A" * 5000, "旅行/b.raw": b"B" * 7000, "旅行/筆記/n.txt": b"note" * 50, "報告.docx": b"D" * 3000}


class DupesTests(CatalogTestCase):
    def setUp(self):
        super().setUp()
        self.one = tree(self.tmp / "硬碟一" / "2019 備份", PHOTOS).parent
        self.two = tree(self.tmp / "硬碟二" / "舊電腦" / "2019 備份（複製）", PHOTOS).parent.parent
        (self.two / "其他.bin").write_bytes(b"x" * 999)
        db.add_root(self.conn, self.one, "硬碟一")
        db.add_root(self.conn, self.two, "硬碟二")
        scan_all(self.conn, self.cfg)

    def hashes(self):
        return {r["name"]: r["content_hash"] for r in self.conn.execute("SELECT name, content_hash FROM files ORDER BY id")}

    def snapshot(self):
        return {str(p): (p.stat().st_size, p.stat().st_mtime_ns) for p in self.tmp.rglob("*") if "home" not in p.parts}

    def test_nothing_is_confirmed_before_reading_whole_files(self):
        self.assertTrue(all(h is None for h in self.hashes().values()))
        folders = dupes.duplicate_folders(self.conn)
        self.assertEqual((folders["total"], folders["confirmed"], folders["releasable"]), (1, 0, 0))
        g = folders["groups"][0]
        self.assertEqual((g["confirmed"], g["copies"], sorted(i["root"] for i in g["items"])), (False, 2, ["硬碟一", "硬碟二"]))
        self.assertEqual(dupes.duplicate_files(self.conn)["total"], 0)
        self.assertEqual(dupes.duplicate_files(self.conn, pending=True)["total"], 4)
        plan = dupes.compare_plan(self.conn)
        self.assertEqual((plan["small"]["files"], plan["large"]["files"], plan["done"]), (8, 0, 0))

    def test_compare_confirms_and_never_touches_the_drives(self):
        before = self.snapshot()
        res = dupes.run_compare(self.conn)
        self.assertEqual((res.hashed, res.changed, res.unreadable), (8, 0, 0))
        self.assertEqual(self.snapshot(), before)  # 只讀取：大小、修改時間、檔案數都沒變
        self.assertIsNone(self.hashes()["其他.bin"])  # 大小獨一無二的檔案不必讀
        folders = dupes.duplicate_folders(self.conn)
        g = folders["groups"][0]
        self.assertEqual((folders["total"], folders["confirmed"], g["confirmed"], g["name"]), (1, 1, True, "2019 備份"))
        self.assertEqual(g["releasable"], sum(len(v) for v in PHOTOS.values()))
        files = dupes.duplicate_files(self.conn)
        self.assertEqual((files["total"], files["groups"][0]["name"], files["groups"][0]["copies"]), (4, "b.raw", 2))
        self.assertEqual(dupes.duplicate_files(self.conn, pending=True)["total"], 0)
        self.assertTrue(all(g["in_folder"] for g in files["groups"]))  # 這些檔案都在已列出的重複資料夾裡
        (self.one / "單獨一份.raw").write_bytes(b"A" * 5000)  # 和 a.raw 內容相同，但不在重複資料夾裡
        scan_all(self.conn, self.cfg)
        dupes.run_compare(self.conn)
        flags = {g["name"]: g["in_folder"] for g in dupes.duplicate_files(self.conn)["groups"]}
        self.assertEqual((flags["a.raw"], flags["b.raw"]), (False, True))

    def test_same_name_and_size_but_different_content_is_not_a_duplicate(self):
        """最危險的情況：檔名、大小都一樣，內容不同。只看頭尾也分不出來的，要讀完整個檔案才知道。"""
        a = b"S" * 70_000 + b"1" * 10 + b"E" * 70_000
        b = b"S" * 70_000 + b"2" * 10 + b"E" * 70_000  # 只有中間不同
        (self.one / "影片.mov").write_bytes(a)
        (self.two / "影片.mov").write_bytes(b)
        scan_all(self.conn, self.cfg)
        self.assertEqual(dupes.duplicate_files(self.conn, pending=True)["groups"][0]["name"], "影片.mov")  # 先被列為待確認
        dupes.run_compare(self.conn)
        names = {g["name"] for g in dupes.duplicate_files(self.conn)["groups"]}
        self.assertNotIn("影片.mov", names)
        self.assertEqual(dupes.duplicate_files(self.conn, pending=True)["total"], 0)

    def test_folder_with_one_changed_file_is_not_a_duplicate_folder(self):
        (self.two / "舊電腦" / "2019 備份（複製）" / "旅行" / "a.raw").write_bytes(b"Z" * 5000)  # 同名同大小，內容不同
        scan_all(self.conn, self.cfg)
        self.assertEqual(dupes.duplicate_folders(self.conn)["groups"][0]["confirmed"], False)
        dupes.run_compare(self.conn)
        folders = dupes.duplicate_folders(self.conn)
        # 整包不再相同；裡面仍然完全相同的子資料夾「筆記」會單獨列出
        self.assertEqual([(g["name"], g["confirmed"]) for g in folders["groups"]], [("筆記", True)])
        self.assertEqual({g["name"] for g in dupes.duplicate_files(self.conn)["groups"]}, {"b.raw", "n.txt", "報告.docx"})

    def test_nested_duplicates_are_listed_once_and_empty_folders_ignored(self):
        (self.one / "空的").mkdir()
        (self.two / "空的").mkdir()
        scan_all(self.conn, self.cfg)
        dupes.run_compare(self.conn)
        self.assertEqual([g["name"] for g in dupes.duplicate_folders(self.conn)["groups"]], ["2019 備份"])

    def test_stop_and_resume(self):
        stop = threading.Event()
        seen = []

        def progress(done, total, name):
            seen.append(done)
            if len(seen) >= 2:
                stop.set()

        real, dupes.COMMIT_ROWS, dupes.REPORT_SECONDS = dupes.COMMIT_ROWS, 1, 0
        try:
            first = dupes.run_compare(self.conn, progress=progress, stop=stop)
        finally:
            dupes.COMMIT_ROWS, dupes.REPORT_SECONDS = real, 0.5
        self.assertTrue(first.stopped)
        self.assertLess(first.hashed, 8)
        second = dupes.run_compare(self.conn)  # 接著做剩下的，不重做已完成的
        self.assertEqual(first.hashed + second.hashed, 8)
        self.assertEqual(dupes.duplicate_folders(self.conn)["confirmed"], 1)

    def test_unplugged_drive_is_interrupted_not_an_error(self):
        shutil.move(str(self.two), str(self.tmp / "拔掉了"))
        res = dupes.run_compare(self.conn)
        self.assertEqual((res.hashed, res.offline, res.unreadable), (4, 4, 0))
        self.assertEqual(dupes.compare_plan(self.conn)["offline"]["files"], 4)
        self.assertEqual(dupes.duplicate_folders(self.conn)["confirmed"], 0)  # 另一份還沒比對：仍是待確認
        shutil.move(str(self.tmp / "拔掉了"), str(self.two))
        self.assertEqual(dupes.run_compare(self.conn).hashed, 4)
        self.assertEqual(dupes.duplicate_folders(self.conn)["confirmed"], 1)

    def test_file_changed_after_scan_is_skipped_and_rescan_clears_its_hash(self):
        dupes.run_compare(self.conn)
        target = self.one / "2019 備份" / "報告.docx"
        target.write_bytes(b"NEW" * 1000)  # 大小不變，內容與修改時間變了
        scan_all(self.conn, self.cfg)
        row = self.conn.execute("SELECT content_hash FROM files WHERE name = ? AND root_id = 1", ("報告.docx",)).fetchone()
        self.assertIsNone(row[0])  # 舊指紋作廢
        self.assertEqual(dupes.duplicate_folders(self.conn)["confirmed"], 0)
        dupes.run_compare(self.conn)
        self.assertNotIn("報告.docx", {g["name"] for g in dupes.duplicate_files(self.conn)["groups"]})

    def test_api_and_background_job(self):
        from fastapi.testclient import TestClient

        from lumilib.server import create_app

        with TestClient(create_app(self.cfg, start_jobs_on_boot=False), base_url="http://127.0.0.1:8766",
                        client=("127.0.0.1", 1)) as c:
            s = c.get("/api/dupes/summary").json()
            self.assertEqual((s["plan"]["small"]["files"], s["folders"]["confirmed"], s["files"]["pending"]), (8, 0, 4))
            self.assertEqual(c.post("/api/jobs", json={"kind": "compare"}).status_code, 200)
            for _ in range(100):
                if not c.get("/api/jobs").json()["running"]:
                    break
                threading.Event().wait(0.05)
            s = c.get("/api/dupes/summary").json()
            self.assertEqual((s["plan"]["small"]["files"], s["folders"]["confirmed"], s["files"]["confirmed"]), (0, 1, 4))
            g = c.get("/api/dupes/folders").json()["groups"][0]
            self.assertEqual((g["confirmed"], len(g["items"]), g["items"][0]["online"]), (True, 2, True))


class PendingTests(CatalogTestCase):
    """待刪除：標記的規則，以及移到垃圾桶之前的再次驗證。每一個測試都是一種「不可以刪錯」的情況。"""

    def setUp(self):
        super().setUp()
        self.one = tree(self.tmp / "硬碟一" / "2019 備份", PHOTOS).parent
        self.two = tree(self.tmp / "硬碟二" / "複製", PHOTOS).parent
        db.add_root(self.conn, self.one, "硬碟一")
        db.add_root(self.conn, self.two, "硬碟二")
        scan_all(self.conn, self.cfg)
        self.trashed = []
        self.bin = self.tmp / "垃圾桶"
        self.bin.mkdir()

    def trash(self, path):
        self.trashed.append(Path(path).name)
        shutil.move(str(path), str(self.bin / f"{len(self.trashed)}-{Path(path).name}"))

    def file(self, root, name):
        return self.conn.execute("SELECT f.* FROM files f JOIN roots r ON r.id = f.root_id WHERE r.name = ? AND f.name = ?", (root, name)).fetchone()

    def folder(self, root, name):
        return self.conn.execute("SELECT d.* FROM folders d JOIN roots r ON r.id = d.root_id WHERE r.name = ? AND d.name = ?", (root, name)).fetchone()

    def marks(self):
        return [r[0] for r in self.conn.execute("SELECT id FROM delete_marks ORDER BY id")]

    def test_cannot_mark_before_full_comparison(self):
        from lumilib import pending

        a, b = self.file("硬碟一", "a.raw"), self.file("硬碟二", "a.raw")
        with self.assertRaises(pending.MarkError):
            pending.mark(self.conn, "file", [a["id"]], [b["id"]])
        self.assertEqual(self.marks(), [])

    def test_marking_rules(self):
        from lumilib import pending

        dupes.run_compare(self.conn)
        a, b = self.file("硬碟一", "a.raw"), self.file("硬碟二", "a.raw")
        other = self.file("硬碟一", "b.raw")
        for keep, remove in (([], [b["id"]]), ([a["id"]], [a["id"]]), ([a["id"]], [other["id"]])):  # 沒留、留又刪、不同內容
            with self.assertRaises(pending.MarkError):
                pending.mark(self.conn, "file", keep, remove)
        self.assertEqual(pending.mark(self.conn, "file", [a["id"]], [b["id"]]), 1)
        with self.assertRaises(pending.MarkError):  # 剩下的那一份不能再被標記：至少保留一份
            pending.mark(self.conn, "file", [b["id"]], [a["id"]])
        self.assertEqual(self.snapshot_count(), 8)  # 標記不會動到硬碟
        listing = pending.listing(self.conn)
        self.assertEqual((listing["count"], listing["bytes"], listing["drives"][0]["items"][0]["stale"]), (1, 5000, False))
        g = next(g for g in dupes.duplicate_files(self.conn)["groups"] if g["name"] == "a.raw")
        self.assertEqual(sorted(bool(i["mark"]) for i in g["items"]), [False, True])
        self.assertEqual(pending.unmark(self.conn, self.marks()), 1)
        self.assertEqual(pending.listing(self.conn)["count"], 0)

    def snapshot_count(self):
        return sum(1 for p in list(self.one.rglob("*")) + list(self.two.rglob("*")) if p.is_file())

    def test_clean_moves_to_trash_after_verifying_both_copies(self):
        from lumilib import pending

        dupes.run_compare(self.conn)
        a, b = self.file("硬碟一", "a.raw"), self.file("硬碟二", "a.raw")
        pending.mark(self.conn, "file", [a["id"]], [b["id"]])
        res = pending.clean(self.conn, self.marks(), trash=self.trash)
        self.assertEqual((len(res["trashed"]), res["skipped"], res["bytes"]), (1, [], 5000))
        self.assertEqual(self.trashed, ["a.raw"])
        self.assertTrue((self.one / "2019 備份" / "旅行" / "a.raw").exists())  # 保留的那份還在
        self.assertFalse((self.two / "複製" / "旅行" / "a.raw").exists())
        self.assertEqual(self.file("硬碟二", "a.raw")["status"], "missing")
        self.assertEqual(pending.listing(self.conn)["count"], 0)

    def test_skips_when_the_kept_copy_changed_or_is_gone(self):
        from lumilib import pending

        dupes.run_compare(self.conn)
        a, b = self.file("硬碟一", "b.raw"), self.file("硬碟二", "b.raw")
        pending.mark(self.conn, "file", [a["id"]], [b["id"]])
        (self.one / "2019 備份" / "旅行" / "b.raw").write_bytes(b"X" * 7000)  # 保留的那份在標記之後被改了
        res = pending.clean(self.conn, self.marks(), trash=self.trash)
        self.assertEqual((res["trashed"], self.trashed), ([], []))
        self.assertIn("保留的那一份", res["skipped"][0]["reason"])
        (self.one / "2019 備份" / "旅行" / "b.raw").unlink()  # 保留的那份不見了
        self.assertEqual(pending.clean(self.conn, self.marks(), trash=self.trash)["trashed"], [])
        self.assertTrue((self.two / "複製" / "旅行" / "b.raw").exists())  # 唯一剩下的一份沒有被動到

    def test_skips_when_the_marked_copy_changed(self):
        from lumilib import pending

        dupes.run_compare(self.conn)
        a, b = self.file("硬碟一", "報告.docx"), self.file("硬碟二", "報告.docx")
        pending.mark(self.conn, "file", [a["id"]], [b["id"]])
        (self.two / "複製" / "報告.docx").write_bytes(b"NEWVER" * 500)  # 要刪的那份其實被改成新版本了
        res = pending.clean(self.conn, self.marks(), trash=self.trash)
        self.assertEqual((res["trashed"], self.trashed), ([], []))
        scan_all(self.conn, self.cfg)  # 重新掃描後，這個標記顯示為需要重新比對
        self.assertTrue(pending.listing(self.conn)["drives"][0]["items"][0]["stale"])
        self.assertEqual(pending.clean(self.conn, self.marks(), trash=self.trash)["trashed"], [])

    def test_skips_when_the_kept_copy_is_on_an_unplugged_drive(self):
        from lumilib import pending

        dupes.run_compare(self.conn)
        a, b = self.file("硬碟一", "a.raw"), self.file("硬碟二", "a.raw")
        pending.mark(self.conn, "file", [a["id"]], [b["id"]])
        shutil.move(str(self.one), str(self.tmp / "拔掉了"))
        res = pending.clean(self.conn, self.marks(), trash=self.trash)
        self.assertEqual(self.trashed, [])
        self.assertIn("沒有接上", res["skipped"][0]["reason"])

    def test_folder_clean_refuses_when_a_new_file_was_added(self):
        from lumilib import pending

        dupes.run_compare(self.conn)
        keep, remove = self.folder("硬碟一", "2019 備份"), self.folder("硬碟二", "複製")
        pending.mark(self.conn, "folder", [keep["id"]], [remove["id"]])
        (self.two / "複製" / "後來才放進來的.txt").write_text("只有這裡有")  # 掃描之後多了一個檔案
        res = pending.clean(self.conn, self.marks(), trash=self.trash)
        self.assertEqual(self.trashed, [])
        self.assertIn("多了", res["skipped"][0]["reason"])
        (self.two / "複製" / "後來才放進來的.txt").unlink()
        res = pending.clean(self.conn, self.marks(), trash=self.trash)
        self.assertEqual((self.trashed, len(res["trashed"])), (["複製"], 1))
        self.assertTrue((self.one / "2019 備份" / "旅行" / "筆記" / "n.txt").exists())
        self.assertEqual(dupes.duplicate_folders(self.conn)["total"], 0)  # 清掉之後不再列為重複

    def test_read_only_drive_exports_a_list_instead(self):
        from lumilib import pending

        dupes.run_compare(self.conn)
        a, b = self.file("硬碟一", "a.raw"), self.file("硬碟二", "a.raw")
        pending.mark(self.conn, "file", [a["id"]], [b["id"]])
        self.conn.execute("UPDATE drives SET fs_type = 'ntfs'")
        self.conn.commit()
        res = pending.clean(self.conn, self.marks(), trash=self.trash)
        self.assertEqual(self.trashed, [])
        self.assertIn("匯出清單", res["skipped"][0]["reason"])
        drive = pending.listing(self.conn)["drives"][0]
        self.assertTrue(drive["read_only"])
        before = self.snapshot_count()
        out = pending.export_list(self.conn, self.cfg.home, drive["drive"])
        self.assertIn("旅行/a.raw", out.read_text(encoding="utf-8"))
        self.assertTrue(str(out).startswith(str(self.cfg.home)))  # 清單存在 Re'memor 的資料目錄，不寫進硬碟
        self.assertEqual(self.snapshot_count(), before)

    def test_api_requires_explicit_confirmation(self):
        from fastapi.testclient import TestClient

        from lumilib.server import create_app

        dupes.run_compare(self.conn)
        a, b = self.file("硬碟一", "a.raw"), self.file("硬碟二", "a.raw")
        with TestClient(create_app(self.cfg, start_jobs_on_boot=False), base_url="http://127.0.0.1:8766",
                        client=("127.0.0.1", 1)) as c:
            self.assertEqual(c.post("/api/dupes/mark", json={"kind": "file", "keep": [], "remove": [b["id"]]}).status_code, 400)
            self.assertEqual(c.post("/api/dupes/mark", json={"kind": "file", "keep": [a["id"]], "remove": [b["id"]]}).json(), {"marked": 1})
            ids = [i["id"] for d in c.get("/api/pending").json()["drives"] for i in d["items"]]
            self.assertEqual(c.get("/api/drives").json()["pending"], 1)
            self.assertEqual(c.post("/api/pending/trash", json={"ids": ids}).status_code, 400)  # 沒有確認就不做
            self.assertTrue((self.two / "複製" / "旅行" / "a.raw").exists())
            self.assertEqual(c.post("/api/dupes/unmark", json={"ids": ids}).json(), {"unmarked": 1})


if __name__ == "__main__":
    unittest.main()
