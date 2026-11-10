"""攝影師功能：星等與標籤（只存在圖庫）、疊放、重複照片、智慧相簿、那年今日。"""

import json
import shutil
import tempfile
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


class RatingTests(Base):
    """星等、顏色標籤、關鍵字只存在圖庫裡，不能寫入或建立硬碟上的任何檔案。"""

    def files(self):
        return {p.relative_to(self.photos).as_posix(): p.read_bytes() for p in self.photos.rglob("*") if p.is_file()}

    def test_rating_label_keywords_library_only(self):
        from lumilib import ratings

        Image.new("RGB", (40, 30)).save(self.photos / "DSC_0001.tif")
        (self.photos / "DSC_0001.tif").rename(self.photos / "DSC_0001.ARW")
        jpeg(self.photos / "p.jpg")
        scan_all(self.conn, self.cfg)
        before = self.files()
        raw, jpg = self.image("DSC_0001.ARW"), self.image("p.jpg")
        ratings.update(self.conn, raw["id"], rating=4, label="red", keywords=["作品集", "婚禮"])
        ratings.update(self.conn, jpg["id"], rating=5, label="blue")
        self.assertEqual(self.files(), before)  # 沒有建立 .xmp，也沒有改動原檔
        row = self.image("DSC_0001.ARW")
        self.assertEqual((row["rating"], row["label"]), (4, "red"))
        self.assertEqual(db.json_list(row["keywords"]), ["作品集", "婚禮"])
        self.assertEqual(search(self.conn, "rating:4 label:紅")["total"], 1)
        self.assertEqual(search(self.conn, "婚禮")["total"], 1)
        # 重新掃描不會清掉圖庫裡的星等
        scan_all(self.conn, self.cfg)
        self.assertEqual(self.image("p.jpg")["rating"], 5)

    def test_reject_and_clear(self):
        from lumilib import ratings

        Image.new("RGB", (40, 30)).save(self.photos / "a.tif")
        (self.photos / "a.tif").rename(self.photos / "a.NEF")
        scan_all(self.conn, self.cfg)
        image_id = self.image("a.NEF")["id"]
        ratings.update(self.conn, image_id, rating=-1)
        self.assertEqual(search(self.conn, "is:rejected")["total"], 1)
        ratings.update(self.conn, image_id, rating=0, label="")
        row = db.get_image(self.conn, image_id)
        self.assertEqual((row["rating"], row["label"]), (None, None))

    def test_invalid_values(self):
        from lumilib import ratings

        jpeg(self.photos / "p.jpg")
        scan_all(self.conn, self.cfg)
        image_id = self.image("p.jpg")["id"]
        with self.assertRaises(ValueError):
            ratings.update(self.conn, image_id, rating=6)
        with self.assertRaises(ValueError):
            ratings.update(self.conn, image_id, label="orange")

    def test_label_names(self):
        from lumilib.ratings import normalize_label

        self.assertEqual(normalize_label("紅色"), "red")
        self.assertEqual(normalize_label("Purple"), "purple")
        self.assertIsNone(normalize_label("Custom"))

    @unittest.skipUnless(HAS_EXIFTOOL, "需要 exiftool")
    def test_scan_ignores_sidecar(self):
        """旁邊的 .xmp 不再被讀取，只讀照片檔案本身的中繼資料。"""
        Image.new("RGB", (40, 30)).save(self.photos / "DSC_0002.tif")
        (self.photos / "DSC_0002.tif").rename(self.photos / "DSC_0002.ARW")
        (self.photos / "DSC_0002.xmp").write_text(
            '<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
            '<rdf:Description xmlns:xmp="http://ns.adobe.com/xap/1.0/" xmp:Rating="5" xmp:Label="Red"/></rdf:RDF></x:xmpmeta>',
            encoding="utf-8")
        scan_all(self.conn, self.cfg)
        row = self.image("DSC_0002.ARW")
        self.assertEqual((row["rating"], row["label"]), (None, None))


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


class KeywordGroupTests(Base):
    def setUp(self):
        super().setUp()
        specs = [("a.jpg", "X-T5", "XF56mm", 85, 1.2, 160), ("b.jpg", "X-T5", "XF16mm", 24, 2.8, 3200),
                 ("c.jpg", "X100VI", "", 35, 2.0, 400), ("d.jpg", "X-T50", "XF56mm", 85, 1.4, 12800)]
        for name, model, lens, focal, ap, iso in specs:
            jpeg(self.photos / name, model=model, taken="2024:05:01 10:00:00")
        scan_all(self.conn, self.cfg)
        for name, model, lens, focal, ap, iso in specs:
            self.conn.execute("UPDATE images SET lens = ?, focal_35 = ?, aperture = ?, iso = ? WHERE rel_path = ?",
                              (lens or None, focal, ap, iso, name))
        self.conn.commit()

    def test_keyword_counts(self):
        from lumilib import keywords as gear

        for name, tags, kws in (("a.jpg", ["海邊", "人像"], ["作品集"]), ("b.jpg", ["海邊", "Beach"], []),
                                ("c.jpg", ["beach"], ["作品集", "海邊"])):
            self.conn.execute("UPDATE images SET tags = ?, keywords = ? WHERE rel_path = ?",
                              (json.dumps(tags, ensure_ascii=False), json.dumps(kws, ensure_ascii=False), name))
        self.conn.commit()
        top = gear.keyword_counts(self.conn)
        self.assertEqual(top[0], {"tag": "海邊", "count": 3, "kind": "mine"})
        self.assertIn({"tag": "Beach", "count": 2, "kind": "ai"}, top)  # 不分大小寫合併
        self.assertEqual([k["tag"] for k in gear.keyword_counts(self.conn, "mine")], ["作品集", "海邊"])

    def test_person_groups_searchable(self):
        import numpy as np

        from lumilib import faces

        ids = [self.image(n)["id"] for n in ("a.jpg", "b.jpg")]
        vec = (np.ones(512) / np.sqrt(512)).astype("float32").tobytes()
        now = db.now_iso()
        pid = self.conn.execute("INSERT INTO persons (name, created_at, updated_at) VALUES ('王小明', ?, ?)", (now, now)).lastrowid
        for i in ids:
            self.conn.execute("INSERT INTO faces (image_id, person_id, embedding, model, created_at) VALUES (?, ?, ?, 'm', ?)",
                              (i, pid, vec, now))
        self.conn.commit()
        faces.set_groups(self.conn, [pid], add=["客戶", "婚禮"])
        self.assertEqual(search(self.conn, "group:客戶")["total"], 2)
        self.assertEqual(search(self.conn, "客戶")["total"], 2)
        self.assertEqual(faces.list_persons(self.conn)[0]["groups"], ["客戶", "婚禮"])
        faces.set_groups(self.conn, [pid], remove=["客戶"])
        self.assertEqual(search(self.conn, "group:客戶")["total"], 0)
        self.assertEqual(faces.all_groups(self.conn)[0], {"name": "婚禮", "count": 1})


class KeywordSplitTests(Base):
    def test_semicolon_keywords_split_on_upgrade(self):
        jpeg(self.photos / "a.jpg")
        scan_all(self.conn, self.cfg)
        self.conn.execute("UPDATE images SET keywords = ?", (json.dumps(["author;walk;beethoven", "Porträt"]),))
        self.conn.execute("PRAGMA user_version = 6")
        self.conn.commit()
        self.conn.close()
        self.conn = db.connect(self.cfg.db_path)  # 升級到 v7 時自動拆開
        self.assertEqual(db.json_list(self.image("a.jpg")["keywords"]), ["author", "walk", "beethoven", "Porträt"])
        self.assertEqual(search(self.conn, "tag:beethoven")["total"], 1)


class CustomModelTests(Base):
    def test_custom_prompt_text_model_and_custom_entries(self):
        from lumilib import clip, faces
        from lumilib.analyzer import build_prompt

        jpeg(self.photos / "a.jpg")
        scan_all(self.conn, self.cfg)
        row = self.image("a.jpg")
        self.assertIn("標註助手", build_prompt(self.cfg, row))
        self.cfg.analysis_prompt = "只用英文列出畫面中的器材。"
        self.assertTrue(build_prompt(self.cfg, row).startswith("只用英文列出畫面中的器材。"))
        self.assertEqual(self.cfg.search_model, self.cfg.vision_model)
        self.cfg.text_model = "qwen3:8b"
        self.assertEqual(self.cfg.search_model, "qwen3:8b")
        self.assertIsNone(faces.model_info(self.cfg, "custom"))
        self.cfg.face_custom_url, self.cfg.face_custom_det, self.cfg.face_custom_rec = "https://x/y.zip", "d.onnx", "r.onnx"
        self.assertEqual(faces.model_info(self.cfg, "custom")["det"], "d.onnx")
        self.assertIsNone(clip.repo_for(self.cfg, "custom"))
        self.cfg.clip_custom_repo = "immich-app/ViT-B-16-SigLIP2__webli"
        self.assertEqual(clip.repo_for(self.cfg, "custom"), "immich-app/ViT-B-16-SigLIP2__webli")
        self.assertTrue(clip.is_multilingual("custom", self.cfg))


if __name__ == "__main__":
    unittest.main()
