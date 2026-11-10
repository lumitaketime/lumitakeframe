"""Re'memor 目錄：拔掉硬碟、多顆備份硬碟時，紀錄要正確。

這裡的測試先寫成能重現問題，再修正程式讓它們通過。
"""

import os
import shutil
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path

from PIL import Image

from lumilib import db
from lumilib.config import load_config
from lumilib.scanner import scan_all, scan_root

try:  # 硬碟辨識（第一步新增）；還沒有這個模組時，所有資料夾都被視為同一個圖庫
    from lumilib import volumes
except ImportError:  # pragma: no cover
    volumes = None


def photo(path: Path, color=(120, 80, 40)):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (64, 48), color).save(path, "JPEG", quality=90)


@contextmanager
def unplug_when_listing(target: Path, drive: Path, parked: Path):
    """模擬拔掉硬碟：程式要列出 target 資料夾的內容時，整顆硬碟（drive）剛好消失。"""
    real = os.scandir

    def scandir(path="."):
        if Path(os.fspath(path)) == target and drive.exists():
            drive.rename(parked)
        return real(path)

    os.scandir = scandir
    try:
        yield
    finally:
        os.scandir = real


@contextmanager
def separate_drives(*mounts: Path):
    """測試環境的資料夾都在同一顆磁碟上；這裡讓每個 mount 被當成不同的硬碟。"""
    if volumes is None:
        yield
        return
    real = volumes.volume_info

    def fake(path):
        p = Path(path).resolve()
        for i, m in enumerate(mounts):
            m = m.resolve()
            if p == m or m in p.parents:
                return {"uuid": f"TEST-DRIVE-{i}", "name": m.name, "fs_type": "exfat",
                        "capacity": 4_000_000_000_000, "mount": str(m), "read_only": False}
        return real(path)

    volumes.volume_info = fake
    try:
        yield
    finally:
        volumes.volume_info = real


class CatalogTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.cfg = load_config(self.tmp / "home")
        self.conn = db.connect(self.cfg.db_path)

    def tearDown(self):
        self.conn.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def status(self, root_name: str) -> dict[str, str]:
        rows = self.conn.execute(
            "SELECT i.rel_path, i.status FROM images i JOIN roots r ON r.id = i.root_id WHERE r.name = ?", (root_name,))
        return {r["rel_path"]: r["status"] for r in rows}


class UnplugTests(CatalogTestCase):
    def test_unplug_midscan_keeps_unvisited_files(self):
        """掃描到一半拔掉硬碟：還沒掃到的檔案不能被標成「遺失」。"""
        drive = self.tmp / "Backup"
        for folder in ("a", "b"):
            for i in range(3):
                photo(drive / folder / f"{folder}{i}.jpg", (i * 60, 20, 20))
        db.add_root(self.conn, drive, "Backup")
        scan_all(self.conn, self.cfg)
        self.assertEqual(set(self.status("Backup").values()), {"ok"})

        parked = self.tmp / "unplugged"
        photo(drive / "a" / "new.jpg", (1, 2, 3))  # 讓第二次掃描有事做
        with unplug_when_listing(drive / "b", drive, parked):
            [res] = scan_all(self.conn, self.cfg)

        st = self.status("Backup")
        self.assertEqual({k: v for k, v in st.items() if v != "ok"}, {}, "拔掉後不能把檔案標成遺失")
        self.assertEqual(res.missing, 0)
        self.assertTrue(res.interrupted, "掃描結果要說明硬碟在掃描中途被拔掉")

        # 接回來再掃一次：全部都在、沒有遺失
        parked.rename(drive)
        [res] = scan_all(self.conn, self.cfg)
        self.assertEqual(res.missing, 0)
        self.assertEqual(set(self.status("Backup").values()), {"ok"})
        self.assertEqual(len(self.status("Backup")), 7)

    def test_unplug_while_reading_files(self):
        """列出資料夾後、逐一讀檔時才被拔掉：同一個資料夾裡還沒讀到的檔案也不能算遺失。"""
        drive = self.tmp / "Backup"
        for i in range(6):
            photo(drive / "a" / f"p{i}.jpg", (i * 30, 20, 20))
        db.add_root(self.conn, drive, "Backup")
        scan_all(self.conn, self.cfg)
        for i in range(6):  # 內容改變，第二次掃描要重新讀每一張
            photo(drive / "a" / f"p{i}.jpg", (i * 30, 90, 20))
            os.utime(drive / "a" / f"p{i}.jpg", (1_700_000_000 + i, 1_700_000_000 + i))

        parked = self.tmp / "unplugged"
        real_stat = os.stat
        calls = {"n": 0}

        def stat(path, *a, **kw):  # Path.stat() 也是透過 os.stat
            name = os.path.basename(os.fspath(path))
            if name.startswith("p") and name.endswith(".jpg"):
                calls["n"] += 1
                if calls["n"] == 3 and drive.exists():
                    drive.rename(parked)
            return real_stat(path, *a, **kw)

        os.stat = stat
        try:
            [res] = scan_all(self.conn, self.cfg)
        finally:
            os.stat = real_stat
        self.assertEqual({k: v for k, v in self.status("Backup").items() if v != "ok"}, {})
        self.assertEqual(res.missing, 0)
        self.assertTrue(res.interrupted)


class MultiDriveTests(CatalogTestCase):
    def test_copy_on_other_drive_is_not_a_move(self):
        """A 硬碟刪掉的檔案，B 硬碟上有一樣的備份：B 的備份是另一個檔案，不是「從 A 搬過來」。"""
        a, b = self.tmp / "DriveA", self.tmp / "DriveB"
        photo(a / "trip" / "sea.jpg", (10, 120, 200))
        photo(a / "trip" / "keep.jpg", (200, 120, 10))
        shutil.copytree(a / "trip", b / "backup" / "trip")  # B 是 A 的備份
        with separate_drives(a, b):
            db.add_root(self.conn, a, "DriveA")
            scan_root(self.conn, self.cfg, db.get_root(self.conn, "DriveA"))
            (a / "trip" / "sea.jpg").unlink()  # 在 A 刪掉一張
            [res_a] = scan_all(self.conn, self.cfg, ["DriveA"])
            self.assertEqual(res_a.missing, 1)

            db.add_root(self.conn, b, "DriveB")
            [res_b] = scan_all(self.conn, self.cfg, ["DriveB"])

        self.assertEqual((res_b.added, res_b.moved), (2, 0), "B 的兩張備份都是新紀錄，不是搬家")
        self.assertEqual(self.status("DriveA"), {"trip/sea.jpg": "missing", "trip/keep.jpg": "ok"})
        self.assertEqual(self.status("DriveB"), {"backup/trip/sea.jpg": "ok", "backup/trip/keep.jpg": "ok"})


def snapshot(folder: Path) -> dict:
    """硬碟上所有檔案（含隱藏檔）的內容與修改時間，用來確認掃描沒有寫入任何東西。"""
    out = {}
    for dirpath, dirnames, filenames in os.walk(folder):
        for d in dirnames:
            out[os.path.join(dirpath, d)] = "dir"
        for f in filenames:
            p = os.path.join(dirpath, f)
            st = os.stat(p)
            out[p] = (Path(p).read_bytes(), st.st_mtime_ns)
    return out


class CatalogFixture(CatalogTestCase):
    """一顆假的備份硬碟：照片、文件、音樂、壓縮檔、空資料夾、隱藏檔與照片圖庫套件。"""

    def setUp(self):
        super().setUp()
        d = self.drive = self.tmp / "Archive"
        photo(d / "2008 國中" / "畢業旅行" / "a.jpg")
        (d / "2008 國中" / "自然科報告.docx").write_bytes(b"x" * 1000)
        (d / "2008 國中" / "notes.txt").write_text("hello", encoding="utf-8")
        (d / "音樂").mkdir(parents=True)
        (d / "音樂" / "song.mp3").write_bytes(b"m" * 3000)
        (d / "備份.zip").write_bytes(b"z" * 500)
        (d / "空資料夾").mkdir()
        (d / ".DS_Store").write_bytes(b"junk")
        (d / ".Trashes").mkdir()
        (d / ".Trashes" / "old.txt").write_text("deleted")
        (d / "Photos Library.photoslibrary" / "originals").mkdir(parents=True)
        photo(d / "Photos Library.photoslibrary" / "originals" / "x.jpg")
        (d / "Photos Library.photoslibrary" / "database.db").write_bytes(b"d" * 4000)
        self.root = db.add_root(self.conn, d, "Archive")

    def folder(self, path):
        return self.conn.execute("SELECT * FROM folders WHERE root_id = ? AND path = ?", (self.root["id"], path)).fetchone()

    def files(self):
        return {(r["path"] + "/" if r["path"] else "") + r["name"]: r for r in self.conn.execute(
            "SELECT f.*, d.path FROM files f JOIN folders d ON d.id = f.folder_id WHERE f.root_id = ?", (self.root["id"],))}


class CatalogTests(CatalogFixture):
    def test_records_every_file_type_and_folder(self):
        [res] = scan_all(self.conn, self.cfg)
        self.assertTrue(res.complete)
        files = self.files()
        kinds = {k: r["kind"] for k, r in files.items()}
        self.assertEqual(kinds, {
            "2008 國中/畢業旅行/a.jpg": "photo", "2008 國中/自然科報告.docx": "document", "2008 國中/notes.txt": "document",
            "音樂/song.mp3": "audio", "備份.zip": "archive", "Photos Library.photoslibrary": "package",
        })
        self.assertNotIn(".DS_Store", files)  # 隱藏檔與系統資料夾不列入
        pkg = files["Photos Library.photoslibrary"]
        self.assertGreater(pkg["size"], 4000)  # 套件算一個項目，大小是裡面所有檔案加總
        self.assertEqual(res.added, 1)  # 套件裡的照片不算進圖庫
        self.assertIsNotNone(files["2008 國中/畢業旅行/a.jpg"]["image_id"])
        self.assertIsNotNone(self.folder("空資料夾"))  # 空資料夾也記錄

    def test_folder_totals(self):
        scan_all(self.conn, self.cfg)
        top, school = self.folder(""), self.folder("2008 國中")
        sizes = {k: r["size"] for k, r in self.files().items()}
        self.assertEqual(top["total_files"], 6)
        self.assertEqual(top["total_bytes"], sum(sizes.values()))
        self.assertEqual((school["files"], school["total_files"], school["subfolders"]), (2, 3, 1))
        self.assertEqual(school["total_bytes"], sizes["2008 國中/畢業旅行/a.jpg"] + 1005)

    def test_scan_never_writes_to_drive(self):
        before = snapshot(self.drive)
        scan_all(self.conn, self.cfg)
        scan_all(self.conn, self.cfg)
        self.assertEqual(snapshot(self.drive), before)

    def test_deleted_folder_marked_missing_with_contents(self):
        scan_all(self.conn, self.cfg)
        shutil.rmtree(self.drive / "2008 國中")
        [res] = scan_all(self.conn, self.cfg)
        self.assertEqual(res.missing, 3)  # 一張照片、兩份文件
        self.assertEqual(self.folder("2008 國中")["status"], "missing")
        self.assertEqual(self.folder("2008 國中/畢業旅行")["status"], "missing")
        self.assertEqual(self.status("Archive"), {"2008 國中/畢業旅行/a.jpg": "missing"})
        self.assertEqual(self.folder("")["total_files"], 3)  # 遺失的不算進總數

    def test_rename_in_same_folder_is_a_move(self):
        scan_all(self.conn, self.cfg)
        folder = self.drive / "2008 國中" / "畢業旅行"
        (folder / "a.jpg").rename(folder / "b.jpg")
        [res] = scan_all(self.conn, self.cfg)
        self.assertEqual((res.moved, res.added, res.missing), (1, 0, 0))
        self.assertEqual(self.status("Archive"), {"2008 國中/畢業旅行/b.jpg": "ok"})

    def test_resume_after_stop_skips_finished_folders(self):
        import threading

        stop = threading.Event()
        real, listed = os.scandir, []

        def scandir(path="."):
            listed.append(Path(os.fspath(path)).name)
            if Path(os.fspath(path)) == self.drive / "2008 國中" / "畢業旅行":
                stop.set()  # 處理到這個資料夾時按下停止
            return real(path)

        os.scandir = scandir
        try:
            [res] = scan_all(self.conn, self.cfg, stop=stop)
            self.assertTrue(res.stopped)
            self.assertEqual(db.get_root(self.conn, "Archive")["scan_state"], "partial")
            first = list(listed)
            listed.clear()
            [res] = scan_all(self.conn, self.cfg)
        finally:
            os.scandir = real
        self.assertTrue(res.resumed and res.complete)
        self.assertEqual(db.get_root(self.conn, "Archive")["scan_state"], "done")
        self.assertIn("2008 國中", first)
        self.assertNotIn("2008 國中", listed)  # 上次已完成的資料夾不再讀取
        self.assertNotIn("畢業旅行", listed)
        self.assertIn("音樂", listed)
        self.assertEqual(self.folder("")["total_files"], 6)

    def test_other_drive_at_same_path_is_not_scanned(self):
        with separate_drives(self.drive):
            scan_all(self.conn, self.cfg)
        before = self.files()
        # 拔掉原本的硬碟、接上另一顆同名硬碟：同一個位置，但是不同的硬碟編號
        shutil.rmtree(self.drive)
        photo(self.drive / "別人的照片.jpg")
        real = volumes.volume_info
        volumes.volume_info = lambda p: {"uuid": "SOMEONE-ELSE", "name": "Archive", "fs_type": "exfat",
                                         "capacity": 1, "mount": str(self.drive), "read_only": False}
        try:
            [res] = scan_all(self.conn, self.cfg)
        finally:
            volumes.volume_info = real
        self.assertTrue(res.other_drive)
        self.assertEqual(res.missing, 0)
        self.assertEqual({k: r["status"] for k, r in self.files().items()}, {k: "ok" for k in before})

    def test_renamed_drive_is_found_by_uuid(self):
        with separate_drives(self.drive):
            scan_all(self.conn, self.cfg)
            renamed = self.tmp / "Archive 1"
            self.drive.rename(renamed)
            real_find = volumes.find_mount
            volumes.find_mount = lambda uuid: renamed if uuid == "TEST-DRIVE-0" else None
            try:
                with separate_drives(renamed):
                    [res] = scan_all(self.conn, self.cfg)
            finally:
                volumes.find_mount = real_find
        self.assertTrue(res.complete)
        self.assertEqual((res.missing, res.files_added), (0, 0))
        self.assertEqual(Path(db.get_root(self.conn, "Archive")["path"]), renamed)

    def test_drive_is_recorded(self):
        with separate_drives(self.drive):
            scan_all(self.conn, self.cfg)
        drive = self.conn.execute("SELECT * FROM drives").fetchone()
        self.assertEqual((drive["uuid"], drive["name"], drive["fs_type"]), ("TEST-DRIVE-0", "Archive", "exfat"))
        self.assertEqual(db.get_root(self.conn, "Archive")["drive_id"], drive["id"])


class FolderApiTests(CatalogFixture):
    def test_folders_api_lists_catalog_even_when_unplugged(self):
        from fastapi.testclient import TestClient

        from lumilib.server import create_app

        scan_all(self.conn, self.cfg)
        self.drive.rename(self.tmp / "unplugged")  # 拔掉硬碟後還是看得到
        with TestClient(create_app(self.cfg, start_jobs_on_boot=False), base_url="http://127.0.0.1:8766",
                        client=("127.0.0.1", 1)) as c:
            roots = c.get("/api/folders").json()["roots"]
            self.assertEqual((roots[0]["online"], roots[0]["catalog"]["files"]), (False, 6))
            top = c.get("/api/folders", params={"root": self.root["id"]}).json()
            names = {f["name"]: f for f in top["folders"]}
            self.assertIn("空資料夾", names)  # 沒有照片的資料夾也列出
            self.assertEqual((names["音樂"]["files"], names["音樂"]["bytes"]), (1, 3000))
            self.assertEqual({f[1] for f in top["catalog"]["files"]}, {"備份.zip", "Photos Library.photoslibrary"})
            school = c.get("/api/folders", params={"root": self.root["id"], "path": "2008 國中"}).json()
            self.assertEqual(sorted(f[1] for f in school["catalog"]["files"]), ["notes.txt", "自然科報告.docx"])
            self.assertEqual(school["catalog"]["total_files"], 3)


class UpgradeTests(unittest.TestCase):
    def test_existing_library_gets_catalog_without_losing_data(self):
        """舊版（v14）的圖庫升級後，照片、分析與相簿都保留，第一次掃描補上完整目錄。"""
        tmp = Path(tempfile.mkdtemp())
        try:
            photo(tmp / "p" / "a.jpg")
            cfg = load_config(tmp / "home")
            conn = db.connect(cfg.db_path)
            db.add_root(conn, tmp / "p", "舊圖庫")
            scan_all(conn, cfg)
            image_id = conn.execute("SELECT id FROM images").fetchone()[0]
            conn.execute("UPDATE images SET description = '舊的分析' WHERE id = ?", (image_id,))
            album = db.create_album(conn, "舊相簿", [image_id])
            for t in ("files", "folders", "drives"):
                conn.execute(f"DROP TABLE {t}")
            for col in ("drive_id", "drive_rel", "scan_gen", "scan_state"):
                conn.execute(f"ALTER TABLE roots DROP COLUMN {col}")
            conn.execute("PRAGMA user_version = 14")
            conn.commit()
            conn.close()

            conn = db.connect(cfg.db_path)
            [res] = scan_all(conn, cfg)
            self.assertEqual((res.added, res.unchanged, res.files_added), (0, 1, 1))
            self.assertEqual(conn.execute("SELECT description FROM images WHERE id = ?", (image_id,)).fetchone()[0], "舊的分析")
            self.assertEqual(db.get_album(conn, album)["count"], 1)
            self.assertEqual(conn.execute("SELECT image_id FROM files").fetchone()[0], image_id)
            conn.close()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class SeparateFromLibraryTests(unittest.TestCase):
    def test_own_data_folder_and_port(self):
        """Re'memor 不能讀寫到 Lumitake Library 的資料（~/.lumilib、連接埠 8765）。"""
        from unittest import mock

        from lumilib.config import DEFAULTS, default_home

        with mock.patch.dict(os.environ, {"LUMILIB_HOME": "/tmp/should-not-use", "LUMILIB_PORT": "8765"}, clear=False):
            os.environ.pop("REMEMOR_HOME", None)
            os.environ.pop("REMEMOR_PORT", None)
            self.assertEqual(default_home(), Path.home() / ".rememor")
            self.assertEqual(load_config(tempfile.mkdtemp()).port, 8766)
        self.assertEqual(DEFAULTS["port"], 8766)
        with mock.patch.dict(os.environ, {"REMEMOR_HOME": "/Volumes/SSD/.rememor"}):
            self.assertEqual(default_home(), Path("/Volumes/SSD/.rememor"))


if __name__ == "__main__":
    unittest.main()
