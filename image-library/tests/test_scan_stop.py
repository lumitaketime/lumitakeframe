"""掃描時按「停止」要馬上停：做照片縮圖做到一半也一樣；做完的保留，沒做的下次掃描再做。"""

import threading

from PIL import Image

from lumilib import db
from lumilib.scanner import scan_all

from test_catalog import CatalogTestCase


class ScanStopTests(CatalogTestCase):
    def test_stop_during_thumbnails(self):
        d = self.tmp / "照片碟" / "旅行"
        d.mkdir(parents=True)
        for i in range(120):
            Image.new("RGB", (320, 240), (i, 100, 200)).save(d / f"{i:03d}.jpg")
        db.add_root(self.conn, self.tmp / "照片碟", "照片碟")
        stop = threading.Event()
        seen = []

        def progress(message, scan=None):
            seen.append(message)
            if "做縮圖" in message:
                stop.set()  # 第一批照片開始做縮圖時按停止

        r = scan_all(self.conn, self.cfg, progress=progress, stop=stop)[0]
        self.assertTrue(r.stopped)
        made = self.conn.execute("SELECT COUNT(*) FROM images").fetchone()[0]
        self.assertLess(made, 120)  # 沒有把整個資料夾做完才停
        self.assertTrue(any("做縮圖" in m for m in seen))  # 進度上看得到正在做縮圖
        # 下次掃描接著做完
        r2 = scan_all(self.conn, self.cfg)[0]
        self.assertTrue(r2.complete)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM images").fetchone()[0], 120)
