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


if __name__ == "__main__":
    unittest.main()
