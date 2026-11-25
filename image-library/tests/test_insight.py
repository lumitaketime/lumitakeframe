"""助理更聰明：一年的回顧、兩份文件的差異、文件的關鍵字與摘要、這週的摘要。只讀目錄。"""

import os
import unittest
from datetime import datetime

from lumilib import assistant, db, insight, textindex
from lumilib.scanner import scan_all

from test_catalog import CatalogTestCase
from test_dupes import tree


class FakeLLM:
    model = "fake"

    def __init__(self):
        self.prompts = []

    def plan_json(self, prompt, schema):
        self.prompts.append(prompt)
        return {"summary": "這是一份段考考卷，考二次方程式。"}


class InsightTests(CatalogTestCase):
    def setUp(self):
        super().setUp()
        base = tree(self.tmp / "教學", {"2015/段考.txt": b"a" * 10, "2015/講義.txt": b"b" * 20, "2020/新.txt": b"c" * 30})
        t2015 = datetime(2015, 5, 3).timestamp()
        for n in ("段考.txt", "講義.txt"):
            os.utime(base / "2015" / n, (t2015, t2015))
        db.add_root(self.conn, base, "教學")
        scan_all(self.conn, self.cfg)
        self.ids = {r["name"]: r["id"] for r in self.conn.execute("SELECT id, name FROM files")}
        self.put("段考.txt", "國三數學段考\n第一題 二次方程式\n第二題 二次方程式的圖形\n二次方程式 練習")
        self.put("講義.txt", "國三數學段考\n第一題 二次方程式\n第二題 一次函數\n二次方程式 練習\n加分題")

    def put(self, name, text):
        fid = self.ids[name]
        r = self.conn.execute("SELECT size, mtime FROM files WHERE id = ?", (fid,)).fetchone()
        textindex._store(self.conn, fid, r["size"], r["mtime"], "text", text, "ok")
        self.conn.commit()

    def test_year_recap(self):
        r = insight.year_recap(self.conn, 2015)
        self.assertEqual(r["files"], 2)
        self.assertEqual(r["months"][4], 2)
        self.assertEqual(r["folders"][0]["path"], "2015")
        text = insight.describe_year(r)
        self.assertIn("2015 年留下 2 個檔案", text)
        self.assertIn("段考.txt", text)
        out = assistant.tool_year_recap(self.conn, {"year": 2015}, assistant.Ctx(level=1))
        self.assertIn("[1] 資料夾", out)
        self.assertIn("沒有找到", insight.describe_year(insight.year_recap(self.conn, 1999)))

    def test_compare(self):
        out = assistant.tool_compare_documents(self.conn, {"file_a": self.ids["段考.txt"], "file_b": self.ids["講義.txt"]}, assistant.Ctx(level=2))
        self.assertIn("一次函數", out)
        self.assertIn("加分題", out)
        self.assertIn("不允許", assistant.tool_compare_documents(self.conn, {"file_a": 1, "file_b": 2}, assistant.Ctx(level=1)))
        self.assertNotIn("compare_documents", assistant.allowed_tools(assistant.Ctx(level=1)))

    def test_keywords_and_summary(self):
        info = insight.insight(self.conn, self.ids["段考.txt"])
        self.assertTrue(info["has_text"])
        self.assertIn("方程式", info["keywords"])
        self.assertIsNone(info["summary"])
        llm = FakeLLM()
        s = insight.summarize(self.conn, llm, self.ids["段考.txt"])
        self.assertIn("二次方程式", llm.prompts[0])
        self.assertEqual(insight.insight(self.conn, self.ids["段考.txt"])["summary"], s)
        self.conn.execute("UPDATE files SET mtime = mtime + 1 WHERE id = ?", (self.ids["段考.txt"],))
        self.assertIsNone(insight.insight(self.conn, self.ids["段考.txt"])["summary"], "檔案改過：舊的摘要不算")
        with self.assertRaisesRegex(ValueError, "還沒讀到"):
            insight.summarize(self.conn, llm, self.ids["新.txt"])

    def test_week_report(self):
        w = insight.week_report(self.conn)
        self.assertEqual(w["files"], 3)
        self.assertEqual(w["docs"], 2)


if __name__ == "__main__":
    unittest.main()
