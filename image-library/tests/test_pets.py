"""寵物辨識：偵測後分群、命名、合併、搜尋、移出照片、清除（用假的模型，不需要下載）。"""

import shutil
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from lumilib import db
from lumilib.config import load_config
from lumilib.petid import Animal, KINDS, PetEngine, _nms, clear_all, cluster_pets, detect_pets, list_pets, merge_pets, rename_pet
from lumilib.scanner import scan_all
from lumilib.search import search


class FakeEngine:
    """依照片顏色決定：紅＝貓「小橘」、藍＝狗「黑糖」、綠＝另一隻狗，灰色沒有動物。"""

    BASES = {"red": ("cat", 0), "blue": ("dog", 1), "green": ("dog", 2)}

    def __init__(self):
        rng = np.random.default_rng(7)
        self.vecs = [rng.normal(size=384).astype(np.float32) for _ in range(3)]
        self.noise = np.random.default_rng(3)

    def analyze(self, img):
        r, g, b = img.convert("RGB").resize((1, 1)).getpixel((0, 0))
        key = "red" if r > 150 and g < 100 else "blue" if b > 150 and r < 100 else "green" if g > 150 and r < 100 else None
        if key is None:
            return []
        kind, i = self.BASES[key]
        v = self.vecs[i] + self.noise.normal(scale=0.15, size=384).astype(np.float32)
        v /= np.linalg.norm(v)
        w, h = img.size
        return [Animal(kind, (w * 0.2, h * 0.2, w * 0.8, h * 0.9), 0.9, v)]


class PetTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        photos = self.tmp / "photos"
        photos.mkdir()
        colors = {"red": (220, 60, 40), "blue": (30, 60, 220), "green": (40, 200, 60), "gray": (128, 128, 128)}
        counts = {"red": 3, "blue": 3, "green": 1, "gray": 2}
        for name, n in counts.items():
            for i in range(n):
                Image.new("RGB", (320, 240), colors[name]).save(photos / f"{name}{i}.jpg")
        self.cfg = load_config(self.tmp / "home")
        self.conn = db.connect(self.cfg.db_path)
        db.add_root(self.conn, photos)
        scan_all(self.conn, self.cfg)

    def tearDown(self):
        self.conn.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_all(self):
        res = detect_pets(self.conn, self.cfg, engine=FakeEngine())
        return res, cluster_pets(self.conn, self.cfg)

    def test_detect_and_cluster(self):
        res, c = self.run_all()
        self.assertEqual(res.scanned, 9)
        self.assertEqual(res.animals, 7)
        # 出現兩次以上才成為寵物：紅貓、藍狗；綠狗只有一張先不建立
        pets = list_pets(self.conn)
        self.assertEqual(sorted((p["kind"], p["count"]) for p in pets), [("cat", 3), ("dog", 3)])
        self.assertEqual(c.pets_new, 2)
        # 縮圖存在
        det = self.conn.execute("SELECT id FROM pet_detections LIMIT 1").fetchone()
        from lumilib.petid import thumb_path

        self.assertTrue(thumb_path(self.cfg, det["id"]).exists())
        # 再跑一次不會重複
        res2, _ = self.run_all()
        self.assertEqual(res2.scanned, 0)

    def test_name_merge_search_clear(self):
        self.run_all()
        pets = {p["kind"]: p for p in list_pets(self.conn)}
        rename_pet(self.conn, pets["cat"]["id"], "小橘")
        self.assertEqual(search(self.conn, "小橘")["total"], 3)
        merge_pets(self.conn, pets["cat"]["id"], [pets["dog"]["id"]])
        self.assertEqual([p["count"] for p in list_pets(self.conn)], [6])
        self.assertEqual(clear_all(self.conn, self.cfg), 7)
        self.assertEqual(list_pets(self.conn), [])
        self.assertEqual(search(self.conn, "小橘")["total"], 0)

    def test_api(self):
        from fastapi.testclient import TestClient

        from lumilib.server import create_app

        self.run_all()
        app = create_app(self.cfg, start_jobs_on_boot=False)
        with TestClient(app, base_url="http://127.0.0.1:8765", client=("127.0.0.1", 50000)) as client:
            data = client.get("/api/pets").json()
            self.assertEqual(len(data["pets"]), 2)
            self.assertFalse(data["installed"])
            cat = next(p for p in data["pets"] if p["kind"] == "cat")
            dog = next(p for p in data["pets"] if p["kind"] == "dog")
            self.assertEqual(client.get(f"/api/pet-thumbs/{cat['cover']}").status_code, 200)
            detail = client.get(f"/api/petid/{cat['id']}").json()
            self.assertEqual(len(detail["assets"]), 3)
            self.assertEqual(client.post(f"/api/petid/{cat['id']}", json={"name": "小橘"}).json()["id"], cat["id"])
            # 照片的資訊會列出牠
            info = client.get(f"/api/assets/{detail['assets'][0]['id']}").json()
            self.assertEqual(info["pets"][0]["name"], "小橘")
            # 移出一張
            out = client.post(f"/api/petid/{cat['id']}", json={"remove": [detail["assets"][0]["id"]]}).json()
            self.assertEqual(out["removed"], 1)
            self.assertEqual(len(client.get(f"/api/petid/{cat['id']}").json()["assets"]), 2)
            # 隱藏
            client.post(f"/api/petid/{dog['id']}", json={"hidden": True})
            self.assertEqual([p["id"] for p in client.get("/api/pets").json()["pets"]], [cat["id"]])
            self.assertEqual(len(client.get("/api/petid/all").json()), 2)
            models = client.get("/api/pets/models").json()
            self.assertEqual({m["name"] for m in models}, {"standard", "fast", "accurate"})
            # 換模型會清掉舊的辨識結果
            client.post("/api/settings", json={"pet_model": "fast"})
            self.assertEqual(client.get("/api/pets").json()["pets"], [])
            self.assertEqual(client.get("/api/pets").json()["pending"], 9)


class YoloxDecodeTests(unittest.TestCase):
    def test_decode_and_nms(self):
        """用假的 YOLOX 輸出確認解碼：網格位置、步距、類別分數。"""

        class FakeSession:
            def __init__(self, out):
                self.out = out

            def run(self, _names, _feeds):
                return [self.out]

        size = 64
        eng = PetEngine.__new__(PetEngine)
        eng.size = size
        eng._grid = PetEngine._make_grid(size)
        eng.det_input = "images"
        n = eng._grid[0].shape[0]
        out = np.zeros((1, n, 85), dtype=np.float32)
        # 第 10 格（stride 8，x=2,y=1）放一隻狗、兩個重疊框
        for idx, obj in ((10, 0.9), (11, 0.7)):
            out[0, idx, 0:2] = 0.5
            out[0, idx, 2:4] = np.log(2)  # 寬高 2*8=16（不超出邊界）
            out[0, idx, 4] = obj
            out[0, idx, 5 + 16] = 0.95
        out[0, 11, 0] = -0.4  # 第二個框幾乎和第一個重疊，應被合併
        eng.det = FakeSession(out)
        found = eng.detect(Image.new("RGB", (128, 128)), threshold=0.4)
        self.assertEqual(len(found), 1)
        a = found[0]
        self.assertEqual(a.kind, KINDS[16])
        # 網格 (2,1)+0.5 → 中心 (20,12)，在 64 輸入上；原圖 128 → 放大兩倍
        cx, cy = (a.box[0] + a.box[2]) / 2, (a.box[1] + a.box[3]) / 2
        self.assertAlmostEqual(cx, 40, delta=0.5)
        self.assertAlmostEqual(cy, 24, delta=0.5)
        self.assertEqual(_nms(np.array([[0, 0, 10, 10], [1, 1, 10, 10], [50, 50, 60, 60]], dtype=np.float32),
                              np.array([0.9, 0.8, 0.7], dtype=np.float32)), [0, 2])


class MigrationTests(unittest.TestCase):
    def test_v8_database_gets_pet_tables(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            path = tmp / "lib.db"
            conn = db.connect(path)
            conn.execute("DROP TABLE pet_detections")
            conn.execute("DROP TABLE pets")
            conn.execute("PRAGMA user_version = 8")
            conn.commit()
            conn.close()
            conn = db.connect(path)
            conn.execute("SELECT pets_at, pets_model FROM images LIMIT 1").fetchall()
            conn.execute("SELECT * FROM pet_detections LIMIT 1").fetchall()
            conn.close()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
