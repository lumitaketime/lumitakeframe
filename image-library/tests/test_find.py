"""搜尋所有硬碟上的檔案：檔名、路徑、文件內容、照片描述，以及篩選與智慧資料夾。"""

import shutil
import time
import unittest
from pathlib import Path

from lumilib import db, find, textindex
from lumilib.scanner import scan_all

from test_catalog import CatalogTestCase, separate_drives

FIXTURES = Path(__file__).parent / "fixtures" / "docs"


class FindTests(CatalogTestCase):
    def setUp(self):
        super().setUp()
        a = self.a = self.tmp / "備份A"
        (a / "2008 國中" / "自然科").mkdir(parents=True)
        shutil.copy(FIXTURES / "report.pdf", a / "2008 國中" / "期末.pdf")  # 內容：國中自然科報告、寄居蟹
        shutil.copy(FIXTURES / "report.docx", a / "2008 國中" / "自然科" / "報告初稿.docx")
        (a / "2008 國中" / "自然科" / "照片清單.txt").write_text("墾丁 2008 合照", encoding="utf-8")
        b = self.b = self.tmp / "備份B"
        (b / "工作").mkdir(parents=True)
        shutil.copy(FIXTURES / "budget.xlsx", b / "工作" / "2019 預算.xlsx")
        (b / "工作" / "會議紀錄.txt").write_text("討論寄居蟹保育的經費", encoding="utf-8")
        self.ra = db.add_root(self.conn, a, "備份A")
        self.rb = db.add_root(self.conn, b, "備份B")
        with separate_drives(a, b):
            scan_all(self.conn, self.cfg)
        textindex.run_extract(self.conn)

    def names(self, q, **kw):
        return [i["name"] for i in find.find(self.conn, q, **kw)["items"]]

    def test_names_come_first_then_contents(self):
        res = find.find(self.conn, "自然科")
        got = [(i["name"], i["match"]) for i in res["items"]]
        names = [g[0] for g in got]
        self.assertEqual(sorted(names[:2]), ["報告初稿.docx", "照片清單.txt"])  # 資料夾名稱符合的排在內容符合的前面
        self.assertIn("期末.pdf", names)  # 檔名沒有「自然科」，是內容裡有
        self.assertEqual(dict(got)["期末.pdf"], "text")
        self.assertEqual(dict(got)["報告初稿.docx"], "path")  # 在「自然科」資料夾裡
        draft = next(i for i in res["items"] if i["name"] == "報告初稿.docx")
        self.assertTrue(any(p["hit"] for p in draft["snippet"]))  # 內容裡也有，一併顯示那一段
        self.assertNotIn("snippet", next(i for i in res["items"] if i["name"] == "照片清單.txt"))  # 內容裡沒有就不顯示
        pdf = next(i for i in res["items"] if i["name"] == "期末.pdf")
        self.assertTrue(any(p["hit"] and "自然科" in p["text"] for p in pdf["snippet"]))
        self.assertEqual((pdf["drive"], pdf["root"], pdf["folder"]), ("備份A", "備份A", "2008 國中"))

    def test_contents_across_drives_and_filters(self):
        self.assertEqual(sorted(self.names("寄居蟹")), sorted(["會議紀錄.txt", "期末.pdf", "報告初稿.docx"]))
        self.assertEqual(self.names("寄居蟹", root=self.rb["id"]), ["會議紀錄.txt"])  # 範圍：只在某個資料夾來源
        self.assertEqual(sorted(self.names("寄居蟹 type:document ext:pdf")), ["期末.pdf"])
        self.assertEqual(self.names("寄居蟹", root=self.ra["id"], path="2008 國中/自然科"), ["報告初稿.docx"])
        self.assertEqual(sorted(self.names("經費", kind="document")), ["2019 預算.xlsx", "會議紀錄.txt"])
        self.assertEqual(self.names("寄居蟹 root:備份B"), ["會議紀錄.txt"])
        year = time.localtime().tm_year
        self.assertEqual(len(self.names("寄居蟹", year=year)), 3)
        self.assertEqual(self.names("寄居蟹", year=1999), [])
        self.assertEqual(self.names("寄居蟹", size="huge"), [])
        # 含數字的詞也能搜（檔名、路徑、內容）
        self.assertIn("照片清單.txt", self.names("2008"))

    def test_still_searchable_when_unplugged(self):
        shutil.move(str(self.a), str(self.tmp / "拔掉了"))
        self.assertIn("期末.pdf", self.names("寄居蟹"))

    def test_filters_without_words_and_smart_folders(self):
        self.assertEqual(sorted(self.names("", kind="document", root=self.rb["id"])), ["2019 預算.xlsx", "會議紀錄.txt"])
        fid = find.save_smart_folder(self.conn, "寄居蟹資料", {"q": "寄居蟹", "kind": "document", "junk": 1})
        saved = find.smart_folders(self.conn)
        self.assertEqual((saved[0]["id"], saved[0]["name"], saved[0]["query"]), (fid, "寄居蟹資料", {"q": "寄居蟹", "kind": "document"}))
        with self.assertRaises(ValueError):
            find.save_smart_folder(self.conn, "", {"q": "x"})
        find.delete_smart_folder(self.conn, fid)
        self.assertEqual(find.smart_folders(self.conn), [])

    def test_api(self):
        from fastapi.testclient import TestClient

        from lumilib.server import create_app

        with TestClient(create_app(self.cfg, start_jobs_on_boot=False), base_url="http://127.0.0.1:8766",
                        client=("127.0.0.1", 1)) as c:
            r = c.get("/api/find", params={"q": "寄居蟹", "limit": 2}).json()
            self.assertEqual((r["total"], len(r["items"])), (3, 2))
            self.assertEqual(c.get("/api/text/status").json()["extract"]["todo"]["files"], 0)
            sid = c.post("/api/smart-folders", json={"name": "預算", "query": {"q": "預算"}}).json()["id"]
            self.assertEqual(c.get("/api/smart-folders").json()[0]["id"], sid)
            self.assertEqual(c.post("/api/smart-folders", json={"name": "空", "query": {}}).status_code, 400)
            self.assertEqual(c.delete(f"/api/smart-folders/{sid}").json(), {"ok": True})
            # 設定頁：啟動頁、清除文件文字（一定要確認，清掉後搜不到內容，重新讀取後又找得到）
            self.assertEqual(c.post("/api/settings", json={"start_page": "find"}).json()["start_page"], "find")
            self.assertEqual(c.get("/api/server").json()["ui"]["start_page"], "find")
            self.assertEqual(c.post("/api/text/reset", json={}).status_code, 400)
            self.assertGreater(c.post("/api/text/reset", json={"confirm": True}).json()["cleared"], 0)
            self.assertEqual(c.get("/api/find", params={"q": "寄居蟹"}).json()["total"], 0)
            self.assertGreater(c.get("/api/text/status").json()["extract"]["todo"]["files"], 0)


if __name__ == "__main__":
    unittest.main()
