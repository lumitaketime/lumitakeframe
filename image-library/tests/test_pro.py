"""攝影師功能：Lightroom XMP 同步、疊放、重複照片、智慧相簿、那年今日。"""

import json
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

from PIL import Image

from lumilib import db
from lumilib.config import load_config
from lumilib.media import exiftool, which
from lumilib.scanner import scan_all
from lumilib.search import search

HAS_EXIFTOOL = which("exiftool") is not None


def jpeg(path: Path, color=(120, 80, 40), size=(64, 48), taken=None, model="X-T5"):
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", size, color)
    exif = Image.Exif()
    exif[271] = "FUJIFILM"
    exif[272] = model
    if taken:
        exif.get_ifd(0x8769)[36867] = taken
    img.save(path, "JPEG", exif=exif.tobytes(), quality=90)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.photos = self.tmp / "photos"
        self.photos.mkdir()
        self.cfg = load_config(self.tmp / "home")
        self.conn = db.connect(self.cfg.db_path)
        self.root = db.add_root(self.conn, self.photos, "相片")

    def tearDown(self):
        self.conn.close()
        exiftool().close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def image(self, name):
        return self.conn.execute("SELECT * FROM images WHERE rel_path LIKE ?", (f"%{name}",)).fetchone()


@unittest.skipUnless(HAS_EXIFTOOL, "需要 exiftool")
class XmpTests(Base):
    def test_raw_sidecar_created_updated_and_read_back(self):
        from lumilib import xmp

        Image.new("RGB", (40, 30)).save(self.photos / "DSC_0001.tif")
        (self.photos / "DSC_0001.tif").rename(self.photos / "DSC_0001.ARW")
        scan_all(self.conn, self.cfg)
        raw = self.image("DSC_0001.ARW")
        where = xmp.write(self.conn, self.cfg, raw["id"], rating=4, label="red", keywords=["作品集", "婚禮"])
        self.assertEqual(where, "sidecar")
        side = self.photos / "DSC_0001.xmp"
        self.assertTrue(side.exists())
        info = xmp.read_sidecars([side])[side]
        self.assertEqual((info["rating"], info["label"], info["keywords"]), (4, "red", ["作品集", "婚禮"]))
        # Lightroom 改了 .xmp（中文版寫「綠色」）：RAW 沒變，重新掃描也要讀到
        time.sleep(0.05)
        subprocess.run(["exiftool", "-q", "-overwrite_original", "-XMP-xmp:Rating=5", "-XMP-xmp:Label=綠色",
                        "-XMP-dc:Subject=精選", str(side)], check=True)
        scan_all(self.conn, self.cfg)
        row = self.image("DSC_0001.ARW")
        self.assertEqual((row["rating"], row["label"], row["label_text"]), (5, "green", "綠色"))
        self.assertEqual(db.json_list(row["keywords"]), ["精選"])
        self.assertEqual(search(self.conn, "rating:5 label:綠")["total"], 1)
        self.assertEqual(search(self.conn, "精選")["total"], 1)
        # 寫回時沿用 Lightroom 的中文標籤文字
        xmp.write(self.conn, self.cfg, raw["id"], rating=3)
        self.assertEqual(xmp.read_sidecars([side])[side]["label_text"], "綠色")

    def test_reject_and_clear(self):
        from lumilib import xmp

        Image.new("RGB", (40, 30)).save(self.photos / "a.tif")
        (self.photos / "a.tif").rename(self.photos / "a.NEF")
        scan_all(self.conn, self.cfg)
        image_id = self.image("a.NEF")["id"]
        xmp.write(self.conn, self.cfg, image_id, rating=-1)
        self.assertEqual(search(self.conn, "is:rejected")["total"], 1)
        xmp.write(self.conn, self.cfg, image_id, rating=0, label="")
        row = db.get_image(self.conn, image_id)
        self.assertEqual((row["rating"], row["label"]), (None, None))

    def test_jpeg_library_only_by_default_then_embedded(self):
        from lumilib import xmp

        jpeg(self.photos / "p.jpg")
        scan_all(self.conn, self.cfg)
        row = self.image("p.jpg")
        self.conn.execute("UPDATE images SET description = '測試描述', analyzed_at = '2026-01-01' WHERE id = ?", (row["id"],))
        self.conn.commit()
        before = (self.photos / "p.jpg").read_bytes()
        self.assertEqual(xmp.write(self.conn, self.cfg, row["id"], rating=2), "library")
        self.assertEqual((self.photos / "p.jpg").read_bytes(), before)  # 預設不動原檔
        self.cfg.xmp_embed = 1
        self.assertEqual(xmp.write(self.conn, self.cfg, row["id"], rating=5, label="blue"), "embedded")
        out = subprocess.run(["exiftool", "-s3", "-XMP:Rating", "-XMP:Label", str(self.photos / "p.jpg")],
                             capture_output=True, text=True).stdout.split()
        self.assertEqual(out, ["5", "Blue"])
        # 檔案內容變了，但重新掃描不能當成新檔案、不能清掉 AI 分析
        [res] = scan_all(self.conn, self.cfg)
        self.assertEqual((res.added, res.updated), (0, 0))
        self.assertEqual(db.get_image(self.conn, row["id"])["description"], "測試描述")
        self.assertEqual(len(list(self.cfg.thumbs_dir.rglob("*.webp"))), 1)

    def test_label_names(self):
        from lumilib.xmp import label_text, normalize_label

        self.assertEqual(normalize_label("紅色"), "red")
        self.assertEqual(normalize_label("Purple"), "purple")
        self.assertIsNone(normalize_label("Custom"))
        self.assertEqual(label_text("red", "紅色"), "紅色")
        self.assertEqual(label_text("blue", "紅色"), "Blue")


class StackTests(Base):
    def setUp(self):
        super().setUp()
        # RAW＋JPEG 同名
        jpeg(self.photos / "trip" / "DSC_0100.JPG", taken="2024:05:01 10:00:00")
        Image.new("RGB", (40, 30)).save(self.photos / "trip" / "x.tif")
        (self.photos / "trip" / "x.tif").rename(self.photos / "trip" / "DSC_0100.ARW")
        # 連拍：同相機、每秒一張、四張
        for i in range(4):
            jpeg(self.photos / "trip" / f"BURST_{i}.jpg", color=(10 * i, 50, 50), taken=f"2024:05:01 12:00:0{i}")
        # 單張：間隔很久
        jpeg(self.photos / "trip" / "SOLO.jpg", taken="2024:05:01 15:00:00")
        scan_all(self.conn, self.cfg)

    def visible(self):
        return [r["rel_path"] for r in self.conn.execute("SELECT rel_path FROM images WHERE stack_top = 1 ORDER BY rel_path")]

    def test_raw_jpeg_and_burst_stacked(self):
        from lumilib import organize

        self.assertEqual(self.visible(), ["trip/BURST_0.jpg", "trip/DSC_0100.JPG", "trip/SOLO.jpg"])
        pair = self.image("DSC_0100.JPG")
        self.assertEqual(len(organize.stack_members(self.conn, pair["stack_id"])), 2)
        self.assertEqual(len(organize.stack_members(self.conn, self.image("BURST_0.jpg")["stack_id"])), 4)
        self.assertIsNone(self.image("SOLO.jpg")["stack_id"])

    def test_unstack_cover_and_manual_survive_rebuild(self):
        from lumilib import organize

        burst = self.image("BURST_0.jpg")["stack_id"]
        organize.set_cover(self.conn, self.image("BURST_2.jpg")["id"])
        organize.rebuild_stacks(self.conn, self.cfg)
        self.assertEqual(self.image("BURST_2.jpg")["stack_top"], 1)  # 手動封面保留
        organize.unstack(self.conn, self.image("BURST_2.jpg")["stack_id"])
        organize.rebuild_stacks(self.conn, self.cfg)
        self.assertEqual(len(self.visible()), 6)  # 解除後不再自動疊放
        sid = organize.make_stack(self.conn, [self.image("SOLO.jpg")["id"], self.image("BURST_0.jpg")["id"]])
        self.assertLess(sid, 0)
        organize.rebuild_stacks(self.conn, self.cfg)
        self.assertEqual(len(organize.stack_members(self.conn, sid)), 2)
        self.assertNotEqual(burst, 0)


class DuplicateTests(Base):
    def test_exact_and_similar(self):
        from lumilib import organize

        from PIL import ImageDraw

        img = Image.new("RGB", (400, 300))
        d = ImageDraw.Draw(img)
        for y in range(300):
            d.line([(0, y), (400, y)], fill=(40 + y // 2, 90, 200 - y // 3))
        d.ellipse([60, 40, 220, 200], fill=(240, 180, 60))
        d.rectangle([250, 150, 380, 280], fill=(30, 120, 40))
        img.save(self.photos / "orig.jpg", quality=95)
        shutil.copy(self.photos / "orig.jpg", self.photos / "copy.jpg")
        img.resize((200, 150)).save(self.photos / "small.jpg", quality=70)  # 縮小再壓縮：幾乎一樣
        Image.new("RGB", (400, 300), (250, 250, 0)).save(self.photos / "other.jpg")
        scan_all(self.conn, self.cfg)
        res = organize.find_duplicates(self.conn, self.cfg)
        names = lambda g: sorted(db.get_image(self.conn, i)["rel_path"] for i in g)  # noqa: E731
        self.assertEqual([names(g) for g in res["exact"]], [["copy.jpg", "orig.jpg"]])
        self.assertIn(["copy.jpg", "orig.jpg", "small.jpg"], [names(g) for g in res["similar"]])
        rows = [db.get_image(self.conn, i) for i in res["similar"][0]]
        self.assertNotEqual(db.get_image(self.conn, organize.suggest_keep(rows))["rel_path"], "small.jpg")
        organize.ignore_group(self.conn, res["exact"][0])
        self.assertEqual(organize.load_duplicates(self.conn, self.cfg)["exact"], [])


class SmartAndMemoryTests(Base):
    def test_smart_album_updates_and_memories(self):
        from datetime import date

        from lumilib import organize

        jpeg(self.photos / "a.jpg", taken="2023:11:02 09:00:00", model="X100VI")
        jpeg(self.photos / "b.jpg", taken="2021:11:04 09:00:00")
        jpeg(self.photos / "c.jpg", taken="2022:06:01 09:00:00")
        scan_all(self.conn, self.cfg)
        sid = organize.save_smart(self.conn, "X100VI 作品", "camera:x100vi")
        self.assertEqual(organize.list_smart(self.conn)[0]["count"], 1)
        jpeg(self.photos / "d.jpg", taken="2024:01:01 09:00:00", model="X100VI")
        scan_all(self.conn, self.cfg)
        self.assertEqual(organize.list_smart(self.conn)[0]["count"], 2)  # 新照片自動出現
        with self.assertRaises(ValueError):
            organize.save_smart(self.conn, "x", "  ")
        self.assertGreater(sid, 0)
        mem = organize.memories(self.conn, today=date(2026, 11, 3))
        self.assertEqual([(m["year"], m["years_ago"]) for m in mem], [(2023, 3), (2021, 5)])


if __name__ == "__main__":
    unittest.main()
