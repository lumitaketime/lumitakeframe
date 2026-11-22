"""分類增強：檔案分析與關鍵字雲、我的關鍵字規則（含年份）、跟助理討論出來的整理計畫（預覽、勾選套用、復原）。
全部只動目錄裡的分類，硬碟上的檔案不變。案例：國中老師（任教蔦松國中，自己也是蔦松畢業）、接攝影與設計案、在職進修。"""

import json
import os
import time
from unittest import mock

from lumilib import actions, analysis, classify, db
from lumilib.scanner import scan_all

from test_catalog import CatalogTestCase


def ts(year):
    return time.mktime((year, 6, 1, 12, 0, 0, 0, 0, -1))


LAYOUT = {
    "蔦松國中/國一下 作業": (2003, ["作文.docx", "數學作業.pdf"]),
    "蔦松國中/105學年 段考": (2017, ["段考.docx", "答案.pdf"]),
    "蔦松國中/105學年 講義": (2017, ["講義.docx"]),
    "蔦松 雜物": (None, []),
    "蔦松 雜物/舊資料": (None, ["a.txt"]),
    "研習/2020 數位教學研習": (2020, ["研習心得.docx"]),
    "研究所/論文": (2022, ["論文.docx"]),
    "婚攝 林家": (2019, ["IMG_0001.jpg", "IMG_0002.jpg"]),
    "婚攝 陳家": (2020, ["IMG_0003.jpg"]),
    "設計 海報案": (2021, ["海報.psd", "封面.psd"]),
    "新增資料夾": (2021, ["IMG_9999.jpg"]),
}


class CategoryPlanTests(CatalogTestCase):
    def setUp(self):
        super().setUp()
        self.drive = self.tmp / "備份碟"
        for folder, (year, files) in LAYOUT.items():
            d = self.drive / folder
            d.mkdir(parents=True, exist_ok=True)
            for f in files:
                p = d / f
                p.write_text("x", encoding="utf-8")
                if year:
                    os.utime(p, (ts(year), ts(year)))
        db.add_root(self.conn, self.drive, "備份碟")
        scan_all(self.conn, self.cfg)
        # 「蔦松 雜物」裡的檔案看不出年份
        self.conn.execute("UPDATE files SET mtime = 0 WHERE name = 'a.txt'")
        self.conn.commit()
        classify.run_rules(self.conn)
        self.before = sorted(str(p) for p in self.drive.rglob("*"))

    def tearDown(self):
        self.assertEqual(sorted(str(p) for p in self.drive.rglob("*")), self.before)  # 硬碟上什麼都沒改
        super().tearDown()

    def fid(self, path):
        return self.conn.execute("SELECT id FROM folders WHERE path = ?", (path,)).fetchone()["id"]

    def cat(self, path):
        return classify.of(self.conn, folder=self.fid(path))

    def test_name_year(self):
        self.assertEqual(classify.name_year("105學年 段考"), 2016)
        self.assertEqual(classify.name_year("民國98年 畢業旅行"), 2009)
        self.assertEqual(classify.name_year("2015 日本"), 2015)
        self.assertIsNone(classify.name_year("三年級"))
        self.assertIsNone(classify.name_year("IMG_1234"))

    def test_keywords(self):
        r = analysis.build_keywords(self.conn)
        self.assertGreater(r.words, 0)
        words = {w["word"]: w for w in analysis.keywords(self.conn)["words"]}
        self.assertIn("蔦松", words)
        self.assertEqual(words["蔦松"]["folders"], 2)  # 蔦松國中、蔦松 雜物
        self.assertIn("婚攝", words)
        for junk in ("新增資料夾", "img", "增資", "資料夾"):
            self.assertNotIn(junk, words)  # 沒意義的字濾掉
        d = analysis.word_detail(self.conn, "蔦松")
        self.assertEqual(d["folders"], 2)  # 子資料夾名稱沒有蔦松，不算
        stats = analysis.file_stats(self.conn)
        self.assertIn(2017, [y["year"] for y in stats["years"]])

    def rule(self, pattern, category, year_from=None, year_to=None):
        return classify.apply_ops(self.conn, [{"op": "rule", "pattern": pattern, "category": category,
                                               "year_from": year_from, "year_to": year_to}])

    def test_rule_priority_and_years(self):
        self.assertEqual(self.cat("蔦松國中/105學年 段考")["category"], "school")  # 內建規則：國中 → 學校
        self.rule("蔦松", "work", year_from=2010)
        self.rule("蔦松", "school", year_to=2009)
        classify.run_rules(self.conn)
        self.assertEqual(self.cat("蔦松國中/105學年 段考")["category"], "work")  # 我的規則比內建優先，看年份
        self.assertEqual(self.cat("蔦松國中/國一下 作業")["category"], "school")  # 2003：自己讀書時
        unsure = self.cat("蔦松 雜物/舊資料")
        self.assertTrue(unsure["review"])  # 看不出年份：請你確認
        self.assertIn("看不出年份", unsure["reason"])
        # 我個別手動改過的永遠最優先
        classify.set_user(self.conn, folder=self.fid("蔦松國中/105學年 講義"), category="hobby")
        self.assertEqual(self.cat("蔦松國中/105學年 講義")["category"], "hobby")

    def test_plan_preview_apply_undo(self):
        classify.set_user(self.conn, folder=self.fid("研究所/論文"), category="school")  # 本人之前手動設的
        ops = [
            {"op": "add_category", "name": "教學工作", "description": "考卷、講義、學生作業與任教學校的資料"},
            {"op": "add_category", "name": "接案", "description": "攝影與設計的接案"},
            {"op": "split", "from": "學校與學習", "into": ["學生時期", "進修"]},
            {"op": "merge", "from": ["作品與創作"], "into": "接案"},
            {"op": "rule", "pattern": "婚攝", "category": "接案"},
            {"op": "rule", "pattern": "研習", "category": "進修"},
            {"op": "rule", "pattern": "蔦松", "category": "教學工作", "year_from": 2010},
            {"op": "rule", "pattern": "蔦松", "category": "學生時期", "year_to": 2009},
            {"op": "set_folder", "pattern": "設計", "category": "接案"},
            {"op": "rename", "category": "沒有這類", "name": "x"},
        ]
        a = actions.propose(self.conn, "category_plan", {"ops": ops, "chat_id": 7}, level=3)
        prev = a["preview"]
        self.assertGreater(prev["changed"], 0)
        names = {c["name"]: c for c in prev["categories"]}
        self.assertIn("教學工作", names)
        self.assertNotIn("學校與學習", names)  # 拆開了
        self.assertFalse(a["items"][-1]["ok"])  # 看不懂的那一步先標出來
        self.assertEqual(self.cat("婚攝 林家")["category"], None)  # 預覽不會改到目錄
        # 同一段對話再說一句：加在同一張計畫卡上
        a2 = actions.propose(self.conn, "category_plan", {"ops": [{"op": "rule", "pattern": "論文", "category": "進修"}], "chat_id": 7}, level=3)
        self.assertEqual(a2["id"], a["id"])
        self.assertEqual(len(a2["items"]), len(ops) + 1)
        # 只套用勾選的（最後那一步看不懂的不勾）
        done = actions.run(self.conn, a["id"], 3, only=list(range(len(ops))) + [len(ops)])
        self.assertIn(done["state"], ("done", "partial"))
        keys = {classify.display_name(c): c["key"] for c in classify.categories(self.conn)}
        self.assertEqual(self.cat("婚攝 林家")["category"], keys["接案"])
        self.assertEqual(self.cat("設計 海報案")["category"], keys["接案"])
        self.assertEqual(self.cat("蔦松國中/105學年 段考")["category"], keys["教學工作"])
        self.assertEqual(self.cat("蔦松國中/國一下 作業")["category"], keys["學生時期"])
        self.assertEqual(self.cat("研習/2020 數位教學研習")["category"], keys["進修"])
        thesis = self.cat("研究所/論文")
        self.assertEqual((thesis["source"], thesis["review"]), ("pending", True))  # 本人設的那一類拆開了：請本人選
        self.assertEqual(classify.categories(self.conn, include_merged=True)[0]["key"], "school")
        self.assertNotIn("school", classify.valid_keys(self.conn))
        # 分類的說明交給 AI 參考
        folder = self.conn.execute("SELECT d.*, r.name AS root FROM folders d JOIN roots r ON r.id = d.root_id WHERE d.path = '新增資料夾'").fetchone()
        prompt = classify._prompt(self.conn, folder, [(c["key"], classify.display_name(c)) for c in classify.categories(self.conn)], False)
        self.assertIn("考卷、講義、學生作業", prompt)
        # 一鍵復原
        actions.undo(self.conn, a["id"])
        self.assertEqual(self.cat("蔦松國中/105學年 段考")["category"], "school")
        self.assertEqual(self.cat("研究所/論文")["source"], "user")
        self.assertIn("school", classify.valid_keys(self.conn))
        self.assertNotIn("教學工作", [classify.display_name(c) for c in classify.categories(self.conn)])

    def test_assistant_tools(self):
        from lumilib import assistant

        analysis.build_keywords(self.conn)
        out = assistant.tool_catalog_analysis(self.conn, {}, None)
        self.assertIn("蔦松", out)
        self.assertIn("學校與學習", out)
        self.assertIn("蔦松", assistant.tool_keyword_folders(self.conn, {"word": "蔦松"}, None))
        assistant.tool_save_profile(self.conn, {"identity": "國中老師，接攝影與設計案", "teach_start_year": "2010"}, None)
        self.assertEqual(classify.profile(self.conn)["teach_start_year"], 2010)

        class Fake:
            remote = False
            model = "fake"

            def __init__(self):
                self.round = 0

            def plan_json(self, prompt, schema):
                self.round += 1
                if self.round == 1:
                    return {"calls": [{"tool": "plan_categories", "args": {"ops": [
                        {"op": "add_category", "name": "接案", "description": "攝影與設計"},
                        {"op": "rule", "pattern": "婚攝", "category": "接案"}]}}]}
                return {"calls": []}

            def stream(self, messages):
                yield "好的，計畫卡在下面。"

        evs = list(assistant.ask(self.conn, Fake(), "名字有婚攝的都放到接案", level=3, chat_id=3))
        acts = [e["action"] for e in evs if e["type"] == "action"]
        self.assertEqual(acts[0]["kind"], "category_plan")
        self.assertEqual(len(acts[0]["items"]), 2)
        self.assertEqual(self.cat("婚攝 林家")["category"], None)  # 還沒確認：目錄不變
        # 權限不夠：不能提出計畫
        evs = list(assistant.ask(self.conn, Fake(), "名字有婚攝的都放到接案", level=2, chat_id=4))
        self.assertFalse([e for e in evs if e["type"] == "action"])

    def test_api(self):
        from fastapi.testclient import TestClient

        from lumilib.server import create_app

        analysis.build_keywords(self.conn)
        with TestClient(create_app(self.cfg, start_jobs_on_boot=False), base_url="http://127.0.0.1:8766", client=("127.0.0.1", 1)) as c:
            d = c.get("/api/analysis").json()
            self.assertTrue(d["kinds"] and d["years"] and d["words"])
            self.assertEqual(c.get("/api/analysis/word", params={"w": "婚攝"}).json()["folders"], 2)
            a = c.post("/api/category/rule/propose", json={"pattern": "婚攝", "category": "creative"}).json()
            self.assertEqual(a["preview"]["changed"], 2)  # 套用前先說會影響幾個資料夾
            self.assertEqual(a["preview"]["changes"][0]["examples"][0]["name"], "婚攝 林家")
            self.assertIsNone(self.cat("婚攝 林家")["category"])
            r = c.post("/api/assistant/actions/run", json={"id": a["id"], "confirm": True}).json()
            self.assertEqual(r["state"], "done")
            self.assertEqual(self.cat("婚攝 林家")["category"], "creative")
            rules = c.get("/api/category/rules").json()["rules"]
            self.assertEqual((rules[0]["pattern"], rules[0]["source"], rules[0]["folders"]), ("婚攝", "user", 2))
            c.post("/api/assistant/actions/undo", json={"id": a["id"], "confirm": True})
            self.assertIsNone(self.cat("婚攝 林家")["category"])
            self.assertEqual(c.get("/api/category/rules").json()["rules"], [])
            c.post("/api/category/profile", json={"identity": "國中老師", "teach_start_year": 2010})
            self.assertEqual(c.get("/api/category/profile").json()["teach_start_year"], 2010)
