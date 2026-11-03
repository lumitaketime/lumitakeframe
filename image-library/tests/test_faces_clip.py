"""人臉分群、CLIP 圖像搜尋、跨語言查詢改寫的測試。

- 人臉：用假的偵測器（固定特徵向量）測分群、命名、合併、搜尋。
  設定 LUMILIB_TEST_FACE_MODELS=含 buffalo_s/ 的資料夾、LUMILIB_TEST_FACE_IMAGE=團體照 時，另外跑真模型測試。
- CLIP：用 onnx 即時建立一組極小的假模型（依顏色比對 red / blue），測整條流程。
"""

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from lumilib import db, faces
from lumilib.config import load_config
from lumilib.scanner import scan_all
from lumilib.search import search

try:
    import onnx
    from onnx import TensorProto, helper
    from tokenizers import Tokenizer, models, pre_tokenizers

    HAS_ONNX_TOOLS = True
except ImportError:  # pragma: no cover
    HAS_ONNX_TOOLS = False


def unit(v):
    v = np.asarray(v, dtype=np.float32)
    return v / np.linalg.norm(v)


PERSON_A = unit(np.r_[np.ones(256), np.zeros(256)])
PERSON_B = unit(np.r_[np.zeros(256), np.ones(256)])


class FakeEngine:
    """依檔名決定照片裡有誰：a、b、ab。"""

    def analyze(self, img):
        return []

    def faces_for(self, name):
        out = []
        rng = np.random.default_rng(len(name))
        for who in name.split("_")[0]:
            base = PERSON_A if who == "a" else PERSON_B
            f = faces.Face((10.0, 10.0, 50.0, 50.0), 0.9, np.zeros((5, 2)))
            f.embedding = unit(base + rng.normal(0, 0.01, 512))
            out.append(f)
        return out


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
        shutil.rmtree(self.tmp, ignore_errors=True)


class FaceTests(Base):
    def setUp(self):
        super().setUp()
        names = ["a_1", "a_2", "a_3", "ab_4", "b_5", "b_6", "b_7", "c_8"]
        for i, n in enumerate(names):
            Image.new("RGB", (80, 60), (i * 20, 80, 120)).save(self.photos / f"{n}.jpg")
        scan_all(self.conn, self.cfg)
        engine = FakeEngine()
        original = engine.analyze

        def analyze(img, _engine=engine):
            return original(img)

        # 讓假偵測器知道目前是哪個檔案
        rows = self.conn.execute("SELECT id, rel_path FROM images").fetchall()
        self.ids = {r["rel_path"].split(".")[0]: r["id"] for r in rows}
        for r in rows:
            stem = r["rel_path"].split(".")[0]
            found = engine.faces_for(stem) if not stem.startswith("c") else []
            for f in found:
                self.conn.execute(
                    "INSERT INTO faces (image_id, x1, y1, x2, y2, score, embedding, model, created_at) VALUES (?, .1, .1, .5, .5, ?, ?, ?, ?)",
                    (r["id"], f.score, f.embedding.tobytes(), self.cfg.face_model, db.now_iso()),
                )
            self.conn.execute("UPDATE images SET faces_at = ?, faces_model = ? WHERE id = ?", (db.now_iso(), self.cfg.face_model, r["id"]))
        self.conn.commit()

    def people(self):
        return faces.list_persons(self.conn)

    def test_cluster_creates_two_people(self):
        res = faces.cluster_faces(self.conn, self.cfg)
        self.assertEqual(res.people_new, 2)
        counts = sorted(p["count"] for p in self.people())
        self.assertEqual(counts, [4, 4])  # 合照 ab_4 兩人都算

    def test_min_faces_threshold(self):
        self.cfg.face_min_faces = 5
        self.assertEqual(faces.cluster_faces(self.conn, self.cfg).people_new, 0)
        self.cfg.face_min_faces = 3
        self.assertEqual(faces.cluster_faces(self.conn, self.cfg).people_new, 2)

    def test_name_search_merge_and_remove(self):
        faces.cluster_faces(self.conn, self.cfg)
        pa = next(p for p in self.people() if self.ids["a_1"] in self._images(p["id"]))
        pb = next(p for p in self.people() if p["id"] != pa["id"])
        faces.rename_person(self.conn, pa["id"], "媽媽")
        self.assertEqual(search(self.conn, "媽媽")["total"], 4)
        self.assertEqual(search(self.conn, "person:媽媽")["total"], 4)
        # 新照片進來會自動歸入已命名的人
        self.conn.execute(
            "INSERT INTO faces (image_id, x1, y1, x2, y2, score, embedding, model, created_at) VALUES (?, .1, .1, .5, .5, .9, ?, ?, ?)",
            (self.ids["c_8"], unit(PERSON_A + 0.01).tobytes(), self.cfg.face_model, db.now_iso()),
        )
        self.assertEqual(faces.cluster_faces(self.conn, self.cfg).assigned, 1)
        self.assertEqual(search(self.conn, "媽媽")["total"], 5)
        # 「不是這個人」之後不會再被自動歸回
        faces.remove_images_from_person(self.conn, pa["id"], [self.ids["c_8"]])
        faces.cluster_faces(self.conn, self.cfg)
        self.assertEqual(search(self.conn, "person:媽媽")["total"], 4)
        # 合併：沒有名字的目標沿用來源名字
        faces.merge_persons(self.conn, pb["id"], [pa["id"]])
        self.assertEqual(len(self.people()), 1)
        self.assertEqual(self.people()[0]["name"], "媽媽")

    def test_recluster_keeps_named(self):
        faces.cluster_faces(self.conn, self.cfg)
        pa = self.people()[0]
        faces.rename_person(self.conn, pa["id"], "阿明")
        faces.recluster(self.conn, self.cfg)
        names = [p["name"] for p in self.people()]
        self.assertIn("阿明", names)
        self.assertEqual(len(names), 2)

    def test_clear_all(self):
        faces.cluster_faces(self.conn, self.cfg)
        faces.clear_all(self.conn, self.cfg)
        self.assertEqual(self.people(), [])
        self.assertEqual(db.stats(self.conn)["faces_pending"], 8)

    def test_alignment_math(self):
        t = faces.similarity_transform(faces.ARCFACE_DST * 2 + 5, faces.ARCFACE_DST)
        pts = (np.c_[faces.ARCFACE_DST * 2 + 5, np.ones(5)] @ t.T)[:, :2]
        np.testing.assert_allclose(pts, faces.ARCFACE_DST, atol=1e-3)

    def _images(self, person_id):
        return {r[0] for r in self.conn.execute("SELECT image_id FROM faces WHERE person_id = ?", (person_id,))}


@unittest.skipUnless(os.environ.get("LUMILIB_TEST_FACE_MODELS") and os.environ.get("LUMILIB_TEST_FACE_IMAGE"), "需要真的人臉模型")
class RealFaceModelTests(Base):
    def test_detect_group_photo(self):
        src = Path(os.environ["LUMILIB_TEST_FACE_MODELS"])
        shutil.copytree(src, self.cfg.home / "models", dirs_exist_ok=True)
        self.cfg.face_model = "buffalo_s"
        shutil.copy(os.environ["LUMILIB_TEST_FACE_IMAGE"], self.photos / "group.jpg")
        Image.open(self.photos / "group.jpg").transpose(Image.Transpose.FLIP_LEFT_RIGHT).save(self.photos / "flip.jpg")
        scan_all(self.conn, self.cfg)
        res = faces.detect_faces(self.conn, self.cfg)
        self.assertGreaterEqual(res.faces, 8)
        self.cfg.face_min_faces = 2
        c = faces.cluster_faces(self.conn, self.cfg)
        self.assertEqual(c.people_new, res.faces // 2)  # 每個人在原圖與翻轉圖各出現一次
        face_id = self.conn.execute("SELECT id FROM faces LIMIT 1").fetchone()[0]
        self.assertTrue(faces.face_thumb_path(self.cfg, face_id).exists())


def build_fake_clip(directory: Path):
    """極小的 CLIP：畫面取各色平均，文字取詞向量總和。"""
    (directory / "visual").mkdir(parents=True)
    (directory / "textual").mkdir(parents=True)
    w = helper.make_tensor("w", TensorProto.FLOAT, [3, 4], [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0])
    visual = helper.make_graph(
        [helper.make_node("ReduceMean", ["image"], ["m"], axes=[2, 3], keepdims=0),
         helper.make_node("MatMul", ["m", "w"], ["embedding"])],
        "visual", [helper.make_tensor_value_info("image", TensorProto.FLOAT, [1, 3, 224, 224])],
        [helper.make_tensor_value_info("embedding", TensorProto.FLOAT, [1, 4])], [w],
    )
    vocab = ["<pad>", "<unk>", "red", "blue", "紅色", "藍色", "car", "sea"]
    table = {"red": [1, -1, -1, 0], "紅色": [1, -1, -1, 0], "car": [1, -1, -1, 0],
             "blue": [-1, -1, 1, 0], "藍色": [-1, -1, 1, 0], "sea": [-1, -1, 1, 0]}
    rows = [table.get(t, [0, 0, 0, 0]) for t in vocab]
    emb = helper.make_tensor("emb", TensorProto.FLOAT, [len(vocab), 4], [x for r in rows for x in r])
    textual = helper.make_graph(
        [helper.make_node("Gather", ["emb", "text"], ["g"]),
         helper.make_node("ReduceSum", ["g", "axes"], ["embedding"], keepdims=0)],
        "textual", [helper.make_tensor_value_info("text", TensorProto.INT32, [1, 77])],
        [helper.make_tensor_value_info("embedding", TensorProto.FLOAT, [1, 4])],
        [emb, helper.make_tensor("axes", TensorProto.INT64, [1], [1])],
    )
    for graph, sub in ((visual, "visual"), (textual, "textual")):
        model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 13)])
        model.ir_version = 8
        onnx.save(model, str(directory / sub / "model.onnx"))
    tok = Tokenizer(models.WordLevel({t: i for i, t in enumerate(vocab)}, unk_token="<unk>"))
    tok.pre_tokenizer = pre_tokenizers.Whitespace()
    tok.save(str(directory / "textual" / "tokenizer.json"))
    (directory / "textual" / "tokenizer_config.json").write_text(json.dumps({"pad_token": "<pad>"}))
    (directory / "visual" / "preprocess_cfg.json").write_text(json.dumps({"size": [224, 224], "resize_mode": "shortest"}))
    (directory / "config.json").write_text(json.dumps({"text_cfg": {"context_length": 77}}))


@unittest.skipUnless(HAS_ONNX_TOOLS, "需要 onnx 與 tokenizers")
class ClipTests(Base):
    def setUp(self):
        super().setUp()
        from lumilib import clip

        self.clip = clip
        Image.new("RGB", (300, 200), (230, 20, 20)).save(self.photos / "IMG_0001.jpg")  # 沒有任何文字資訊
        Image.new("RGB", (300, 200), (20, 30, 240)).save(self.photos / "IMG_0002.jpg")
        Image.new("RGB", (300, 200), (220, 30, 30)).save(self.photos / "IMG_0003.jpg")
        build_fake_clip(clip.model_dir(self.cfg, self.cfg.clip_model))
        clip._models.clear()
        clip.invalidate()
        scan_all(self.conn, self.cfg)

    def test_index_and_rank(self):
        self.assertTrue(self.clip.model_installed(self.cfg, self.cfg.clip_model))
        self.assertEqual(self.clip.index_images(self.conn, self.cfg), 3)
        self.assertEqual(self.clip.index_images(self.conn, self.cfg), 0)  # 已建立的不重做
        ranked = self.clip.rank(self.conn, self.cfg, ["紅色"])
        names = [db.get_image(self.conn, i)["rel_path"] for i, _ in ranked]
        self.assertEqual(set(names[:2]), {"IMG_0001.jpg", "IMG_0003.jpg"})
        self.assertEqual(names[-1], "IMG_0002.jpg")

    def test_search_finds_untagged_photos_by_image(self):
        self.clip.index_images(self.conn, self.cfg)

        def clip_rank(texts, allowed):
            return self.clip.rank(self.conn, self.cfg, texts, allowed)

        out = search(self.conn, "sea", clip_rank=clip_rank)
        self.assertEqual([r["filename"] for r in out["results"]], ["IMG_0002.jpg"])
        self.assertEqual(out["results"][0]["match"], "image")
        self.assertIn("image", out["modes"])
        # 篩選條件仍然有效
        self.assertEqual(search(self.conn, "sea -IMG_0002", clip_rank=clip_rank)["total"], 0)


class RewriteTests(Base):
    def setUp(self):
        super().setUp()
        for n, desc, tags in (("a", "A cat sleeping on the sofa", ["cat", "sofa"]),
                              ("b", "海邊的夕陽", ["海邊", "夕陽"]),
                              ("c", "城市夜景", ["城市"])):
            Image.new("RGB", (40, 30)).save(self.photos / f"{n}.jpg")
        scan_all(self.conn, self.cfg)
        for n, desc, tags in (("a", "A cat sleeping on the sofa", ["cat", "sofa"]),
                              ("b", "海邊的夕陽", ["海邊", "夕陽"]),
                              ("c", "城市夜景", ["城市"])):
            row = self.conn.execute("SELECT id FROM images WHERE rel_path = ?", (f"{n}.jpg",)).fetchone()
            self.conn.execute("UPDATE images SET description = ?, tags = ?, analyzed_at = ? WHERE id = ?",
                              (desc, json.dumps(tags, ensure_ascii=False), db.now_iso(), row["id"]))
            db.refresh_search_text(self.conn, row["id"])
        self.conn.commit()

    def test_rewrite_enables_cross_language(self):
        from lumilib.analyzer import rewrite_query

        class Client:
            calls = 0

            def chat_json(self, model, prompt, schema, timeout=None):
                Client.calls += 1
                return {"groups": [{"term": "貓", "synonyms": ["cat", "kitten", "貓咪"]},
                                   {"term": "沙發", "synonyms": ["sofa", "couch"]}],
                        "english": "a cat on a sofa"}

        self.assertEqual(search(self.conn, "貓 沙發")["total"], 0)  # 只有英文描述，原本找不到
        rw = rewrite_query(Client(), "m", ["貓", "沙發"])
        self.assertEqual(rw["groups"][0][:2], ["貓", "cat"])
        out = search(self.conn, "貓 沙發", groups=rw["groups"])
        self.assertEqual([r["filename"] for r in out["results"]], ["a.jpg"])
        self.assertIn("sofa", out["expanded"])
        rewrite_query(Client(), "m", ["貓", "沙發"])
        self.assertEqual(Client.calls, 1)  # 有快取

    def test_rewrite_english_to_chinese(self):
        from lumilib.analyzer import rewrite_query

        class Client:
            def chat_json(self, *a, **k):
                return {"groups": [{"term": "beach", "synonyms": ["海邊", "沙灘", "seaside"]}], "english": "beach"}

        rw = rewrite_query(Client(), "m2", ["beach"])
        self.assertEqual(search(self.conn, "beach", groups=rw["groups"])["results"][0]["filename"], "b.jpg")


class PlaceTests(Base):
    def test_gps_becomes_searchable_place(self):
        from lumilib import places

        if not places.available():
            self.skipTest("需要 geonamescache")
        Image.new("RGB", (40, 30)).save(self.photos / "kenting.jpg")
        Image.new("RGB", (40, 30)).save(self.photos / "nogps.jpg")
        scan_all(self.conn, self.cfg)
        self.conn.execute("UPDATE images SET lat = 21.95, lon = 120.78 WHERE rel_path = 'kenting.jpg'")
        self.conn.commit()
        self.assertEqual(places.geocode_images(self.conn), 1)
        row = self.conn.execute("SELECT * FROM images WHERE rel_path = 'kenting.jpg'").fetchone()
        self.assertEqual((row["place"], row["place_en"], row["country"]), ("恆春鎮", "Hengchun", "TW"))
        for q in ("恆春", "hengchun", "台灣", "taiwan", "place:恆春"):
            self.assertEqual(search(self.conn, q)["total"], 1, q)
        self.assertEqual(places.geocode_images(self.conn), 0)


if __name__ == "__main__":
    unittest.main()
