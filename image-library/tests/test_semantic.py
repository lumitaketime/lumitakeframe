"""用意思找文件：向量建立後，搜「預算」也找得到 budget.xlsx 與寫著「經費」的文件，排在字面相符的後面。"""

import unittest

from lumilib import db, semantic, textindex
from lumilib.find import find
from lumilib.scanner import scan_all

from test_catalog import CatalogTestCase

TOPICS = [("預算", "budget", "經費"), ("旅行", "travel", "旅遊"), ("婚禮", "wedding")]


class FakeEmbedder:
    """假的向量模型：同一個主題（不分語言）的文字給相同方向的向量。"""

    def __init__(self):
        self.calls = 0

    def embed(self, model, texts):
        self.calls += 1
        out = []
        for t in texts:
            low = t.lower()
            v = [0.05] * 8
            for k, words in enumerate(TOPICS):
                if any(w in low for w in words):
                    v[k] = 1.0
            out.append(v)
        return out

    def list_models(self):
        return ["bge-m3:latest"]


class SemanticTests(CatalogTestCase):
    def setUp(self):
        super().setUp()
        d = self.drive = self.tmp / "備份A"
        d.mkdir()
        (d / "budget-2019.txt").write_text("Q3 numbers", encoding="utf-8")
        (d / "會議紀錄.txt").write_text("這次討論明年的經費分配", encoding="utf-8")
        (d / "預算表.txt").write_text("一月 二月", encoding="utf-8")
        (d / "京都.txt").write_text("travel plan for Kyoto", encoding="utf-8")
        db.add_root(self.conn, d, "備份A")
        scan_all(self.conn, self.cfg)
        textindex.run_extract(self.conn)
        self.client = FakeEmbedder()

    def test_build_resume_and_search(self):
        model = "bge-m3"
        self.assertEqual(semantic.plan(self.conn, model), {"todo": 4, "done": 0})
        r = semantic.run_embed(self.conn, self.client, model)
        self.assertEqual(r.done, 4)
        self.assertEqual(semantic.plan(self.conn, model), {"todo": 0, "done": 4})
        self.assertEqual(semantic.run_embed(self.conn, self.client, model).done, 0)  # 做過的不再做

        meaning = lambda text: semantic.nearest(self.conn, self.client, model, text)  # noqa: E731
        res = find(self.conn, "預算", meaning=meaning)
        names = [(i["name"], i["match"]) for i in res["items"]]
        self.assertEqual(names[0], ("預算表.txt", "name"))  # 字面相符的排前面
        self.assertIn(("budget-2019.txt", "meaning"), names)  # 跨語言
        self.assertIn(("會議紀錄.txt", "meaning"), names)  # 同義詞
        self.assertNotIn("京都.txt", [n for n, _ in names])  # 不相關的不列出
        self.assertEqual(len(find(self.conn, "預算")["items"]), 1)  # 沒開「用意思找」時只有字面相符

        # 文件改過：重新建立
        p = self.drive / "京都.txt"
        p.write_text("travel plan for Kyoto and Osaka", encoding="utf-8")
        scan_all(self.conn, self.cfg)
        textindex.run_extract(self.conn)
        self.assertEqual(semantic.plan(self.conn, model)["todo"], 1)

    def test_stop_and_model_errors(self):
        import threading

        stop = threading.Event()
        stop.set()
        self.assertTrue(semantic.run_embed(self.conn, self.client, "bge-m3", stop=stop).stopped)

        class Broken(FakeEmbedder):
            def embed(self, model, texts):
                raise RuntimeError("沒有連到 Ollama")

        r = semantic.run_embed(self.conn, Broken(), "bge-m3")
        self.assertEqual(r.done, 0)
        self.assertIn("Ollama", r.error)
        self.assertEqual(semantic.nearest(self.conn, Broken(), "bge-m3", "預算"), [])  # 模型沒開：只用字面搜尋

    def test_status_api(self):
        from fastapi.testclient import TestClient

        from lumilib.server import create_app

        app = create_app(self.cfg, start_jobs_on_boot=False, client_factory=lambda: self.client)
        with TestClient(app, base_url="http://127.0.0.1:8766", client=("127.0.0.1", 1)) as c:
            st = c.get("/api/semantic/status").json()
            self.assertFalse(st["enabled"])
            self.assertTrue(st["model_ready"])
            self.assertEqual(st["todo"], 4)
            c.post("/api/settings", json={"doc_semantic": 1})
            semantic.run_embed(self.conn, self.client, "bge-m3")
            names = [i["name"] for i in c.get("/api/find", params={"q": "預算"}).json()["items"]]
            self.assertIn("budget-2019.txt", names)


if __name__ == "__main__":
    unittest.main()
