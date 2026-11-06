"""EXIF 編輯器：一次修改一張或多張照片的拍攝時間、相機、鏡頭、GPS、標題與說明、作者與版權，也能重新命名檔案。

寫入方式（依使用者決定）：
- RAW（CR3、NEF、ARW…）：寫進同名的 .xmp 附屬檔，原始 RAW 不動，Lightroom 讀得到
- JPEG、HEIC、TIFF、PNG、DNG：直接寫進檔案（exiftool 覆蓋原檔，保留修改時間）
- 重新命名：直接改硬碟上的檔名，同名的 .xmp、.aae 一起改；RAW+JPEG 同名雙檔取相同序號
- 影片：目前只支援重新命名

每次套用都會記下原本的值（edit_batches），可以「復原」。
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

from . import db
from .config import Config
from .media import RAW_EXTENSIONS, exiftool

FIELDS = ("taken_at", "tz", "make", "model", "lens", "gps", "title", "caption", "artist", "copyright")
EMBEDDED = {".jpg", ".jpeg", ".heic", ".heif", ".tif", ".tiff", ".png", ".dng", ".webp", ".avif"}


def _target_kind(path: Path, media_type: str) -> str:
    ext = path.suffix.lower()
    if media_type == "video":
        return "video"
    if ext in RAW_EXTENSIONS and ext != ".dng":
        return "sidecar"
    if ext in EMBEDDED:
        return "embedded"
    return "sidecar"


def _exif_time(iso: str) -> str:
    """2024-06-25T18:06:00 → 2024:06:25 18:06:00"""
    return iso[:19].replace("-", ":", 2).replace("T", " ")


def _iso(value) -> str | None:
    """exiftool 的 2024:06:25 18:06:00 → 2024-06-25T18:06:00"""
    if not value or not isinstance(value, str) or len(value) < 19:
        return None
    s = value[:19]
    if s[4] == ":" and s[7] == ":":
        s = s[:4] + "-" + s[5:7] + "-" + s[8:]
    return s.replace(" ", "T")


def _read_current(paths: list[Path]) -> dict[str, dict]:
    et = exiftool()
    if not et.available or not paths:
        return {}
    try:
        return et.read(paths)
    except Exception:  # noqa: BLE001 讀不到就用圖庫裡的值
        return {}


def current_values(conn: sqlite3.Connection, ids: list[int]) -> list[dict]:
    """每張照片目前的值（以檔案為準，讀不到時用圖庫資料）。RAW 以 .xmp 附屬檔的值優先。"""
    from .xmp import sidecar_path

    rows = [db.get_image(conn, i) for i in ids]
    rows = [r for r in rows if r is not None]
    paths, targets = [], {}
    for r in rows:
        p = db.absolute_path(conn, r)
        kind = _target_kind(p, r["media_type"])
        side = sidecar_path(p) if kind == "sidecar" and p.exists() else None
        targets[r["id"]] = (p, side)
        if p.exists():
            paths.append(p)
            if side is not None:
                paths.append(side)
    meta = _read_current(paths[:2000])
    out = []
    for r in rows:
        p, side = targets[r["id"]]
        m = dict(meta.get(str(p), {}))
        if side is not None:
            m.update({k: v for k, v in meta.get(str(side), {}).items() if v not in (None, "")})
        lat, lon = m.get("GPSLatitude"), m.get("GPSLongitude")
        out.append({
            "id": r["id"], "name": r["rel_path"].rsplit("/", 1)[-1], "rel_path": r["rel_path"], "media_type": r["media_type"],
            "raw": bool(r["is_raw"]), "kind": _target_kind(p, r["media_type"]), "exists": p.exists(),
            "taken_at": _iso(m.get("DateTimeOriginal")) or r["taken_at"],
            "tz": m.get("OffsetTimeOriginal") or r["tz_offset"] or "",
            "make": str(m.get("Make") or "").strip(), "model": str(m.get("Model") or "").strip() or (r["camera"] or ""),
            "lens": str(m.get("LensModel") or m.get("Lens") or r["lens"] or "").strip(),
            "gps": [float(lat), float(lon)] if isinstance(lat, (int, float)) and isinstance(lon, (int, float))
            else ([r["lat"], r["lon"]] if r["lat"] is not None and r["lon"] is not None else None),
            "title": str(m.get("Title") or r["title"] or ""),
            "caption": str(m.get("Description") or m.get("ImageDescription") or m.get("Caption-Abstract") or r["caption"] or ""),
            "artist": str(m.get("Artist") or m.get("Creator") or r["artist"] or ""),
            "copyright": str(m.get("Copyright") or r["copyright"] or ""),
        })
    return out


def inspect(conn: sqlite3.Connection, ids: list[int]) -> dict:
    """選取的照片：每個欄位若全部相同就給值，不同就標「多個值」。"""
    cur = current_values(conn, ids)
    fields = {}
    for key in FIELDS:
        vals = [json.dumps(c[key], ensure_ascii=False) for c in cur if c["media_type"] != "video"]
        uniq = set(vals)
        fields[key] = {"mixed": len(uniq) > 1, "value": json.loads(vals[0]) if len(uniq) == 1 else None}
    return {
        "count": len(cur),
        "raw": sum(1 for c in cur if c["kind"] == "sidecar"),
        "embedded": sum(1 for c in cur if c["kind"] == "embedded"),
        "video": sum(1 for c in cur if c["kind"] == "video"),
        "missing": sum(1 for c in cur if not c["exists"]),
        "fields": fields,
        "items": cur[:500],
    }


# ---- 計算新的值 ---------------------------------------------------------------

def _new_values(cur: dict, changes: dict) -> dict:
    """依變更算出這張照片的新值（只包含有改的欄位）。"""
    new: dict = {}
    t = changes.get("time")
    if t and cur["media_type"] != "video":
        if t.get("mode") == "set" and t.get("value"):
            new["taken_at"] = str(t["value"])[:19]
        elif t.get("mode") == "shift" and cur["taken_at"]:
            base = datetime.fromisoformat(cur["taken_at"][:19])
            new["taken_at"] = (base + timedelta(seconds=int(t.get("seconds") or 0))).isoformat(timespec="seconds")
    if "tz" in changes and cur["media_type"] != "video":
        new["tz"] = str(changes["tz"] or "")
    for key in ("make", "model", "lens", "title", "caption", "artist", "copyright"):
        if key in changes and cur["media_type"] != "video":
            new[key] = str(changes[key] or "").strip()
    g = changes.get("gps")
    if g and cur["media_type"] != "video":
        if g.get("remove"):
            new["gps"] = None
        elif g.get("lat") is not None and g.get("lon") is not None:
            lat, lon = float(g["lat"]), float(g["lon"])
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                raise ValueError("GPS 座標超出範圍")
            new["gps"] = [round(lat, 7), round(lon, 7)]
    return new


def _rename_plan(conn: sqlite3.Connection, items: list[dict], pattern: str, after_time: dict[int, str]) -> dict[int, str]:
    """新檔名（不含副檔名）。RAW+JPEG 同名雙檔取相同序號。"""
    from .export import output_name

    groups: dict[tuple, list[dict]] = {}
    for it in items:
        folder, _, name = it["rel_path"].rpartition("/")
        groups.setdefault((folder, Path(name).stem), []).append(it)
    ordered = sorted(groups.values(), key=lambda g: (after_time.get(g[0]["id"]) or g[0]["taken_at"] or "", g[0]["rel_path"]))
    out = {}
    total = len(ordered)
    for seq, group in enumerate(ordered, 1):
        for it in group:
            row = dict(db.get_image(conn, it["id"]))
            if it["id"] in after_time:
                row["taken_at"] = after_time[it["id"]]
            out[it["id"]] = Path(output_name(pattern, row, seq, total)).stem
    return out


def preview(conn: sqlite3.Connection, ids: list[int], changes: dict, limit: int = 12) -> dict:
    cur = current_values(conn, ids)
    after_time = {}
    rows = []
    for c in cur:
        new = _new_values(c, changes)
        if "taken_at" in new:
            after_time[c["id"]] = new["taken_at"]
        rows.append((c, new))
    names = _rename_plan(conn, cur, changes["rename"], after_time) if changes.get("rename") else {}
    sample = []
    changed = 0
    for c, new in rows:
        diff = {k: {"from": c[k], "to": v} for k, v in new.items() if c[k] != v}
        if c["id"] in names:
            new_name = names[c["id"]] + Path(c["name"]).suffix
            if new_name != c["name"]:
                diff["name"] = {"from": c["name"], "to": new_name}
        if diff:
            changed += 1
            if len(sample) < limit:
                sample.append({"id": c["id"], "name": c["name"], "diff": diff})
    return {"count": len(cur), "changed": changed, "sample": sample,
            "skipped_video": sum(1 for c in cur if c["kind"] == "video" and not changes.get("rename"))}


# ---- 寫入 ---------------------------------------------------------------------

def _args(new: dict, kind: str) -> list[str]:
    """exiftool 參數。空字串代表刪除那個欄位。"""
    a: list[str] = []
    x = kind == "sidecar"
    if "taken_at" in new:
        v = _exif_time(new["taken_at"]) if new["taken_at"] else ""
        a += [f"-XMP-exif:DateTimeOriginal={v}", f"-XMP-xmp:CreateDate={v}"] if x else [
            f"-DateTimeOriginal={v}", f"-CreateDate={v}", f"-XMP-exif:DateTimeOriginal={v}"]
    if "tz" in new:
        a += [f"-OffsetTimeOriginal={new['tz']}", f"-OffsetTime={new['tz']}"] if not x else []
    if "make" in new:
        a.append(f"-{'XMP-tiff:' if x else ''}Make={new['make']}")
    if "model" in new:
        a.append(f"-{'XMP-tiff:' if x else ''}Model={new['model']}")
    if "lens" in new:
        a += [f"-XMP-exifEX:LensModel={new['lens']}", f"-XMP-aux:Lens={new['lens']}"] if x else [f"-LensModel={new['lens']}"]
    if "gps" in new:
        if new["gps"] is None:
            a += ["-XMP-exif:GPSLatitude=", "-XMP-exif:GPSLongitude="] if x else ["-GPS:all=", "-XMP-exif:GPS*="]
        else:
            lat, lon = new["gps"]
            if x:
                a += [f"-XMP-exif:GPSLatitude={abs(lat)} {'N' if lat >= 0 else 'S'}",
                      f"-XMP-exif:GPSLongitude={abs(lon)} {'E' if lon >= 0 else 'W'}"]
            else:
                a += [f"-GPSLatitude={abs(lat)}", f"-GPSLatitudeRef={'N' if lat >= 0 else 'S'}",
                      f"-GPSLongitude={abs(lon)}", f"-GPSLongitudeRef={'E' if lon >= 0 else 'W'}"]
    if "title" in new:
        a += [f"-XMP-dc:Title={new['title']}"] + ([] if x else [f"-IPTC:ObjectName={new['title'][:64]}"])
    if "caption" in new:
        a += [f"-XMP-dc:Description={new['caption']}"] + ([] if x else [
            f"-EXIF:ImageDescription={new['caption']}", f"-IPTC:Caption-Abstract={new['caption'][:2000]}"])
    if "artist" in new:
        a += [f"-XMP-dc:Creator={new['artist']}"] + ([] if x else [f"-EXIF:Artist={new['artist']}", f"-IPTC:By-line={new['artist'][:32]}"])
    if "copyright" in new:
        a += [f"-XMP-dc:Rights={new['copyright']}"] + ([] if x else [f"-EXIF:Copyright={new['copyright']}", f"-IPTC:CopyrightNotice={new['copyright'][:128]}"])
    return a


def _camera_name(make: str, model: str) -> str | None:
    if model and make and model.lower().startswith(make.lower().split()[0]):
        return model
    return " ".join(p for p in (make, model) if p) or None


def _update_library(conn: sqlite3.Connection, image_id: int, cur: dict, new: dict) -> None:
    sets, params = [], []
    if "taken_at" in new:
        sets += ["taken_at = ?", "sort_at = COALESCE(?, sort_at)"]
        params += [new["taken_at"] or None, new["taken_at"] or None]
    if "tz" in new:
        sets.append("tz_offset = ?")
        params.append(new["tz"] or None)
    if "make" in new or "model" in new:
        sets.append("camera = ?")
        params.append(_camera_name(new.get("make", cur["make"]), new.get("model", cur["model"])))
    if "lens" in new:
        sets.append("lens = ?")
        params.append(new["lens"] or None)
    if "gps" in new:
        if new["gps"] is None:
            sets += ["lat = NULL", "lon = NULL", "place = NULL", "place_en = NULL", "country = NULL"]
        else:
            from . import places

            lat, lon = new["gps"]
            sets += ["lat = ?", "lon = ?"]
            params += [lat, lon]
            if places.available():
                p = places.lookup([(lat, lon)])[0]
                far = p["km"] > 80
                sets += ["place = ?", "place_en = ?", "country = ?"]
                params += ["" if far else p["place"], "" if far else p["place_en"], p["country"]]
    for key in ("title", "caption", "artist", "copyright"):
        if key in new:
            sets.append(f"{key} = ?")
            params.append(new[key] or None)
    if sets:
        conn.execute(f"UPDATE images SET {', '.join(sets)} WHERE id = ?", (*params, image_id))
        db.refresh_search_text(conn, image_id)


def _rename_file(conn: sqlite3.Connection, image, new_stem: str) -> str | None:
    """改硬碟上的檔名（同名附屬檔一起改），回傳新的相對路徑；檔名沒變回傳 None。"""
    from .fileops import _unique, sidecars

    src = db.absolute_path(conn, image)
    if new_stem == src.stem:
        return None
    dest = _unique(src.with_name(new_stem + src.suffix))
    extras = sidecars(src)
    src.rename(dest)
    for extra in extras:
        suffix = extra.name[len(src.stem):] if extra.name.startswith(src.stem) else extra.suffix
        try:
            extra.rename(_unique(dest.with_name(dest.stem + suffix)))
        except OSError:
            pass
    root = db.get_root(conn, image["root_id"])
    rel = dest.relative_to(Path(root["path"]).resolve()).as_posix() if root else dest.name
    conn.execute("UPDATE images SET rel_path = ?, folder = ?, mtime = ? WHERE id = ?",
                 (rel, db.folder_of(rel), dest.stat().st_mtime, image["id"]))
    db.refresh_search_text(conn, image["id"])
    return rel


def _write_one(conn: sqlite3.Connection, cfg: Config, image, cur: dict, new: dict) -> None:
    from .xmp import _refresh_identity, sidecar_path

    if not new:
        return
    path = db.absolute_path(conn, image)
    if not path.exists():
        raise FileNotFoundError("找不到檔案（硬碟可能未連接）")
    et = exiftool()
    if not et.available:
        raise RuntimeError("找不到 exiftool，無法寫入")
    kind = _target_kind(path, image["media_type"])
    args = _args(new, kind)
    common = ["-m", "-codedcharacterset=utf8", "-charset", "iptc=utf8"]
    if kind == "sidecar":
        side = sidecar_path(path)
        if side is not None:
            et.execute("-overwrite_original", *common, *args, str(side))
        else:
            side = path.with_suffix(".xmp")
            et.execute("-o", str(side), *common, *args, str(path))
        if not side.exists():
            raise RuntimeError("無法建立 .xmp 附屬檔（資料夾可能是唯讀）")
        conn.execute("UPDATE images SET xmp_mtime = ? WHERE id = ?", (side.stat().st_mtime, image["id"]))
    elif kind == "embedded":
        et.execute("-overwrite_original", "-P", *common, *args, str(path))
        _refresh_identity(conn, cfg, image, path)
    _update_library(conn, image["id"], cur, new)


def apply_edits(conn: sqlite3.Connection, cfg: Config, ids: list[int], changes: dict,
                progress: Callable[[int, int, str], None] | None = None,
                stop: threading.Event | None = None, record: bool = True, label: str = "") -> dict:
    """套用變更。回傳 {done, errors, skipped, batch}。batch 可用來復原。"""
    cur_all = current_values(conn, ids)
    after_time = {}
    plan = []
    for c in cur_all:
        new = _new_values(c, changes)
        if "taken_at" in new:
            after_time[c["id"]] = new["taken_at"]
        plan.append((c, new))
    names = _rename_plan(conn, cur_all, changes["rename"], after_time) if changes.get("rename") else {}
    if changes.get("names"):  # 復原時直接指定原本的檔名
        names = {int(k): v for k, v in changes["names"].items()}
    done, errors, skipped, undo_items = [], [], 0, []
    total = len(plan)
    for i, (c, new) in enumerate(plan, 1):
        if stop is not None and stop.is_set():
            break
        image = db.get_image(conn, c["id"])
        new = {k: v for k, v in new.items() if c[k] != v}
        rename_to = names.get(c["id"])
        if not new and (not rename_to or rename_to == Path(c["name"]).stem):
            skipped += 1
            continue
        try:
            _write_one(conn, cfg, image, c, new)
            old_stem = Path(c["name"]).stem
            if rename_to and rename_to != old_stem:
                _rename_file(conn, db.get_image(conn, c["id"]), rename_to)
            undo_items.append({"id": c["id"], "old": {k: c[k] for k in new}, "name": old_stem if rename_to else None})
            done.append(c["id"])
        except Exception as exc:  # noqa: BLE001 一張失敗不影響其他張
            errors.append(f"{c['rel_path']}: {exc}")
        if i % 10 == 0:
            conn.commit()
        if progress:
            progress(i, total, c["name"])
    batch = None
    if record and undo_items:
        batch = conn.execute(
            "INSERT INTO edit_batches (created_at, label, items) VALUES (?, ?, ?)",
            (db.now_iso(), label or f"修改 {len(done)} 張的資訊", json.dumps(undo_items, ensure_ascii=False)),
        ).lastrowid
    conn.commit()
    return {"done": len(done), "errors": errors, "skipped": skipped, "batch": batch}


def undo_batch(conn: sqlite3.Connection, cfg: Config, batch_id: int, progress=None, stop=None) -> dict:
    """把一次修改還原成原本的值與檔名。"""
    row = conn.execute("SELECT * FROM edit_batches WHERE id = ?", (batch_id,)).fetchone()
    if row is None or row["undone"]:
        raise ValueError("這次修改已經復原過，或找不到紀錄")
    items = json.loads(row["items"])
    done, errors = 0, []
    for i, it in enumerate(items, 1):
        if stop is not None and stop.is_set():
            break
        changes = {}
        old = it["old"]
        if "taken_at" in old:
            changes["time"] = {"mode": "set", "value": old["taken_at"] or ""}
        if "gps" in old:
            changes["gps"] = {"remove": True} if old["gps"] is None else {"lat": old["gps"][0], "lon": old["gps"][1]}
        for k in ("tz", "make", "model", "lens", "title", "caption", "artist", "copyright"):
            if k in old:
                changes[k] = old[k]
        if it.get("name"):
            changes["names"] = {str(it["id"]): it["name"]}
        res = apply_edits(conn, cfg, [it["id"]], changes, record=False)
        # 原本沒有拍攝時間的照片：刪除寫入的時間
        if "taken_at" in old and not old["taken_at"]:
            image = db.get_image(conn, it["id"])
            if image is not None:
                try:
                    _write_one(conn, cfg, image, current_values(conn, [it["id"]])[0], {"taken_at": ""})
                except Exception:  # noqa: BLE001
                    pass
        done += res["done"]
        errors += res["errors"]
        if progress:
            progress(i, len(items), "")
    conn.execute("UPDATE edit_batches SET undone = 1 WHERE id = ?", (batch_id,))
    conn.commit()
    return {"done": done, "errors": errors}
