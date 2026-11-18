"""掃描整個家目錄時：~/Library 裡 App 的資料不編目（雲端硬碟資料夾除外）、.noindex 不編目；
之前編進去的改成不編目時不算「遺失」；內容全是 0 的雲端檔案不算「讀不了」。"""

import unittest
from unittest import mock

from lumilib import db, scanner, textindex
from lumilib.scanner import scan_all

from test_catalog import CatalogTestCase


class SkipLibraryTests(CatalogTestCase):
    def setUp(self):
        super().setUp()
        h = self.home = self.tmp / "elaine"
        for d in ("Library/Preferences", "Library/Application Support/App", "Library/Group Containers/OneDrive.noindex/OneDrive",
                  "Library/CloudStorage/OneDrive-個人/課程", "Documents", "Photos Library.noindex"):
            (h / d).mkdir(parents=True)
        (h / "Library/Group Containers/OneDrive.noindex/OneDrive/講義.txt").write_text("內部的副本", encoding="utf-8")
        (h / "Library/Application Support/App/cache.json").write_text("{}", encoding="utf-8")
        (h / "Library/CloudStorage/OneDrive-個人/課程/講義.txt").write_text("小號教材", encoding="utf-8")
        (h / "Library/notes.txt").write_text("x", encoding="utf-8")
        (h / "Documents/報告.txt").write_text("自然科", encoding="utf-8")
        (h / "Photos Library.noindex/a.txt").write_text("x", encoding="utf-8")
        self.root = db.add_root(self.conn, h, "家目錄")

    def paths(self):
        return sorted(r[0] for r in self.conn.execute(
            "SELECT d.path || '/' || f.name FROM files f JOIN folders d ON d.id = f.folder_id WHERE f.status = 'ok'"))

    def test_only_user_files_and_cloud_drives_are_cataloged(self):
        scan_all(self.conn, self.cfg)
        self.assertEqual(self.paths(), ["Documents/報告.txt", "Library/CloudStorage/OneDrive-個人/課程/講義.txt"])

    def test_folders_that_become_skipped_are_not_counted_missing(self):
        with mock.patch.object(scanner, "skip_dir", lambda *a: False):
            scan_all(self.conn, self.cfg)
        self.assertGreater(len(self.paths()), 2)
        res = scan_all(self.conn, self.cfg)[0]
        self.assertEqual(res.missing, 0)
        self.assertGreaterEqual(res.skipped, 2)
        self.assertEqual(len(self.paths()), 2)

    def test_zero_filled_cloud_files_are_marked_cloud(self):
        (self.home / "Documents/還沒下載.pdf").write_bytes(b"\x00" * 50_000)
        scan_all(self.conn, self.cfg)
        res = textindex.run_extract(self.conn)
        self.assertEqual((res.cloud, res.failed), (1, 0))


if __name__ == "__main__":
    unittest.main()
