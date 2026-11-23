"""自動分類：規則先分、子資料夾跟著上層、AI 只問分不出來的、本人的修正永遠優先並且學起來；只記在目錄裡。"""

from unittest import mock

from lumilib import classify, db
from lumilib.scanner import scan_all

from test_catalog import CatalogTestCase


def make(base, files):
    for rel in files:
        p = base / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x", encoding="utf-8")


class FakeLLM:
    model = "fake"

    def __init__(self, answers):
        self.answers, self.asked = answers, []

    def plan_json(self, prompt, schema):
        name = prompt.split("資料夾名稱：", 1)[1].split("\n", 1)[0]
        self.asked.append(name)
        return self.answers.get(name, {"category": "unknown", "confidence": 0.2, "reason": "看不出來"})


class ClassifyTests(CatalogTestCase):
    def setUp(self):
        super().setUp()
        self.drive = self.tmp / "備份碟"
        make(self.drive, [
            "國中/自然科/寄居蟹報告.docx", "國中/自然科/實驗照片/1.jpg", "國中/數學/段考.pdf",
            "2015 發票/a.pdf", "Installers/a.dmg", "Installers/b.pkg", "Installers/readme.txt",
            "小說/a.epub", "音樂/周杰倫/a.mp3", "雜七雜八/x.txt", "雜七雜八/子/y.txt", "阿嬤家/IMG1.jpg",
        ])
        db.add_root(self.conn, self.drive, "備份碟")
        scan_all(self.conn, self.cfg)
        self.before = sorted(str(p) for p in self.drive.rglob("*"))

    def tearDown(self):
        self.assertEqual(sorted(str(p) for p in self.drive.rglob("*")), self.before)  # 硬碟上什麼都沒改
        super().tearDown()

    def fid(self, path):
        return self.conn.execute("SELECT id FROM folders WHERE path = ?", (path,)).fetchone()["id"]

    def cat(self, path):
        return classify.of(self.conn, folder=self.fid(path))

    def test_rules(self):
        classify.run_rules(self.conn)
        self.assertEqual((self.cat("國中")["category"], self.cat("國中")["source"]), ("school", "rule"))
        self.assertIn("國中", self.cat("國中")["reason"])
        self.assertEqual(self.cat("國中/自然科/實驗照片")["source"], "inherit")  # 子資料夾跟著上層
        self.assertEqual(self.cat("國中/自然科/實驗照片")["category"], "school")
        self.assertEqual(self.cat("2015 發票")["category"], "finance")
        self.assertEqual(self.cat("Installers")["category"], "software")  # 名稱是英文整個字
        self.assertEqual(self.cat("小說")["category"], "hobby")
        self.assertEqual(self.cat("音樂/周杰倫")["category"], "hobby")
        self.assertIsNone(self.cat("雜七雜八")["category"])  # 分不出來：留給 AI
        stats = {c["key"]: c for c in classify.overview(self.conn)}
        self.assertEqual(stats["school"]["files"], 3)

    def test_user_wins_and_learns(self):
        classify.run_rules(self.conn)
        out = classify.set_user(self.conn, folder=self.fid("國中/自然科"), category="hobby")
        self.assertEqual((self.cat("國中/自然科")["category"], self.cat("國中/自然科")["source"]), ("hobby", "user"))
        self.assertEqual(self.cat("國中/自然科/實驗照片")["category"], "hobby")  # 裡面的跟著本人的設定
        self.assertEqual(self.cat("國中")["category"], "school")  # 上層不變
        self.assertEqual(out["tokens"], ["自然科"])
        # 名稱相近的：先問，不自動改
        classify.set_user(self.conn, folder=self.fid("雜七雜八"), category="life")
        sim = classify.similar(self.conn, self.fid("雜七雜八"), "life")
        self.assertEqual(sim["similar"], [])
        classify.learn(self.conn, self.fid("阿嬤家"), "life")
        self.assertEqual(self.cat("阿嬤家")["source"], "learned")
        # 重新跑規則、AI 也不會蓋掉本人的設定
        classify.run_rules(self.conn)
        classify.run_ai(self.conn, FakeLLM({"自然科": {"category": "school", "confidence": 0.99, "reason": "x"}}))
        self.assertEqual(self.cat("國中/自然科")["category"], "hobby")
        # 回到自動
        classify.set_user(self.conn, folder=self.fid("國中/自然科"), category="auto")
        self.assertEqual(self.cat("國中/自然科")["category"], "school")
        # 不分類：AI 也不會再去問
        classify.set_user(self.conn, folder=self.fid("雜七雜八"), category=None)
        self.assertNotIn("雜七雜八", [r["name"] for r in classify.ai_candidates(self.conn)])

    def test_ai_only_for_undecided_and_review(self):
        classify.run_rules(self.conn)
        llm = FakeLLM({"雜七雜八": {"category": "work", "confidence": 0.4, "reason": "看起來像工作資料"},
                       "阿嬤家": {"category": "life", "confidence": 0.9, "reason": "家人"}})
        r = classify.run_ai(self.conn, llm)
        self.assertNotIn("國中", llm.asked)  # 規則分好的不問
        self.assertNotIn("子", llm.asked)  # 上層剛被 AI 分好：跟著上層，不再問
        self.assertEqual((r.classified, r.review), (2, 1))
        self.assertEqual(self.cat("雜七雜八/子")["category"], "work")
        self.assertTrue(self.cat("雜七雜八")["review"])  # 沒把握：放進「請你確認」
        self.assertEqual([x["name"] for x in classify.review_list(self.conn)], ["雜七雜八"])
        classify.accept(self.conn, [self.fid("雜七雜八")])
        self.assertEqual((self.cat("雜七雜八")["source"], classify.review_count(self.conn)), ("user", 0))
        llm2 = FakeLLM({})
        classify.run_ai(self.conn, llm2)
        self.assertNotIn("阿嬤家", llm2.asked)  # 內容沒變：不重問

    def test_prompt_privacy(self):
        classify.run_rules(self.conn)
        folder = classify.ai_candidates(self.conn)[0]
        keys = [(c["key"], c["key"]) for c in classify.categories(self.conn)]
        self.assertNotIn("文件「", classify._prompt(self.conn, folder, keys, read_text=False))  # 不讀內容時，只有名稱與統計

    def test_category_scope_and_custom(self):
        from lumilib.catalog import items_page

        classify.run_rules(self.conn)
        page = items_page(self.conn, category="school")
        self.assertEqual([i["name"] for i in page["items"]], ["國中"])  # 只列最上層，裡面的不重複列
        key = classify.add_category(self.conn, "社團")
        classify.set_user(self.conn, folder=self.fid("雜七雜八"), category=key)
        self.assertEqual(items_page(self.conn, category=key)["total"], 1)
        classify.delete_category(self.conn, key)
        self.assertIsNone(self.cat("雜七雜八")["category"])
        # 預設的分類也可以刪：內建關鍵字不再把資料夾分到這裡，也不會自己跑回來
        classify.delete_category(self.conn, "school")
        self.assertIsNone(self.cat("國中")["category"])
        classify.run_rules(self.conn)
        self.assertNotIn("school", classify.valid_keys(self.conn))
        self.assertEqual(classify.restore_defaults(self.conn), 1)  # 加回預設的分類
        self.assertEqual(self.cat("國中")["category"], "school")

    def test_api_and_consent(self):
        from fastapi.testclient import TestClient

        from lumilib.server import create_app

        with TestClient(create_app(self.cfg, start_jobs_on_boot=False), base_url="http://127.0.0.1:8766", client=("127.0.0.1", 1)) as c:
            st = c.get("/api/categories").json()
            self.assertEqual((st["asked"], st["rules_auto"], st["ai_auto"]), (False, False, False))  # 沒問過：不自動跑
            c.post("/api/classify/consent", json={"rules_auto": True, "ai_auto": False, "read_text": True})
            import time

            for _ in range(100):
                st = c.get("/api/categories").json()
                if any(x["folders"] for x in st["categories"]):
                    break
                time.sleep(0.05)
            self.assertTrue(st["asked"] and st["rules_auto"])
            school = next(x for x in st["categories"] if x["key"] == "school")
            self.assertGreater(school["folders"], 0)
            fid = self.fid("雜七雜八")
            out = c.post("/api/category/set", json={"folder": fid, "category": "work"}).json()
            self.assertEqual(out["category"]["source"], "user")
            self.assertEqual(c.post("/api/category/set", json={"folder": fid, "category": "沒有這類"}).status_code, 400)
            items = c.get("/api/items", params={"category": "work"}).json()
            self.assertEqual([i["name"] for i in items["items"]], ["雜七雜八"])
            self.assertIn("categories", c.get("/api/drives").json())
