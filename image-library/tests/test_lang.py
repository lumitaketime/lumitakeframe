"""語言包：英文詞形變化（report↔reports、run↔running）；德文、法文加入語言包後才處理；改了就重建索引（不讀硬碟）。"""

import unittest

from lumilib import db, lang, textindex
from lumilib.scanner import scan_all

from test_catalog import CatalogTestCase
from test_dupes import tree


class LangTests(CatalogTestCase):
    def setUp(self):
        super().setUp()
        lang.configure([])
        tree(self.tmp / "文件", {"a.txt": b"x", "b.txt": b"y", "c.txt": b"z"})
        db.add_root(self.conn, self.tmp / "文件", "文件")
        scan_all(self.conn, self.cfg)
        ids = {r["name"]: r["id"] for r in self.conn.execute("SELECT id, name FROM files")}
        self.ids = ids
        self.put(ids["a.txt"], "The quarterly reports were running late")
        self.put(ids["b.txt"], "Das Haus ist fertig und der Bericht ist gut")
        self.put(ids["c.txt"], "Le journal économique est dans le dossier")

    def tearDown(self):
        lang.configure([])
        super().tearDown()

    def put(self, fid, text):
        r = self.conn.execute("SELECT size, mtime FROM files WHERE id = ?", (fid,)).fetchone()
        textindex._store(self.conn, fid, r["size"], r["mtime"], "text", text, "ok")
        self.conn.commit()

    def find(self, q):
        names = {v: k for k, v in self.ids.items()}
        return sorted(names[i] for i in textindex.text_matches(self.conn, q))

    def test_english_word_forms(self):
        self.assertEqual(self.find("report"), ["a.txt"])
        self.assertEqual(self.find("reports"), ["a.txt"])
        self.assertEqual(self.find("run"), ["a.txt"])
        self.assertEqual(self.find("quarterly report"), ["a.txt"])

    def test_german_and_french_packs(self):
        self.assertEqual(self.find("häuser"), [])  # 還沒加入德文：複數找不到單數
        self.assertEqual(self.find("journaux"), [])
        lang.configure(["de", "fr"])
        self.assertFalse(textindex.index_current(self.conn))
        textindex.rebuild_index(self.conn)
        self.assertTrue(textindex.index_current(self.conn))
        self.assertEqual(self.find("häuser"), ["b.txt"])
        self.assertEqual(self.find("journaux"), ["c.txt"])
        self.assertEqual(self.find("reports"), ["a.txt"], "英文照樣找得到")

    def test_ocr_languages(self):
        self.assertEqual(lang.ocr_languages(["ja", "ko", "xx"]), "zh-Hant,zh-Hans,en-US,ja-JP,ko-KR")
        self.assertEqual(lang.parse("de, fr,de"), ["de", "fr"])

    def test_rebuild_can_stop(self):
        import threading

        lang.configure(["de"])
        stop = threading.Event()
        stop.set()
        self.assertTrue(textindex.rebuild_index(self.conn, stop=stop)["stopped"])
        self.assertFalse(textindex.index_current(self.conn), "停下來就維持舊的，下次再重做")
        self.assertEqual(self.find("report"), ["a.txt"], "停下來時原本的索引還在")


if __name__ == "__main__":
    unittest.main()
