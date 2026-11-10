"""目錄掃描的效能實測：建立大量假檔案，量第一次掃描、沒有變動的重新掃描、查詢資料夾的時間。

用法（在 image-library 資料夾）：
    python tools/bench_catalog.py 100000 /tmp/bench

會在指定位置建立一個假的「硬碟」（大部分是小文件，加上少量照片），結束後自動刪除。
不會碰到任何真實的硬碟或圖庫資料。
"""

from __future__ import annotations

import random
import shutil
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image  # noqa: E402

from lumilib import catalog, db  # noqa: E402
from lumilib.config import load_config  # noqa: E402
from lumilib.scanner import scan_all  # noqa: E402

EXTS = ["pdf", "docx", "txt", "xlsx", "pptx", "mp3", "flac", "zip", "psd", "dat", "md", "csv"]


def build(drive: Path, total: int, photos: int) -> int:
    rnd = random.Random(1)
    per_folder = 40
    folders = max(1, total // per_folder)
    made = 0
    for i in range(folders):
        d = drive / f"年份 {2005 + i % 20}" / f"專案 {i // 20:04d}" / f"資料夾 {i:05d}"
        d.mkdir(parents=True, exist_ok=True)
        for j in range(per_folder):
            if made >= total:
                break
            (d / f"檔案 {j:03d}.{rnd.choice(EXTS)}").write_bytes(b"x" * rnd.randint(10, 400))
            made += 1
    img = Image.new("RGB", (64, 48), (120, 80, 40))
    for k in range(photos):
        d = drive / "照片" / f"{k // 100:03d}"
        d.mkdir(parents=True, exist_ok=True)
        img.save(d / f"IMG_{k:05d}.jpg", "JPEG", quality=70)
    return made + photos


def main() -> None:
    total = int(sys.argv[1]) if len(sys.argv) > 1 else 100_000
    base = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(tempfile.mkdtemp())
    photos = min(1000, total // 100)
    work = base / "rememor-bench"
    shutil.rmtree(work, ignore_errors=True)
    drive = work / "Drive"
    t = time.perf_counter()
    n = build(drive, total - photos, photos)
    print(f"建立 {n:,} 個測試檔案（其中照片 {photos:,} 張）：{time.perf_counter() - t:.1f} 秒")

    cfg = load_config(work / "home")
    conn = db.connect(cfg.db_path)
    db.add_root(conn, drive, "Bench")

    t = time.perf_counter()
    [res] = scan_all(conn, cfg)
    first = time.perf_counter() - t
    print(f"第一次掃描：{first:.1f} 秒（每秒 {res.files / first:,.0f} 個檔案），"
          f"檔案 {res.files:,}、資料夾 {res.folders:,}、照片 {res.added:,}")

    t = time.perf_counter()
    [res2] = scan_all(conn, cfg)
    print(f"沒有變動的重新掃描：{time.perf_counter() - t:.1f} 秒（新增 {res2.files_added}、遺失 {res2.missing}）")

    t = time.perf_counter()
    catalog.update_folder_totals(conn, 1)
    conn.commit()
    print(f"重新計算資料夾總大小：{time.perf_counter() - t:.2f} 秒")

    path = conn.execute("SELECT path FROM folders WHERE files > 0 ORDER BY id DESC LIMIT 1").fetchone()[0]
    t = time.perf_counter()
    for _ in range(20):
        catalog.folder_listing(conn, 1, path)
        catalog.folder_listing(conn, 1, "")
    print(f"列出資料夾內容：每次 {(time.perf_counter() - t) / 40 * 1000:.1f} 毫秒")

    top = conn.execute("SELECT total_files, total_bytes FROM folders WHERE path = ''").fetchone()
    conn.close()
    size = sum(p.stat().st_size for p in (work / "home").glob("library.db*"))
    print(f"目錄總計 {top[0]:,} 個檔案、{top[1] / 1e6:.1f} MB；資料庫 {size / 1e6:.1f} MB")
    shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
