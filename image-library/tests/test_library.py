"""執行：python -m unittest discover -s tests（在 image-library 目錄下）

使用合成照片／影片與假模型，不需要 Ollama。影片相關測試需要 ffmpeg，
完整 EXIF 測試需要 exiftool；沒有安裝時會略過。
"""

import base64
import io
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

from PIL import Image

from lumilib import db, fileops
from lumilib.analyzer import OllamaUnavailable, analyze_images, embed_images, parse_model_json
from lumilib.config import load_config
from lumilib.media import exiftool, which
from lumilib.scanner import scan_all
from lumilib.search import parse_query, search

HAS_FFMPEG = which("ffmpeg") is not None
HAS_EXIFTOOL = which("exiftool") is not None


def make_photo(path: Path, color, size=(64, 48), taken="2023:07:14 18:30:00", model="iPhone 15 Pro", make="Apple"):
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", size, color)
    exif = Image.Exif()
    exif[271] = make
    exif[272] = model
    exif.get_ifd(0x8769)[36867] = taken
    img.save(path, "JPEG", exif=exif.tobytes())


def make_video(path: Path, seconds=3):
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [which("ffmpeg"), "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c=blue:size=320x240:duration={seconds}:rate=10",
         "-metadata", "creation_time=2022-01-02T03:04:05Z", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)],
        check=True,
    )


class FakeClient:
    """依畫面中央顏色回傳固定結果，避免測試需要真的模型。"""

    def __init__(self):
        self.calls = []

    def describe(self, model, prompt, images):
        self.calls.append((prompt, len(images)))
        img = Image.open(io.BytesIO(base64.b64decode(images[0]))).convert("RGB")
        r, g, b = img.getpixel((img.width // 2, img.height // 2))
        if r > 200 and g < 80:
            return {"description": "紅色的跑車停在街道上", "tags": ["跑車", "car", "紅色", "#街道"],
                    "objects": ["汽車"], "scene": "街道", "text_in_image": ""}
        if b > 200:
            return {"description": "藍色的海邊與夕陽", "tags": ["海邊", "beach", "夕陽"],
                    "objects": ["海浪"], "scene": "海邊", "text_in_image": "SUNSET BAR"}
        return {"description": "綠色的森林步道", "tags": ["森林", "forest", "步道"],
                "objects": ["樹"], "scene": "山區", "text_in_image": ""}

    def embed(self, model, texts):
        return [[1.0 if ("海" in t or "沙灘" in t) else 0.0, 1.0 if "車" in t else 0.0,
                 1.0 if ("森林" in t or "樹" in t) else 0.0, 0.1] for t in texts]

    def installed(self):
        return [{"name": "qwen2.5vl:7b", "size": 6_000_000_000, "parameter_size": "8.3B", "families": [], "modified_at": None}]

    def pull(self, model, progress=None, stop=None):
        if progress:
            progress("pulling", 50, 100)
            progress("success", 100, 100)

    def delete(self, model):
        pass


class LibraryTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.photos = self.tmp / "photos"
        make_photo(self.photos / "2023 旅行" / "car.jpg", (230, 30, 30))
        make_photo(self.photos / "2023 旅行" / "sea.jpg", (20, 60, 240), taken="2023:08:01 19:00:00")
        make_photo(self.photos / "hiking" / "forest.jpg", (30, 160, 40), taken="2021:05:02 09:00:00",
                   model="X-T5", make="FUJIFILM")
        (self.photos / "notes.txt").write_text("not an image")
        (self.photos / ".hidden").mkdir()
        make_photo(self.photos / ".hidden" / "secret.jpg", (0, 0, 0))
        self.cfg = load_config(self.tmp / "home")
        self.conn = db.connect(self.cfg.db_path)
        self.root = db.add_root(self.conn, self.photos, "相片")

    def tearDown(self):
        self.conn.close()
        exiftool().close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def analyze(self, client=None, **kw):
        return analyze_images(self.conn, self.cfg, client or FakeClient(), **kw)

    def image(self, name):
        return self.conn.execute("SELECT * FROM images WHERE rel_path LIKE ?", (f"%{name}",)).fetchone()


class ScanTests(LibraryTestCase):
    def test_scan_indexes_media_and_metadata(self):
        [res] = scan_all(self.conn, self.cfg)
        self.assertEqual(res.added, 3)  # 隱藏資料夾與非媒體檔略過
        row = self.image("forest.jpg")
        self.assertEqual(row["camera"], "FUJIFILM X-T5")
        self.assertEqual(row["taken_at"], "2021-05-02T09:00:00")
        self.assertEqual(row["sort_at"], "2021-05-02T09:00:00")
        self.assertEqual(row["folder"], "hiking")
        self.assertEqual((row["width"], row["height"], row["media_type"]), (64, 48, "photo"))
        self.assertEqual(self.image("car.jpg")["camera"], "Apple iPhone 15 Pro")
        self.assertEqual(len(list(self.cfg.thumbs_dir.rglob("*.webp"))), 3)

    def test_photo_without_date_sorts_by_file_time(self):
        Image.new("RGB", (10, 10)).save(self.photos / "plain.png")
        scan_all(self.conn, self.cfg)
        row = self.image("plain.png")
        self.assertIsNone(row["taken_at"])
        self.assertTrue(row["sort_at"])

    def test_rescan_is_incremental(self):
        scan_all(self.conn, self.cfg)
        [res] = scan_all(self.conn, self.cfg)
        self.assertEqual((res.added, res.unchanged, res.missing), (0, 3, 0))

    def test_move_keeps_analysis_and_albums(self):
        scan_all(self.conn, self.cfg)
        self.analyze()
        old = self.image("sea.jpg")
        album = db.create_album(self.conn, "夏天", [old["id"]])
        (self.photos / "海邊").mkdir()
        (self.photos / "2023 旅行" / "sea.jpg").rename(self.photos / "海邊" / "renamed.jpg")
        [res] = scan_all(self.conn, self.cfg)
        self.assertEqual((res.moved, res.added, res.missing), (1, 0, 0))
        new = db.get_image(self.conn, old["id"])
        self.assertEqual((new["rel_path"], new["folder"]), ("海邊/renamed.jpg", "海邊"))
        self.assertEqual(new["description"], old["description"])
        self.assertEqual(db.get_album(self.conn, album)["count"], 1)

    def test_deleted_file_marked_missing_then_restored(self):
        scan_all(self.conn, self.cfg)
        target = self.photos / "hiking" / "forest.jpg"
        backup = self.tmp / "forest.bak"
        shutil.move(target, backup)
        [res] = scan_all(self.conn, self.cfg)
        self.assertEqual(res.missing, 1)
        self.assertEqual(search(self.conn, "is:missing")["total"], 1)
        shutil.move(backup, target)
        scan_all(self.conn, self.cfg)
        self.assertEqual(db.stats(self.conn)["missing"], 0)

    def test_offline_drive_is_not_marked_missing(self):
        scan_all(self.conn, self.cfg)
        moved = self.tmp / "unplugged"
        self.photos.rename(moved)
        [res] = scan_all(self.conn, self.cfg)
        self.assertTrue(res.offline)
        self.assertEqual(db.stats(self.conn)["missing"], 0)
        db.relocate_root(self.conn, "相片", moved)
        [res] = scan_all(self.conn, self.cfg)
        self.assertEqual((res.added, res.unchanged), (0, 3))

    def test_duplicate_reuses_analysis(self):
        scan_all(self.conn, self.cfg)
        self.analyze()
        shutil.copy2(self.photos / "hiking" / "forest.jpg", self.photos / "hiking" / "copy.jpg")
        [res] = scan_all(self.conn, self.cfg)
        self.assertEqual((res.added, res.reused), (1, 1))
        self.assertEqual(self.image("copy.jpg")["description"], "綠色的森林步道")

    def test_overlapping_roots_rejected(self):
        with self.assertRaises(ValueError):
            db.add_root(self.conn, self.photos / "hiking", "子資料夾")

    def test_unreadable_image_recorded_as_error(self):
        (self.photos / "broken.jpg").write_bytes(b"not really a jpeg")
        scan_all(self.conn, self.cfg)
        self.assertTrue(self.image("broken.jpg")["error"])

    def test_skips_catalog_packages(self):
        make_photo(self.photos / "Photos Library.photoslibrary" / "originals" / "x.jpg", (1, 1, 1))
        make_photo(self.photos / "Catalog Previews.lrdata" / "p.jpg", (1, 1, 1))
        [res] = scan_all(self.conn, self.cfg)
        self.assertEqual(res.added, 3)

    @unittest.skipUnless(HAS_FFMPEG, "需要 ffmpeg")
    def test_video_scan_and_analysis_uses_frames(self):
        make_video(self.photos / "clips" / "sea.mp4", 4)
        scan_all(self.conn, self.cfg)
        row = self.image("sea.mp4")
        self.assertEqual(row["media_type"], "video")
        self.assertAlmostEqual(row["duration"], 4.0, delta=0.5)
        self.assertEqual((row["width"], row["height"]), (320, 240))
        self.assertTrue(row["sort_at"].startswith("2022-01-02"))
        self.assertEqual(row["thumb_ok"], 1)
        client = FakeClient()
        self.analyze(client, ids=[row["id"]])
        prompt, frames = client.calls[-1]
        self.assertEqual(frames, 4)
        self.assertIn("影片", prompt)
        self.assertEqual(search(self.conn, "type:video 海邊")["total"], 1)


@unittest.skipUnless(HAS_EXIFTOOL, "需要 exiftool")
class ExifToolTests(LibraryTestCase):
    def test_full_exif_and_keywords(self):
        target = self.photos / "port.jpg"
        Image.new("RGB", (300, 200), (10, 10, 10)).save(target)
        subprocess.run(
            ["exiftool", "-q", "-overwrite_original", "-Make=SONY", "-Model=ILCE-7M4", "-LensModel=FE 35mm F1.4 GM",
             "-FNumber=2", "-ExposureTime=0.008", "-ISO=400", "-FocalLength=35", "-Orientation#=6",
             "-DateTimeOriginal=2024:03:02 17:45:10", "-GPSLatitude=21.95", "-GPSLatitudeRef=N",
             "-GPSLongitude=120.78", "-GPSLongitudeRef=E", "-XMP:Subject=作品集", "-XMP:Subject=墾丁", str(target)],
            check=True,
        )
        scan_all(self.conn, self.cfg)
        row = self.image("port.jpg")
        self.assertEqual(row["camera"], "SONY ILCE-7M4")
        self.assertEqual(row["lens"], "FE 35mm F1.4 GM")
        self.assertEqual((row["aperture"], row["iso"], row["focal_length"]), (2.0, 400, 35.0))
        self.assertAlmostEqual(row["exposure_time"], 0.008)
        self.assertEqual((row["width"], row["height"]), (200, 300))  # 依方向轉正
        self.assertEqual((row["lat"], row["lon"]), (21.95, 120.78))
        self.assertEqual(db.json_list(row["keywords"]), ["作品集", "墾丁"])
        self.assertEqual(search(self.conn, "作品集")["total"], 1)
        self.assertEqual(search(self.conn, "tag:墾丁 lens:35mm")["total"], 1)


class AnalyzeAndSearchTests(LibraryTestCase):
    def setUp(self):
        super().setUp()
        scan_all(self.conn, self.cfg)

    def test_analyze_and_keyword_search(self):
        client = FakeClient()
        res = self.analyze(client)
        self.assertEqual((res.analyzed, res.failed), (3, 0))
        self.assertIn("2023 旅行/car.jpg", " ".join(p for p, _ in client.calls))
        self.assertEqual([r["filename"] for r in search(self.conn, "跑車")["results"]], ["car.jpg"])
        self.assertEqual(search(self.conn, "BEACH")["results"][0]["filename"], "sea.jpg")
        self.assertEqual(search(self.conn, "sunset bar")["total"], 1)
        self.assertEqual(search(self.conn, "街道")["results"][0]["tags"][-1], "街道")
        self.assertEqual(self.analyze(client).analyzed, 0)

    def test_scoped_analysis(self):
        self.assertEqual(self.analyze(folder="hiking").analyzed, 1)
        album = db.create_album(self.conn, "a", [self.image("car.jpg")["id"]])
        self.assertEqual(self.analyze(album_id=album).analyzed, 1)
        self.assertEqual(self.analyze(retry_failed=True).analyzed, 1)

    def test_filters_and_excludes(self):
        self.analyze()
        self.assertEqual(search(self.conn, "year:2023")["total"], 2)
        self.assertEqual(search(self.conn, "year:2023 -海邊")["total"], 1)
        self.assertEqual(search(self.conn, "camera:x-t5")["total"], 1)
        self.assertEqual(search(self.conn, "folder:旅行")["total"], 2)
        self.assertEqual(search(self.conn, "after:2023-08-01")["total"], 1)
        self.assertEqual(search(self.conn, "before:2023-08-01")["total"], 2)
        self.assertEqual(search(self.conn, "tag:forest")["total"], 1)
        self.assertEqual(search(self.conn, "ext:jpg")["total"], 3)
        self.assertEqual(search(self.conn, "type:photo")["total"], 3)
        self.assertEqual(search(self.conn, "type:video")["total"], 0)
        self.assertEqual(search(self.conn, "root:相片 森林")["total"], 1)
        self.assertEqual(search(self.conn, "100%_")["total"], 0)
        db.set_user_fields(self.conn, self.image("car.jpg")["id"], favorite=True)
        self.assertEqual(search(self.conn, "is:favorite")["total"], 1)

    def test_user_tags_searchable(self):
        self.analyze()
        image = search(self.conn, "森林")["results"][0]
        db.set_user_fields(self.conn, image["id"], user_tags=["家庭出遊", " 家庭出遊 ", ""], note="和爸媽")
        self.assertEqual(search(self.conn, "家庭出遊")["results"][0]["user_tags"], ["家庭出遊"])
        self.assertEqual(search(self.conn, "爸媽")["total"], 1)

    def test_semantic_search(self):
        self.cfg.embed_model = "fake-embed"
        self.assertEqual(self.analyze().embedded, 3)
        client = FakeClient()
        out = search(self.conn, "沙灘", semantic=True, embedder=client, embed_model="fake-embed")
        self.assertEqual(out["mode"], "hybrid")
        self.assertEqual((out["results"][0]["filename"], out["results"][0]["match"]), ("sea.jpg", "semantic"))
        self.assertEqual(embed_images(self.conn, self.cfg, client), 0)

    def test_model_failures(self):
        class Broken(FakeClient):
            def describe(self, *a):
                raise ValueError("模型沒有回傳有效 JSON")

        self.assertEqual(self.analyze(Broken()).failed, 3)
        self.assertEqual(search(self.conn, "is:failed")["total"], 3)
        self.assertEqual(self.analyze().analyzed, 0)
        self.assertEqual(self.analyze(retry_failed=True).analyzed, 3)

    def test_ollama_down_aborts_without_marking(self):
        class Down(FakeClient):
            def describe(self, *a):
                raise OllamaUnavailable("down")

        with self.assertRaises(OllamaUnavailable):
            self.analyze(Down())
        self.assertEqual(db.stats(self.conn)["pending"], 3)


class FileOpsTests(LibraryTestCase):
    def setUp(self):
        super().setUp()
        scan_all(self.conn, self.cfg)

    def test_move_with_sidecars_and_conflicts(self):
        car = self.image("car.jpg")
        (self.photos / "2023 旅行" / "car.xmp").write_text("<xmp/>")
        (self.photos / "作品集").mkdir()
        make_photo(self.photos / "作品集" / "car.jpg", (1, 2, 3))  # 目的地已有同名檔
        res = fileops.move_images(self.conn, [car["id"]], self.root["id"], "作品集")
        self.assertEqual(res.done, [car["id"]])
        moved = db.get_image(self.conn, car["id"])
        self.assertEqual(moved["rel_path"], "作品集/car (1).jpg")
        self.assertTrue((self.photos / "作品集" / "car (1).xmp").exists())
        self.assertFalse((self.photos / "2023 旅行" / "car.jpg").exists())
        [res] = scan_all(self.conn, self.cfg)
        self.assertEqual((res.missing, res.moved), (0, 0))

    def test_raw_jpeg_pair_keeps_xmp_with_raw(self):
        folder = self.photos / "pair"
        make_photo(folder / "IMG_1.JPG", (5, 5, 5))
        (folder / "IMG_1.CR3").write_bytes(b"raw")
        (folder / "IMG_1.xmp").write_text("<xmp/>")
        self.assertEqual(fileops.sidecars(folder / "IMG_1.JPG"), [])
        self.assertEqual(fileops.sidecars(folder / "IMG_1.CR3"), [folder / "IMG_1.xmp"])

    def test_move_rejects_escape(self):
        with self.assertRaises(ValueError):
            fileops.move_images(self.conn, [self.image("car.jpg")["id"]], self.root["id"], "../outside")

    def test_trash_uses_trash_function(self):
        trashed = []
        sea = self.image("sea.jpg")
        (self.photos / "2023 旅行" / "sea.jpg.xmp").write_text("x")
        res = fileops.trash_images(self.conn, [sea["id"]], trash=lambda p: (trashed.append(p.name), p.unlink()))
        self.assertEqual(res.done, [sea["id"]])
        self.assertEqual(sorted(trashed), ["sea.jpg", "sea.jpg.xmp"])
        self.assertIsNone(db.get_image(self.conn, sea["id"]))

    def test_albums(self):
        ids = [self.image("car.jpg")["id"], self.image("sea.jpg")["id"]]
        album = db.create_album(self.conn, "作品", ids)
        self.assertEqual(db.add_to_album(self.conn, album, ids), 0)  # 不重複加入
        info = db.get_album(self.conn, album)
        self.assertEqual((info["name"], info["count"]), ("作品", 2))
        db.remove_from_album(self.conn, album, ids[:1])
        self.assertEqual(db.get_album(self.conn, album)["count"], 1)
        db.delete_album(self.conn, album)
        self.assertEqual(db.list_albums(self.conn), [])
        self.assertIsNotNone(db.get_image(self.conn, ids[0]))  # 刪相簿不刪照片


class ParsingTests(unittest.TestCase):
    def test_parse_query(self):
        q = parse_query('貓 "日落 海邊" -狗 tag:可愛 year:2024 type:video http://x')
        self.assertEqual(q.terms, ["貓", "日落 海邊", "http://x"])
        self.assertEqual(q.excludes, ["狗"])
        self.assertEqual(q.filters, [("tag", "可愛"), ("year", "2024"), ("type", "video")])
        self.assertEqual(parse_query('unbalanced "quote').terms, ["unbalanced", "quote"])

    def test_parse_model_json(self):
        self.assertEqual(parse_model_json('<think>hmm</think>{"a": 1}'), {"a": 1})
        self.assertEqual(parse_model_json('```json\n{"a": 2}\n```'), {"a": 2})
        with self.assertRaises(ValueError):
            parse_model_json("no json")

    def test_parse_datetime(self):
        from lumilib.media import parse_datetime

        self.assertEqual(parse_datetime("2023:07:14 18:30:00.12+08:00"), ("2023-07-14T18:30:00", "+08:00"))
        self.assertEqual(parse_datetime("2023:07:14 18:30:00-05:00"), ("2023-07-14T18:30:00", "-05:00"))
        self.assertEqual(parse_datetime("0000:00:00 00:00:00"), (None, None))
        self.assertEqual(parse_datetime("2024-05-01T03:04:05Z"), ("2024-05-01T03:04:05", "+00:00"))


def wait_jobs(client, timeout=10):
    end = time.monotonic() + timeout
    snap = client.get("/api/jobs").json()
    while time.monotonic() < end:
        snap = client.get("/api/jobs").json()
        if not snap["running"] and not snap["queued"]:
            break
        time.sleep(0.05)
    return snap


class ServerTests(LibraryTestCase):
    def setUp(self):
        super().setUp()
        from fastapi.testclient import TestClient

        from lumilib.server import create_app

        scan_all(self.conn, self.cfg)
        self.analyze()
        self.trashed = []
        app = create_app(self.cfg, client_factory=FakeClient, start_jobs_on_boot=False,
                         trash=lambda p: (self.trashed.append(p.name), p.unlink()))
        self.client = TestClient(app, base_url="http://127.0.0.1:8765", client=("127.0.0.1", 50000))
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        super().tearDown()

    def post(self, path, body=None):
        return self.client.post(path, json=body or {})

    def test_timeline_assets_and_media(self):
        info = self.client.get("/api/server").json()
        self.assertEqual(info["stats"]["photos"], 3)
        buckets = self.client.get("/api/timeline/buckets").json()
        self.assertEqual([b["month"] for b in buckets], ["2023-08", "2023-07", "2021-05"])
        items = self.client.get("/api/timeline/bucket", params={"month": "2023-07"}).json()
        self.assertEqual(items[0]["name"], "car.jpg")
        image_id = items[0]["id"]
        r = self.client.get(f"/api/assets/{image_id}/thumb")
        self.assertEqual((r.status_code, r.headers["content-type"]), (200, "image/webp"))
        r = self.client.get(f"/api/assets/{image_id}/preview")
        self.assertTrue(r.content.startswith(b"\xff\xd8"))
        r = self.client.get(f"/api/assets/{image_id}/original", headers={"Range": "bytes=0-9"})
        self.assertEqual((r.status_code, len(r.content)), (206, 10))
        detail = self.post(f"/api/assets/{image_id}", {"favorite": True, "user_tags": "作品集、紅色"}).json()
        self.assertEqual((detail["favorite"], detail["user_tags"]), (1, ["作品集", "紅色"]))
        self.assertEqual(len(self.client.get("/api/timeline/buckets", params={"fav": "1"}).json()), 1)

    def test_folders_albums_and_bulk(self):
        roots = self.client.get("/api/folders").json()["roots"]
        self.assertEqual(roots[0]["count"], 3)
        rid = roots[0]["id"]
        top = self.client.get("/api/folders", params={"root": rid}).json()
        self.assertEqual([f["name"] for f in top["folders"]], ["2023 旅行", "hiking"])
        self.assertEqual(top["folders"][0]["count"], 2)
        sub = self.client.get("/api/folders", params={"root": rid, "path": "2023 旅行"}).json()
        self.assertEqual(len(sub["assets"]), 2)
        self.assertEqual(sub["crumbs"], [{"name": "2023 旅行", "path": "2023 旅行"}])
        ids = [a["id"] for a in sub["assets"]]

        res = self.post("/api/assets/bulk", {"ids": ids, "action": "add_to_album", "name": "夏日"}).json()
        album = self.client.get(f"/api/albums/{res['album_id']}").json()
        self.assertEqual((album["name"], len(album["assets"])), ("夏日", 2))

        self.assertEqual(self.post("/api/folders", {"root_id": rid, "path": "精選/2024"}).json()["path"], "精選/2024")
        dirs = self.client.get("/api/fs/dirs", params={"root": rid, "path": "精選"}).json()["dirs"]
        self.assertEqual(dirs, ["2024"])
        res = self.post("/api/assets/bulk", {"ids": ids[:1], "action": "move", "root_id": rid, "folder": "精選/2024"}).json()
        self.assertEqual(res["done"], 1)
        moved = self.client.get("/api/folders", params={"root": rid, "path": "精選/2024"}).json()
        self.assertEqual(len(moved["assets"]), 1)

        res = self.post("/api/assets/bulk", {"ids": ids[1:], "action": "trash"}).json()
        self.assertEqual(res["done"], 1)
        self.assertEqual(len(self.trashed), 1)
        self.assertEqual(self.client.get(f"/api/albums/{album['id']}").json()["count"], 1)
        self.assertEqual(self.client.delete(f"/api/albums/{album['id']}").status_code, 200)

    def test_bulk_tags(self):
        self.post("/api/jobs", {"kind": "scan"})
        wait_jobs(self.client)
        ids = [a["id"] for a in self.client.get("/api/search", params={"q": "旅行"}).json()["results"]][:2]
        self.assertEqual(len(ids), 2)
        r = self.post("/api/assets/bulk", {"ids": ids, "action": "add_tags", "tags": ["#嘉義車站", "交件"]}).json()
        self.assertEqual(r["done"], 2)
        found = self.client.get("/api/search", params={"q": "tag:嘉義車站"}).json()
        self.assertEqual(sorted(a["id"] for a in found["results"]), sorted(ids))
        self.assertEqual(self.post("/api/assets/bulk", {"ids": ids, "action": "add_tags", "tags": ["嘉義車站"]}).json()["done"], 0)
        self.post("/api/assets/bulk", {"ids": ids[:1], "action": "remove_tags", "tags": ["嘉義車站"]})
        found = self.client.get("/api/search", params={"q": "嘉義車站"}).json()
        self.assertEqual([a["id"] for a in found["results"]], ids[1:])
        kw = self.client.get(f"/api/assets/{ids[0]}").json()["keywords"]
        self.assertEqual(kw, ["交件"])

    def test_marks_library_only(self):
        """星等、顏色標籤與拒絕（單張與批次）只寫進圖庫，硬碟上的檔案一個位元都不變。"""
        self.post("/api/jobs", {"kind": "scan"})
        wait_jobs(self.client)
        before = {p: p.read_bytes() for p in self.photos.rglob("*") if p.is_file()}
        ids = [a["id"] for a in self.client.get("/api/search", params={"q": "type:photo"}).json()["results"]]
        d = self.post(f"/api/assets/{ids[0]}/marks", {"rating": 4, "label": "red"}).json()
        self.assertEqual((d["rating"], d["label"]), (4, "red"))
        self.assertNotIn("written_to", d)
        self.assertEqual(self.post(f"/api/assets/{ids[0]}/marks", {"label": "orange"}).status_code, 400)
        r = self.post("/api/assets/bulk", {"ids": ids, "action": "rating", "value": -1}).json()
        self.assertEqual((r["done"], r["errors"]), (len(ids), []))
        self.assertEqual(self.client.get("/api/search", params={"q": "is:rejected"}).json()["total"], len(ids))
        after = {p: p.read_bytes() for p in self.photos.rglob("*") if p.is_file()}
        self.assertEqual(after, before)
        self.assertIn(self.post(f"/api/assets/{ids[0]}/xmp", {"rating": 5}).status_code, (404, 405))  # 舊的寫回 API 已移除

    def test_search_scope(self):
        rid = self.client.get("/api/folders").json()["roots"][0]["id"]
        every = self.client.get("/api/search", params={"q": "type:photo"}).json()
        self.assertEqual((every["total"], every["scope"]), (3, None))
        here = self.client.get("/api/search", params={"q": "type:photo", "scope": f"folder:{rid}:2023 旅行"}).json()
        self.assertEqual(sorted(a["name"] for a in here["results"]), ["car.jpg", "sea.jpg"])
        self.assertEqual(here["scope"]["label"], "資料夾「2023 旅行」")
        whole = self.client.get("/api/search", params={"q": "type:photo", "scope": f"folder:{rid}:"}).json()
        self.assertEqual(whole["total"], 3)
        sea = self.client.get("/api/search", params={"q": "海邊", "scope": f"folder:{rid}:hiking"}).json()
        self.assertEqual(sea["total"], 0)
        car = next(a for a in every["results"] if a["name"] == "car.jpg")
        res = self.post("/api/assets/bulk", {"ids": [car["id"]], "action": "add_to_album", "name": "車"}).json()
        album = self.client.get("/api/search", params={"q": "type:photo", "scope": f"album:{res['album_id']}"}).json()
        self.assertEqual([a["name"] for a in album["results"]], ["car.jpg"])
        # 收藏後快取要失效，我的最愛範圍立刻看得到
        self.assertEqual(self.client.get("/api/search", params={"q": "type:photo", "scope": "favorites"}).json()["total"], 0)
        self.post(f"/api/assets/{car['id']}", {"favorite": True})
        self.assertEqual(self.client.get("/api/search", params={"q": "type:photo", "scope": "favorites"}).json()["total"], 1)
        # 看不懂的範圍就當作全部圖庫
        self.assertEqual(self.client.get("/api/search", params={"q": "type:photo", "scope": "nope:1"}).json()["total"], 3)

    def test_background_warm(self):
        import io
        from contextlib import redirect_stdout

        out = io.StringIO()
        with redirect_stdout(out):
            self.client.app.state.warm_now()  # 預先計算所有統計頁，不應該有任何一頁失敗
        self.assertNotIn("預先計算", out.getvalue())
        before = self.client.get("/api/explore").json()
        self.post(f"/api/assets/{self.image('car.jpg')['id']}", {"user_tags": "暖機測試"})
        after = self.client.get("/api/explore").json()
        self.assertNotEqual(before, after)  # 修改後快取已清掉

    def test_search_explore_models_jobs(self):
        data = self.client.get("/api/search", params={"q": "海邊"}).json()
        self.assertEqual((data["total"], data["results"][0]["type"]), (1, "photo"))
        explore = self.client.get("/api/explore").json()
        self.assertIn("森林", [t["value"] for t in explore["tags"]])
        self.assertEqual(explore["years"][0]["value"], "2023")
        models = self.client.get("/api/models").json()
        self.assertTrue(models["ollama_ok"])
        rec = {m["name"]: m for m in models["recommended"]}
        self.assertTrue(rec["qwen2.5vl:7b"]["installed"])
        self.assertFalse(rec["bge-m3"]["installed"])
        self.post("/api/jobs", {"kind": "pull", "model": "bge-m3"})
        self.post("/api/jobs", {"kind": "scan"})
        snap = wait_jobs(self.client)
        scans = [j for j in snap["recent"] if j["label"] == "掃描"]
        self.assertTrue(scans and scans[0]["error"] is None, snap["recent"])
        pulls = [j for j in snap["recent"] if j["kind"] == "pull"]
        self.assertTrue(pulls and pulls[0]["error"] is None, snap["recent"])
        s = self.post("/api/settings", {"vision_model": "qwen2.5vl:3b", "port": 1}).json()
        self.assertEqual((s["vision_model"], s["port"]), ("qwen2.5vl:3b", 8765))  # port 不能從網頁改

    def test_ai_test_endpoint(self):
        self.post("/api/jobs", {"kind": "scan"})
        wait_jobs(self.client)
        r = self.client.post("/api/ai/test", json={})
        self.assertEqual(r.status_code, 200, r.text)
        data = r.json()
        self.assertTrue(data["ok"], data)
        self.assertTrue(data["name"].endswith(".jpg"))
        self.assertTrue(data["result"]["description"])

    def test_detail_with_binary_columns(self):
        self.post("/api/jobs", {"kind": "scan"})
        wait_jobs(self.client)
        conn = db.connect(self.cfg.db_path)
        image_id = conn.execute("SELECT id FROM images LIMIT 1").fetchone()[0]
        conn.execute("UPDATE images SET clip = ?, embedding = ? WHERE id = ?", (b"\xae\xcb\x00\xff" * 8, b"\xae\x01", image_id))
        conn.commit()
        conn.close()
        r = self.client.get(f"/api/assets/{image_id}")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertNotIn("clip", r.json())

    def test_spa_and_errors(self):
        self.assertEqual(self.client.get("/albums/3").status_code, 200)
        self.assertEqual(self.client.get("/api/assets/99999").status_code, 404)
        r = self.client.post("/api/assets/bulk", content="x", headers={"content-type": "text/plain"})
        self.assertEqual(r.status_code, 415)


class SecurityTests(LibraryTestCase):
    def make_client(self, host, client_ip, lan=0, bound="127.0.0.1"):
        from fastapi.testclient import TestClient

        from lumilib.server import create_app

        self.cfg.lan = lan
        app = create_app(self.cfg, bound_host=bound, client_factory=FakeClient, start_jobs_on_boot=False)
        client = TestClient(app, base_url=f"http://{host}", client=(client_ip, 50000))
        client.__enter__()
        self.addCleanup(client.__exit__, None, None, None)
        return client

    def test_remote_blocked_when_lan_off(self):
        c = self.make_client("192.168.1.5:8765", "192.168.1.9")
        self.assertEqual(c.get("/api/server").status_code, 403)

    def test_dns_rebinding_host_is_not_local(self):
        c = self.make_client("evil.example:8765", "127.0.0.1")
        self.assertEqual(c.get("/api/server").status_code, 403)

    def test_cross_origin_post_blocked(self):
        c = self.make_client("127.0.0.1:8765", "127.0.0.1")
        r = c.post("/api/albums", json={"name": "x"}, headers={"Origin": "http://evil.example"})
        self.assertEqual(r.status_code, 403)

    def test_lan_requires_login(self):
        from lumilib.auth import Auth

        Auth(self.cfg.auth_file).set_password("secret123")
        c = self.make_client("192.168.1.5:8765", "192.168.1.9", lan=1, bound="0.0.0.0")
        self.assertEqual(c.get("/api/server").status_code, 401)
        self.assertFalse(c.get("/api/auth/status").json()["authenticated"])
        self.assertEqual(c.post("/api/auth/login", json={"password": "wrong"}).status_code, 401)
        self.assertEqual(c.post("/api/auth/login", json={"password": "secret123"}).status_code, 200)
        self.assertEqual(c.get("/api/server").status_code, 200)
        self.assertEqual(c.post("/api/pick-folder", json={}).status_code, 403)  # 只能在 Mac 本機
        self.assertEqual(c.post("/api/lan", json={"enabled": False}).status_code, 403)


if __name__ == "__main__":
    unittest.main()
