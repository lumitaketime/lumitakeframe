"""Spotlight 的項目清單：硬碟（包括沒接上的）與智慧資料夾；id 就是要打開的頁面。"""

import shutil

from lumilib import db
from lumilib.find import save_smart_folder
from lumilib.scanner import scan_all
from lumilib.spotlight import payload

from test_catalog import CatalogTestCase


class SpotlightTests(CatalogTestCase):
    def test_items(self):
        d = self.tmp / "備份碟 3"
        d.mkdir()
        (d / "a.txt").write_text("x", encoding="utf-8")
        db.add_root(self.conn, d, "備份碟 3")
        scan_all(self.conn, self.cfg)
        save_smart_folder(self.conn, "預算文件", {"q": "預算 表", "kind": "document"})
        p = payload(self.conn)
        titles = {i["title"]: i for i in p["items"]}
        drive = next(i for i in p["items"] if i["type"] == "public.volume")
        self.assertTrue(drive["path"].startswith("/folders/"))
        self.assertEqual(drive["id"], "rememor:" + drive["path"])
        self.assertIn("已接上", drive["description"])
        smart = titles["預算文件"]
        self.assertIn("smart=", smart["path"])
        self.assertNotIn("'", smart["path"])  # 外殼用 JavaScript 字串打開頁面：網址裡不能有單引號
        v1 = p["version"]
        shutil.rmtree(d)
        p2 = payload(self.conn)
        self.assertIn("沒接上", next(i for i in p2["items"] if i["type"] == "public.volume")["description"])  # 拔掉之後還在
        self.assertNotEqual(p2["version"], v1)
        self.assertEqual(payload(self.conn, enabled=False), {"enabled": False, "version": "off", "items": []})
