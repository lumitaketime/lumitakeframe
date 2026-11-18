"""快速預覽：還沒進照片圖庫的照片（例如從佔比圖打開）直接從硬碟讀原檔做預覽，不在硬碟上留下任何東西。"""

from PIL import Image

from lumilib import db
from lumilib.scanner import scan_all

from test_catalog import CatalogTestCase


class PhotoPreviewTests(CatalogTestCase):
    def test_preview_from_file(self):
        from fastapi.testclient import TestClient

        from lumilib.server import create_app

        d = self.tmp / "照片碟"
        d.mkdir()
        Image.new("RGB", (3000, 2000), (200, 30, 30)).save(d / "想去看雪.jpg", quality=90)
        (d / "說明.txt").write_text("x", encoding="utf-8")
        db.add_root(self.conn, d, "照片碟")
        scan_all(self.conn, self.cfg)
        before = sorted(p.name for p in d.iterdir())
        rid = self.conn.execute("SELECT id FROM roots").fetchone()[0]
        with TestClient(create_app(self.cfg, start_jobs_on_boot=False), base_url="http://127.0.0.1:8766", client=("127.0.0.1", 1)) as c:
            r = c.get("/api/items/photo", params={"root": rid, "path": "想去看雪.jpg", "size": 1024})
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.headers["content-type"], "image/jpeg")
            import io

            self.assertEqual(max(Image.open(io.BytesIO(r.content)).size), 1024)
            self.assertEqual(c.get("/api/items/photo", params={"root": rid, "path": "說明.txt"}).status_code, 415)
            self.assertEqual(c.get("/api/items/photo", params={"root": rid, "path": "../x.jpg"}).status_code, 400)
        self.assertEqual(sorted(p.name for p in d.iterdir()), before)
