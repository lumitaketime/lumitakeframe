"""文字辨識：哪些檔案要辨識、結果放進全文索引、可中斷接續。不是 Mac 時用假的辨識結果測流程；在 Mac 上另外真的辨識一張圖。"""

import shutil
import sys
import threading
import unittest
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from lumilib import db, ocr, textindex
from lumilib.scanner import scan_all

from test_catalog import CatalogTestCase, photo


class OcrFlowTests(CatalogTestCase):
    def setUp(self):
        super().setUp()
        d = self.drive = self.tmp / "相片碟"
        d.mkdir()
        Image.new("RGB", (200, 100), (255, 255, 255)).save(d / "掃描合約.pdf")  # 沒有文字層
        Image.new("RGB", (120, 80), (250, 250, 250)).save(d / "Screenshot 2024-05-01.png")
        Image.new("RGB", (120, 80), (240, 240, 240)).save(d / "介面.png")  # PNG、沒有相機資訊：當成截圖
        photo(d / "旅行" / "海邊.jpg")
        shutil.copy(Path(__file__).parent / "fixtures" / "docs" / "report.pdf", d / "有文字的.pdf")
        self.root = db.add_root(self.conn, d, "相片碟")
        scan_all(self.conn, self.cfg)
        textindex.run_extract(self.conn)
        self.seen = []
        self.real, ocr.recognize = ocr.recognize, self.fake

    def tearDown(self):
        ocr.recognize = self.real
        super().tearDown()

    def fake(self, data, languages):
        self.seen.append(len(data))
        return f"辨識出來的文字 第{len(self.seen)}次 receipt"

    def names(self, query):
        ids = textindex.text_matches(self.conn, query)
        return sorted(r[0] for r in self.conn.execute(f"SELECT name FROM files WHERE id IN ({','.join('?' * len(ids))})", ids)) if ids else []

    def test_default_scope_is_scans_and_screenshots(self):
        plan = ocr.ocr_plan(self.conn, "scans")
        self.assertEqual(plan["todo"], 3)  # 掃描的 PDF、兩張截圖；一般照片與有文字層的 PDF 不辨識
        before = {p: p.stat().st_mtime_ns for p in self.drive.rglob("*")}
        res = ocr.run_ocr(self.conn, "scans", force=True)
        self.assertEqual({p: p.stat().st_mtime_ns for p in self.drive.rglob("*")}, before)  # 只讀取
        self.assertEqual((res.read, res.failed), (3, 0))
        self.assertEqual(self.names("辨識出來的文字"), ["Screenshot 2024-05-01.png", "介面.png", "掃描合約.pdf"])
        self.assertEqual(ocr.ocr_plan(self.conn, "scans")["todo"], 0)
        self.assertEqual(ocr.ocr_plan(self.conn, "all")["todo"], 1)  # 「所有照片」再加上海邊.jpg
        self.assertEqual(ocr.run_ocr(self.conn, "off", force=True).read, 0)

    def test_stop_resume_and_unplug(self):
        stop = threading.Event()
        real = (ocr.COMMIT_ROWS, ocr.REPORT_SECONDS)
        ocr.COMMIT_ROWS, ocr.REPORT_SECONDS = 1, 0
        try:
            first = ocr.run_ocr(self.conn, "scans", force=True, stop=stop, progress=lambda d, t, n: d >= 2 and stop.set())
        finally:
            ocr.COMMIT_ROWS, ocr.REPORT_SECONDS = real
        self.assertTrue(first.stopped)
        self.assertTrue(0 < ocr.ocr_plan(self.conn, "scans")["todo"] < 3)
        shutil.move(str(self.drive), str(self.tmp / "拔掉了"))
        res = ocr.run_ocr(self.conn, "scans", force=True)
        self.assertEqual((res.read, res.failed), (0, 0))
        self.assertGreater(res.offline, 0)
        shutil.move(str(self.tmp / "拔掉了"), str(self.drive))
        ocr.run_ocr(self.conn, "scans", force=True)
        self.assertEqual(ocr.ocr_plan(self.conn, "scans")["todo"], 0)

    def test_not_a_mac_does_nothing(self):
        if sys.platform == "darwin":
            self.skipTest("這台是 Mac")
        res = ocr.run_ocr(self.conn, "scans")
        self.assertTrue(res.unavailable)
        self.assertEqual(self.seen, [])
        self.assertIn("Mac", ocr.describe(res))


@unittest.skipUnless(ocr.available(), "只有 Mac 能用 Apple Vision 辨識")
class VisionTests(unittest.TestCase):
    def test_recognizes_english_and_chinese(self):
        img = Image.new("RGB", (900, 260), "white")
        draw = ImageDraw.Draw(img)
        draw.text((30, 30), "Hello Vision 2008", fill="black", font=ImageFont.load_default(size=56))
        for font in ("/System/Library/Fonts/Hiragino Sans GB.ttc", "/System/Library/Fonts/STHeiti Medium.ttc",
                     "/System/Library/Fonts/PingFang.ttc", "/Library/Fonts/Arial Unicode.ttf"):
            if Path(font).exists():
                draw.text((30, 140), "國中自然科報告", fill="black", font=ImageFont.truetype(font, 64))
                chinese = True
                break
        else:
            chinese = False
        import io

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        text = ocr.recognize(buf.getvalue(), ["zh-Hant", "en-US"])
        self.assertIn("Vision", text)
        if chinese:
            self.assertIn("自然科", text.replace(" ", ""))


if __name__ == "__main__":
    unittest.main()
