"""側邊欄的「喜好項目」：拖進去的資料夾、檔案、側邊欄捷徑都記得住、可以排順序、可以拿掉；不動硬碟上的檔案。"""

from lumilib import db
from lumilib.scanner import scan_all

from test_catalog import CatalogTestCase


class FavoritesTests(CatalogTestCase):
    def test_pin_files_folders_and_links(self):
        from fastapi.testclient import TestClient

        from lumilib.server import create_app

        d = self.tmp / "備份碟"
        (d / "國中").mkdir(parents=True)
        (d / "國中" / "報告.txt").write_text("x", encoding="utf-8")
        db.add_root(self.conn, d, "備份碟")
        scan_all(self.conn, self.cfg)
        rid = self.conn.execute("SELECT id FROM roots").fetchone()[0]
        before = sorted(p.name for p in d.rglob("*"))
        file_href = f"/folders/{rid}?path=%E5%9C%8B%E4%B8%AD&select=%E5%A0%B1%E5%91%8A.txt"
        with TestClient(create_app(self.cfg, start_jobs_on_boot=False), base_url="http://127.0.0.1:8766", client=("127.0.0.1", 1)) as c:
            favs = lambda: [(f["kind"], f["name"]) for f in c.get("/api/server").json()["favorites"]]  # noqa: E731
            self.assertEqual(favs(), [])
            c.post("/api/folders/prefs", json={"root_id": rid, "path": "國中", "favorite": True})
            self.assertEqual(c.post("/api/favorites/link", json={"href": file_href, "kind": "file", "name": "報告.txt", "icon": "document"}).status_code, 200)
            c.post("/api/favorites/link", json={"href": "/kind/photo", "kind": "link", "ref": "kind:photo", "name": "照片"})
            self.assertEqual(sorted(favs()), [("file", "報告.txt"), ("folder", "國中"), ("link", "照片")])
            # 外部網址不能放
            self.assertEqual(c.post("/api/favorites/link", json={"href": "https://example.com", "kind": "link", "name": "x"}).status_code, 400)
            self.assertEqual(c.post("/api/favorites/link", json={"href": "//example.com", "kind": "link", "name": "x"}).status_code, 400)
            # 排順序：捷徑、資料夾、檔案
            c.post("/api/favorites/order", json={"items": [
                {"kind": "link", "href": "/kind/photo"}, {"kind": "folder", "root_id": rid, "path": "國中"}, {"kind": "file", "href": file_href}]})
            self.assertEqual(favs(), [("link", "照片"), ("folder", "國中"), ("file", "報告.txt")])
            # 新釘的放最後
            c.post("/api/favorites/link", json={"href": "/duplicates", "kind": "link", "ref": "duplicates", "name": "重複項目"})
            self.assertEqual(favs()[-1], ("link", "重複項目"))
            c.post("/api/favorites/link", json={"href": file_href, "kind": "file", "on": False})
            self.assertNotIn(("file", "報告.txt"), favs())
        self.assertEqual(sorted(p.name for p in d.rglob("*")), before)  # 硬碟上的檔案沒有被動到
