"""文件封面縮圖：PDF 第一頁、電子書封面、Office 附的預覽圖；只讀硬碟，縮圖存在 Re'memor 的資料目錄。"""

import io
import unittest
import zipfile

from PIL import Image

from lumilib import catalog, covers, db
from lumilib.scanner import scan_all

from test_catalog import CatalogTestCase


def jpeg(color) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (60, 80), color).save(out, "JPEG")
    return out.getvalue()


class CoverTests(CatalogTestCase):
    def setUp(self):
        super().setUp()
        self.drive = self.tmp / "書"
        self.drive.mkdir()
        Image.new("RGB", (200, 280), (200, 30, 30)).save(self.drive / "講義.pdf", "PDF")
        with zipfile.ZipFile(self.drive / "小說.epub", "w") as z:
            z.writestr("META-INF/container.xml", '<container><rootfiles><rootfile full-path="OEBPS/content.opf"/></rootfiles></container>')
            z.writestr("OEBPS/content.opf", '<package><metadata><meta name="cover" content="c1"/></metadata>'
                                            '<manifest><item id="c1" href="images/front.jpg" media-type="image/jpeg"/></manifest></package>')
            z.writestr("OEBPS/images/front.jpg", jpeg((30, 30, 200)))
        with zipfile.ZipFile(self.drive / "報告.docx", "w") as z:
            z.writestr("docProps/thumbnail.jpeg", jpeg((30, 200, 30)))
        (self.drive / "壞掉.pdf").write_bytes(b"%PDF-1.4 broken")
        db.add_root(self.conn, self.drive, "書")
        scan_all(self.conn, self.cfg)

    def snapshot(self):
        return {str(p): (p.stat().st_size, p.stat().st_mtime_ns) for p in self.drive.rglob("*")}

    def test_make_covers(self):
        before = self.snapshot()
        self.assertEqual(covers.plan(self.conn)["todo"], 4)
        res = covers.run(self.conn, self.cfg.home)
        self.assertEqual(self.snapshot(), before, "做封面只能讀，不能在硬碟上建立或改任何東西")
        self.assertEqual((res["made"], res["failed"]), (3, 1))
        ids = {r["name"]: r["id"] for r in self.conn.execute("SELECT id, name FROM files")}
        img = Image.open(covers.cover_path(self.cfg.home, ids["講義.pdf"]))
        self.assertGreater(img.getpixel((img.width // 2, img.height // 2))[0], 150)  # PDF 第一頁是紅色
        self.assertGreater(Image.open(covers.cover_path(self.cfg.home, ids["小說.epub"])).getpixel((5, 5))[2], 150)
        self.assertGreater(Image.open(covers.cover_path(self.cfg.home, ids["報告.docx"])).getpixel((5, 5))[1], 150)
        self.assertEqual(covers.plan(self.conn)["todo"], 0, "做過的（包括做不出來的）不再重做")
        root = self.conn.execute("SELECT id FROM roots").fetchone()[0]
        page = catalog.items_page(self.conn, root_id=root, path="")
        flags = {it["name"]: it["cover"] for it in page["items"]}
        self.assertEqual(flags, {"講義.pdf": True, "小說.epub": True, "報告.docx": True, "壞掉.pdf": False})
        self.assertIn("做好 3 份文件的封面", covers.describe(res))


if __name__ == "__main__":
    unittest.main()
