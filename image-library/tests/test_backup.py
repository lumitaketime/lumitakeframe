"""目錄檔管理：備份、只保留最近幾份自動備份、還原（目前那份收起來不刪）、從頭開始（移到垃圾桶）、舊目錄移到垃圾桶。
全程只動 Re'memor 自己的目錄，被掃描的資料夾裡不寫任何東西。"""

import json
import os
import time
from pathlib import Path
from unittest import mock

from lumilib import backup as bk
from lumilib import db
from lumilib.jobs import JobRunner
from lumilib.scanner import scan_all

from test_catalog import CatalogTestCase


class BackupTests(CatalogTestCase):
    def setUp(self):
        super().setUp()
        self.drive = self.tmp / "工作碟"
        (self.drive / "文件").mkdir(parents=True)
        (self.drive / "文件" / "報告.txt").write_text("寄居蟹", encoding="utf-8")
        db.add_root(self.conn, self.drive, "工作碟")
        scan_all(self.conn, self.cfg)
        self.dest = self.tmp / "備份碟"
        self.dest.mkdir()
        self.cfg.save_setting("assistant_claude_key", "sk-secret")
        self.before = sorted(str(p) for p in self.drive.rglob("*"))

    def tearDown(self):
        self.assertEqual(sorted(str(p) for p in self.drive.rglob("*")), self.before)  # 被掃描的資料夾沒有被寫入
        super().tearDown()

    def make(self, auto=False):
        r = bk.create(self.cfg.db_path, self.cfg.home, self.dest, auto=auto, version="test")
        time.sleep(1.05)  # 檔名有秒數：讓每一份的名字不同
        return r

    def test_backup_is_complete_and_has_no_secrets(self):
        r = self.make()
        self.assertTrue(r.path.name.startswith("Re'memor 目錄備份 ") and r.path.name.endswith(".rememor-backup"))
        m = bk.read_manifest(r.path)
        self.assertEqual((m["files"], m["auto"]), (1, False))
        import zipfile

        with zipfile.ZipFile(r.path) as z:
            self.assertNotIn("sk-secret", z.read("config.json").decode())  # API 金鑰不放進備份
            self.assertNotIn("auth.json", z.namelist())
        self.assertEqual([b["name"] for b in bk.list_backups(self.dest)], [r.path.name])
        self.assertEqual([p.name for p in self.dest.iterdir()], [r.path.name])  # 沒有留下暫存檔

    def test_destination_rules(self):
        roots = [str(self.drive)]
        self.assertTrue(bk.check_dest(self.dest, self.cfg.home, roots)[0])
        self.assertIn("被掃描", bk.check_dest(self.drive / "文件", self.cfg.home, roots)[1])  # 不在被掃描的資料夾裡寫東西
        self.assertIn("目錄資料夾裡", bk.check_dest(self.cfg.home, self.cfg.home, roots)[1])
        self.assertIn("找不到", bk.check_dest(self.tmp / "沒有", self.cfg.home, roots)[1])

    def test_keep_latest_auto_backups_only(self):
        manual = self.make()
        autos = [self.make(auto=True) for _ in range(3)]
        removed = bk.prune(self.dest, 2)
        self.assertEqual(removed, [autos[0].path.name])  # 最舊的自動備份拿掉
        names = {b["name"] for b in bk.list_backups(self.dest)}
        self.assertIn(manual.path.name, names)  # 本人按的「立即備份」不動
        self.assertEqual(len(names), 3)

    def test_restore_keeps_current_copy(self):
        r = self.make()
        other = self.tmp / "後來加的"
        other.mkdir()
        db.add_root(self.conn, other, "後來加的")
        self.conn.close()
        bk.prepare_restore(self.cfg.home, r.path)
        msg = bk.apply_pending(self.cfg.home)
        self.assertIn("已改用備份", msg)
        self.conn = db.connect(self.cfg.db_path)
        self.assertEqual([x["name"] for x in db.list_roots(self.conn)], ["工作碟"])  # 回到備份時的樣子
        kept = [p for p in self.cfg.home.iterdir() if p.name.startswith("還原前的目錄 ")]
        self.assertEqual(len(kept), 1)
        self.assertTrue((kept[0] / "library.db").exists())  # 目前那份收起來，沒有刪除
        self.assertIsNone(bk.apply_pending(self.cfg.home))  # 只做一次

    def test_restore_rejects_other_files(self):
        bad = self.dest / "Re'memor 目錄備份 假的.rememor-backup"
        bad.write_bytes(b"not a zip")
        with self.assertRaises(bk.BackupError):
            bk.prepare_restore(self.cfg.home, bad)
        self.assertFalse((self.cfg.home / bk.PENDING).exists())

    def test_reset_moves_to_trash(self):
        trashed = []
        self.conn.close()
        bk.prepare_reset(self.cfg.home)
        with mock.patch("send2trash.send2trash", side_effect=lambda p: (trashed.append(Path(p).name), os.rename(p, str(p) + ".trashed"))):
            self.assertIn("垃圾桶", bk.apply_pending(self.cfg.home))
        self.assertIn("library.db", trashed)
        self.assertTrue((self.cfg.home / "config.json").exists())  # 設定保留
        self.conn = db.connect(self.cfg.db_path)  # 重新開啟：一份空的目錄
        self.assertEqual(db.list_roots(self.conn), [])

    def test_old_copy_after_move(self):
        base = self.tmp / "起點"
        base.mkdir()
        (base / "library.db").write_bytes(b"x" * 100)
        (base / "location.json").write_text(json.dumps({"home": str(self.cfg.home)}), encoding="utf-8")
        copies = bk.old_copies(base, self.cfg.home)
        self.assertEqual([(c["kind"], c["bytes"]) for c in copies], [("moved", 100)])
        with mock.patch("send2trash.send2trash", side_effect=lambda p: os.remove(p)):
            self.assertEqual(bk.trash_old_copy(base, self.cfg.home, str(base)), 100)
        self.assertEqual(sorted(p.name for p in base.iterdir()), ["location.json"])  # 記著目錄在哪裡的那個留著
        with self.assertRaises(bk.BackupError):
            bk.trash_old_copy(base, self.cfg.home, str(self.drive))  # 不是舊目錄：不動

    def test_job_and_api(self):
        from fastapi.testclient import TestClient

        from lumilib.server import create_app

        with TestClient(create_app(self.cfg, start_jobs_on_boot=False), base_url="http://127.0.0.1:8766", client=("127.0.0.1", 1)) as c:
            st = c.get("/api/catalog/backups").json()
            self.assertEqual((st["dir"], st["auto"], st["keep"]), (None, True, 4))  # 預設：每週自動備份，保留 4 份
            self.assertEqual(c.post("/api/catalog/backup", json={}).status_code, 400)  # 還沒選位置
            self.assertEqual(c.post("/api/catalog/backup/dir", json={"path": str(self.drive)}).status_code, 400)
            st = c.post("/api/catalog/backup/dir", json={"path": str(self.dest)}).json()
            self.assertTrue(st["dir_ok"])
            c.post("/api/catalog/backup", json={})
            from lumilib.server import create_app as _  # noqa: F401

            for _i in range(100):
                st = c.get("/api/catalog/backups").json()
                if st["backups"]:
                    break
                time.sleep(0.1)
            self.assertEqual(len(st["backups"]), 1)
            self.assertTrue(st["last"])
            self.assertEqual(c.post("/api/catalog/reset", json={}).status_code, 400)  # 沒有確認：不做
            self.assertEqual(c.post("/api/catalog/restore", json={"path": "/etc/passwd"}).status_code, 400)

    def test_auto_backup_due(self):
        self.assertTrue(bk.due(None))
        self.assertFalse(bk.due(time.strftime("%Y-%m-%dT%H:%M:%S")))
        self.assertTrue(bk.due("2020-01-01T00:00:00"))
        m = JobRunner(self.cfg)
        try:
            m.submit("backup", dest=str(self.dest), auto=True)
            self.assertTrue(m.wait_idle(30))
        finally:
            m.close()
        self.assertEqual([b["auto"] for b in bk.list_backups(self.dest)], [True])
