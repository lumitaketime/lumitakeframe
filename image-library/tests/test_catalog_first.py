"""先建目錄、照片之後再做：掃描只記檔名與大小，照片的拍攝資訊與縮圖由「整理照片」工作補做，可以停止、接著做。"""

import threading

from PIL import Image

from lumilib import db
from lumilib.jobs import JobRunner
from lumilib.scanner import photos_plan, process_photos, scan_all

from test_catalog import CatalogTestCase


class CatalogFirstTests(CatalogTestCase):
    def setUp(self):
        super().setUp()
        d = self.drive = self.tmp / "照片碟"
        for folder in ("2019", "2020"):
            (d / folder).mkdir(parents=True)
            for i in range(30):
                Image.new("RGB", (64, 48), (i * 5, 80, 160)).save(d / folder / f"{i:02d}.jpg")
        (d / "說明.txt").write_text("x", encoding="utf-8")
        db.add_root(self.conn, d, "照片碟")

    def images(self):
        return self.conn.execute("SELECT COUNT(*) FROM images WHERE status = 'ok'").fetchone()[0]

    def test_scan_then_photos(self):
        r = scan_all(self.conn, self.cfg, photos=False)[0]
        self.assertTrue(r.complete)
        self.assertEqual(r.files, 61)  # 目錄已經完整
        self.assertEqual(r.photos_later, 60)
        self.assertEqual(self.images(), 0)  # 還沒做縮圖
        self.assertEqual(photos_plan(self.conn)["todo"], 60)

        stop = threading.Event()
        seen = []

        def progress(done, total, name):
            seen.append((done, total))
            if done >= 30:
                stop.set()

        p = process_photos(self.conn, self.cfg, progress=progress, stop=stop)
        self.assertTrue(p.stopped)
        self.assertGreater(self.images(), 0)
        self.assertLess(self.images(), 60)
        self.assertEqual(seen[0][1], 60)  # 知道總共要做幾張（估計剩餘時間用）
        p2 = process_photos(self.conn, self.cfg)  # 接著做完
        self.assertFalse(p2.stopped)
        self.assertEqual(self.images(), 60)
        self.assertEqual(photos_plan(self.conn)["todo"], 0)
        linked = self.conn.execute("SELECT COUNT(*) FROM files WHERE image_id IS NOT NULL").fetchone()[0]
        self.assertEqual(linked, 60)

        # 刪掉一張照片：下次掃描（先建目錄）就標成遺失，不用等縮圖
        (self.drive / "2019" / "00.jpg").unlink()
        scan_all(self.conn, self.cfg, photos=False)
        self.assertEqual(self.images(), 59)

    def test_job_runs_photos_after_scan_with_eta(self):
        runner = JobRunner(self.cfg)
        try:
            runner.submit("scan")
            self.assertTrue(runner.wait_idle(60))
            done = {j["kind"]: j for j in reversed(runner.recent)}
        finally:
            runner.close()
        self.assertIn("photos", done)
        self.assertIn("做縮圖", done["scan"]["message"])
        self.assertEqual(self.images(), 60)
        # 第二次掃描：知道上次有幾個資料夾，可以估計剩餘時間
        seen = []

        def progress(message, scan=None):
            seen.append(scan)

        progress.wants_scan = True
        scan_all(self.conn, self.cfg, progress=progress, photos=False)
        self.assertTrue(any(s and s["folders_total"] == 3 for s in seen))
