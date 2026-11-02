"""執行：python -m unittest discover -s tests（在 image-library 目錄下）"""

import json
import shutil
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from PIL import Image

from lumilib import db
from lumilib.analyzer import OllamaUnavailable, analyze_images, embed_images, parse_model_json
from lumilib.config import load_config
from lumilib.scanner import scan_all
from lumilib.search import parse_query, search
from lumilib.server import JobRunner, make_handler


def make_photo(path: Path, color, size=(64, 48), taken="2023:07:14 18:30:00", model="iPhone 15 Pro", make="Apple"):
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", size, color)
    exif = Image.Exif()
    exif[271] = make
    exif[272] = model
    exif.get_ifd(0x8769)[36867] = taken
    img.save(path, "JPEG", exif=exif.tobytes())


class FakeClient:
    """依圖片主色回傳固定的分析結果，避免測試需要真的模型。"""

    def __init__(self):
        self.calls = 0
        self.prompts = []

    def describe(self, model, prompt, image_b64):
        import base64
        import io

        self.calls += 1
        self.prompts.append(prompt)
        img = Image.open(io.BytesIO(base64.b64decode(image_b64))).convert("RGB")
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
        vecs = []
        for t in texts:
            vecs.append([
                1.0 if ("海" in t or "沙灘" in t) else 0.0,
                1.0 if ("車" in t) else 0.0,
                1.0 if ("森林" in t or "樹" in t) else 0.0,
                0.1,
            ])
        return vecs


class LibraryTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.photos = self.tmp / "photos"
        make_photo(self.photos / "2023 旅行" / "car.jpg", (230, 30, 30))
        make_photo(self.photos / "2023 旅行" / "sea.jpg", (20, 60, 240), taken="2023:08:01 19:00:00")
        make_photo(self.photos / "hiking" / "forest.jpg", (30, 160, 40), taken="2021:05:02 09:00:00", model="X-T5", make="FUJIFILM")
        (self.photos / "notes.txt").write_text("not an image")
        (self.photos / ".hidden").mkdir()
        make_photo(self.photos / ".hidden" / "secret.jpg", (0, 0, 0))
        self.cfg = load_config(self.tmp / "home")
        self.conn = db.connect(self.cfg.db_path)
        self.root = db.add_root(self.conn, self.photos, "相片")

    def tearDown(self):
        self.conn.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def analyze(self, client=None):
        return analyze_images(self.conn, self.cfg, client or FakeClient())


class ScanTests(LibraryTestCase):
    def test_scan_indexes_images_and_metadata(self):
        [res] = scan_all(self.conn, self.cfg)
        self.assertEqual(res.added, 3)  # 隱藏資料夾與非圖片略過
        row = self.conn.execute("SELECT * FROM images WHERE rel_path = 'hiking/forest.jpg'").fetchone()
        self.assertEqual(row["camera"], "FUJIFILM X-T5")
        self.assertEqual(row["taken_at"], "2021-05-02T09:00:00")
        self.assertEqual((row["width"], row["height"]), (64, 48))
        car = self.conn.execute("SELECT * FROM images WHERE rel_path LIKE '%car.jpg'").fetchone()
        self.assertEqual(car["camera"], "Apple iPhone 15 Pro")
        make_photo(self.tmp / "canon.jpg", (1, 2, 3), model="Canon EOS R5", make="Canon")
        from lumilib.imaging import open_image
        img, meta = open_image(self.tmp / "canon.jpg")
        img.close()
        self.assertEqual(meta["camera"], "Canon EOS R5")  # 品牌不重複
        self.assertTrue(list(self.cfg.thumbs_dir.rglob("*.jpg")))

    def test_rescan_is_incremental(self):
        scan_all(self.conn, self.cfg)
        [res] = scan_all(self.conn, self.cfg)
        self.assertEqual((res.added, res.unchanged, res.missing), (0, 3, 0))

    def test_move_keeps_analysis(self):
        scan_all(self.conn, self.cfg)
        self.analyze()
        old = self.conn.execute("SELECT * FROM images WHERE rel_path LIKE '%sea.jpg'").fetchone()
        (self.photos / "海邊").mkdir()
        (self.photos / "2023 旅行" / "sea.jpg").rename(self.photos / "海邊" / "renamed.jpg")
        [res] = scan_all(self.conn, self.cfg)
        self.assertEqual((res.moved, res.added, res.missing), (1, 0, 0))
        new = db.get_image(self.conn, old["id"])
        self.assertEqual(new["rel_path"], "海邊/renamed.jpg")
        self.assertEqual(new["description"], old["description"])

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
        # 硬碟換了代號：relocate 後全部找回，分析不丟失
        db.relocate_root(self.conn, "相片", moved)
        [res] = scan_all(self.conn, self.cfg)
        self.assertEqual((res.added, res.unchanged), (0, 3))

    def test_duplicate_reuses_analysis(self):
        scan_all(self.conn, self.cfg)
        self.analyze()
        shutil.copy2(self.photos / "hiking" / "forest.jpg", self.photos / "hiking" / "copy.jpg")
        [res] = scan_all(self.conn, self.cfg)
        self.assertEqual((res.added, res.reused), (1, 1))
        copy = self.conn.execute("SELECT * FROM images WHERE rel_path = 'hiking/copy.jpg'").fetchone()
        self.assertEqual(copy["description"], "綠色的森林步道")

    def test_overlapping_roots_rejected(self):
        with self.assertRaises(ValueError):
            db.add_root(self.conn, self.photos / "hiking", "子資料夾")

    def test_unreadable_image_recorded_as_error(self):
        (self.photos / "broken.jpg").write_bytes(b"not really a jpeg")
        scan_all(self.conn, self.cfg)
        row = self.conn.execute("SELECT * FROM images WHERE rel_path = 'broken.jpg'").fetchone()
        self.assertIn("無法讀取", row["error"])


class AnalyzeAndSearchTests(LibraryTestCase):
    def setUp(self):
        super().setUp()
        scan_all(self.conn, self.cfg)

    def test_analyze_and_keyword_search(self):
        client = FakeClient()
        res = self.analyze(client)
        self.assertEqual((res.analyzed, res.failed), (3, 0))
        self.assertIn("2023 旅行/car.jpg", " ".join(client.prompts))
        self.assertEqual([r["filename"] for r in search(self.conn, "跑車")["results"]], ["car.jpg"])
        self.assertEqual(search(self.conn, "BEACH")["results"][0]["filename"], "sea.jpg")
        self.assertEqual(search(self.conn, "sunset bar")["total"], 1)  # 圖中文字
        self.assertEqual(search(self.conn, "街道")["results"][0]["tags"][-1], "街道")  # 去掉 #
        # 再次執行不會重跑
        self.assertEqual(self.analyze(client).analyzed, 0)

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
        self.assertEqual(search(self.conn, "root:相片 森林")["total"], 1)
        self.assertEqual(search(self.conn, "100%_")["total"], 0)  # LIKE 萬用字元被跳脫

    def test_status_filters(self):
        self.assertEqual(search(self.conn, "is:pending")["total"], 3)
        self.analyze()
        self.assertEqual(search(self.conn, "is:analyzed")["total"], 3)

    def test_user_tags_searchable(self):
        self.analyze()
        image = search(self.conn, "森林")["results"][0]
        db.set_user_fields(self.conn, image["id"], user_tags=["家庭出遊", " 家庭出遊 ", ""], note="和爸媽")
        self.assertEqual(search(self.conn, "家庭出遊")["results"][0]["user_tags"], ["家庭出遊"])
        self.assertEqual(search(self.conn, "爸媽")["total"], 1)

    def test_semantic_search(self):
        self.cfg.embed_model = "fake-embed"
        res = self.analyze()
        self.assertEqual(res.embedded, 3)
        client = FakeClient()
        # 「沙灘」不在任何文字中，但語意向量相近
        out = search(self.conn, "沙灘", semantic=True, embedder=client, embed_model="fake-embed")
        self.assertEqual(out["mode"], "hybrid")
        self.assertEqual(out["results"][0]["filename"], "sea.jpg")
        self.assertEqual(out["results"][0]["match"], "semantic")
        self.assertEqual(embed_images(self.conn, self.cfg, client), 0)

    def test_model_failures(self):
        class Broken(FakeClient):
            def describe(self, *a):
                raise ValueError("模型沒有回傳有效 JSON")

        res = self.analyze(Broken())
        self.assertEqual(res.failed, 3)
        self.assertEqual(search(self.conn, "is:failed")["total"], 3)
        self.assertEqual(self.analyze().analyzed, 0)  # 失敗的預設不重試
        self.assertEqual(analyze_images(self.conn, self.cfg, FakeClient(), retry_failed=True).analyzed, 3)

    def test_ollama_down_aborts_without_marking(self):
        class Down(FakeClient):
            def describe(self, *a):
                raise OllamaUnavailable("down")

        with self.assertRaises(OllamaUnavailable):
            self.analyze(Down())
        self.assertEqual(db.stats(self.conn)["pending"], 3)


class ParsingTests(unittest.TestCase):
    def test_parse_query(self):
        q = parse_query('貓 "日落 海邊" -狗 tag:可愛 year:2024 http://x')
        self.assertEqual(q.terms, ["貓", "日落 海邊", "http://x"])
        self.assertEqual(q.excludes, ["狗"])
        self.assertEqual(q.filters, [("tag", "可愛"), ("year", "2024")])
        self.assertEqual(parse_query('unbalanced "quote').terms, ["unbalanced", "quote"])

    def test_parse_model_json(self):
        self.assertEqual(parse_model_json('<think>hmm</think>{"a": 1}'), {"a": 1})
        self.assertEqual(parse_model_json('```json\n{"a": 2}\n```'), {"a": 2})
        with self.assertRaises(ValueError):
            parse_model_json("no json")


class ServerTests(LibraryTestCase):
    def setUp(self):
        super().setUp()
        scan_all(self.conn, self.cfg)
        self.analyze()
        jobs = JobRunner(self.cfg)
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.cfg, jobs, set()))
        port = self.httpd.server_address[1]
        self.httpd.RequestHandlerClass = make_handler(self.cfg, jobs, {f"127.0.0.1:{port}"})
        self.base = f"http://127.0.0.1:{port}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        super().tearDown()

    def get(self, path, headers=None):
        req = urllib.request.Request(self.base + path, headers=headers or {})
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, resp.headers.get("Content-Type"), resp.read()

    def post(self, path, body):
        req = urllib.request.Request(
            self.base + path, data=json.dumps(body).encode(), method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read())

    def test_pages_and_api(self):
        status, ctype, body = self.get("/")
        self.assertEqual(status, 200)
        self.assertIn(b"Lumitake Library", body)
        _, ctype, _ = self.get("/static/app.js")
        self.assertIn("javascript", ctype)
        stats = json.loads(self.get("/api/stats")[2])
        self.assertEqual(stats["stats"]["analyzed"], 3)
        data = json.loads(self.get("/api/search?q=%E6%B5%B7%E9%82%8A")[2])  # 海邊
        self.assertEqual(data["total"], 1)
        image_id = data["results"][0]["id"]
        _, ctype, thumb = self.get(f"/thumb/{image_id}")
        self.assertEqual(ctype, "image/jpeg")
        self.assertTrue(thumb.startswith(b"\xff\xd8"))
        _, ctype, _ = self.get(f"/preview/{image_id}")
        self.assertEqual(ctype, "image/jpeg")
        detail = self.post(f"/api/image/{image_id}", {"user_tags": "度假，夏天", "note": "好天氣"})
        self.assertEqual(detail["user_tags"], ["度假", "夏天"])
        self.assertNotIn("embedding", detail)
        tags = json.loads(self.get("/api/tags")[2])
        self.assertIn("度假", [t["tag"] for t in tags])

    def test_rejects_foreign_host_and_traversal(self):
        for path, headers in (
            ("/api/stats", {"Host": "evil.example:80"}),
            ("/api/stats", {"Origin": "http://evil.example"}),
        ):
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                self.get(path, headers)
            self.assertEqual(ctx.exception.code, 403)
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.get("/static/..%2F..%2Fdb.py")
        self.assertEqual(ctx.exception.code, 404)


if __name__ == "__main__":
    unittest.main()
