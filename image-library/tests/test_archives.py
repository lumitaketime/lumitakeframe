"""壓縮檔內容：不解開，只記下裡面有哪些檔案；搜尋找得到壓縮檔裡的檔案；不在硬碟上建立任何東西。"""

import io
import shutil
import subprocess
import tarfile
import unittest
import zipfile

from lumilib import archives, db, textindex
from lumilib.find import find
from lumilib.scanner import scan_all

from test_catalog import CatalogTestCase


def big5_zip(path, names):
    """做一個舊 Windows 中文版產生的 ZIP：檔名是 Big5，而且沒有標明 UTF-8。"""
    orig = zipfile.ZipInfo._encodeFilenameFlags

    def legacy(self):
        return self.filename.encode("cp950"), self.flag_bits & ~0x800

    zipfile.ZipInfo._encodeFilenameFlags = legacy
    try:
        with zipfile.ZipFile(path, "w") as z:
            for n in names:
                z.writestr(n, "內容")
    finally:
        zipfile.ZipInfo._encodeFilenameFlags = orig


class ArchiveTests(CatalogTestCase):
    def setUp(self):
        super().setUp()
        d = self.drive = self.tmp / "備份A"
        d.mkdir()
        with zipfile.ZipFile(d / "2012 備份.zip", "w") as z:
            z.writestr("國中/自然科/期末報告.docx", "x")
            z.writestr("國中/照片/海邊.jpg", "x")
            z.writestr("__MACOSX/._海邊.jpg", "x")
            z.writestr("國中/", "")
        big5_zip(d / "舊電腦.zip", ["我的文件/預算表.xls", "我的文件/履歷.doc"])
        buf = io.BytesIO(b"hello")
        with tarfile.open(d / "專案.tar.gz", "w:gz") as t:
            info = tarfile.TarInfo("src/budget-2019.csv")
            info.size = 5
            t.addfile(info, buf)
        (d / "壞掉.zip").write_bytes(b"PK\x03\x04 not really a zip")
        self.before = sorted(p.name for p in d.rglob("*"))
        db.add_root(self.conn, d, "備份A")
        scan_all(self.conn, self.cfg)

    def test_lists_without_extracting(self):
        r = textindex.run_extract(self.conn)
        self.assertEqual(r.archives, 3)
        self.assertEqual(sorted(p.name for p in self.drive.rglob("*")), self.before)  # 硬碟上沒有多出任何東西
        rows = {x["name"]: x for x in self.conn.execute(
            "SELECT f.name, t.status, t.source, t.error FROM files f JOIN file_text t ON t.file_id = f.id")}
        self.assertEqual(rows["2012 備份.zip"]["source"], "archive")
        self.assertEqual(rows["壞掉.zip"]["status"], "error")
        self.assertIn("ZIP", rows["壞掉.zip"]["error"])
        fid = self.conn.execute("SELECT id FROM files WHERE name = '2012 備份.zip'").fetchone()[0]
        self.assertEqual(textindex.body(self.conn, fid).splitlines(), ["國中/自然科/期末報告.docx", "國中/照片/海邊.jpg"])  # 不含 __MACOSX 與資料夾
        fid = self.conn.execute("SELECT id FROM files WHERE name = '舊電腦.zip'").fetchone()[0]
        self.assertIn("我的文件/預算表.xls", textindex.body(self.conn, fid))  # Big5 檔名正確還原

    def test_search_finds_files_inside_archives(self):
        textindex.run_extract(self.conn)
        res = find(self.conn, "期末報告")
        self.assertEqual(res["items"][0]["name"], "2012 備份.zip")
        self.assertEqual(res["items"][0]["match"], "archive")
        self.assertEqual(res["items"][0]["entries"], ["國中/自然科/期末報告.docx"])
        self.assertEqual(find(self.conn, "預算表")["items"][0]["name"], "舊電腦.zip")
        self.assertEqual(find(self.conn, "budget")["items"][0]["name"], "專案.tar.gz")
        # 拔掉硬碟之後還搜得到
        shutil.rmtree(self.drive)
        self.assertEqual(find(self.conn, "期末報告")["items"][0]["name"], "2012 備份.zip")

    def test_listing_api(self):
        from fastapi.testclient import TestClient

        from lumilib.server import create_app

        fid = self.conn.execute("SELECT id FROM files WHERE name = '2012 備份.zip'").fetchone()[0]
        with TestClient(create_app(self.cfg, start_jobs_on_boot=False), base_url="http://127.0.0.1:8766", client=("127.0.0.1", 1)) as c:
            self.assertEqual(c.get(f"/api/archive?file={fid}").json()["status"], "todo")
            textindex.run_extract(self.conn)
            out = c.get(f"/api/archive?file={fid}").json()
            self.assertEqual(out["total"], 2)
            self.assertEqual(out["entries"][0], {"path": "國中/自然科/期末報告.docx", "name": "期末報告.docx", "folder": "國中/自然科"})

    def test_cap_and_helpers(self):
        self.assertTrue(archives.as_text(["a"] * 3, 5).endswith("…還有 2 個檔案"))
        self.assertEqual(archives.listing("a/b.txt\n…還有 2 個檔案"), [{"path": "a/b.txt", "name": "b.txt", "folder": "a"}])
        self.assertEqual(archives.matching("x/期末報告.doc\ny/報告.pdf\nz/其他", ["期末", "報告"]), ["x/期末報告.doc"])
        self.assertEqual(archives.matching("x/期末報告.doc\ny/報告.pdf", ["報告", "pdf"]), ["y/報告.pdf"])

    @unittest.skipUnless(archives.bsdtar(), "沒有 bsdtar")
    def test_7z_through_bsdtar(self):
        src = self.tmp / "src"
        (src / "相簿").mkdir(parents=True)
        (src / "相簿" / "婚禮.jpg").write_bytes(b"x")
        out = self.tmp / "out.7z"
        subprocess.run([archives.bsdtar(), "--format", "7zip", "-cf", str(out), "-C", str(src), "相簿"], check=True)
        names, total = archives.entries(out)
        self.assertEqual(names, ["相簿/婚禮.jpg"])
        self.assertEqual(total, 1)


if __name__ == "__main__":
    unittest.main()
