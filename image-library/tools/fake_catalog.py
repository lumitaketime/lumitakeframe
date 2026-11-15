"""產生假的目錄紀錄，用來測試大量檔案時的瀏覽速度（不需要真的硬碟，也不會動到你的資料）。

用法：
    python tools/fake_catalog.py <資料目錄> [檔案總數=1000000] [單一資料夾的檔案數=100000]

會在 <資料目錄> 建立一個全新的 Re'memor 資料庫，裡面有兩顆「沒接上」的假硬碟。
啟動時指定這個資料目錄就能看到：REMEMOR_HOME=<資料目錄> rememor serve
為了安全，資料目錄裡已經有資料庫時不會執行。
"""

from __future__ import annotations

import random
import sys
import time
from pathlib import Path

from lumilib import catalog, db
from lumilib.config import load_config

EXTS = {
    "photo": [".jpg", ".heic", ".png"], "raw": [".cr3", ".arw"], "video": [".mp4", ".mov"], "audio": [".mp3", ".flac"],
    "document": [".pdf", ".docx", ".txt", ".xlsx"], "archive": [".zip", ".dmg"], "other": [".dat", ".bin"],
}
WEIGHTS = {"photo": 40, "raw": 8, "video": 4, "audio": 8, "document": 25, "archive": 1, "other": 14}
SIZES = {"photo": 4e6, "raw": 3e7, "video": 8e8, "audio": 8e6, "document": 3e5, "archive": 2e8, "other": 1e5}
WORDS = ["旅行", "報告", "會議", "家庭", "專案", "備份", "發票", "合約", "scan", "IMG", "DSC", "notes", "draft", "final", "音樂會", "畢業"]


def build(home: Path, total: int, big: int) -> None:
    cfg = load_config(home)
    if Path(cfg.db_path).exists():
        sys.exit(f"{cfg.db_path} 已經存在。請換一個空的資料目錄，避免蓋掉真正的資料。")
    conn = db.connect(cfg.db_path)
    rng = random.Random(7)
    now = db.now_iso()
    kinds = rng.choices(list(WEIGHTS), weights=list(WEIGHTS.values()), k=1000)
    t0 = time.perf_counter()
    remaining = total
    for d, (name, fs, cap) in enumerate([("測試硬碟 A", "apfs", 8e12), ("測試硬碟 B", "exfat", 16e12)]):
        conn.execute("INSERT INTO drives (key, uuid, name, fs_type, capacity, mount_path, first_seen, last_seen) VALUES (?,?,?,?,?,?,?,?)",
                     (f"uuid:FAKE-{d}", f"FAKE-{d}", name, fs, int(cap), f"/Volumes/{name}", now, now))
        drive_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute("INSERT INTO roots (name, path, created_at, last_scan, drive_id, drive_rel, scan_gen, scan_state) VALUES (?,?,?,?,?,?,1,'done')",
                     (name, f"/Volumes/{name}", now, now, drive_id, ""))
        root_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        def folder(parent, path, fname):
            conn.execute("INSERT INTO folders (root_id, parent_id, path, name, mtime, scan_gen, first_seen, last_seen) VALUES (?,?,?,?,?,1,?,?)",
                         (root_id, parent, path, fname, 1.6e9 + rng.random() * 1.5e8, now, now))
            return conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        def fill(folder_id, count, prefix=""):
            rows = []
            for i in range(count):
                kind = kinds[rng.randrange(1000)]
                ext = rng.choice(EXTS[kind])
                fname = f"{prefix}{rng.choice(WORDS)}_{i:06d}{ext}"
                rows.append((root_id, folder_id, fname, ext, kind, int(rng.lognormvariate(0, 1) * SIZES[kind]),
                             1.2e9 + rng.random() * 5.5e8, now, now))
            conn.executemany("INSERT INTO files (root_id, folder_id, name, ext, kind, size, mtime, first_seen, last_seen) "
                             "VALUES (?,?,?,?,?,?,?,?,?)", rows)

        top = folder(None, "", name)
        share = remaining if d == 1 else total // 2
        if d == 0:
            fill(folder(top, f"{big} 個檔案", f"{big} 個檔案"), big)
            share -= big
        years = list(range(2008, 2027))
        per_leaf = max(1, share // (len(years) * 12 * 8))
        for y in years:
            yf = folder(top, str(y), str(y))
            for m in range(1, 13):
                mf = folder(yf, f"{y}/{m:02d} 月", f"{m:02d} 月")
                for k in range(8):
                    word = WORDS[(y + m + k) % len(WORDS)]
                    fill(folder(mf, f"{y}/{m:02d} 月/{word} {k + 1}", f"{word} {k + 1}"), per_leaf)
        conn.commit()
        catalog.update_folder_totals(conn, root_id)
        conn.commit()
        remaining -= total // 2
    n = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
    print(f"建立 {n:,} 個檔案紀錄、{conn.execute('SELECT COUNT(*) FROM folders').fetchone()[0]:,} 個資料夾：{time.perf_counter() - t0:.1f} 秒")
    conn.execute("ANALYZE")
    conn.commit()
    measure(conn, big)
    conn.close()
    size = sum(p.stat().st_size for p in Path(cfg.db_path).parent.glob(Path(cfg.db_path).name + "*"))
    print(f"資料庫 {size / 1e6:.0f} MB：{cfg.db_path}")


def measure(conn, big: int) -> None:
    def ms(fn, times=5):
        t = time.perf_counter()
        for _ in range(times):
            fn()
        return (time.perf_counter() - t) / times * 1000

    path = f"{big} 個檔案"
    page = lambda **kw: (lambda: catalog.items_page(conn, **kw))  # noqa: E731
    print("每次查詢（毫秒）：")
    print(f"  進入 {big:,} 個檔案的資料夾，第一屏：{ms(page(root_id=1, path=path, limit=200)):.1f}")
    print(f"  同一個資料夾，跳到中間：{ms(page(root_id=1, path=path, offset=big // 2, limit=200)):.1f}")
    print(f"  同一個資料夾，依大小排序：{ms(page(root_id=1, path=path, sort='size', desc=True, limit=200)):.1f}")
    print(f"  同一個資料夾，依日期排序：{ms(page(root_id=1, path=path, sort='mtime', limit=200)):.1f}")
    print(f"  一般資料夾：{ms(page(root_id=1, path='2015/06 月', limit=200)):.1f}")
    print(f"  類型「照片」第一屏（跨硬碟）：{ms(page(kind='photo', limit=200)):.1f}")
    total = catalog.items_page(conn, kind="photo", limit=1)["total"]
    print(f"  類型「照片」跳到中間（共 {total:,} 個）：{ms(page(kind='photo', offset=total // 2, limit=200)):.1f}")
    print(f"  類型「照片」捲到最後：{ms(page(kind='photo', offset=total - 200, limit=200)):.1f}")
    print(f"  類型「照片」依大小排序：{ms(page(kind='photo', sort='size', desc=True, limit=200)):.1f}")
    print(f"  類型「影片」依日期排序：{ms(page(kind='video', sort='mtime', desc=True, limit=200)):.1f}")
    print(f"  側邊欄類型統計：{ms(lambda: catalog.kinds_overview(conn)):.1f}；硬碟清單：{ms(lambda: catalog.drives_overview(conn)):.1f}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    build(Path(sys.argv[1]).expanduser(), int(sys.argv[2]) if len(sys.argv) > 2 else 1_000_000,
          int(sys.argv[3]) if len(sys.argv) > 3 else 100_000)
