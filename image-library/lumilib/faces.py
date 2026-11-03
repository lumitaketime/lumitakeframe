"""人臉辨識：InsightFace 模型（SCRFD 偵測 + ArcFace 特徵），以 onnxruntime 在本機執行。

- 不需要編譯 insightface 套件；直接下載官方模型檔（只保留偵測與特徵兩個檔案）。
- 臉部特徵（512 維向量）只存在本機資料庫，可在設定頁一鍵全部刪除。
- 分群：與既有人物的平均特徵比對，相似度超過門檻就歸入；新出現且次數夠多的臉成為新人物。
- InsightFace 預訓練模型授權僅限非商業研究用途。
"""

from __future__ import annotations

import io
import shutil
import sqlite3
import threading
import urllib.request
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np
from PIL import Image

from . import db
from .config import Config
from .media import MediaError, load_image

FACE_MODELS = {
    "buffalo_l": {
        "label": "buffalo_l（準確，推薦）",
        "url": "https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_l.zip",
        "download_mb": 289,
        "disk_mb": 191,
        "det": "det_10g.onnx",
        "rec": "w600k_r50.onnx",
        "note": "辨識最準，M1 每張約 0.05–0.1 秒，十萬張約 2–3 小時。",
    },
    "buffalo_s": {
        "label": "buffalo_s（輕量）",
        "url": "https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_s.zip",
        "download_mb": 128,
        "disk_mb": 16,
        "det": "det_500m.onnx",
        "rec": "w600k_mbf.onnx",
        "note": "檔案小、速度快，側臉與小臉較容易漏掉。",
    },
}

# ArcFace 標準 112×112 對齊位置：左眼、右眼、鼻尖、左嘴角、右嘴角
ARCFACE_DST = np.array(
    [[38.2946, 51.6963], [73.5318, 51.5014], [56.0252, 71.7366], [41.5493, 92.3655], [70.7299, 92.2041]],
    dtype=np.float32,
)

DET_SIZE = 640
LOAD_SIDE = 1600  # 讀圖尺寸：團體照的小臉也偵測得到


# ---- 模型檔案 -----------------------------------------------------------------

def model_dir(cfg: Config, name: str) -> Path:
    return cfg.home / "models" / name


def model_installed(cfg: Config, name: str) -> bool:
    info = FACE_MODELS.get(name)
    return bool(info) and all((model_dir(cfg, name) / info[k]).exists() for k in ("det", "rec"))


def download_model(cfg: Config, name: str, progress: Callable[[str, int, int], None] | None = None,
                   stop: threading.Event | None = None) -> None:
    info = FACE_MODELS[name]
    target = model_dir(cfg, name)
    target.mkdir(parents=True, exist_ok=True)
    tmp = target / "download.zip.part"
    with urllib.request.urlopen(info["url"], timeout=60) as resp, open(tmp, "wb") as out:
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        while True:
            if stop is not None and stop.is_set():
                out.close()
                tmp.unlink(missing_ok=True)
                return
            chunk = resp.read(1 << 20)
            if not chunk:
                break
            out.write(chunk)
            done += len(chunk)
            if progress:
                progress(f"下載 {name}", done, total)
    with zipfile.ZipFile(tmp) as zf:
        for member in zf.namelist():
            base = Path(member).name
            if base in (info["det"], info["rec"]):
                with zf.open(member) as src, open(target / base, "wb") as dst:
                    shutil.copyfileobj(src, dst)
    tmp.unlink(missing_ok=True)
    if not model_installed(cfg, name):
        raise RuntimeError("下載的檔案不完整，請重試")


def delete_model(cfg: Config, name: str) -> None:
    shutil.rmtree(model_dir(cfg, name), ignore_errors=True)


# ---- 偵測與特徵 -----------------------------------------------------------------

def _nms(boxes: np.ndarray, scores: np.ndarray, thresh: float = 0.4) -> list[int]:
    x1, y1, x2, y2 = boxes.T
    areas = (x2 - x1 + 1) * (y2 - y1 + 1)
    order = scores.argsort()[::-1]
    keep = []
    while order.size:
        i = order[0]
        keep.append(int(i))
        xx1 = np.maximum(x1[i], x1[order[1:]])
        yy1 = np.maximum(y1[i], y1[order[1:]])
        xx2 = np.minimum(x2[i], x2[order[1:]])
        yy2 = np.minimum(y2[i], y2[order[1:]])
        inter = np.maximum(0.0, xx2 - xx1 + 1) * np.maximum(0.0, yy2 - yy1 + 1)
        iou = inter / (areas[i] + areas[order[1:]] - inter)
        order = order[np.where(iou <= thresh)[0] + 1]
    return keep


def similarity_transform(src: np.ndarray, dst: np.ndarray) -> np.ndarray:
    """Umeyama：回傳把 src 對到 dst 的 3×3 相似變換矩陣。"""
    n, dim = src.shape
    src_mean, dst_mean = src.mean(0), dst.mean(0)
    src_d, dst_d = src - src_mean, dst - dst_mean
    a = dst_d.T @ src_d / n
    d = np.ones(dim)
    if np.linalg.det(a) < 0:
        d[-1] = -1
    t = np.eye(dim + 1)
    u, s, vt = np.linalg.svd(a)
    t[:dim, :dim] = u @ np.diag(d) @ vt
    scale = 1.0 / src_d.var(0).sum() * (s @ d)
    t[:dim, dim] = dst_mean - scale * (t[:dim, :dim] @ src_mean)
    t[:dim, :dim] *= scale
    return t


def align_face(img: Image.Image, kps: np.ndarray) -> Image.Image:
    t = similarity_transform(kps.astype(np.float64), ARCFACE_DST.astype(np.float64))
    inv = np.linalg.inv(t)[:2]  # Pillow 需要「輸出座標 → 輸入座標」
    return img.transform((112, 112), Image.Transform.AFFINE, data=tuple(inv.flatten()), resample=Image.Resampling.BILINEAR)


@dataclass
class Face:
    box: tuple[float, float, float, float]  # 原圖像素座標
    score: float
    kps: np.ndarray
    embedding: np.ndarray | None = None


class FaceEngine:
    def __init__(self, det_path: Path, rec_path: Path):
        import onnxruntime as ort

        opts = ort.SessionOptions()
        opts.log_severity_level = 3
        providers = ["CPUExecutionProvider"]
        self.det = ort.InferenceSession(str(det_path), opts, providers=providers)
        self.rec = ort.InferenceSession(str(rec_path), opts, providers=providers)
        self.det_input = self.det.get_inputs()[0].name
        self.rec_input = self.rec.get_inputs()[0].name
        self._centers: dict[int, np.ndarray] = {}

    @classmethod
    def load(cls, cfg: Config, name: str) -> "FaceEngine":
        info = FACE_MODELS[name]
        if not model_installed(cfg, name):
            raise MediaError(f"人臉模型 {name} 尚未下載，請到設定頁下載")
        return cls(model_dir(cfg, name) / info["det"], model_dir(cfg, name) / info["rec"])

    def _anchor_centers(self, stride: int) -> np.ndarray:
        if stride not in self._centers:
            size = DET_SIZE // stride
            grid = np.stack(np.mgrid[:size, :size][::-1], axis=-1).astype(np.float32)
            centers = (grid * stride).reshape(-1, 2)
            self._centers[stride] = np.stack([centers] * 2, axis=1).reshape(-1, 2)
        return self._centers[stride]

    def detect(self, img: Image.Image, threshold: float = 0.5) -> list[Face]:
        w, h = img.size
        if h / w > 1:
            new_h, new_w = DET_SIZE, max(1, int(DET_SIZE * w / h))
        else:
            new_w, new_h = DET_SIZE, max(1, int(DET_SIZE * h / w))
        scale = new_h / h
        canvas = np.zeros((DET_SIZE, DET_SIZE, 3), dtype=np.float32)
        canvas[:new_h, :new_w] = np.asarray(img.resize((new_w, new_h), Image.Resampling.BILINEAR), dtype=np.float32)
        blob = ((canvas - 127.5) / 128.0).transpose(2, 0, 1)[None]
        outs = self.det.run(None, {self.det_input: blob})
        boxes, scores, kpss = [], [], []
        for i, stride in enumerate((8, 16, 32)):
            sc = outs[i][:, 0]
            pos = np.where(sc >= threshold)[0]
            if not pos.size:
                continue
            centers = self._anchor_centers(stride)[pos]
            d = outs[i + 3][pos] * stride
            k = outs[i + 6][pos] * stride
            boxes.append(np.stack([centers[:, 0] - d[:, 0], centers[:, 1] - d[:, 1],
                                   centers[:, 0] + d[:, 2], centers[:, 1] + d[:, 3]], axis=1))
            kpss.append(np.stack([centers[:, j % 2] + k[:, j] for j in range(10)], axis=1).reshape(-1, 5, 2))
            scores.append(sc[pos])
        if not boxes:
            return []
        boxes_a = np.concatenate(boxes) / scale
        scores_a = np.concatenate(scores)
        kpss_a = np.concatenate(kpss) / scale
        return [
            Face(tuple(float(v) for v in boxes_a[i]), float(scores_a[i]), kpss_a[i])
            for i in _nms(boxes_a, scores_a)
        ]

    def embed(self, img: Image.Image, faces: list[Face]) -> None:
        if not faces:
            return
        batch = np.stack([
            (np.asarray(align_face(img, f.kps), dtype=np.float32) - 127.5) / 127.5 for f in faces
        ]).transpose(0, 3, 1, 2)
        feats = []
        for i in range(len(faces)):  # 部分模型的 batch 維度固定為 1
            feats.append(self.rec.run(None, {self.rec_input: batch[i:i + 1]})[0][0])
        for f, v in zip(faces, feats):
            f.embedding = (v / (np.linalg.norm(v) or 1.0)).astype(np.float32)

    def analyze(self, img: Image.Image, min_score: float = 0.6, min_size: int = 36) -> list[Face]:
        faces = [
            f for f in self.detect(img, threshold=0.5)
            if f.score >= min_score and min(f.box[2] - f.box[0], f.box[3] - f.box[1]) >= min_size
        ]
        self.embed(img, faces)
        return faces


# ---- 圖庫整合 -------------------------------------------------------------------

def face_thumb_path(cfg: Config, face_id: int) -> Path:
    return cfg.thumbs_dir / "faces" / f"{face_id // 1000}" / f"{face_id}.webp"


def save_face_thumb(cfg: Config, img: Image.Image, face_id: int, box) -> None:
    x1, y1, x2, y2 = box
    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
    half = max(x2 - x1, y2 - y1) * 0.8
    crop = img.crop((int(cx - half), int(cy - half), int(cx + half), int(cy + half)))
    crop.thumbnail((192, 192), Image.Resampling.LANCZOS)
    target = face_thumb_path(cfg, face_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    buf = io.BytesIO()
    crop.save(buf, "WEBP", quality=80)
    target.write_bytes(buf.getvalue())


@dataclass
class FaceResult:
    scanned: int = 0
    faces: int = 0
    failed: int = 0
    people_new: int = 0
    assigned: int = 0
    errors: list[str] = field(default_factory=list)


def detect_faces(conn: sqlite3.Connection, cfg: Config, engine: FaceEngine | None = None,
                 progress: Callable[[int, int, str], None] | None = None,
                 stop: threading.Event | None = None, ids: list[int] | None = None) -> FaceResult:
    """偵測尚未處理的照片（影片略過）。"""
    engine = engine or FaceEngine.load(cfg, cfg.face_model)
    result = FaceResult()
    where = "status = 'ok' AND media_type = 'photo' AND (faces_at IS NULL OR faces_model IS NOT ?)"
    params: list = [cfg.face_model]
    if ids:
        where += f" AND id IN ({','.join('?' * len(ids))})"
        params += [int(i) for i in ids]
    rows = conn.execute(f"SELECT * FROM images WHERE {where} ORDER BY sort_at DESC", params).fetchall()
    total = len(rows)
    for index, image in enumerate(rows, 1):
        if stop is not None and stop.is_set():
            break
        path = db.absolute_path(conn, image)
        if not path.exists():
            continue
        try:
            img = load_image(path, "photo", bool(image["is_raw"]), LOAD_SIDE, None, image["orientation"])
            img.thumbnail((LOAD_SIDE, LOAD_SIDE))
            faces = engine.analyze(img)
        except (MediaError, OSError, ValueError) as exc:
            result.failed += 1
            result.errors.append(f"{image['rel_path']}: {exc}")
            conn.execute("UPDATE images SET faces_at = ?, faces_model = ? WHERE id = ?", (db.now_iso(), cfg.face_model, image["id"]))
            continue
        _clear_image_faces(conn, cfg, image["id"])
        w, h = img.size
        for f in faces:
            x1, y1, x2, y2 = f.box
            cur = conn.execute(
                "INSERT INTO faces (image_id, x1, y1, x2, y2, score, embedding, model, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (image["id"], max(0, x1 / w), max(0, y1 / h), min(1, x2 / w), min(1, y2 / h), f.score,
                 f.embedding.tobytes(), cfg.face_model, db.now_iso()),
            )
            save_face_thumb(cfg, img, cur.lastrowid, f.box)
        conn.execute("UPDATE images SET faces_at = ?, faces_model = ? WHERE id = ?", (db.now_iso(), cfg.face_model, image["id"]))
        result.scanned += 1
        result.faces += len(faces)
        if index % 20 == 0:
            conn.commit()
        if progress:
            progress(index, total, f"{image['rel_path']}（{len(faces)} 張臉）")
    conn.commit()
    return result


def _clear_image_faces(conn: sqlite3.Connection, cfg: Config, image_id: int) -> None:
    for row in conn.execute("SELECT id FROM faces WHERE image_id = ?", (image_id,)).fetchall():
        face_thumb_path(cfg, row["id"]).unlink(missing_ok=True)
    conn.execute("DELETE FROM faces WHERE image_id = ?", (image_id,))


def _vec(blob: bytes) -> np.ndarray:
    return np.frombuffer(blob, dtype=np.float32)


def cluster_faces(conn: sqlite3.Connection, cfg: Config, progress=None, stop=None) -> FaceResult:
    """把還沒歸屬的臉分到既有人物，或建立新人物。"""
    result = FaceResult()
    threshold = cfg.face_similarity / 100
    model = cfg.face_model

    # 既有人物的平均特徵
    sums: list[np.ndarray] = []
    counts: list[int] = []
    owners: list[int | None] = []  # person_id；None 代表尚未成為人物的暫時群組
    members: list[list[int]] = []
    for person in conn.execute("SELECT id FROM persons").fetchall():
        vecs = [_vec(r["embedding"]) for r in conn.execute(
            "SELECT embedding FROM faces WHERE person_id = ? AND model = ?", (person["id"], model))]
        if not vecs:
            continue
        sums.append(np.sum(vecs, axis=0))
        counts.append(len(vecs))
        owners.append(person["id"])
        members.append([])

    pending = conn.execute(
        "SELECT id, embedding FROM faces WHERE person_id IS NULL AND excluded = 0 AND model = ? ORDER BY score DESC",
        (model,),
    ).fetchall()
    centroids = np.array([s / np.linalg.norm(s) for s in sums], dtype=np.float32).reshape(-1, 512)
    for n, row in enumerate(pending, 1):
        if stop is not None and stop.is_set():
            break
        v = _vec(row["embedding"])
        best = -1
        if len(centroids):
            sims = centroids @ v
            best = int(sims.argmax())
            if sims[best] < threshold:
                best = -1
        if best == -1:
            sums.append(v.copy())
            counts.append(1)
            owners.append(None)
            members.append([row["id"]])
            centroids = np.vstack([centroids, v[None]]) if len(centroids) else v[None].copy()
        else:
            sums[best] = sums[best] + v
            counts[best] += 1
            members[best].append(row["id"])
            centroids[best] = sums[best] / np.linalg.norm(sums[best])
        if progress and n % 500 == 0:
            progress(n, len(pending), f"分群中 {n}/{len(pending)}")

    now = db.now_iso()
    touched_images: set[int] = set()
    for owner, ids, cnt in zip(owners, members, counts):
        if not ids:
            continue
        if owner is None:
            if cnt < cfg.face_min_faces:
                continue  # 次數太少，先不建立人物，之後可能再歸入
            owner = conn.execute("INSERT INTO persons (created_at, updated_at) VALUES (?, ?)", (now, now)).lastrowid
            result.people_new += 1
        conn.executemany("UPDATE faces SET person_id = ? WHERE id = ?", [(owner, i) for i in ids])
        result.assigned += len(ids)
        touched_images.update(r[0] for r in conn.execute(
            f"SELECT image_id FROM faces WHERE id IN ({','.join('?' * len(ids))})", ids))
    refresh_covers(conn)
    for image_id in touched_images:
        db.refresh_search_text(conn, image_id)
    conn.commit()
    return result


def refresh_covers(conn: sqlite3.Connection) -> None:
    """沒有指定封面的人物，用分數最高的臉。"""
    conn.execute(
        """UPDATE persons SET cover_face_id = (
               SELECT f.id FROM faces f WHERE f.person_id = persons.id ORDER BY f.score DESC LIMIT 1)
           WHERE cover_face_id IS NULL
              OR cover_face_id NOT IN (SELECT id FROM faces WHERE person_id = persons.id)"""
    )
    conn.execute("DELETE FROM persons WHERE id NOT IN (SELECT DISTINCT person_id FROM faces WHERE person_id IS NOT NULL)")


def recluster(conn: sqlite3.Connection, cfg: Config, progress=None, stop=None) -> FaceResult:
    """重新分群：保留已命名的人物與手動指定，其餘重新計算。"""
    conn.execute(
        "UPDATE faces SET person_id = NULL WHERE manual = 0 AND person_id IN (SELECT id FROM persons WHERE name IS NULL OR name = '')"
    )
    conn.execute("DELETE FROM persons WHERE (name IS NULL OR name = '') AND id NOT IN (SELECT DISTINCT person_id FROM faces WHERE person_id IS NOT NULL)")
    return cluster_faces(conn, cfg, progress, stop)


def clear_all(conn: sqlite3.Connection, cfg: Config) -> int:
    n = conn.execute("SELECT COUNT(*) FROM faces").fetchone()[0]
    conn.execute("DELETE FROM faces")
    conn.execute("DELETE FROM persons")
    conn.execute("UPDATE images SET faces_at = NULL, faces_model = NULL")
    shutil.rmtree(cfg.thumbs_dir / "faces", ignore_errors=True)
    for row in conn.execute("SELECT id FROM images WHERE search_text LIKE '%'").fetchall():
        db.refresh_search_text(conn, row["id"])
    conn.commit()
    return n


# ---- 人物操作 -------------------------------------------------------------------

def _refresh_person_images(conn: sqlite3.Connection, person_id: int) -> None:
    for row in conn.execute("SELECT DISTINCT image_id FROM faces WHERE person_id = ?", (person_id,)).fetchall():
        db.refresh_search_text(conn, row["image_id"])


def rename_person(conn: sqlite3.Connection, person_id: int, name: str) -> None:
    conn.execute("UPDATE persons SET name = ?, updated_at = ? WHERE id = ?", (name.strip() or None, db.now_iso(), person_id))
    _refresh_person_images(conn, person_id)
    conn.commit()


def merge_persons(conn: sqlite3.Connection, target: int, sources: list[int]) -> None:
    sources = [int(s) for s in sources if int(s) != int(target)]
    if not sources:
        return
    marks = ",".join("?" * len(sources))
    name = conn.execute("SELECT name FROM persons WHERE id = ?", (target,)).fetchone()
    if name is not None and not name["name"]:  # 目標沒名字時沿用來源的名字
        other = conn.execute(f"SELECT name FROM persons WHERE id IN ({marks}) AND name IS NOT NULL AND name != '' LIMIT 1", sources).fetchone()
        if other:
            conn.execute("UPDATE persons SET name = ? WHERE id = ?", (other["name"], target))
    conn.execute(f"UPDATE faces SET person_id = ? WHERE person_id IN ({marks})", [target, *sources])
    conn.execute(f"DELETE FROM persons WHERE id IN ({marks})", sources)
    refresh_covers(conn)
    _refresh_person_images(conn, target)
    conn.commit()


def assign_face(conn: sqlite3.Connection, face_id: int, person_id: int | None, new_name: str | None = None) -> int | None:
    """手動指定或移除：person_id=None 代表「不是這個人」，之後自動分群也不會再歸入。"""
    old = conn.execute("SELECT person_id, image_id FROM faces WHERE id = ?", (face_id,)).fetchone()
    if old is None:
        raise ValueError("找不到這張臉")
    if new_name:
        now = db.now_iso()
        person_id = conn.execute("INSERT INTO persons (name, created_at, updated_at) VALUES (?, ?, ?)",
                                 (new_name.strip(), now, now)).lastrowid
    conn.execute(
        "UPDATE faces SET person_id = ?, manual = 1, excluded = ? WHERE id = ?",
        (person_id, 1 if person_id is None else 0, face_id),
    )
    refresh_covers(conn)
    db.refresh_search_text(conn, old["image_id"])
    conn.commit()
    return person_id


def remove_images_from_person(conn: sqlite3.Connection, person_id: int, image_ids: list[int]) -> int:
    rows = conn.execute(
        f"SELECT id FROM faces WHERE person_id = ? AND image_id IN ({','.join('?' * len(image_ids))})",
        [person_id, *[int(i) for i in image_ids]],
    ).fetchall()
    for r in rows:
        conn.execute("UPDATE faces SET person_id = NULL, manual = 1, excluded = 1 WHERE id = ?", (r["id"],))
    for i in image_ids:
        db.refresh_search_text(conn, int(i))
    refresh_covers(conn)
    conn.commit()
    return len(rows)


def list_persons(conn: sqlite3.Connection, include_hidden: bool = False, min_count: int = 1) -> list[dict]:
    rows = conn.execute(
        f"""SELECT p.*, COUNT(DISTINCT f.image_id) AS count
            FROM persons p JOIN faces f ON f.person_id = p.id JOIN images i ON i.id = f.image_id AND i.status = 'ok'
            {'' if include_hidden else 'WHERE p.hidden = 0'}
            GROUP BY p.id HAVING count >= ?
            ORDER BY (p.name IS NULL OR p.name = ''), count DESC""",
        (min_count,),
    ).fetchall()
    return [dict(r) for r in rows]
