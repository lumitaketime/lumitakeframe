"""EXIF 編輯器：JPEG 直接寫入、RAW 寫進 .xmp、重新命名、時間平移、GPS、多個值、復原。"""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from lumilib import db
from lumilib.config import load_config
from lumilib.exifedit import apply_edits, inspect, preview, undo_batch
from lumilib.media import exiftool, which
from lumilib.scanner import scan_all

HAS_EXIFTOOL = which("exiftool") is not None


def jpeg(path: Path, taken: str, model: str, color=(120, 90, 60)):
    exif = Image.Exif()
    exif[0x010F] = "FUJIFILM"
    exif[0x0110] = model
    exif.get_ifd(0x8769)[0x9003] = taken  # DateTimeOriginal
    Image.new("RGB", (64, 48), color).save(path, quality=90, exif=exif)


@unittest.skipUnless(HAS_EXIFTOOL, "需要 exiftool")
class ExifEditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        p = self.tmp / "photos" / "trip"
        p.mkdir(parents=True)
        jpeg(p / "DSCF0001.jpg", "2024:06:25 18:06:00", "X-T5")
        jpeg(p / "DSCF0002.jpg", "2024:06:25 19:30:00", "X100VI", (40, 90, 160))
        # 假的 RAW 加上已有的 Lightroom 附屬檔
        (p / "DSC0003.ARW").write_bytes(b"\x00" * 2048)
        (p / "DSC0003.xmp").write_text(
            '<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
            '<rdf:Description xmlns:xmp="http://ns.adobe.com/xap/1.0/" xmp:Rating="3"/></rdf:RDF></x:xmpmeta>', encoding="utf-8")
        self.cfg = load_config(self.tmp / "home")
        self.conn = db.connect(self.cfg.db_path)
        db.add_root(self.conn, self.tmp / "photos")
        scan_all(self.conn, self.cfg)
        self.ids = {r["rel_path"].rsplit("/", 1)[-1]: r["id"] for r in self.conn.execute("SELECT id, rel_path FROM images")}
        self.dir = p

    def tearDown(self):
        self.conn.close()
        exiftool().close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def read(self, path):
        return exiftool().read([path])[str(path)]

    def test_inspect_mixed_values(self):
        info = inspect(self.conn, [self.ids["DSCF0001.jpg"], self.ids["DSCF0002.jpg"]])
        self.assertEqual(info["count"], 2)
        self.assertTrue(info["fields"]["model"]["mixed"])
        self.assertFalse(info["fields"]["make"]["mixed"])
        self.assertEqual(info["fields"]["make"]["value"], "FUJIFILM")

    def test_jpeg_edit_rename_and_undo(self):
        ids = [self.ids["DSCF0001.jpg"], self.ids["DSCF0002.jpg"]]
        analyzed = "2026-01-01T00:00:00"
        self.conn.execute("UPDATE images SET analyzed_at = ?, description = '海邊' WHERE id = ?", (analyzed, ids[0]))
        self.conn.commit()
        changes = {
            "time": {"mode": "shift", "seconds": 3600}, "tz": "+08:00",
            "gps": {"lat": 23.4793, "lon": 120.4485}, "title": "嘉義車站", "artist": "Lumi", "copyright": "© 2026 Lumi",
            "rename": "{date}_{seq}",
        }
        prev = preview(self.conn, ids, changes)
        self.assertEqual(prev["changed"], 2)
        diff = prev["sample"][0]["diff"]
        self.assertEqual(diff["taken_at"]["to"], "2024-06-25T19:06:00")
        self.assertEqual(diff["name"]["to"], "20240625_001.jpg")

        res = apply_edits(self.conn, self.cfg, ids, changes)
        self.assertEqual((res["done"], res["errors"]), (2, []))
        new1 = self.dir / "20240625_001.jpg"
        self.assertTrue(new1.exists())
        self.assertFalse((self.dir / "DSCF0001.jpg").exists())
        meta = self.read(new1)
        self.assertEqual(meta["DateTimeOriginal"], "2024:06:25 19:06:00")
        self.assertAlmostEqual(meta["GPSLatitude"], 23.4793, places=3)
        self.assertEqual(meta["Title"], "嘉義車站")
        self.assertEqual(meta["Artist"], "Lumi")
        row = db.get_image(self.conn, ids[0])
        self.assertEqual(row["rel_path"], "trip/20240625_001.jpg")
        self.assertEqual(row["taken_at"], "2024-06-25T19:06:00")
        self.assertAlmostEqual(row["lat"], 23.4793, places=3)
        self.assertEqual(row["analyzed_at"], analyzed)  # 分析結果保留
        self.assertIn("嘉義車站", row["search_text"])

        # 再掃描不會把改過的檔案當成新檔
        scan_all(self.conn, self.cfg)
        self.assertEqual(db.get_image(self.conn, ids[0])["analyzed_at"], analyzed)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM images WHERE status = 'ok'").fetchone()[0], 3)

        undo_batch(self.conn, self.cfg, res["batch"])
        old = self.dir / "DSCF0001.jpg"
        self.assertTrue(old.exists())
        meta = self.read(old)
        self.assertEqual(meta["DateTimeOriginal"], "2024:06:25 18:06:00")
        self.assertNotIn("GPSLatitude", meta)
        self.assertEqual(meta.get("Title", ""), "")
        row = db.get_image(self.conn, ids[0])
        self.assertEqual(row["rel_path"], "trip/DSCF0001.jpg")
        self.assertIsNone(row["lat"])
        with self.assertRaises(ValueError):
            undo_batch(self.conn, self.cfg, res["batch"])

    def test_raw_goes_to_sidecar(self):
        rid = self.ids["DSC0003.ARW"]
        raw = self.dir / "DSC0003.ARW"
        before = raw.read_bytes()
        res = apply_edits(self.conn, self.cfg, [rid], {"make": "SONY", "model": "ILCE-7M4", "lens": "FE 35mm F1.4 GM",
                                                       "caption": "婚禮進場", "time": {"mode": "set", "value": "2025-03-01T10:00:00"}})
        self.assertEqual(res["errors"], [])
        self.assertEqual(raw.read_bytes(), before)  # RAW 本身不動
        side = self.read(self.dir / "DSC0003.xmp")
        self.assertEqual(side["Model"], "ILCE-7M4")
        self.assertEqual(side["Description"], "婚禮進場")
        self.assertEqual(side["Rating"], 3)  # 原本的 Lightroom 星等保留
        self.assertEqual(db.get_image(self.conn, rid)["camera"], "SONY ILCE-7M4")

    def test_api_job(self):
        from fastapi.testclient import TestClient

        from lumilib.server import create_app

        app = create_app(self.cfg, start_jobs_on_boot=False)
        with TestClient(app, base_url="http://127.0.0.1:8765", client=("127.0.0.1", 50000)) as client:
            ids = [self.ids["DSCF0002.jpg"]]
            info = client.post("/api/exif/inspect", json={"ids": ids}).json()
            self.assertEqual(info["fields"]["model"]["value"], "X100VI")
            prev = client.post("/api/exif/preview", json={"ids": ids, "changes": {"model": "X100VI", "lens": "23mm"}}).json()
            self.assertEqual(list(prev["sample"][0]["diff"]), ["lens"])
            bad = client.post("/api/exif/preview", json={"ids": ids, "changes": {"gps": {"lat": 120, "lon": 23}}})
            self.assertEqual(bad.status_code, 400)
            found = client.get("/api/places/search", params={"q": "嘉義"}).json()
            self.assertTrue(any(p["name"].startswith("嘉義") for p in found))


if __name__ == "__main__":
    unittest.main()
