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
        # macOS 的暫存資料夾 /var/folders 其實是 /private/var/folders 的捷徑；
        # 加入資料夾時程式會換成真正的路徑，所以測試也用真正的路徑來模擬「拔掉」與「停止」
        self.tmp = Path(tempfile.mkdtemp()).resolve()
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


class DrivesApiTests(CatalogFixture):
    """側邊欄用的硬碟清單與類型統計。"""

    def test_drive_list_shows_offline_drives_with_totals(self):
        from lumilib.catalog import drives_overview

        with separate_drives(self.drive):
            scan_all(self.conn, self.cfg)
        (d,) = drives_overview(self.conn)
        self.assertEqual((d["name"], d["online"], d["files"], d["capacity"], d["complete"]),
                         ("Archive", True, 6, 4_000_000_000_000, True))
        self.assertIsNotNone(d["last_scan"])
        self.drive.rename(self.tmp / "unplugged")  # 拔掉之後仍然列出，只是變成未連線
        (d,) = drives_overview(self.conn)
        self.assertEqual((d["online"], d["files"], d["roots"][0]["id"]), (False, 6, self.root["id"]))

    def test_two_folders_on_one_drive_are_one_entry(self):
        from lumilib.catalog import drives_overview

        disk = self.tmp / "Disk"  # 同一顆硬碟上加入兩個不同的資料夾
        for name in ("甲", "乙"):
            (disk / name).mkdir(parents=True)
            (disk / name / "a.txt").write_text("hello", encoding="utf-8")
            db.add_root(self.conn, disk / name, name)
        with separate_drives(self.drive, disk):
            scan_all(self.conn, self.cfg)
        d = next(x for x in drives_overview(self.conn) if x["name"] == "Disk")
        self.assertEqual((sorted(r["name"] for r in d["roots"]), d["files"]), (["乙", "甲"], 2))
        self.assertEqual(len(drives_overview(self.conn)), 2)

    def test_unscanned_folder_is_listed_without_drive(self):
        from lumilib.catalog import drives_overview

        (d,) = drives_overview(self.conn)  # 還沒掃描過：沒有硬碟資料，也要列出來
        self.assertEqual((d["key"], d["drive_id"], d["files"], d["complete"]), (f"root:{self.root['id']}", None, 0, False))

    def test_scanning_progress(self):
        from lumilib.catalog import drives_overview

        (d,) = drives_overview(self.conn, {"root_id": self.root["id"], "files": 3})
        self.assertEqual((d["scanning"], d["progress"]), (True, None))  # 第一次掃描：不知道總數，不給百分比
        scan_all(self.conn, self.cfg)
        (d,) = drives_overview(self.conn, {"root_id": self.root["id"], "files": 3})
        self.assertEqual((d["scanning"], d["progress"]), (True, 0.5))
        (d,) = drives_overview(self.conn, {"root_id": self.root["id"], "files": 60})
        self.assertEqual(d["progress"], 0.99)  # 檔案變多時不會超過 100%

    def test_scan_job_reports_which_root(self):
        seen = []

        def progress(message, scan=None):
            seen.append(scan)

        progress.wants_scan = True
        scan_all(self.conn, self.cfg, progress=progress)
        self.assertIn({"root_id": self.root["id"], "files": 6}, seen)
        plain = []
        scan_all(self.conn, self.cfg, progress=plain.append)  # 只收文字的呼叫方式（指令列）照舊
        self.assertTrue(all(isinstance(m, str) for m in plain))

    def test_detail_has_kinds_per_drive_and_new_volumes(self):
        from lumilib import volumes as vol
        from lumilib.catalog import drives_overview, new_volumes

        with separate_drives(self.drive):
            scan_all(self.conn, self.cfg)
        (d,) = drives_overview(self.conn, detail=True)
        kinds = {k["kind"]: (k["files"], k["bytes"]) for k in d["kinds"]}
        self.assertEqual((kinds["audio"], kinds["archive"]), ((1, 3000), (1, 500)))
        self.assertEqual(sum(k["files"] for k in d["kinds"]), d["files"])
        plan = " ".join(r[3] for r in self.conn.execute(
            "EXPLAIN QUERY PLAN SELECT root_id, kind, COUNT(*), SUM(size) FROM files INDEXED BY idx_files_root_kind WHERE status = 'ok' GROUP BY root_id, kind"))
        self.assertIn("COVERING INDEX", plan)
        # 已接上但還沒加入目錄的硬碟：列出來等使用者按「加入目錄」，不會自動加入或掃描
        other = self.tmp / "NewDisk"
        other.mkdir()
        real = vol.mounted_volumes
        vol.mounted_volumes = lambda: [Path("/"), self.drive, other]
        try:
            with separate_drives(self.drive, other):
                self.assertEqual([(v["name"], v["path"]) for v in new_volumes(self.conn)], [("NewDisk", str(other))])
        finally:
            vol.mounted_volumes = real
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM roots").fetchone()[0], 1)

    def test_kinds_and_api(self):
        from fastapi.testclient import TestClient

        from lumilib.catalog import kinds_overview
        from lumilib.server import create_app

        scan_all(self.conn, self.cfg)
        kinds = {k["kind"]: (k["files"], k["bytes"]) for k in kinds_overview(self.conn)}
        self.assertEqual(kinds["audio"], (1, 3000))
        self.assertEqual(kinds["archive"], (1, 500))
        self.assertEqual(kinds["document"][0], 2)
        self.assertEqual(kinds["video"], (0, 0))  # 沒有的類型也回傳 0，側邊欄的順序才固定
        with TestClient(create_app(self.cfg, start_jobs_on_boot=False), base_url="http://127.0.0.1:8766",
                        client=("127.0.0.1", 1)) as c:
            data = c.get("/api/drives").json()
            self.assertEqual((len(data["drives"]), data["drives"][0]["scanning"]), (1, False))
            self.assertEqual(len(data["kinds"]), 8)


class ItemsPageTests(CatalogFixture):
    """列表與圖像檢視用的分段讀取。"""

    def setUp(self):
        super().setUp()
        big = self.drive / "很多檔案"
        big.mkdir()
        for i in range(120):
            (big / f"file{i:03d}.txt").write_bytes(b"x" * (i + 1))
        scan_all(self.conn, self.cfg)

    def page(self, **kw):
        from lumilib.catalog import items_page

        return items_page(self.conn, **kw)

    def test_folders_first_then_files_in_pages(self):
        top = self.page(root_id=self.root["id"])
        self.assertEqual((top["total"], top["folders"]), (6, 4))
        self.assertEqual([i["type"] for i in top["items"]], ["folder"] * 4 + ["file"] * 2)
        self.assertEqual({i["name"] for i in top["items"] if i["type"] == "file"}, {"備份.zip", "Photos Library.photoslibrary"})
        # 一段一段拿，接起來和一次拿完一樣，而且跨過「資料夾 → 檔案」的交界
        joined = self.page(root_id=self.root["id"], offset=0, limit=3)["items"] + self.page(root_id=self.root["id"], offset=3, limit=3)["items"]
        self.assertEqual([i["name"] for i in joined], [i["name"] for i in top["items"]])

    def test_window_in_the_middle_of_a_big_folder(self):
        p = self.page(root_id=self.root["id"], path="很多檔案", offset=50, limit=10)
        self.assertEqual((p["total"], [i["name"] for i in p["items"]]), (120, [f"file{i:03d}.txt" for i in range(50, 60)]))
        self.assertEqual(p["items"][0]["path"], "很多檔案/file050.txt")

    def test_sort_by_size_and_descending(self):
        p = self.page(root_id=self.root["id"], path="很多檔案", sort="size", desc=True, limit=3)
        self.assertEqual([i["size"] for i in p["items"]], [120, 119, 118])
        folders = self.page(root_id=self.root["id"], sort="size", desc=True)["items"]
        self.assertEqual(folders[0]["name"], "很多檔案")  # 資料夾依「含子資料夾的總大小」排

    def test_kind_filter_across_drives(self):
        docs = self.page(kind="document", limit=500)
        self.assertEqual(docs["total"], 122)  # 120 個 txt＋原本的 docx、txt
        self.assertTrue(all(i["kind"] == "document" for i in docs["items"]))
        names = [i["name"].casefold() for i in docs["items"]]
        self.assertEqual(names, sorted(names))
        self.assertEqual(self.page(kind="document", sort="size", desc=True, limit=1)["items"][0]["name"], "自然科報告.docx")
        self.assertEqual(self.page(kind="photo")["total"], 1)
        self.assertIsNone(self.page(kind="nonsense"))

    def test_queries_use_indexes_instead_of_sorting(self):
        plan = " ".join(r[3] for r in self.conn.execute(
            "EXPLAIN QUERY PLAN SELECT id FROM files INDEXED BY idx_files_all_name WHERE status = 'ok' AND kind IN ('photo','raw') "
            "ORDER BY name COLLATE NOCASE LIMIT 50 OFFSET 1000"))
        self.assertNotIn("TEMP B-TREE", plan)
        plan = " ".join(r[3] for r in self.conn.execute(
            "EXPLAIN QUERY PLAN SELECT f.id FROM files f WHERE f.folder_id = 1 AND f.status = 'ok' ORDER BY f.name COLLATE NOCASE, f.id LIMIT 50"))
        self.assertIn("idx_files_folder_name", plan)
        self.assertNotIn("TEMP B-TREE", plan)

    def test_still_browsable_when_unplugged_and_location(self):
        from lumilib.catalog import location_info

        self.drive.rename(self.tmp / "unplugged")
        self.assertEqual(self.page(root_id=self.root["id"], path="音樂")["items"][0]["name"], "song.mp3")
        loc = location_info(self.conn, self.root["id"], "2008 國中/畢業旅行")
        self.assertEqual((loc["root"]["online"], loc["name"], [c["name"] for c in loc["crumbs"]], loc["files"]),
                         (False, "畢業旅行", ["2008 國中", "畢業旅行"], 1))
        self.assertIsNone(location_info(self.conn, self.root["id"], "不存在"))

    def test_items_api(self):
        from fastapi.testclient import TestClient

        from lumilib.server import create_app

        with TestClient(create_app(self.cfg, start_jobs_on_boot=False), base_url="http://127.0.0.1:8766",
                        client=("127.0.0.1", 1)) as c:
            r = c.get("/api/items", params={"root": self.root["id"], "path": "很多檔案", "offset": 100, "limit": 500}).json()
            self.assertEqual((r["total"], len(r["items"])), (120, 20))
            self.assertEqual(c.get("/api/items").status_code, 400)
            self.assertEqual(c.get("/api/items", params={"root": 999}).status_code, 404)
            self.assertEqual(c.get("/api/location", params={"root": self.root["id"]}).json()["name"], "Archive")

    def test_usage_map_two_levels(self):
        from lumilib.catalog import subtree_kinds, usage_map

        u = usage_map(self.conn, self.root["id"])
        self.assertEqual(u["bytes"], self.folder("")["total_bytes"])
        self.assertEqual(sum(b["bytes"] for b in u["children"]), u["bytes"])  # 每一層加起來等於上一層
        blocks = {b.get("name") or b.get("kind") or b["type"]: b for b in u["children"]}
        self.assertEqual(blocks["archive"]["bytes"], 500)  # 直接放在最上層的 備份.zip
        big = blocks["很多檔案"]
        self.assertEqual((big["type"], big["bytes"]), ("folder", sum(range(1, 121))))
        self.assertEqual([(c["type"], c["kind"], c["files"]) for c in big["children"]], [("kind", "document", 120)])
        school = blocks["2008 國中"]
        self.assertEqual(sum(c["bytes"] for c in school["children"]), school["bytes"])
        self.assertIn("畢業旅行", {c.get("name") for c in school["children"]})
        self.assertNotIn("空資料夾", blocks)  # 沒有大小的不畫
        self.assertEqual((big["kind"], blocks["音樂"]["kind"], school["kind"]), ("document", "audio", "document"))  # 主要類型
        self.assertIsNone(usage_map(self.conn, self.root["id"], "不存在"))
        # 太小的合併成「其他」
        (self.drive / "音樂" / "huge.bin").write_bytes(b"0" * 3_000_000)
        scan_all(self.conn, self.cfg)
        u = usage_map(self.conn, self.root["id"])
        rest = [b for b in u["children"] if b["type"] == "rest"]
        self.assertEqual(len(rest), 1)
        self.assertGreater(rest[0]["count"], 1)
        self.assertEqual(sum(b["bytes"] for b in u["children"]), u["bytes"])
        # 資訊欄的類型佔比：整個來源與子資料夾
        whole = {k["kind"]: k["files"] for k in subtree_kinds(self.conn, self.root["id"])}
        self.assertEqual((whole["document"], whole["audio"]), (122, 1))
        sub = {k["kind"]: k["files"] for k in subtree_kinds(self.conn, self.root["id"], "2008 國中")}
        self.assertEqual(sub, {"photo": 1, "document": 2})
        self.assertEqual(sum(k["bytes"] for k in subtree_kinds(self.conn, self.root["id"], "2008 國中")), self.folder("2008 國中")["total_bytes"])

    def test_labels_live_in_the_catalog_only(self):
        from lumilib import ratings
        from lumilib.catalog import labels_overview, set_labels

        before = {p: p.stat().st_mtime_ns for p in self.drive.rglob("*")}
        files = self.files()
        song, photo = files["音樂/song.mp3"], files["2008 國中/畢業旅行/a.jpg"]
        folder = self.folder("音樂")
        self.assertEqual(set_labels(self.conn, [song["id"], photo["id"]], [folder["id"]], "red"), 3)
        self.assertEqual({i["name"] for i in self.page(label="red")["items"]}, {"音樂", "song.mp3", "a.jpg"})
        self.assertEqual(self.page(label="red")["items"][0]["type"], "folder")
        self.assertEqual({x["label"]: x["count"] for x in labels_overview(self.conn)}["red"], 3)
        # 照片在圖庫裡的標籤跟著變；從照片那邊改，檔案目錄也跟著變
        self.assertEqual(self.conn.execute("SELECT label FROM images WHERE id = ?", (photo["image_id"],)).fetchone()[0], "red")
        ratings.update(self.conn, photo["image_id"], label="blue")
        self.assertEqual(self.files()["2008 國中/畢業旅行/a.jpg"]["label"], "blue")
        # 重新掃描後標籤還在；拿掉標籤；不認得的顏色不收
        scan_all(self.conn, self.cfg)
        self.assertEqual(self.files()["音樂/song.mp3"]["label"], "red")
        set_labels(self.conn, [song["id"]], [], None)
        self.assertIsNone(self.files()["音樂/song.mp3"]["label"])
        with self.assertRaises(ValueError):
            set_labels(self.conn, [song["id"]], [], "pink")
        # 硬碟上什麼都沒被改（不寫標籤到檔案，也不建立任何檔案）
        self.assertEqual({p: p.stat().st_mtime_ns for p in self.drive.rglob("*")}, before)
        self.drive.rename(self.tmp / "unplugged")  # 硬碟沒接上也能加標籤
        self.assertEqual(set_labels(self.conn, [song["id"]], [], "green"), 1)

    def test_quick_look_reads_only_previewable_files(self):
        from fastapi.testclient import TestClient

        from lumilib.server import create_app

        (self.drive / "2008 國中" / "big5.txt").write_bytes("繁體中文筆記".encode("big5"))
        with TestClient(create_app(self.cfg, start_jobs_on_boot=False), base_url="http://127.0.0.1:8766",
                        client=("127.0.0.1", 1)) as c:
            rid = self.root["id"]
            self.assertEqual(c.get("/api/items/text", params={"root": rid, "path": "2008 國中/notes.txt"}).json(),
                             {"text": "hello", "truncated": False})
            self.assertEqual(c.get("/api/items/text", params={"root": rid, "path": "2008 國中/big5.txt"}).json()["text"], "繁體中文筆記")
            long = c.get("/api/items/text", params={"root": rid, "path": "很多檔案/file119.txt"}).json()
            self.assertEqual((len(long["text"]), long["truncated"]), (120, False))
            r = c.get("/api/items/raw", params={"root": rid, "path": "音樂/song.mp3"})
            self.assertEqual((r.status_code, r.headers["content-type"], len(r.content)), (200, "audio/mpeg", 3000))
            # 不能直接顯示的類型不送出內容；不能跑到硬碟以外
            self.assertEqual(c.get("/api/items/raw", params={"root": rid, "path": "備份.zip"}).status_code, 415)
            self.assertEqual(c.get("/api/items/text", params={"root": rid, "path": "2008 國中/自然科報告.docx"}).status_code, 415)
            self.assertEqual(c.get("/api/items/text", params={"root": rid, "path": "../home/config.txt"}).status_code, 400)
            self.drive.rename(self.tmp / "unplugged")
            r = c.get("/api/items/raw", params={"root": rid, "path": "音樂/song.mp3"})
            self.assertEqual(r.status_code, 409)
            self.assertIn("Archive", r.text)

    def test_open_item_needs_the_drive_and_stays_inside_it(self):
        from fastapi.testclient import TestClient

        from lumilib import fileops
        from lumilib.server import create_app

        calls, real = [], fileops.reveal
        fileops.reveal = lambda path, select=True: calls.append((Path(path).name, select))
        try:
            with TestClient(create_app(self.cfg, start_jobs_on_boot=False), base_url="http://127.0.0.1:8766",
                            client=("127.0.0.1", 1)) as c:
                body = {"root_id": self.root["id"], "path": "音樂/song.mp3"}
                self.assertEqual(c.post("/api/items/open", json=body).status_code, 200)
                self.assertEqual(c.post("/api/items/open", json={**body, "action": "reveal"}).status_code, 200)
                self.assertEqual(calls, [("song.mp3", False), ("song.mp3", True)])
                self.assertEqual(c.post("/api/items/open", json={**body, "path": "../外面.txt"}).status_code, 400)
                self.drive.rename(self.tmp / "unplugged")  # 硬碟沒接上：說明要接上哪一顆
                r = c.post("/api/items/open", json=body)
                self.assertEqual(r.status_code, 409)
                self.assertIn("Archive", r.text)
                self.assertEqual(len(calls), 2)
        finally:
            fileops.reveal = real


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
