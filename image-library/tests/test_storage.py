"""儲存空間管理：用量統計、移除資料夾連同快取、清理孤立快取、清除分析、刪除模型。"""

import shutil
import tempfile
import unittest
from pathlib import Path

from lumilib import db
from lumilib.config import load_config
from lumilib.media import thumb_path
from lumilib.scanner import scan_all
from lumilib.storage import clean_orphans, clear_analysis, delete_model_files, remove_root, usage

from test_library import make_photo


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        make_photo(self.tmp / "a" / "1.jpg", (230, 30, 30))
        make_photo(self.tmp / "a" / "2.jpg", (30, 230, 30))
        make_photo(self.tmp / "b" / "3.jpg", (30, 30, 230))
        self.cfg = load_config(self.tmp / "home")
        self.conn = db.connect(self.cfg.db_path)
        self.ra = db.add_root(self.conn, self.tmp / "a")
        self.rb = db.add_root(self.conn, self.tmp / "b")
        scan_all(self.conn, self.cfg)

    def tearDown(self):
        self.conn.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_usage_and_remove_root_deletes_cache(self):
        u = usage(self.conn, self.cfg, [{"name": "gemma4:e4b", "size": 6_600_000_000}])
        self.assertEqual(u["thumbs"]["files"], 3)
        by = {r["name"]: r for r in u["roots"]}
        self.assertEqual(by[self.ra["name"]]["items"], 2)
        self.assertGreater(by[self.ra["name"]]["thumb_bytes"], 0)
        self.assertEqual(u["models"][0]["roles"], ["照片分析"])
        fps = [r[0] for r in self.conn.execute("SELECT fingerprint FROM images WHERE root_id = ?", (self.ra["id"],))]
        res = remove_root(self.conn, self.cfg, self.ra["id"])
        self.assertEqual(res["removed"], 2)
        self.assertGreater(res["freed"], 0)
        for fp in fps:
            self.assertFalse(thumb_path(self.cfg.thumbs_dir, fp).exists())
        self.assertEqual(usage(self.conn, self.cfg)["thumbs"]["files"], 1)
        self.assertTrue((self.tmp / "a" / "1.jpg").exists())  # 照片本身還在

    def test_clean_orphans(self):
        stray = thumb_path(self.cfg.thumbs_dir, "ffffffffffffffff")
        stray.parent.mkdir(parents=True, exist_ok=True)
        stray.write_bytes(b"x" * 100)
        self.assertEqual(usage(self.conn, self.cfg)["orphans"]["files"], 1)
        res = clean_orphans(self.conn, self.cfg)
        self.assertEqual(res["files"], 1)
        self.assertFalse(stray.exists())
        self.assertEqual(usage(self.conn, self.cfg)["thumbs"]["files"], 3)

    def test_clear_analysis(self):
        self.conn.execute("UPDATE images SET analyzed_at = '2026-01-01', description = '海邊'")
        self.conn.commit()
        self.assertEqual(clear_analysis(self.conn, self.rb["id"]), 1)
        st = db.stats(self.conn)
        self.assertEqual((st["analyzed"], st["pending"]), (2, 1))

    def test_delete_model_files(self):
        d = self.cfg.home / "models" / "buffalo_s"
        d.mkdir(parents=True)
        (d / "det.onnx").write_bytes(b"x" * 1000)
        self.assertEqual(delete_model_files(self.cfg, "face", "buffalo_s"), 1000)
        self.assertFalse(d.exists())
        with self.assertRaises(ValueError):
            delete_model_files(self.cfg, "face", "../x")


if __name__ == "__main__":
    unittest.main()
