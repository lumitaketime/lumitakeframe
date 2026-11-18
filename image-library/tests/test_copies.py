"""列表上標出「別的硬碟也有一模一樣的副本」：只標完整比對過內容的，並區分別顆硬碟與同一顆硬碟。"""

from lumilib import db
from lumilib.catalog import items_page
from lumilib.scanner import scan_all

from test_catalog import CatalogTestCase


class CopiesTests(CatalogTestCase):
    def test_marks_copies(self):
        for name in ("備份A", "備份B"):
            d = self.tmp / name / "照片"
            d.mkdir(parents=True)
            (d / "a.jpg.txt").write_text("一樣", encoding="utf-8")
            (d / "b.txt").write_text(name, encoding="utf-8")
            db.add_root(self.conn, self.tmp / name, name)
        scan_all(self.conn, self.cfg)
        # 測試時兩個資料夾在同一顆磁碟上；把第二個當成另一顆硬碟
        self.conn.execute("UPDATE roots SET drive_id = NULL WHERE name = '備份B'")
        ids = {(r["root"], r["name"]): r["id"] for r in self.conn.execute(
            "SELECT f.id, f.name, r.name AS root FROM files f JOIN roots r ON r.id = f.root_id")}
        # 還沒比對內容：不標
        page = items_page(self.conn, root_id=1, path="照片")
        self.assertFalse(any("copies" in it for it in page["items"]))
        # 比對過：一樣的那份標出另一顆硬碟
        self.conn.execute("UPDATE files SET content_hash = 'same' WHERE name = 'a.jpg.txt'")
        self.conn.execute("UPDATE files SET content_hash = name || root_id WHERE name = 'b.txt'")
        self.conn.execute("UPDATE folders SET content_sig = 'f' WHERE path = '照片'")
        top = {it["name"]: it for it in items_page(self.conn, root_id=1, path="")["items"]}
        self.assertEqual(top["照片"]["copies"], {"n": 1, "drives": ["備份B"], "other_drive": True})
        items = {it["name"]: it for it in items_page(self.conn, root_id=1, path="照片")["items"]}
        self.assertEqual(items["a.jpg.txt"]["copies"]["drives"], ["備份B"])
        self.assertNotIn("copies", items["b.txt"])
        # 同一顆硬碟上的副本：標成灰色（other_drive=False）
        self.conn.execute("UPDATE roots SET drive_id = (SELECT drive_id FROM roots WHERE name = '備份A') WHERE name = '備份B'")
        items = {it["name"]: it for it in items_page(self.conn, root_id=1, path="照片")["items"]}
        self.assertEqual(items["a.jpg.txt"]["copies"], {"n": 1, "drives": [], "other_drive": False})
        self.assertTrue(ids)
