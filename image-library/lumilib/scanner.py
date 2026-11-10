"""掃描硬碟：把所有檔案登錄進目錄，照片與影片另外登錄進圖庫。

- 目錄：每個資料夾（含空資料夾）、每個檔案（所有類型）都記下名稱、大小、日期與類型，硬碟拔掉後仍可瀏覽。
  一般檔案只讀檔案系統的資訊（不開啟檔案），所以很快；照片與影片另外讀取拍攝資訊並產生縮圖。
- 只讀不寫：只讀取硬碟；縮圖與資料庫都存在目錄資料庫所在的位置，不在硬碟上建立任何東西。
- 拔掉硬碟不會誤判：只有「確實列出了資料夾內容、而且沒看到」的檔案才標成遺失。
  掃描中途硬碟消失時，還沒寫入資料庫的部分全部放棄，已經存好的紀錄保持原樣。
- 可中斷、可接續：每處理完一個資料夾就記下「這一輪已完成」；中途拔掉、按停止或關閉 App，
  下次掃描同一個資料夾來源時，跳過已完成的資料夾，從還沒完成的地方繼續。
- 認得硬碟：用系統的硬碟編號辨識（見 volumes.py）。同一個位置換成另一顆硬碟時不掃描，
  硬碟改名、掛載位置改變時自動找到新位置。
- 搬移偵測只在同一顆硬碟內：檔案在同一顆硬碟換資料夾或改名，用內容指紋找回原紀錄，分析與相簿都保留；
  其他硬碟上一樣的檔案是「備份」，是另一筆紀錄（內容相同時直接沿用已完成的分析）。
- 中繼資料以 exiftool 一批一批讀取，大量照片也不會太慢。
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import db, filetypes, volumes
from .config import Config
from .media import MediaError, load_image, media_kind, read_metadata_batch, write_thumbnail

# 系統與垃圾桶資料夾不掃（以點開頭的隱藏資料夾也不掃）
SKIP_DIRS = {
    "$recycle.bin", "system volume information", "@eadir", "#recycle", "node_modules",
    "__pycache__", ".thumbnails", ".trash", ".trashes", ".spotlight-v100", ".fseventsd",
    ".documentrevisions-v100", ".temporaryitems",
}

ANALYSIS_FIELDS = (
    "analyzed_at", "model", "description", "tags", "objects", "scene",
    "ocr_text", "error", "embedding", "embed_model",
)
RESET_FIELDS = ANALYSIS_FIELDS + ("faces_at", "faces_model", "clip", "clip_model", "place", "place_en", "country")

_CHUNK = 64 * 1024
BATCH = 48  # 一次交給 exiftool 讀取的照片數
COMMIT_ROWS = 2000  # 累積多少筆變更就寫入資料庫
COMMIT_SECONDS = 2.0  # 或每隔幾秒寫入一次（拔掉硬碟時最多只會重做這段時間的工作）
MEDIA_KINDS = ("photo", "raw", "video")  # 這些檔案另外記在圖庫（images），遺失與搬移以圖庫為準


@dataclass
class ScanResult:
    root: str
    offline: bool = False  # 開始掃描時硬碟沒接上
    other_drive: bool = False  # 這個位置現在接的是另一顆硬碟，沒有掃描
    interrupted: bool = False  # 掃描中途硬碟被拔掉，下次接上會從中斷處繼續
    stopped: bool = False  # 使用者按了停止，下次會從中斷處繼續
    resumed: bool = False  # 這次是接著上次沒掃完的地方繼續
    # 照片與影片（圖庫）
    added: int = 0
    updated: int = 0
    moved: int = 0
    reused: int = 0
    unchanged: int = 0
    # 目錄（所有檔案）
    files: int = 0  # 這次檢查了幾個檔案
    files_added: int = 0
    folders: int = 0  # 這次處理了幾個資料夾
    missing: int = 0  # 這次新標成遺失的檔案：照片與影片（搬到同一顆硬碟其他地方的不算）＋其他檔案
    errors: list[str] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        return not (self.offline or self.interrupted or self.stopped)


class _Unplugged(Exception):
    """掃描中途硬碟消失。"""


class _Stopped(Exception):
    """使用者要求停止。"""


def fingerprint(path: Path, size: int) -> str:
    """檔案大小 + 開頭與結尾各 64KB 的雜湊，大檔也很快。用來認出搬移過的照片；不能單獨作為刪除依據。"""
    h = hashlib.blake2b(digest_size=16)
    h.update(size.to_bytes(8, "little"))
    with open(path, "rb") as fh:
        if size <= _CHUNK * 2:
            h.update(fh.read())
        else:
            h.update(fh.read(_CHUNK))
            fh.seek(-_CHUNK, os.SEEK_END)
            h.update(fh.read(_CHUNK))
    return h.hexdigest()


def _root_online(conn: sqlite3.Connection, root_id: int) -> bool:
    row = conn.execute("SELECT path FROM roots WHERE id = ?", (root_id,)).fetchone()
    return row is not None and Path(row["path"]).is_dir()


def _find_moved(conn: sqlite3.Connection, fp: str, size: int, root_id: int, drive_id: int | None) -> sqlite3.Row | None:
    """找出搬到這裡的原紀錄：只在同一顆硬碟（不知道是哪顆硬碟時只在同一個資料夾來源）裡找。"""
    if drive_id is not None:
        where, args = "i.root_id IN (SELECT id FROM roots WHERE drive_id = ?)", [drive_id]
    else:
        where, args = "i.root_id = ?", [root_id]
    for row in conn.execute(
        f"SELECT i.* FROM images i WHERE i.fingerprint = ? AND i.size = ? AND {where} "
        "ORDER BY i.status = 'missing' DESC, i.id", (fp, size, *args)
    ):
        if row["status"] == "missing":
            return row
        if _root_online(conn, row["root_id"]) and not db.absolute_path(conn, row).exists():
            return row
    return None


def _meta_values(meta: dict) -> list:
    values = []
    for key in db.META_FIELDS:
        value = meta.get(key)
        if key == "keywords":
            value = json.dumps(value, ensure_ascii=False) if value else None
        values.append(value)
    return values


def make_thumbnail(cfg: Config, path: Path, kind: tuple[str, bool], fp: str, meta: dict) -> str | None:
    try:
        img = load_image(path, kind[0], kind[1], cfg.thumb_size * 2, meta.get("duration"), meta.get("orientation"))
        write_thumbnail(img, cfg.thumbs_dir, fp, cfg.thumb_size)
        if not meta.get("width") and img:  # 沒有尺寸資訊時用縮圖比例
            meta["width"], meta["height"] = img.width, img.height
        return None
    except MediaError as exc:
        return str(exc)


@dataclass
class _Pending:
    path: Path
    rel: str
    size: int
    mtime: float
    fp: str
    kind: tuple[str, bool]
    row: sqlite3.Row | None  # 同一路徑既有紀錄（內容被替換）
    file_id: int | None = None


def _process_batch(conn: sqlite3.Connection, cfg: Config, root: sqlite3.Row, batch: list[_Pending],
                   result: ScanResult, now: str) -> None:
    """讀取一批照片的拍攝資訊、產生縮圖並寫入圖庫（不在這裡寫入資料庫檔案，由掃描流程決定何時提交）。"""
    metas = read_metadata_batch([p.path for p in batch])
    set_meta = ", ".join(f"{f} = ?" for f in db.META_FIELDS)
    for item in batch:
        meta = metas.get(item.path)
        err = None
        if isinstance(meta, MediaError):
            err, meta = str(meta), {}
        meta = meta or {}
        thumb_err = make_thumbnail(cfg, item.path, item.kind, item.fp, meta)
        err = err or thumb_err
        sort_at = meta.get("taken_at") or db.local_iso(item.mtime)
        values = _meta_values(meta)
        if item.row is not None:
            conn.execute(
                f"""UPDATE images SET size = ?, mtime = ?, fingerprint = ?, media_type = ?, is_raw = ?,
                        sort_at = ?, status = 'ok', last_seen = ?, thumb_ok = ?, {set_meta},
                        {", ".join(f"{f} = NULL" for f in RESET_FIELDS)}
                    WHERE id = ?""",
                (item.size, item.mtime, item.fp, item.kind[0], int(item.kind[1]), sort_at, now,
                 0 if thumb_err else 1, *values, item.row["id"]),
            )
            conn.execute("DELETE FROM faces WHERE image_id = ?", (item.row["id"],))
            image_id = item.row["id"]
            result.updated += 1
        else:
            cur = conn.execute(
                f"""INSERT INTO images (root_id, rel_path, folder, size, mtime, fingerprint, media_type, is_raw,
                        sort_at, status, first_seen, last_seen, thumb_ok, {", ".join(db.META_FIELDS)})
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'ok', ?, ?, ?, {", ".join("?" * len(db.META_FIELDS))})""",
                (root["id"], item.rel, db.folder_of(item.rel), item.size, item.mtime, item.fp, item.kind[0],
                 int(item.kind[1]), sort_at, now, now, 0 if thumb_err else 1, *values),
            )
            image_id = cur.lastrowid
            result.added += 1
            copy = conn.execute(
                "SELECT * FROM images WHERE fingerprint = ? AND size = ? AND analyzed_at IS NOT NULL AND id != ? LIMIT 1",
                (item.fp, item.size, image_id),
            ).fetchone()
            if copy is not None and not err:
                conn.execute(
                    f"UPDATE images SET {', '.join(f'{f} = ?' for f in ANALYSIS_FIELDS)} WHERE id = ?",
                    (*(copy[f] for f in ANALYSIS_FIELDS), image_id),
                )
                result.reused += 1
        if err:
            conn.execute("UPDATE images SET error = ? WHERE id = ?", (err, image_id))
            result.errors.append(f"{item.rel}: {err}")
        if item.file_id is not None:
            conn.execute("UPDATE files SET image_id = ? WHERE id = ?", (image_id, item.file_id))
        db.refresh_search_text(conn, image_id)


def _like_prefix(path: str) -> str:
    return path.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "/%"


# ---- 硬碟 ---------------------------------------------------------------------

def _locate(conn: sqlite3.Connection, root: sqlite3.Row) -> sqlite3.Row:
    """資料夾來源不在原本的位置時，依硬碟編號找出硬碟現在掛在哪裡（例如硬碟改了名稱）。"""
    if Path(root["path"]).is_dir() or not root["drive_id"]:
        return root
    drive = conn.execute("SELECT uuid FROM drives WHERE id = ?", (root["drive_id"],)).fetchone()
    mount = volumes.find_mount(drive["uuid"]) if drive else None
    if mount is None:
        return root
    rel = root["drive_rel"] or ""
    new_path = mount.joinpath(*[p for p in rel.split("/") if p]) if rel else mount
    if not new_path.is_dir():
        return root
    conn.execute("UPDATE roots SET path = ? WHERE id = ?", (str(new_path), root["id"]))
    conn.commit()
    return db.get_root(conn, root["id"])


def _attach_drive(conn: sqlite3.Connection, root: sqlite3.Row, root_path: Path, now: str) -> tuple[int | None, bool]:
    """記錄這個資料夾來源在哪一顆硬碟上。回傳 (drive_id, 是不是原本那顆硬碟)。"""
    info = volumes.volume_info(root_path)
    if not info:
        return root["drive_id"], True
    key = volumes.drive_key(info)
    if root["drive_id"]:
        old = conn.execute("SELECT id, key FROM drives WHERE id = ?", (root["drive_id"],)).fetchone()
        if old is not None and old["key"] != key:
            return old["id"], False
    row = conn.execute("SELECT id FROM drives WHERE key = ?", (key,)).fetchone()
    values = (info.get("uuid"), info.get("name") or "", info.get("fs_type"), info.get("capacity"),
              1 if info.get("read_only") else 0, info.get("mount"), now)
    if row is not None:
        drive_id = row["id"]
        conn.execute("UPDATE drives SET uuid = ?, name = ?, fs_type = ?, capacity = ?, read_only = ?, mount_path = ?, "
                     "last_seen = ? WHERE id = ?", (*values, drive_id))
    else:
        drive_id = conn.execute(
            "INSERT INTO drives (key, uuid, name, fs_type, capacity, read_only, mount_path, last_seen, first_seen) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (key, *values, now)).lastrowid
    try:
        rel = root_path.resolve().relative_to(Path(info["mount"]).resolve()).as_posix()
    except (ValueError, OSError, KeyError, TypeError):
        rel = None
    conn.execute("UPDATE roots SET drive_id = ?, drive_rel = ? WHERE id = ?",
                 (drive_id, "" if rel == "." else rel, root["id"]))
    return drive_id, True


# ---- 掃描一個資料夾來源 ------------------------------------------------------------

class _Scan:
    def __init__(self, conn, cfg: Config, root, root_path: Path, drive_id, gen: int, now: str,
                 result: ScanResult, progress, stop):
        self.conn, self.cfg, self.root, self.root_path = conn, cfg, root, root_path
        self.drive_id, self.gen, self.now, self.result = drive_id, gen, now, result
        self.progress, self.stop = progress, stop
        self.batch: list[_Pending] = []
        self.missing_ids: set[int] = set()  # 這次標成遺失的照片；之後發現只是搬家時要扣回來
        self.pending = 0
        self.last_commit = time.monotonic()
        self.last_report = 0.0
        home = cfg.home.resolve() if cfg.home.exists() else None
        self.exclude = str(home) if home else None

    # ---- 共用 ----
    def online(self) -> bool:
        return self.root_path.is_dir()

    def check_online(self) -> None:
        if not self.online():
            raise _Unplugged()

    def check_stop(self) -> None:
        if self.stop is not None and self.stop.is_set():
            raise _Stopped()

    def flush(self) -> None:
        if self.batch:
            batch, self.batch = self.batch, []
            _process_batch(self.conn, self.cfg, self.root, batch, self.result, self.now)
            self.pending += len(batch)
            # 讀取這批照片時硬碟被拔掉，結果不可信：整批放棄
            self.check_online()

    def commit(self) -> None:
        self.flush()
        self.conn.commit()
        self.pending = 0
        self.last_commit = time.monotonic()

    def maybe_commit(self) -> None:
        if self.pending >= COMMIT_ROWS or (self.pending and time.monotonic() - self.last_commit >= COMMIT_SECONDS):
            self.commit()

    def report(self, force: bool = False) -> None:
        now = time.monotonic()
        if self.progress and (force or now - self.last_report >= 1.0):
            self.last_report = now
            r = self.result
            self.progress(f"{self.root['name']}：已檢查 {r.files:,} 個檔案、{r.folders:,} 個資料夾，新增 {r.files_added:,} 個")

    # ---- 資料夾 ----
    def ensure_folder(self, parent_id, rel: str, name: str) -> tuple[int, int]:
        """回傳 (folder_id, scan_gen)。"""
        row = self.conn.execute("SELECT id, status, scan_gen FROM folders WHERE root_id = ? AND path = ?",
                                (self.root["id"], rel)).fetchone()
        if row is not None:
            if row["status"] != "ok":
                self.conn.execute("UPDATE folders SET status = 'ok', last_seen = ? WHERE id = ?", (self.now, row["id"]))
                self.pending += 1
            return row["id"], row["scan_gen"]
        cur = self.conn.execute(
            "INSERT INTO folders (root_id, parent_id, path, name, first_seen, last_seen) VALUES (?, ?, ?, ?, ?, ?)",
            (self.root["id"], parent_id, rel, name, self.now, self.now))
        self.pending += 1
        return cur.lastrowid, 0

    def mark_subtree_missing(self, rel: str) -> None:
        """整個資料夾（含子資料夾）不見了：資料夾、檔案、照片都標成遺失。"""
        conn, rid, like = self.conn, self.root["id"], _like_prefix(rel)
        sub = "SELECT id FROM folders WHERE root_id = ? AND (path = ? OR path LIKE ? ESCAPE '\\')"
        others = conn.execute(f"SELECT COUNT(*) FROM files WHERE status = 'ok' AND kind NOT IN {MEDIA_KINDS} "
                              f"AND folder_id IN ({sub})", (rid, rel, like)).fetchone()[0]
        n = conn.execute(f"UPDATE files SET status = 'missing' WHERE status = 'ok' AND folder_id IN ({sub})",
                         (rid, rel, like)).rowcount
        conn.execute(f"UPDATE folders SET status = 'missing' WHERE status = 'ok' AND id IN ({sub})", (rid, rel, like))
        ids = [r[0] for r in conn.execute("SELECT id FROM images WHERE root_id = ? AND status = 'ok' "
                                          "AND (folder = ? OR folder LIKE ? ESCAPE '\\')", (rid, rel, like))]
        for start in range(0, len(ids), 500):
            chunk = ids[start:start + 500]
            conn.execute(f"UPDATE images SET status = 'missing' WHERE id IN ({','.join('?' * len(chunk))})", chunk)
        self.missing_ids.update(ids)
        self.result.missing += others + len(ids)
        self.pending += n + len(ids) + 1

    def package_size(self, path: str) -> int:
        """套件（.app、照片圖庫…）裡所有檔案的總大小。"""
        total = 0
        stack = [path]
        while stack:
            current = stack.pop()
            try:
                with os.scandir(current) as it:
                    entries = list(it)
            except OSError:
                self.check_online()
                continue
            for e in entries:
                try:
                    if e.is_dir(follow_symlinks=False):
                        stack.append(e.path)
                    elif e.is_file(follow_symlinks=False):
                        total += e.stat(follow_symlinks=False).st_size
                except OSError:
                    self.check_online()
        return total

    def process_folder(self, folder_id: int, rel: str, done_gen: int) -> list[tuple[int, str, int]]:
        """處理一個資料夾；回傳子資料夾 [(id, 相對路徑, scan_gen)]。"""
        conn = self.conn
        if done_gen == self.gen:  # 這一輪已經處理過（上次掃描中斷前）：直接往下走
            return [(r["id"], r["path"], r["scan_gen"]) for r in conn.execute(
                "SELECT id, path, scan_gen FROM folders WHERE parent_id = ? AND status = 'ok' ORDER BY name", (folder_id,))]
        abs_path = self.root_path.joinpath(*rel.split("/")) if rel else self.root_path
        abs_str = str(abs_path)
        try:
            with os.scandir(abs_path) as it:
                entries = list(it)
            dir_mtime = os.stat(abs_path).st_mtime
        except OSError as exc:
            self.check_online()
            self.result.errors.append(f"{rel or '（最上層）'}：無法讀取資料夾（{exc.strerror or exc}）")
            return []  # 讀不到的資料夾：保留原本的紀錄，不判定遺失

        dirs, files, packages = [], [], []
        for e in entries:
            name = e.name
            if name.startswith("."):
                continue
            try:
                if e.is_dir(follow_symlinks=False):
                    low = name.lower()
                    if low in SKIP_DIRS or (self.exclude and os.path.join(abs_str, name) == self.exclude):
                        continue
                    (packages if filetypes.is_package(name) else dirs).append(name)
                elif e.is_file(follow_symlinks=False):
                    files.append(name)
            except OSError:
                self.check_online()
        self.result.folders += 1

        # ---- 檔案 ----
        existing = {r["name"]: r for r in conn.execute(
            "SELECT id, name, size, mtime, status, kind FROM files WHERE folder_id = ?", (folder_id,))}
        listed = set(files) | set(packages)
        media: list[tuple[str, int, os.stat_result]] = []
        for i, name in enumerate(sorted(files)):
            if i % 200 == 199:
                self.check_stop()
                self.maybe_commit()
            full = os.path.join(abs_str, name)
            try:
                st = os.stat(full, follow_symlinks=False)
            except OSError as exc:
                self.check_online()
                self.result.errors.append(f"{rel + '/' if rel else ''}{name}：無法讀取（{exc.strerror or exc}）")
                continue
            file_id = self.upsert_file(folder_id, name, filetypes.kind_of(name), st.st_size, st.st_mtime,
                                       getattr(st, "st_birthtime", None), existing.get(name))
            self.result.files += 1
            if media_kind(name):
                media.append((name, file_id, st))
            self.report()
        for name in sorted(packages):
            full = os.path.join(abs_str, name)
            rec = existing.get(name)
            try:
                st = os.stat(full, follow_symlinks=False)
            except OSError:
                self.check_online()
                continue
            if rec is not None and rec["mtime"] == st.st_mtime and rec["status"] == "ok":
                size = rec["size"]  # 套件沒變就不重算大小（照片圖庫可能有幾十萬個檔案）
            else:
                size = self.package_size(full)
            self.upsert_file(folder_id, name, filetypes.package_kind(name), size, st.st_mtime,
                             getattr(st, "st_birthtime", None), rec)
            self.result.files += 1

        gone = [r for n, r in existing.items() if n not in listed and r["status"] == "ok"]
        for start in range(0, len(gone), 500):
            chunk = [r["id"] for r in gone[start:start + 500]]
            conn.execute(f"UPDATE files SET status = 'missing' WHERE id IN ({','.join('?' * len(chunk))})", chunk)
        self.result.missing += sum(1 for r in gone if r["kind"] not in MEDIA_KINDS)  # 照片與影片在下面另外算
        self.pending += len(gone)

        # ---- 照片與影片（圖庫） ----
        self.process_media(rel, abs_path, media, listed)

        # ---- 子資料夾 ----
        known = {r["name"]: r for r in conn.execute(
            "SELECT id, name, status FROM folders WHERE parent_id = ?", (folder_id,))}
        children = []
        for name in sorted(dirs):
            child_rel = f"{rel}/{name}" if rel else name
            cid, cgen = self.ensure_folder(folder_id, child_rel, name)
            children.append((cid, child_rel, cgen))
        for name, r in known.items():
            if name not in dirs and r["status"] == "ok":
                self.mark_subtree_missing(f"{rel}/{name}" if rel else name)

        conn.execute("UPDATE folders SET scan_gen = ?, mtime = ?, status = 'ok', last_seen = ? WHERE id = ?",
                     (self.gen, dir_mtime, self.now, folder_id))
        self.pending += 1
        return children

    def upsert_file(self, folder_id, name, kind, size, mtime, ctime, rec) -> int:
        conn = self.conn
        if rec is not None:
            if rec["size"] == size and rec["mtime"] == mtime:
                if rec["status"] != "ok":
                    conn.execute("UPDATE files SET status = 'ok', last_seen = ? WHERE id = ?", (self.now, rec["id"]))
                    self.pending += 1
                return rec["id"]
            conn.execute("UPDATE files SET size = ?, mtime = ?, ctime = ?, kind = ?, status = 'ok', last_seen = ? WHERE id = ?",
                         (size, mtime, ctime, kind, self.now, rec["id"]))
            self.pending += 1
            return rec["id"]
        cur = conn.execute(
            "INSERT INTO files (root_id, folder_id, name, ext, kind, size, mtime, ctime, first_seen, last_seen) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (self.root["id"], folder_id, name, filetypes.ext_of(name), kind, size, mtime, ctime, self.now, self.now))
        self.result.files_added += 1
        self.pending += 1
        return cur.lastrowid

    def process_media(self, rel: str, abs_path: Path, media: list, listed: set[str]) -> None:
        conn, root, result, now = self.conn, self.root, self.result, self.now
        existing = {r["rel_path"]: r for r in conn.execute(
            "SELECT * FROM images WHERE root_id = ? AND folder = ?", (root["id"], rel))}
        for name, file_id, st in media:
            path = abs_path / name
            item_rel = f"{rel}/{name}" if rel else name
            size, mtime = st.st_size, st.st_mtime
            kind = media_kind(name)
            row = existing.get(item_rel)
            if row is not None and row["size"] == size and row["mtime"] == mtime:
                if row["status"] != "ok":
                    conn.execute("UPDATE images SET status = 'ok', last_seen = ? WHERE id = ?", (now, row["id"]))
                    result.updated += 1
                else:
                    result.unchanged += 1
                conn.execute("UPDATE files SET image_id = ? WHERE id = ? AND image_id IS NOT ?", (row["id"], file_id, row["id"]))
                continue
            try:
                fp = fingerprint(path, size)
            except OSError as exc:
                self.check_online()
                result.errors.append(f"{item_rel}: {exc}")
                continue
            self.pending += 1
            if row is not None and row["fingerprint"] == fp:
                conn.execute("UPDATE images SET mtime = ?, status = 'ok', last_seen = ? WHERE id = ?", (mtime, now, row["id"]))
                conn.execute("UPDATE files SET image_id = ? WHERE id = ?", (row["id"], file_id))
                result.unchanged += 1
            elif row is not None:
                self.batch.append(_Pending(path, item_rel, size, mtime, fp, kind, row, file_id))
            else:
                moved = _find_moved(conn, fp, size, root["id"], self.drive_id)
                if moved is not None:
                    conn.execute(
                        "UPDATE images SET root_id = ?, rel_path = ?, folder = ?, mtime = ?, status = 'ok', last_seen = ? WHERE id = ?",
                        (root["id"], item_rel, rel, mtime, now, moved["id"]),
                    )
                    conn.execute("UPDATE files SET image_id = ? WHERE id = ?", (moved["id"], file_id))
                    db.refresh_search_text(conn, moved["id"])
                    result.moved += 1
                    if moved["id"] in self.missing_ids:  # 剛才算成遺失，其實是搬家
                        self.missing_ids.discard(moved["id"])
                        result.missing -= 1
                    if moved["root_id"] == root["id"]:  # 同一個資料夾裡改名：舊名稱那筆已經搬走了
                        existing.pop(moved["rel_path"], None)
                else:
                    self.batch.append(_Pending(path, item_rel, size, mtime, fp, kind, None, file_id))
            if len(self.batch) >= BATCH:
                self.flush()
        # 這個資料夾裡已經不在的照片（資料夾確實列出來了、卻沒看到）
        for item_rel, row in existing.items():
            if row["status"] == "ok" and item_rel.rsplit("/", 1)[-1] not in listed:
                conn.execute("UPDATE images SET status = 'missing' WHERE id = ?", (row["id"],))
                self.missing_ids.add(row["id"])
                result.missing += 1
                self.pending += 1

    def run(self) -> None:
        root_id, gen = self.ensure_folder(None, "", self.root["name"])
        stack = [(root_id, "", gen)]
        while stack:
            self.check_stop()
            folder_id, rel, done_gen = stack.pop()
            children = self.process_folder(folder_id, rel, done_gen)
            stack.extend(reversed(children))
            self.maybe_commit()
        self.commit()


def scan_root(
    conn: sqlite3.Connection,
    cfg: Config,
    root: sqlite3.Row,
    progress: Callable[[str], None] | None = None,
    stop=None,
) -> ScanResult:
    result = ScanResult(root=root["name"])
    root = _locate(conn, root)
    root_path = Path(root["path"])
    if not root_path.is_dir():
        result.offline = True
        return result
    now = db.now_iso()
    drive_id, same_drive = _attach_drive(conn, root, root_path, now)
    if not same_drive:
        conn.rollback()
        result.offline = result.other_drive = True
        return result

    # 這一輪的編號：上次沒掃完就沿用（跳過已完成的資料夾），否則開始新的一輪
    if root["scan_state"] == "partial" and root["scan_gen"]:
        gen = root["scan_gen"]
        result.resumed = True
    else:
        gen = (root["scan_gen"] or 0) + 1
    conn.execute("UPDATE roots SET scan_gen = ?, scan_state = 'partial' WHERE id = ?", (gen, root["id"]))
    conn.commit()
    root = db.get_root(conn, root["id"])

    scan = _Scan(conn, cfg, root, root_path, drive_id, gen, now, result, progress, stop)
    try:
        scan.run()
    except _Unplugged:
        conn.rollback()  # 放棄還沒寫入的部分；已寫入的資料夾下次會跳過
        result.interrupted = True
    except _Stopped:
        try:
            scan.commit()  # 停止時保留已做完的工作
        except _Unplugged:
            conn.rollback()
            result.interrupted = True
        result.stopped = not result.interrupted
    except BaseException:
        conn.rollback()
        raise
    if result.complete:
        conn.execute("UPDATE roots SET scan_state = 'done', last_scan = ? WHERE id = ?", (now, root["id"]))
    from .catalog import update_folder_totals

    update_folder_totals(conn, root["id"])
    conn.commit()
    scan.report(force=True)
    return result


def scan_all(conn, cfg, root_names=None, progress=None, stop=None) -> list[ScanResult]:
    roots = db.list_roots(conn)
    if root_names:
        wanted = {str(n) for n in root_names}
        roots = [r for r in roots if r["name"] in wanted or str(r["id"]) in wanted]
    results = []
    for root in roots:
        if stop is not None and stop.is_set():
            break
        results.append(scan_root(conn, cfg, root, progress, stop))
    from .organize import rebuild_stacks
    from .places import geocode_images

    geocode_images(conn, progress)
    rebuild_stacks(conn, cfg)
    return results


def describe(r: ScanResult) -> str:
    """一般人看得懂的掃描結果。"""
    if r.other_drive:
        return f"{r.root}：這個位置現在接的是另一顆硬碟，沒有掃描（避免把兩顆硬碟的內容混在一起）"
    if r.offline:
        return f"{r.root}：未連接，已略過"
    parts = [f"新增 {r.files_added:,} 個檔案"]
    if r.added:
        parts.append(f"其中照片與影片 {r.added:,} 個")
    if r.updated:
        parts.append(f"更新 {r.updated:,}")
    if r.moved:
        parts.append(f"搬移 {r.moved:,}")
    parts.append(f"遺失 {r.missing:,}")
    text = f"{r.root}：" + "、".join(parts)
    if r.interrupted:
        text += "；硬碟在掃描中途被拔掉，下次接上會從中斷處繼續"
    elif r.stopped:
        text += "；已停止，下次掃描會從中斷處繼續"
    return text
