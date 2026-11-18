"""助理提出的動作：先「提案」，本人在畫面上看過、按下確認才執行；每一個動作都記下來，可以復原。

核心原則第 1 條（永不自動刪除）在這裡的做法：
- 助理（模型）只能建立「提案」：寫一筆紀錄，硬碟和目錄都不變。
- 只有使用者在介面上按下確認，伺服器收到 confirm=true 才執行（run），而且只限這台 Mac。背景工作、排程都不會呼叫 run。
- 沒有任何刪除檔案的動作。最接近的是「移到待刪除資料夾」：同一顆硬碟上的一個資料夾，隨時可以搬回來。
- 執行前逐項再驗證：硬碟有接上、檔案還在原位而且和目錄記的一樣（大小、修改時間）、目的地沒有同名的東西。
  任何一項不符就跳過那一項並說明原因，不會覆蓋任何檔案。
- 復原（undo）把每一項搬回原位；同樣先驗證，原位已經有東西就不動。

權限（設定 → AI 助理）：
- 3：只在 Re'memor 裡整理（顏色標籤、智慧資料夾、待刪除標記），不碰硬碟。
- 4：再加上搬移、改名、移到待刪除資料夾（會改變硬碟上檔案的位置或名稱，但不會刪除或修改內容）。
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from pathlib import Path

from . import db

PENDING_DIR = "Re'memor 待刪除"  # 「移到待刪除資料夾」放在該來源最上層的這個資料夾裡，保留原本的資料夾結構
MAX_ITEMS = 200
LEVEL = {"label": 3, "smart_folder": 3, "mark_delete": 3, "move": 4, "rename": 4, "to_pending": 4}
FILE_OPS = ("move", "rename", "to_pending")

_lock = threading.Lock()


class ActionError(ValueError):
    """提案或執行被拒絕，訊息是給使用者看的。"""


# ---- 檢查名稱與路徑 ----

def _bad_part(p: str) -> bool:
    return (not p or p in (".", "..") or p.startswith(".") or p.startswith("~") or "/" in p or ":" in p or "\\" in p
            or "\0" in p or len(p.encode("utf-8")) > 255)


def clean_folder(path: str) -> str:
    """模型給的資料夾路徑（相對於來源）：拿掉頭尾的斜線，每一段都要是正常的名稱。"""
    parts = [p.strip() for p in str(path or "").replace("\\", "/").split("/") if p.strip() not in ("", ".")]
    if any(_bad_part(p) for p in parts):
        raise ActionError(f"資料夾名稱不能用：{path}")
    return "/".join(parts)


def clean_name(new: str, old: str) -> str:
    new = str(new or "").strip()
    if _bad_part(new):
        raise ActionError(f"檔名不能用：{new or '（空白）'}")
    if Path(new).suffix.lower() != Path(old).suffix.lower():
        raise ActionError(f"不能改副檔名（{old} → {new}），改了檔案可能會打不開")
    return new


def _join(folder: str, name: str) -> str:
    return f"{folder}/{name}" if folder else name


# ---- 讀目錄 ----

def _files(conn: sqlite3.Connection, ids: list) -> list[sqlite3.Row]:
    try:
        ids = list(dict.fromkeys(int(i) for i in ids or []))
    except (TypeError, ValueError) as exc:
        raise ActionError("檔案編號不對") from exc
    if not ids:
        raise ActionError("沒有指定檔案")
    if len(ids) > MAX_ITEMS:
        raise ActionError(f"一次最多 {MAX_ITEMS} 個項目")
    rows = conn.execute(
        f"SELECT f.id, f.name, f.size, f.mtime, f.root_id, f.status, f.label, f.content_hash, f.image_id, d.path AS folder, "
        f"COALESCE(v.name, r.name) AS drive FROM files f JOIN folders d ON d.id = f.folder_id JOIN roots r ON r.id = f.root_id "
        f"LEFT JOIN drives v ON v.id = r.drive_id WHERE f.id IN ({','.join('?' * len(ids))})", ids).fetchall()
    by_id = {r["id"]: r for r in rows}
    missing = [i for i in ids if i not in by_id or by_id[i]["status"] != "ok"]
    if missing:
        raise ActionError(f"目錄裡找不到這些檔案（編號 {', '.join(map(str, missing[:5]))}），可能已經不在了")
    return [by_id[i] for i in ids]


def _item(r: sqlite3.Row, **extra) -> dict:
    return {"type": "file", "id": r["id"], "name": r["name"], "root_id": r["root_id"], "drive": r["drive"],
            "from": _join(r["folder"], r["name"]), "size": r["size"], "mtime": r["mtime"], **extra}


# ---- 建立提案（模型呼叫；只寫一筆紀錄） ----

def propose(conn: sqlite3.Connection, kind: str, args: dict, level: int, question: str = "") -> dict:
    if kind not in LEVEL:
        raise ActionError("不認得的動作")
    if level < LEVEL[kind]:
        raise ActionError("目前的權限不允許這個動作" + ("（要「可以搬移、改名檔案」）" if LEVEL[kind] == 4 else "（要「可以幫你整理」）"))
    payload, summary = _BUILD[kind](conn, args or {})
    cur = conn.execute(
        "INSERT INTO assistant_actions (kind, level, summary, payload, state, question, created_at) VALUES (?, ?, ?, ?, 'proposed', ?, ?)",
        (kind, LEVEL[kind], summary, json.dumps(payload, ensure_ascii=False), question[:500], db.now_iso()))
    conn.commit()
    return get(conn, cur.lastrowid)


def _build_label(conn, args):
    from .catalog import LABELS

    color = str(args.get("color") or "").lower()
    if color in ("", "none", "clear"):
        color = None
    elif color not in LABELS:
        raise ActionError("顏色只能是紅、黃、綠、藍、紫，或拿掉")
    items = [_item(r) for r in _files(conn, args.get("file_ids") or [])] if args.get("file_ids") else []
    folder_ids = [int(i) for i in args.get("folder_ids") or [] if str(i).lstrip("-").isdigit()]
    if folder_ids:
        rows = conn.execute(
            f"SELECT d.id, d.name, d.path, d.root_id, COALESCE(v.name, r.name) AS drive FROM folders d JOIN roots r ON r.id = d.root_id "
            f"LEFT JOIN drives v ON v.id = r.drive_id WHERE d.status = 'ok' AND d.id IN ({','.join('?' * len(folder_ids))})",
            folder_ids).fetchall()
        items += [{"type": "folder", "id": r["id"], "name": r["name"] or r["drive"], "root_id": r["root_id"], "drive": r["drive"],
                   "from": r["path"]} for r in rows]
    if not items:
        raise ActionError("沒有指定檔案或資料夾")
    if len(items) > MAX_ITEMS:
        raise ActionError(f"一次最多 {MAX_ITEMS} 個項目")
    return {"color": color, "items": items}, f"{'拿掉' if color is None else '加上'}顏色標籤：{len(items)} 個項目"


def _build_smart(conn, args):
    name = str(args.get("name") or "").strip()[:60]
    q = str(args.get("query") or "").strip()[:200]
    if not name or not q:
        raise ActionError("智慧資料夾要有名字和搜尋關鍵字")
    query = {"q": q}
    kind = args.get("kind")
    if kind in ("document", "photo", "video", "audio", "archive", "other"):
        query["kind"] = kind
    if str(args.get("year") or "").isdigit():
        query["year"] = int(args["year"])
    return {"name": name, "query": query, "items": []}, f"建立智慧資料夾「{name}」"


def _build_mark(conn, args):
    rows = _files(conn, args.get("file_ids") or [])
    remove = {r["id"] for r in rows}
    marked = {m[0] for m in conn.execute("SELECT item_id FROM delete_marks WHERE kind = 'file'")}
    items = []
    for r in rows:
        if not r["content_hash"]:
            raise ActionError(f"「{r['name']}」還沒完整比對內容，不能標記為待刪除（請先到「重複項目」比對）")
        keep = [k[0] for k in conn.execute(
            "SELECT id FROM files WHERE content_hash = ? AND size = ? AND status = 'ok' AND id != ?",
            (r["content_hash"], r["size"], r["id"])) if k[0] not in remove and k[0] not in marked]
        if not keep:
            raise ActionError(f"「{r['name']}」沒有其他一模一樣的副本，標記了就沒有保留的那份，所以不行")
        items.append(_item(r, keep=keep[:5]))
    return {"items": items}, f"把 {len(items)} 個重複的副本標記為待刪除（只是標記，不會刪除）"


def _same_root(rows) -> int:
    roots = {r["root_id"] for r in rows}
    if len(roots) != 1:
        raise ActionError("一次只能整理同一個來源裡的檔案")
    return roots.pop()


def _build_move(conn, args):
    rows = _files(conn, args.get("file_ids") or [])
    root_id = _same_root(rows)
    folder = clean_folder(args.get("folder") or "")
    if folder == PENDING_DIR or folder.startswith(PENDING_DIR + "/"):
        raise ActionError("要移到待刪除資料夾，請用「移到待刪除」")
    items = [_item(r, to=_join(folder, r["name"])) for r in rows if r["folder"] != folder]
    if not items:
        raise ActionError("這些檔案已經在那個資料夾裡了")
    targets = [i["to"] for i in items]
    if len(set(targets)) != len(targets):
        raise ActionError("有好幾個檔案同名，不能搬到同一個資料夾")
    return {"root_id": root_id, "folder": folder, "items": items}, f"把 {len(items)} 個檔案搬到「{folder or '最上層'}」"


def _build_rename(conn, args):
    pairs = [p for p in args.get("renames") or [] if isinstance(p, dict)]
    if not pairs and args.get("file_id") is not None:
        pairs = [{"file_id": args.get("file_id"), "new_name": args.get("new_name")}]
    rows = _files(conn, [p.get("file_id") for p in pairs])
    by_id = {r["id"]: r for r in rows}
    items = []
    for p in pairs:
        r = by_id[int(p["file_id"])]
        new = clean_name(p.get("new_name"), r["name"])
        if new != r["name"]:
            items.append(_item(r, to=_join(r["folder"], new), new_name=new))
    if not items:
        raise ActionError("新名稱和原本一樣")
    targets = [(i["root_id"], i["to"]) for i in items]
    if len(set(targets)) != len(targets):
        raise ActionError("有兩個檔案會改成同一個名字")
    return {"items": items}, f"替 {len(items)} 個檔案改名"


def _build_pending(conn, args):
    rows = _files(conn, args.get("file_ids") or [])
    items = []
    for r in rows:
        if r["folder"] == PENDING_DIR or r["folder"].startswith(PENDING_DIR + "/"):
            continue
        items.append(_item(r, to=_join(PENDING_DIR, _join(r["folder"], r["name"]))))
    if not items:
        raise ActionError("這些檔案已經在待刪除資料夾裡了")
    return {"items": items}, f"把 {len(items)} 個檔案移到「{PENDING_DIR}」資料夾（不會刪除，隨時可以搬回來）"


_BUILD = {"label": _build_label, "smart_folder": _build_smart, "mark_delete": _build_mark, "move": _build_move,
          "rename": _build_rename, "to_pending": _build_pending}


# ---- 讀取紀錄 ----

def _public(r: sqlite3.Row) -> dict:
    payload = json.loads(r["payload"] or "{}")
    result = json.loads(r["result"] or "{}") if r["result"] else {}
    items = payload.get("items") or []
    outcome = {i.get("index"): i for i in result.get("items") or []}
    return {"id": r["id"], "kind": r["kind"], "level": r["level"], "summary": r["summary"], "state": r["state"],
            "question": r["question"], "created_at": r["created_at"], "done_at": r["done_at"], "undone_at": r["undone_at"],
            "color": payload.get("color"), "name": payload.get("name"), "query": payload.get("query"),
            "folder": payload.get("folder"), "file_op": r["kind"] in FILE_OPS,
            "items": [{k: it.get(k) for k in ("type", "id", "name", "drive", "from", "to", "size", "new_name")}
                      | {"status": (outcome.get(n) or {}).get("status"), "reason": (outcome.get(n) or {}).get("reason")}
                      for n, it in enumerate(items[:MAX_ITEMS])],
            "message": result.get("message") or ""}


def get(conn: sqlite3.Connection, action_id: int) -> dict:
    r = conn.execute("SELECT * FROM assistant_actions WHERE id = ?", (int(action_id),)).fetchone()
    if r is None:
        raise ActionError("找不到這個動作")
    return _public(r)


def history(conn: sqlite3.Connection, limit: int = 30) -> list[dict]:
    rows = conn.execute("SELECT * FROM assistant_actions WHERE state != 'proposed' AND state != 'dismissed' "
                        "ORDER BY COALESCE(done_at, created_at) DESC, id DESC LIMIT ?", (max(1, min(limit, 200)),)).fetchall()
    return [_public(r) for r in rows]


def dismiss(conn: sqlite3.Connection, action_id: int) -> dict:
    conn.execute("UPDATE assistant_actions SET state = 'dismissed' WHERE id = ? AND state = 'proposed'", (int(action_id),))
    conn.commit()
    return get(conn, action_id)


# ---- 執行（只在本人按下確認後） ----

def run(conn: sqlite3.Connection, action_id: int, level: int, only: list[int] | None = None) -> dict:
    """執行一個提案。only＝只做勾選的那幾項（索引）；其他項目記成「略過」。"""
    with _lock:
        r = conn.execute("SELECT * FROM assistant_actions WHERE id = ?", (int(action_id),)).fetchone()
        if r is None:
            raise ActionError("找不到這個動作")
        if r["state"] != "proposed":
            raise ActionError("這個動作已經處理過了")
        if level < r["level"]:
            raise ActionError("目前的權限不允許這個動作，請到設定 → AI 助理調整權限")
        payload = json.loads(r["payload"])
        items = payload.get("items") or []
        chosen = set(range(len(items))) if only is None else {int(i) for i in only}
        results = _RUN[r["kind"]](conn, payload, chosen)
        ok = results.get("count", sum(1 for x in results["items"] if x["status"] == "done"))
        tried = len(chosen & set(range(len(items)))) if items else 1
        state = "done" if ok == tried else ("partial" if ok else "failed")
        results["message"] = _message(r["kind"], ok, tried)
        conn.execute("UPDATE assistant_actions SET state = ?, result = ?, done_at = ? WHERE id = ?",
                     (state, json.dumps(results, ensure_ascii=False), db.now_iso(), r["id"]))
        conn.commit()
        return get(conn, r["id"])


def _message(kind: str, ok: int, tried: int) -> str:
    if kind == "smart_folder":
        return "已建立智慧資料夾" if ok else "沒有建立"
    if ok == tried:
        return f"完成 {ok} 項"
    return f"完成 {ok} 項，{tried - ok} 項沒有做（原因寫在每一項旁邊）"


def _skip(index: int, reason: str) -> dict:
    return {"index": index, "status": "skipped", "reason": reason}


def _run_label(conn, payload, chosen):
    out = []
    for n, it in enumerate(payload["items"]):
        if n not in chosen:
            out.append(_skip(n, "沒有勾選"))
            continue
        table = "files" if it["type"] == "file" else "folders"
        row = conn.execute(f"SELECT label FROM {table} WHERE id = ? AND status = 'ok'", (it["id"],)).fetchone()
        if row is None:
            out.append(_skip(n, "目錄裡已經沒有這個項目"))
            continue
        from .catalog import set_labels

        set_labels(conn, [it["id"]] if table == "files" else [], [it["id"]] if table == "folders" else [], payload.get("color"))
        out.append({"index": n, "status": "done", "before": row["label"]})
    return {"items": out}


def _run_smart(conn, payload, chosen):
    from .find import save_smart_folder

    sid = save_smart_folder(conn, payload["name"], payload["query"])
    return {"items": [], "smart_id": sid, "count": 1}


def _run_mark(conn, payload, chosen):
    from . import pending

    out = []
    for n, it in enumerate(payload["items"]):
        if n not in chosen:
            out.append(_skip(n, "沒有勾選"))
            continue
        try:
            pending.mark(conn, "file", it.get("keep") or [], [it["id"]])
        except pending.MarkError as exc:
            out.append(_skip(n, str(exc)))
            continue
        m = conn.execute("SELECT id FROM delete_marks WHERE kind = 'file' AND item_id = ?", (it["id"],)).fetchone()
        out.append({"index": n, "status": "done", "mark_id": m[0] if m else None})
    return {"items": out}


def _root_path(conn, root_id: int) -> Path | None:
    r = conn.execute("SELECT path FROM roots WHERE id = ?", (root_id,)).fetchone()
    return Path(r["path"]) if r else None


def _inside(root: Path, rel: str) -> Path:
    """相對路徑轉成實際路徑，並確認還在這個來源裡（不跟著捷徑跑出去）。"""
    parts = [p for p in rel.split("/") if p]
    if not parts or any(p in (".", "..") for p in parts):
        raise ActionError("路徑不合法")
    target = root.joinpath(*parts)
    real_root = root.resolve()
    real_parent = target.parent.resolve()
    if real_parent != real_root and real_root not in real_parent.parents:
        raise ActionError("路徑不在這個來源裡")
    return target


def _relocate(conn, it: dict, src_rel: str, dst_rel: str, expect: tuple[int, float]) -> dict:
    """把一個檔案從 src_rel 搬到 dst_rel（同一個來源裡），成功後更新目錄。回傳結果（含復原要用的資料）。"""
    root = _root_path(conn, it["root_id"])
    if root is None or not root.is_dir():
        return {"status": "skipped", "reason": "硬碟沒有接上"}
    try:
        src = _inside(root, src_rel)
        dst = _inside(root, dst_rel)
    except ActionError as exc:
        return {"status": "skipped", "reason": str(exc)}
    try:
        st = os.lstat(src)
    except OSError:
        return {"status": "skipped", "reason": "原本的位置找不到這個檔案（可能已經被搬走），請重新掃描"}
    import stat as stat_

    if not stat_.S_ISREG(st.st_mode):
        return {"status": "skipped", "reason": "這不是一般的檔案（可能是捷徑），不處理"}
    if st.st_size != expect[0] or abs(st.st_mtime - expect[1]) > 1:
        return {"status": "skipped", "reason": "這個檔案在掃描之後改過了，請重新掃描後再試"}
    if os.path.lexists(dst):
        return {"status": "skipped", "reason": "目的地已經有同名的檔案，不覆蓋"}
    created = []
    parent = dst.parent
    missing = []
    while not parent.exists():
        missing.append(parent)
        parent = parent.parent
    try:
        for p in reversed(missing):
            p.mkdir()
            created.append(str(p.relative_to(root)))
        if os.path.lexists(dst):  # 再檢查一次（建立資料夾的同時，可能有別的程式放了檔案進來）
            raise FileExistsError
        os.rename(src, dst)
    except FileExistsError:
        _remove_empty(root, created)
        return {"status": "skipped", "reason": "目的地已經有同名的檔案，不覆蓋"}
    except OSError as exc:
        _remove_empty(root, created)
        import errno

        if exc.errno == errno.EROFS:
            return {"status": "skipped", "reason": "這顆硬碟是唯讀的（例如 Windows 格式），不能搬移"}
        if exc.errno in (errno.EACCES, errno.EPERM):
            return {"status": "skipped", "reason": "沒有權限更動這個檔案"}
        if exc.errno == errno.EXDEV:
            return {"status": "skipped", "reason": "目的地在另一顆硬碟上，不能直接搬"}
        return {"status": "skipped", "reason": f"沒有搬成功：{exc.strerror or exc}"}
    _catalog_move(conn, it, dst_rel)
    return {"status": "done", "created": created}


def _remove_empty(root: Path, created: list[str]) -> None:
    """拿掉這次為了搬檔案而建立、現在還是空的資料夾（只刪空資料夾，裡面有任何東西就不動）。"""
    for rel in sorted(created, key=lambda p: p.count("/"), reverse=True):
        try:
            os.rmdir(root / rel)
        except OSError:
            pass


def _ensure_folder(conn, root_id: int, rel: str) -> int:
    row = conn.execute("SELECT id, status FROM folders WHERE root_id = ? AND path = ?", (root_id, rel)).fetchone()
    now = db.now_iso()
    if row is not None:
        if row["status"] != "ok":
            conn.execute("UPDATE folders SET status = 'ok', last_seen = ? WHERE id = ?", (now, row["id"]))
        return row["id"]
    parent = _ensure_folder(conn, root_id, rel.rsplit("/", 1)[0] if "/" in rel else "") if rel else None
    name = rel.rsplit("/", 1)[-1] if rel else ""
    return conn.execute("INSERT INTO folders (root_id, parent_id, path, name, first_seen, last_seen) VALUES (?, ?, ?, ?, ?, ?)",
                        (root_id, parent, rel, name, now, now)).lastrowid


def _chain(rel: str) -> list[str]:
    out = [""]
    parts = rel.split("/") if rel else []
    for i in range(1, len(parts) + 1):
        out.append("/".join(parts[:i]))
    return out


def _catalog_move(conn, it: dict, dst_rel: str) -> None:
    """目錄跟著更新：檔案的資料夾與名稱、照片的路徑、待刪除標記的路徑。資料夾的大小統計在整批做完後重算。"""
    folder = dst_rel.rsplit("/", 1)[0] if "/" in dst_rel else ""
    name = dst_rel.rsplit("/", 1)[-1]
    old = conn.execute("SELECT f.folder_id, f.image_id, d.path FROM files f JOIN folders d ON d.id = f.folder_id WHERE f.id = ?",
                       (it["id"],)).fetchone()
    fid = _ensure_folder(conn, it["root_id"], folder)
    conn.execute("UPDATE files SET folder_id = ?, name = ?, last_seen = ? WHERE id = ?", (fid, name, db.now_iso(), it["id"]))
    if old and old["image_id"]:
        try:
            conn.execute("UPDATE images SET rel_path = ? WHERE id = ?", (dst_rel, old["image_id"]))
        except sqlite3.IntegrityError:
            pass
    conn.execute("UPDATE delete_marks SET path = ? WHERE kind = 'file' AND item_id = ?", (dst_rel, it["id"]))
    # 內容變了的資料夾：重複資料夾的比對結果不再可靠，清掉，等下次比對重新算
    paths = set(_chain(folder)) | set(_chain(old["path"] if old else ""))
    marks = ",".join("?" * len(paths))
    conn.execute(f"UPDATE folders SET shape_sig = NULL, content_sig = NULL WHERE root_id = ? AND path IN ({marks})",
                 (it["root_id"], *paths))


def _finish_roots(conn, roots: set[int]) -> None:
    from .catalog import update_folder_totals

    for rid in roots:
        update_folder_totals(conn, rid)
    conn.commit()


def _run_file_op(conn, payload, chosen):
    out, roots = [], set()
    for n, it in enumerate(payload["items"]):
        if n not in chosen:
            out.append(_skip(n, "沒有勾選"))
            continue
        res = _relocate(conn, it, it["from"], it["to"], (it["size"], it["mtime"]))
        if res["status"] == "done":
            roots.add(it["root_id"])
            conn.commit()  # 每搬一個就存一次：中途當機或拔掉，目錄和硬碟仍然一致
        out.append({"index": n, **res})
    _finish_roots(conn, roots)
    return {"items": out}


_RUN = {"label": _run_label, "smart_folder": _run_smart, "mark_delete": _run_mark, "move": _run_file_op,
        "rename": _run_file_op, "to_pending": _run_file_op}


# ---- 復原 ----

def undo(conn: sqlite3.Connection, action_id: int) -> dict:
    """把做過的動作還原。檔案搬回原位前同樣先驗證；原位已經有東西的那一項就不動並說明。"""
    with _lock:
        r = conn.execute("SELECT * FROM assistant_actions WHERE id = ?", (int(action_id),)).fetchone()
        if r is None:
            raise ActionError("找不到這個動作")
        if r["state"] not in ("done", "partial"):
            raise ActionError("這個動作沒有執行過，或已經復原了")
        payload = json.loads(r["payload"])
        result = json.loads(r["result"] or "{}")
        kind = r["kind"]
        problems = []
        if kind == "smart_folder":
            from .find import delete_smart_folder

            if result.get("smart_id"):
                delete_smart_folder(conn, result["smart_id"])
        else:
            roots, created = set(), {}
            for x in result.get("items") or []:
                if x.get("status") != "done":
                    continue
                it = payload["items"][x["index"]]
                if kind == "label":
                    from .catalog import set_labels

                    set_labels(conn, [it["id"]] if it["type"] == "file" else [], [it["id"]] if it["type"] == "folder" else [],
                               x.get("before"))
                elif kind == "mark_delete":
                    if x.get("mark_id"):
                        conn.execute("DELETE FROM delete_marks WHERE id = ?", (x["mark_id"],))
                else:
                    back = _relocate(conn, it, it["to"], it["from"], (it["size"], it["mtime"]))
                    if back["status"] == "done":
                        roots.add(it["root_id"])
                        created.setdefault(it["root_id"], []).extend(x.get("created") or [])
                        x["status"] = "undone"
                        conn.commit()
                    else:
                        problems.append(f"{it['name']}：{back['reason']}")
                        x["undo_reason"] = back["reason"]
                        continue
                x["status"] = "undone"
            for rid, rels in created.items():  # 全部搬回去之後，再拿掉當初為了搬檔案建立、現在空了的資料夾
                root = _root_path(conn, rid)
                if root is not None:
                    _remove_empty(root, rels)
                    _drop_empty_folders(conn, rid, rels, root)
            _finish_roots(conn, roots)
        result["undo_problems"] = problems
        state = "undone" if not problems else "partial"
        result["message"] = "已復原" if not problems else f"復原了一部分；{len(problems)} 項沒辦法搬回原位"
        conn.execute("UPDATE assistant_actions SET state = ?, result = ?, undone_at = ? WHERE id = ?",
                     (state, json.dumps(result, ensure_ascii=False), db.now_iso(), r["id"]))
        conn.commit()
        return get(conn, r["id"])


def _drop_empty_folders(conn, root_id: int, created: list[str], root: Path) -> None:
    """目錄裡也拿掉剛剛在硬碟上移除的空資料夾。"""
    for rel in sorted(created, key=lambda p: p.count("/"), reverse=True):
        if not (root / rel).exists():
            conn.execute("DELETE FROM folders WHERE root_id = ? AND path = ? AND NOT EXISTS "
                         "(SELECT 1 FROM files WHERE folder_id = folders.id)", (root_id, rel))


__all__ = ["propose", "run", "undo", "dismiss", "get", "history", "ActionError", "LEVEL", "PENDING_DIR", "FILE_OPS"]
