"""目錄搬到其他磁碟：複製後確認完整才改用、舊的不刪除、不能放進被掃描的資料夾、磁碟沒接上時不另開空目錄。"""

import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from lumilib import db, location
from lumilib.config import load_config
from lumilib.scanner import scan_all


class LocationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()).resolve()
        self.base = self.tmp / "home-anchor"
        self.env = mock.patch.dict(os.environ, {"REMEMOR_HOME": str(self.base)})
        self.env.start()
        self.cfg = load_config()
        self.conn = db.connect(self.cfg.db_path)
        drive = self.tmp / "備份A"
        (drive / "文件").mkdir(parents=True)
        for i in range(5):
            (drive / "文件" / f"報告{i}.txt").write_text(f"第 {i} 份", encoding="utf-8")
        self.drive = drive
        db.add_root(self.conn, drive, "備份A")
        scan_all(self.conn, self.cfg)
        (self.base / "thumbs" / "ab").mkdir(parents=True, exist_ok=True)
        (self.base / "thumbs" / "ab" / "x.jpg").write_bytes(b"thumb" * 100)
        self.ssd = self.tmp / "SSD"
        self.ssd.mkdir()

    def tearDown(self):
        self.conn.close()
        self.env.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def move(self, dest):
        target, error = location.check_target(dest, self.cfg.home, [str(self.drive)])
        self.assertEqual(error, "")
        res = location.move_catalog(self.cfg.db_path, self.cfg.home, target)
        self.assertEqual((res.errors, res.stopped), ([], False))
        location.use_home(self.base, target)
        return target, res

    def test_cannot_move_into_a_scanned_folder_or_a_missing_one(self):
        roots = [str(self.drive)]
        self.assertIn("被掃描", location.check_target(self.drive / "文件", self.cfg.home, roots)[1])
        (self.drive / ".隱藏").mkdir()
        self.assertEqual(location.check_target(self.drive / ".隱藏", self.cfg.home, roots)[1], "")  # 掃描會略過隱藏資料夾
        self.assertIn("找不到", location.check_target(self.tmp / "沒有這個", self.cfg.home, roots)[1])
        self.assertIn("已經在這裡", location.check_target(self.base, self.cfg.home, roots)[1])

    def test_move_copies_everything_keeps_the_old_one_and_switches(self):
        before = {p: p.stat().st_mtime for p in self.drive.rglob("*")}
        n_files = self.conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
        target, res = self.move(self.ssd)
        self.assertEqual(target, self.ssd / "Re'memor 目錄")
        self.assertTrue((target / "thumbs" / "ab" / "x.jpg").exists())
        self.assertTrue((self.base / "library.db").exists())  # 原本那份還在，不自動刪除
        self.assertEqual(location.current_home(), target)
        moved = load_config()
        self.assertEqual(moved.home, target)
        c = db.connect(moved.db_path)
        try:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM files").fetchone()[0], n_files)
        finally:
            c.close()
        self.assertEqual({p: p.stat().st_mtime for p in self.drive.rglob("*")}, before)  # 被掃描的硬碟沒有被動到
        self.assertIn("複製到", location.describe(res, target, self.base))

    def test_unplugged_catalog_disk_never_opens_an_empty_catalog(self):
        target, _ = self.move(self.ssd)
        shutil.move(str(target), str(self.tmp / "拔掉了"))
        with self.assertRaises(location.CatalogUnavailable) as ctx:
            load_config()
        self.assertEqual(ctx.exception.target, target)
        self.assertFalse(target.exists())  # 沒有在原位置建立空的目錄
        shutil.move(str(self.tmp / "拔掉了"), str(target))
        self.assertEqual(load_config().home, target)

    def test_moving_back_to_the_mac_keeps_the_old_copy_aside(self):
        target, _ = self.move(self.ssd)
        self.conn.close()
        moved = load_config()
        c = db.connect(moved.db_path)
        c.execute("INSERT INTO smart_folders (name, query, created_at) VALUES ('在 SSD 上加的', '{}', '')")
        c.commit()
        c.close()
        back, error = location.check_target(self.base, moved.home, [str(self.drive)])
        self.assertEqual((back, error), (self.base, ""))
        res = location.move_catalog(moved.db_path, moved.home, back)
        self.assertEqual(res.errors, [])
        location.use_home(self.base, back)
        self.assertEqual(location.current_home(), self.base)
        self.assertFalse((self.base / location.POINTER).exists())
        c = db.connect(self.base / "library.db")
        try:
            self.assertEqual(c.execute("SELECT name FROM smart_folders").fetchone()[0], "在 SSD 上加的")  # 用的是新的那份
        finally:
            c.close()
        self.assertTrue(res.stash and (res.stash / "library.db").exists())  # 舊的那份收起來，沒有刪除
        self.assertTrue((target / "library.db").exists())  # SSD 上那份也還在
        self.conn = db.connect(self.base / "library.db")

    def test_api_moves_in_the_background_then_restarts(self):
        import time

        from fastapi.testclient import TestClient

        from lumilib.server import create_app

        app = create_app(self.cfg, start_jobs_on_boot=False)
        restarted = []
        with TestClient(app, base_url="http://127.0.0.1:8766", client=("127.0.0.1", 1)) as c:
            app.state.restart_later = lambda delay=0: restarted.append(delay)  # 測試裡不真的重新啟動
            info = c.get("/api/catalog/location").json()
            self.assertEqual((info["home"], info["moved"]), (str(self.base), False))
            self.assertIn("被掃描", c.post("/api/catalog/location/check", json={"path": str(self.drive)}).json()["error"])
            self.assertEqual(c.post("/api/catalog/move", json={"path": str(self.drive)}).status_code, 400)
            self.assertEqual(c.post("/api/catalog/move", json={"path": str(self.ssd)}).status_code, 200)
            for _ in range(200):
                if restarted:
                    break
                time.sleep(0.05)
        self.assertTrue(restarted)
        self.assertEqual(location.current_home(), self.ssd / "Re'memor 目錄")

    def test_stop_leaves_nothing_half_done(self):
        import threading

        target, _ = location.check_target(self.ssd, self.cfg.home, [])
        stop = threading.Event()
        stop.set()
        res = location.move_catalog(self.cfg.db_path, self.cfg.home, target, stop=stop)
        self.assertTrue(res.stopped)
        self.assertEqual(list(self.ssd.iterdir()), [])
        self.assertEqual(location.current_home(), self.base)


if __name__ == "__main__":
    unittest.main()
