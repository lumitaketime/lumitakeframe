"""整理工具：品質檢查、截圖與文件、大檔案、批次匯出。"""

import shutil
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from lumilib import db
from lumilib.config import load_config
from lumilib.export import export_images, output_name, watermark
from lumilib.quality import blurry, check_images, exposure_problems
from lumilib.scanner import scan_all
from lumilib.tools import large_files, large_folders, screens_and_documents


def busy_scene(seed=1):
    rng = np.random.default_rng(seed)
    im = Image.new("RGB", (1600, 1100), (120, 130, 140))
    d = ImageDraw.Draw(im)
    for _ in range(60):
        x, y, r = rng.integers(0, 1600), rng.integers(0, 1100), rng.integers(20, 160)
        d.ellipse([x, y, x + r, y + r], fill=tuple(int(v) for v in rng.integers(0, 255, 3)))
    for _ in range(40):
        d.line([tuple(rng.integers(0, 1600, 2)), tuple(rng.integers(0, 1100, 2))], fill=tuple(int(v) for v in rng.integers(0, 255, 3)), width=3)
    return im


class ToolsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        p = self.tmp / "photos"
        (p / "trip").mkdir(parents=True)
        (p / "misc").mkdir(parents=True)
        sharp = busy_scene()
        exif = Image.Exif()
        exif[0x0110] = "X-T5"
        exif[0x8825] = {1: "N", 2: (25.0, 2.0, 0.0)}
        sharp.save(p / "trip" / "sharp.jpg", quality=92, exif=exif)
        sharp.filter(ImageFilter.GaussianBlur(4)).save(p / "trip" / "blurry.jpg", quality=92)
        Image.new("RGB", (1200, 800), (2, 2, 2)).save(p / "trip" / "black.jpg")
        Image.new("RGB", (800, 1600), (240, 240, 245)).save(p / "misc" / "Screenshot 2024-01-01.png")
        self.cfg = load_config(self.tmp / "home")
        self.conn = db.connect(self.cfg.db_path)
        db.add_root(self.conn, p)
        scan_all(self.conn, self.cfg)

    def tearDown(self):
        self.conn.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def names(self, rows):
        return {r["rel_path"].rsplit("/", 1)[-1] for r in rows}

    def test_quality(self):
        self.assertEqual(check_images(self.conn, self.cfg), 4)
        self.assertEqual(self.names(blurry(self.conn)) - {"black.jpg", "Screenshot 2024-01-01.png"}, {"blurry.jpg"})
        flags = {r["rel_path"].rsplit("/", 1)[-1]: f for r, f in exposure_problems(self.conn)}
        self.assertEqual(flags.get("black.jpg"), "black")
        self.assertNotIn("sharp.jpg", flags)
        self.assertEqual(check_images(self.conn, self.cfg), 0)  # 已檢查過的不重做

    def test_screens_and_large(self):
        found = {r["rel_path"].rsplit("/", 1)[-1]: reason for r, reason in screens_and_documents(self.conn)}
        self.assertIn("Screenshot 2024-01-01.png", found)
        self.assertNotIn("sharp.jpg", found)
        self.assertEqual(len(large_files(self.conn)), 4)
        folders = {f["path"]: f for f in large_folders(self.conn)}
        self.assertEqual(folders[""]["files"], 4)  # 根目錄含子資料夾
        self.assertEqual(folders["trip"]["files"], 3)

    def test_export(self):
        ids = [r[0] for r in self.conn.execute("SELECT id FROM images ORDER BY rel_path")]
        dest = self.tmp / "out"
        res = export_images(self.conn, self.cfg, ids, {
            "long_side": 800, "quality": 85, "strip_gps": True, "rename": "{date}_{seq}",
            "watermark": {"enabled": True, "text": "© Lumi Taketime", "position": "br", "size": 4, "opacity": 80},
            "dest": str(dest),
        })
        self.assertEqual(res["exported"], 4)
        files = sorted(p.name for p in dest.iterdir())
        self.assertEqual(len(files), 4)
        self.assertTrue(all(f.endswith(".jpg") for f in files))
        with Image.open(dest / [f for f in files if f.endswith("_004.jpg") or True][0]) as im:
            self.assertLessEqual(max(im.size), 800)
        sharp_out = [f for f in files if Image.open(dest / f).getexif().get(0x0110) == "X-T5"]
        self.assertEqual(len(sharp_out), 1)
        exif = Image.open(dest / sharp_out[0]).getexif()
        self.assertNotIn(0x8825, exif)  # GPS 已移除

    def test_name_and_watermark(self):
        row = {"rel_path": "a/IMG_1.jpg", "taken_at": "2024-06-25T18:06:00", "sort_at": None, "camera": "ILCE 7M4"}
        self.assertEqual(output_name("{date}_{camera}_{seq}", row, 7, 120), "20240625_ILCE-7M4_007")
        self.assertEqual(output_name("客戶/交件:{name}", row, 1, 1), "客戶_交件_IMG_1")
        img = Image.new("RGB", (1000, 600), (10, 10, 10))
        out = watermark(img, "Lumi", "br", 5, 100)
        self.assertGreater(np.asarray(out)[500:590, 700:980].max(), 200)  # 右下角出現白字


if __name__ == "__main__":
    unittest.main()


class MigrationTests(unittest.TestCase):
    def test_old_library_gets_quality_columns(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            path = tmp / "library.db"
            conn = db.connect(path)
            conn.execute("ALTER TABLE images DROP COLUMN highlight")
            conn.execute("PRAGMA user_version = 7")
            conn.commit()
            conn.close()
            conn = db.connect(path)
            cols = {r[1] for r in conn.execute("PRAGMA table_info(images)")}
            self.assertTrue({"quality_at", "sharpness", "highlight"} <= cols)
            conn.close()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
