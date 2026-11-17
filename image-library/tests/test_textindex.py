"""文件文字與全文索引：真正由 Office 存出來的 Word、Excel、PDF（tests/fixtures/docs），加上手做的簡報與電子書。"""

import shutil
import sys
import threading
import unittest
import zipfile
from pathlib import Path

from PIL import Image

from lumilib import db, textindex
from lumilib.scanner import scan_all

from test_catalog import CatalogTestCase

FIXTURES = Path(__file__).parent / "fixtures" / "docs"


def make_pptx(path: Path, slides: list[str]) -> None:
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        for i, text in enumerate(slides, 1):
            z.writestr(f"ppt/slides/slide{i}.xml",
                       '<p:sld xmlns:p="p" xmlns:a="a"><p:cSld><p:spTree><p:sp><p:txBody><a:p><a:r>'
                       f"<a:t>{text}</a:t></a:r></a:p></p:txBody></p:sp></p:spTree></p:cSld></p:sld>")


def make_epub(path: Path, chapters: list[str]) -> None:
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("mimetype", "application/epub+zip")
        for i, text in enumerate(chapters, 1):
            z.writestr(f"OEBPS/ch{i}.xhtml", f"<html><body><h1>第{i}章</h1><p>{text}</p></body></html>")


class TextIndexTests(CatalogTestCase):
    def setUp(self):
        super().setUp()
        d = self.drive = self.tmp / "文件碟"
        (d / "國中").mkdir(parents=True)
        for name in ("report.docx", "report.pdf", "budget.xlsx", "report.doc"):
            shutil.copy(FIXTURES / name, d / "國中" / name)
        make_pptx(d / "國中" / "發表.pptx", ["科展題目：潮間帶生物", "結論與心得"])
        make_epub(d / "小說.epub", ["從前從前有一座山", "山上有一座廟"])
        (d / "筆記.txt").write_bytes("今天去圖書館借了三本書\nLibrary visit".encode("big5"))
        (d / "頁面.html").write_text("<html><script>var x='不要這段';</script><body><p>網頁裡的段落</p></body></html>", encoding="utf-8")
        Image.new("RGB", (200, 100), (255, 255, 255)).save(d / "國中" / "掃描.pdf")  # 只有圖片、沒有文字層：像掃描檔
        (d / "壞掉.docx").write_bytes(b"this is not a zip file")
        self.root = db.add_root(self.conn, d, "文件碟")
        scan_all(self.conn, self.cfg)

    def text_of(self, name):
        r = self.conn.execute("SELECT f.id FROM files f WHERE f.name = ?", (name,)).fetchone()
        return textindex.body(self.conn, r["id"])

    def status_of(self, name):
        return self.conn.execute("SELECT t.status FROM file_text t JOIN files f ON f.id = t.file_id WHERE f.name = ?", (name,)).fetchone()[0]

    def found(self, query):
        ids = textindex.text_matches(self.conn, query)
        return sorted(self.conn.execute(f"SELECT name FROM files WHERE id IN ({','.join('?' * len(ids))})", ids).fetchall()[i][0]
                      for i in range(len(ids))) if ids else []

    def test_reads_every_supported_format_without_touching_the_drive(self):
        before = {p: p.stat().st_mtime_ns for p in self.drive.rglob("*")}
        plan = textindex.extract_plan(self.conn)
        self.assertEqual((plan["todo"]["files"], plan["done"]), (10, 0))
        res = textindex.run_extract(self.conn)
        self.assertEqual({p: p.stat().st_mtime_ns for p in self.drive.rglob("*")}, before)  # 只讀取
        self.assertEqual(set(self.drive.rglob("*")), set(before))  # 沒有建立任何檔案
        self.assertIn("國中自然科報告", self.text_of("report.docx"))
        self.assertIn("潮間帶的寄居蟹", self.text_of("report.pdf"))
        self.assertIn("經費", self.text_of("budget.xlsx"))
        self.assertIn("科展題目", self.text_of("發表.pptx"))
        self.assertIn("山上有一座廟", self.text_of("小說.epub"))
        self.assertIn("圖書館", self.text_of("筆記.txt"))  # Big5 編碼也讀得出來
        self.assertIn("網頁裡的段落", self.text_of("頁面.html"))
        self.assertNotIn("不要這段", self.text_of("頁面.html"))
        self.assertEqual(self.status_of("掃描.pdf"), "needs_ocr")
        self.assertEqual(self.status_of("壞掉.docx"), "error")  # 壞掉的檔案不會讓工作停下來
        self.assertEqual(self.status_of("report.doc"), "ok" if sys.platform == "darwin" else "unsupported")
        self.assertGreaterEqual(res.read, 7)
        plan = textindex.extract_plan(self.conn)
        self.assertEqual((plan["todo"]["files"], plan["needs_ocr"]), (0, 1))

    def test_search_finds_chinese_and_english_inside_documents(self):
        textindex.run_extract(self.conn)
        self.assertEqual(self.found("自然科報告"), ["report.doc", "report.docx", "report.pdf"] if sys.platform == "darwin" else ["report.docx", "report.pdf"])
        self.assertIn("report.pdf", self.found("寄居蟹"))
        self.assertIn("發表.pptx", self.found("潮間帶"))
        self.assertIn("budget.xlsx", self.found("budget"))
        self.assertIn("report.pdf", self.found("Hermit"))  # 不分大小寫
        self.assertEqual(self.found("不存在的詞"), [])
        parts = textindex.snippet(self.text_of("report.pdf"), ["寄居蟹"])
        self.assertTrue(any(p["hit"] and p["text"] == "寄居蟹" for p in parts))
        self.assertIn("潮間帶", "".join(p["text"] for p in parts))

    def test_changed_file_is_reread_and_old_words_disappear(self):
        textindex.run_extract(self.conn)
        self.assertIn("筆記.txt", self.found("圖書館"))
        (self.drive / "筆記.txt").write_text("改成去游泳池", encoding="utf-8")
        scan_all(self.conn, self.cfg)
        self.assertEqual(self.found("圖書館"), [])  # 檔案改過之後，舊的文字不再算數
        self.assertEqual(textindex.extract_plan(self.conn)["todo"]["files"], 1)
        textindex.run_extract(self.conn)
        self.assertEqual((self.found("游泳池"), self.found("圖書館")), (["筆記.txt"], []))

    def test_reset_clears_only_the_catalog_and_can_be_read_again(self):
        textindex.run_extract(self.conn)
        before = {p: p.stat().st_mtime for p in self.drive.rglob("*")}
        self.assertGreater(textindex.index_bytes(self.conn), 0)
        self.assertGreater(textindex.reset(self.conn), 0)
        self.assertEqual(self.found("圖書館"), [])
        self.assertLess(textindex.index_bytes(self.conn), 100)  # 全文索引清空後只剩幾個位元組的結構
        self.assertEqual({p: p.stat().st_mtime for p in self.drive.rglob("*")}, before)  # 硬碟上的檔案沒有被動到
        self.assertGreater(textindex.extract_plan(self.conn)["todo"]["files"], 0)
        textindex.run_extract(self.conn)
        self.assertIn("筆記.txt", self.found("圖書館"))

    def test_failed_files_can_be_retried_and_cloud_files_are_not_downloaded(self):
        from unittest import mock

        broken = self.drive / "壞掉.docx"
        broken.write_bytes(b"PK\x03\x04garbage")
        scan_all(self.conn, self.cfg)
        textindex.run_extract(self.conn)
        row = self.conn.execute("SELECT t.status, t.error FROM file_text t JOIN files f ON f.id = t.file_id WHERE f.name = '壞掉.docx'").fetchone()
        self.assertEqual(row["status"], "error")
        self.assertIn("BadZipFile", row["error"])  # 錯誤訊息完整記下來，方便找原因
        self.assertEqual(textindex.run_extract(self.conn).failed, 0)  # 一般重跑不會一直重試
        self.assertEqual(textindex.run_extract(self.conn, retry=True).failed, 1)  # 「再試一次」才重試
        # 只在雲端的檔案（macOS 的佔位檔）：不讀（讀了會從網路下載），標成「在雲端」
        real_stat = Path.stat

        def fake_stat(p, *a, **kw):
            st = real_stat(p, *a, **kw)
            if p.name == "筆記.txt":
                return mock.Mock(st_size=st.st_size, st_mtime=st.st_mtime, st_flags=textindex.SF_DATALESS)
            return st

        self.conn.execute("DELETE FROM file_text WHERE file_id IN (SELECT id FROM files WHERE name = '筆記.txt')")
        with mock.patch.object(Path, "stat", fake_stat):
            res = textindex.run_extract(self.conn)
        self.assertEqual(res.cloud, 1)
        self.assertEqual(self.conn.execute("SELECT t.status FROM file_text t JOIN files f ON f.id = t.file_id WHERE f.name = '筆記.txt'").fetchone()[0], "cloud")
        self.assertEqual(textindex.extract_plan(self.conn)["cloud"], 1)
        textindex.run_extract(self.conn)  # 下載回來之後就讀得到
        self.assertIn("筆記.txt", self.found("圖書館"))

    def test_stop_and_resume(self):
        stop = threading.Event()
        real = (textindex.COMMIT_ROWS, textindex.REPORT_SECONDS)
        textindex.COMMIT_ROWS, textindex.REPORT_SECONDS = 1, 0
        try:
            def progress(done, total, name):
                if done >= 3:
                    stop.set()
            first = textindex.run_extract(self.conn, progress=progress, stop=stop)
        finally:
            textindex.COMMIT_ROWS, textindex.REPORT_SECONDS = real
        self.assertTrue(first.stopped)
        left = textindex.extract_plan(self.conn)["todo"]["files"]
        self.assertTrue(0 < left < 10)
        textindex.run_extract(self.conn)
        self.assertEqual(textindex.extract_plan(self.conn)["todo"]["files"], 0)

    def test_unplugged_drive_is_interrupted_not_an_error(self):
        shutil.move(str(self.drive), str(self.tmp / "拔掉了"))
        res = textindex.run_extract(self.conn)
        self.assertEqual((res.read, res.offline, res.failed), (0, 10, 0))
        self.assertEqual(textindex.extract_plan(self.conn)["offline"]["files"], 10)
        shutil.move(str(self.tmp / "拔掉了"), str(self.drive))
        textindex.run_extract(self.conn)
        self.assertIn("report.pdf", self.found("寄居蟹"))  # 硬碟拔掉之後仍然搜得到（索引在資料庫裡）
        shutil.move(str(self.drive), str(self.tmp / "又拔掉了"))
        self.assertIn("report.pdf", self.found("寄居蟹"))

    def test_background_job_and_log(self):
        from fastapi.testclient import TestClient

        from lumilib.server import create_app

        with TestClient(create_app(self.cfg, start_jobs_on_boot=False), base_url="http://127.0.0.1:8766",
                        client=("127.0.0.1", 1)) as c:
            self.assertEqual(c.post("/api/jobs", json={"kind": "extract"}).status_code, 200)
            for _ in range(200):
                if not c.get("/api/jobs").json()["running"]:
                    break
                threading.Event().wait(0.05)
            top = c.get("/api/activity").json()["history"][0]
            self.assertEqual((top["kind"], top["state"]), ("extract", "done"))
        self.assertIn("report.docx", self.found("自然科"))


if __name__ == "__main__":
    unittest.main()
