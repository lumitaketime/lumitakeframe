"""寵物辨識：找出照片裡的貓狗，認出是哪一隻，像「人物」一樣分組、命名。

- 偵測：YOLOX（Apache-2.0，COCO 資料集訓練，認得貓與狗），onnxruntime 在本機執行。
- 認出是哪一隻：DINOv2（Apache-2.0）把每隻動物的裁切圖變成特徵向量；毛色、花紋、臉型越像，向量越接近。
- 分群方式與人物相同：先比對已有的寵物，相似度夠高就歸入，否則成為新的候選；
  出現兩次以上才建立寵物，避免路邊偶遇的貓狗佔滿畫面。
- 只在這台電腦上計算；特徵與裁切縮圖都存在本機，可一鍵刪除。
"""

from __future__ import annotations

import io
import shutil
import sqlite3
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np
from PIL import Image, ImageOps

from . import db, net
from .config import Config
from .media import MediaError, load_image

YOLOX = "https://github.com/Megvii-BaseDetection/YOLOX/releases/download/0.1.1rc0"
HF = "https://huggingface.co"

# 偵測模型與特徵模型的組合；下載的檔案存在 models/pets/<名稱>/
PET_MODELS = {
    "standard": {
        "label": "標準（建議）",
        "note": "YOLOX-S 偵測＋DINOv2-small 特徵。速度與準確度平衡，M1 約每張 0.1–0.2 秒。",
        "det": {"file": "det.onnx", "urls": [f"{YOLOX}/yolox_s.onnx"], "size": 640, "mb": 36},
        "emb": {"file": "emb.onnx", "urls": [
            f"{HF}/onnx-community/dinov2-small/resolve/main/onnx/model.onnx",
            f"{HF}/Xenova/dinov2-small/resolve/main/onnx/model.onnx",
        ], "mb": 88},
    },
    "fast": {
        "label": "快速",
        "note": "YOLOX-Tiny 偵測＋DINOv2-small 特徵。偵測比較快，遠處或被遮住的貓狗可能漏掉。",
        "det": {"file": "det.onnx", "urls": [f"{YOLOX}/yolox_tiny.onnx"], "size": 416, "mb": 20},
        "emb": {"file": "emb.onnx", "urls": [
            f"{HF}/onnx-community/dinov2-small/resolve/main/onnx/model.onnx",
            f"{HF}/Xenova/dinov2-small/resolve/main/onnx/model.onnx",
        ], "mb": 88},
    },
    "accurate": {
        "label": "精準",
        "note": "YOLOX-M 偵測＋DINOv2-base 特徵。分辨同品種、花色相近的毛孩比較準，速度約慢 3 倍。",
        "det": {"file": "det.onnx", "urls": [f"{YOLOX}/yolox_m.onnx"], "size": 640, "mb": 97},
        "emb": {"file": "emb.onnx", "urls": [
            f"{HF}/onnx-community/dinov2-base/resolve/main/onnx/model.onnx",
            f"{HF}/Xenova/dinov2-base/resolve/main/onnx/model.onnx",
        ], "mb": 346},
    },
}

# COCO 類別編號
KINDS = {15: "cat", 16: "dog"}
KIND_LABELS = {"cat": "貓", "dog": "狗"}
LOAD_SIDE = 1280
EMB_SIZE = 224
MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


def model_dir(cfg: Config, name: str) -> Path:
    return cfg.home / "models" / "pets" / name


def model_installed(cfg: Config, name: str) -> bool:
    info = PET_MODELS.get(name)
    return bool(info) and all((model_dir(cfg, name) / info[k]["file"]).exists() for k in ("det", "emb"))


def models_status(cfg: Config) -> list[dict]:
    return [
        {"name": k, "label": v["label"], "note": v["note"], "download_mb": v["det"]["mb"] + v["emb"]["mb"],
         "installed": model_installed(cfg, k), "active": k == cfg.pet_model}
        for k, v in PET_MODELS.items()
    ]


def _fetch(urls: list[str], target: Path, label: str, progress, stop, base: int, grand: int) -> int:
    """依序嘗試網址，下載到 target；回傳下載的位元組數。"""
    last: Exception | None = None
    for url in urls:
        tmp = target.with_suffix(".part")
        try:
            with net.urlopen(url, timeout=60) as resp, open(tmp, "wb") as out:
                done = 0
                while True:
                    if stop is not None and stop.is_set():
                        out.close()
                        tmp.unlink(missing_ok=True)
                        return done
                    chunk = resp.read(1 << 20)
                    if not chunk:
                        break
                    out.write(chunk)
                    done += len(chunk)
                    if progress:
                        progress(label, base + done, grand)
            if done < 100_000:
                raise RuntimeError("下載的檔案太小")
            tmp.replace(target)
            return done
        except Exception as exc:  # noqa: BLE001 - 換下一個網址
            last = exc
            tmp.unlink(missing_ok=True)
    raise RuntimeError(f"{label}失敗：{net.describe_error(last) if last else '沒有可用的網址'}")


def download_model(cfg: Config, name: str, progress: Callable[[str, int, int], None] | None = None,
                   stop: threading.Event | None = None) -> None:
    info = PET_MODELS.get(name)
    if info is None:
        raise ValueError("未知的寵物模型")
    target = model_dir(cfg, name)
    target.mkdir(parents=True, exist_ok=True)
    grand = (info["det"]["mb"] + info["emb"]["mb"]) * 1_000_000
    done = 0
    for key, label in (("det", "下載偵測模型"), ("emb", "下載特徵模型")):
        path = target / info[key]["file"]
        if path.exists():
            done += path.stat().st_size
            continue
        done += _fetch(info[key]["urls"], path, label, progress, stop, done, grand)
        if stop is not None and stop.is_set():
            return
    if not model_installed(cfg, name):
        raise RuntimeError("下載的檔案不完整，請重試")


def delete_model(cfg: Config, name: str) -> None:
    shutil.rmtree(model_dir(cfg, name), ignore_errors=True)


# ---- 偵測與特徵 -----------------------------------------------------------------

def _nms(boxes: np.ndarray, scores: np.ndarray, thresh: float = 0.45) -> list[int]:
    x1, y1, x2, y2 = boxes.T
    areas = (x2 - x1) * (y2 - y1)
    order = scores.argsort()[::-1]
    keep: list[int] = []
    while order.size:
        i = int(order[0])
        keep.append(i)
        xx1 = np.maximum(x1[i], x1[order[1:]])
        yy1 = np.maximum(y1[i], y1[order[1:]])
        xx2 = np.minimum(x2[i], x2[order[1:]])
        yy2 = np.minimum(y2[i], y2[order[1:]])
        inter = np.maximum(0, xx2 - xx1) * np.maximum(0, yy2 - yy1)
        iou = inter / (areas[i] + areas[order[1:]] - inter + 1e-9)
        order = order[1:][iou <= thresh]
    return keep


@dataclass
class Animal:
    kind: str
    box: tuple[float, float, float, float]  # 原圖像素座標
    score: float
    embedding: np.ndarray | None = None


class PetEngine:
    def __init__(self, det_path: Path, emb_path: Path, det_size: int):
        import onnxruntime as ort

        opts = ort.SessionOptions()
        opts.log_severity_level = 3
        providers = ["CPUExecutionProvider"]
        self.det = ort.InferenceSession(str(det_path), opts, providers=providers)
        self.emb = ort.InferenceSession(str(emb_path), opts, providers=providers)
        self.det_input = self.det.get_inputs()[0].name
        self.emb_input = self.emb.get_inputs()[0].name
        names = [o.name for o in self.emb.get_outputs()]
        self.emb_output = "pooler_output" if "pooler_output" in names else names[0]
        self.size = det_size
        self._grid = self._make_grid(det_size)

    @classmethod
    def load(cls, cfg: Config, name: str | None = None) -> "PetEngine":
        name = name or cfg.pet_model
        info = PET_MODELS.get(name)
        if info is None or not model_installed(cfg, name):
            raise MediaError("寵物辨識模型尚未下載，請到「設定 → 寵物辨識」下載")
        d = model_dir(cfg, name)
        return cls(d / info["det"]["file"], d / info["emb"]["file"], info["det"]["size"])

    @staticmethod
    def _make_grid(size: int) -> tuple[np.ndarray, np.ndarray]:
        grids, strides = [], []
        for stride in (8, 16, 32):
            n = size // stride
            yv, xv = np.meshgrid(np.arange(n), np.arange(n), indexing="ij")
            grids.append(np.stack((xv, yv), 2).reshape(-1, 2))
            strides.append(np.full((n * n, 1), stride))
        return np.concatenate(grids).astype(np.float32), np.concatenate(strides).astype(np.float32)

    def detect(self, img: Image.Image, threshold: float = 0.4) -> list[Animal]:
        """YOLOX：等比例縮放貼在左上角（其餘填灰），輸入 BGR 0–255。"""
        w, h = img.size
        r = min(self.size / w, self.size / h)
        nw, nh = max(1, int(w * r)), max(1, int(h * r))
        canvas = np.full((self.size, self.size, 3), 114, dtype=np.float32)
        canvas[:nh, :nw] = np.asarray(img.convert("RGB").resize((nw, nh), Image.Resampling.BILINEAR), dtype=np.float32)
        blob = canvas[:, :, ::-1].transpose(2, 0, 1)[None].copy()
        out = self.det.run(None, {self.det_input: blob})[0][0]
        grid, stride = self._grid
        if out.shape[0] != grid.shape[0]:
            raise MediaError("偵測模型的輸出格式不符")
        xy = (out[:, :2] + grid) * stride
        wh = np.exp(np.clip(out[:, 2:4], -10, 10)) * stride
        boxes = np.concatenate([xy - wh / 2, xy + wh / 2], axis=1) / r
        found: list[Animal] = []
        for cls_id, kind in KINDS.items():
            scores = out[:, 4] * out[:, 5 + cls_id]
            pos = np.where(scores >= threshold)[0]
            if not pos.size:
                continue
            b, s = boxes[pos], scores[pos]
            for i in _nms(b, s):
                x1, y1, x2, y2 = b[i]
                found.append(Animal(kind, (max(0.0, float(x1)), max(0.0, float(y1)), min(float(w), float(x2)), min(float(h), float(y2))), float(s[i])))
        # 同一隻被同時認成貓和狗時只留分數高的
        found.sort(key=lambda a: -a.score)
        kept: list[Animal] = []
        for a in found:
            if all(_iou(a.box, k.box) < 0.7 for k in kept):
                kept.append(a)
        return kept

    def _prep(self, crop: Image.Image) -> np.ndarray:
        # 補成正方形（不裁掉頭或尾巴）再縮成 224
        crop = ImageOps.pad(crop.convert("RGB"), (EMB_SIZE, EMB_SIZE), Image.Resampling.BICUBIC, color=(124, 116, 104))
        arr = (np.asarray(crop, dtype=np.float32) / 255.0 - MEAN) / STD
        return arr.transpose(2, 0, 1)

    def embed(self, img: Image.Image, animals: list[Animal]) -> None:
        for a in animals:
            x1, y1, x2, y2 = a.box
            mx, my = (x2 - x1) * 0.06, (y2 - y1) * 0.06
            crop = img.crop((int(max(0, x1 - mx)), int(max(0, y1 - my)), int(min(img.width, x2 + mx)), int(min(img.height, y2 + my))))
            vecs = []
            for c in (crop, ImageOps.mirror(crop)):  # 左右翻轉平均，朝向不同也比較穩
                out = self.emb.run([self.emb_output], {self.emb_input: self._prep(c)[None]})[0]
                v = out[0] if out.ndim == 2 else out[0, 0]
                vecs.append(v / (np.linalg.norm(v) or 1.0))
            v = np.mean(vecs, axis=0)
            a.embedding = (v / (np.linalg.norm(v) or 1.0)).astype(np.float32)

    def analyze(self, img: Image.Image, min_score: float = 0.45, min_size: int = 56) -> list[Animal]:
        animals = [
            a for a in self.detect(img)
            if a.score >= min_score and min(a.box[2] - a.box[0], a.box[3] - a.box[1]) >= min_size
        ]
        self.embed(img, animals)
        return animals


def _iou(a, b) -> float:
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


# ---- 圖庫整合 -------------------------------------------------------------------

def thumb_path(cfg: Config, det_id: int) -> Path:
    return cfg.thumbs_dir / "pets" / f"{det_id // 1000}" / f"{det_id}.webp"


def save_thumb(cfg: Config, img: Image.Image, det_id: int, box) -> None:
    x1, y1, x2, y2 = box
    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
    half = max(x2 - x1, y2 - y1) * 0.58
    crop = img.crop((int(cx - half), int(cy - half), int(cx + half), int(cy + half)))
    crop.thumbnail((256, 256), Image.Resampling.LANCZOS)
    target = thumb_path(cfg, det_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    buf = io.BytesIO()
    crop.save(buf, "WEBP", quality=82)
    target.write_bytes(buf.getvalue())


@dataclass
class PetResult:
    scanned: int = 0
    animals: int = 0
    failed: int = 0
    pets_new: int = 0
    assigned: int = 0
    errors: list[str] = field(default_factory=list)


def _clear_image(conn: sqlite3.Connection, cfg: Config, image_id: int) -> None:
    for row in conn.execute("SELECT id FROM pet_detections WHERE image_id = ?", (image_id,)).fetchall():
        thumb_path(cfg, row["id"]).unlink(missing_ok=True)
    conn.execute("DELETE FROM pet_detections WHERE image_id = ?", (image_id,))


def detect_pets(conn: sqlite3.Connection, cfg: Config, engine: PetEngine | None = None,
                progress: Callable[[int, int, str], None] | None = None,
                stop: threading.Event | None = None, ids: list[int] | None = None) -> PetResult:
    """找出尚未處理的照片裡的貓狗（影片略過）。"""
    engine = engine or PetEngine.load(cfg)
    result = PetResult()
    where = "status = 'ok' AND media_type = 'photo' AND (pets_at IS NULL OR pets_model IS NOT ?)"
    params: list = [cfg.pet_model]
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
            animals = engine.analyze(img)
        except (MediaError, OSError, ValueError) as exc:
            result.failed += 1
            result.errors.append(f"{image['rel_path']}: {exc}")
            conn.execute("UPDATE images SET pets_at = ?, pets_model = ? WHERE id = ?", (db.now_iso(), cfg.pet_model, image["id"]))
            continue
        _clear_image(conn, cfg, image["id"])
        w, h = img.size
        for a in animals:
            x1, y1, x2, y2 = a.box
            cur = conn.execute(
                "INSERT INTO pet_detections (image_id, kind, x1, y1, x2, y2, score, embedding, model, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (image["id"], a.kind, x1 / w, y1 / h, x2 / w, y2 / h, a.score, a.embedding.tobytes(), cfg.pet_model, db.now_iso()),
            )
            save_thumb(cfg, img, cur.lastrowid, a.box)
        conn.execute("UPDATE images SET pets_at = ?, pets_model = ? WHERE id = ?", (db.now_iso(), cfg.pet_model, image["id"]))
        result.scanned += 1
        result.animals += len(animals)
        if index % 20 == 0:
            conn.commit()
        if progress:
            label = "、".join(f"{KIND_LABELS[a.kind]}" for a in animals) or "沒有貓狗"
            progress(index, total, f"{image['rel_path']}（{label}）")
    conn.commit()
    return result


def _vec(blob: bytes) -> np.ndarray:
    return np.frombuffer(blob, dtype=np.float32)


def cluster_pets(conn: sqlite3.Connection, cfg: Config, progress=None, stop=None) -> PetResult:
    """把還沒歸屬的貓狗分到既有寵物，或建立新寵物（貓和狗分開比）。"""
    result = PetResult()
    threshold = cfg.pet_similarity / 100
    model = cfg.pet_model
    now = db.now_iso()
    touched: set[int] = set()
    for kind in KINDS.values():
        sums: list[np.ndarray] = []
        counts: list[int] = []
        owners: list[int | None] = []
        members: list[list[int]] = []
        for pet in conn.execute("SELECT id FROM pets WHERE kind = ?", (kind,)).fetchall():
            vecs = [_vec(r["embedding"]) for r in conn.execute(
                "SELECT embedding FROM pet_detections WHERE pet_id = ? AND model = ?", (pet["id"], model))]
            if not vecs:
                continue
            sums.append(np.sum(vecs, axis=0))
            counts.append(len(vecs))
            owners.append(pet["id"])
            members.append([])
        pending = conn.execute(
            "SELECT id, embedding FROM pet_detections WHERE pet_id IS NULL AND excluded = 0 AND model = ? AND kind = ? ORDER BY score DESC",
            (model, kind),
        ).fetchall()
        dim = len(_vec(pending[0]["embedding"])) if pending else (len(sums[0]) if sums else 384)
        centroids = np.array([s / np.linalg.norm(s) for s in sums], dtype=np.float32).reshape(-1, dim)
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
            if progress and n % 200 == 0:
                progress(n, len(pending), f"分群中 {n}/{len(pending)}")
        for owner, ids, cnt in zip(owners, members, counts):
            if not ids:
                continue
            if owner is None:
                if cnt < cfg.pet_min_photos:
                    continue
                owner = conn.execute("INSERT INTO pets (kind, created_at, updated_at) VALUES (?, ?, ?)", (kind, now, now)).lastrowid
                result.pets_new += 1
            conn.executemany("UPDATE pet_detections SET pet_id = ? WHERE id = ?", [(owner, i) for i in ids])
            result.assigned += len(ids)
            touched.update(r[0] for r in conn.execute(
                f"SELECT image_id FROM pet_detections WHERE id IN ({','.join('?' * len(ids))})", ids))
    refresh_covers(conn)
    for image_id in touched:
        db.refresh_search_text(conn, image_id)
    conn.commit()
    return result


def refresh_covers(conn: sqlite3.Connection) -> None:
    conn.execute(
        """UPDATE pets SET cover_id = (
               SELECT d.id FROM pet_detections d WHERE d.pet_id = pets.id ORDER BY d.score DESC LIMIT 1)
           WHERE cover_id IS NULL OR cover_id NOT IN (SELECT id FROM pet_detections WHERE pet_id = pets.id)"""
    )
    conn.execute("DELETE FROM pets WHERE id NOT IN (SELECT DISTINCT pet_id FROM pet_detections WHERE pet_id IS NOT NULL)")


def recluster(conn: sqlite3.Connection, cfg: Config, progress=None, stop=None) -> PetResult:
    """重新分群：保留已命名的寵物與手動指定，其餘重新計算。"""
    conn.execute(
        "UPDATE pet_detections SET pet_id = NULL WHERE manual = 0 AND pet_id IN (SELECT id FROM pets WHERE name IS NULL OR name = '')"
    )
    conn.execute("DELETE FROM pets WHERE (name IS NULL OR name = '') AND id NOT IN (SELECT DISTINCT pet_id FROM pet_detections WHERE pet_id IS NOT NULL)")
    return cluster_pets(conn, cfg, progress, stop)


def clear_all(conn: sqlite3.Connection, cfg: Config) -> int:
    n = conn.execute("SELECT COUNT(*) FROM pet_detections").fetchone()[0]
    ids = [r[0] for r in conn.execute("SELECT DISTINCT image_id FROM pet_detections")]
    conn.execute("DELETE FROM pet_detections")
    conn.execute("DELETE FROM pets")
    conn.execute("UPDATE images SET pets_at = NULL, pets_model = NULL")
    shutil.rmtree(cfg.thumbs_dir / "pets", ignore_errors=True)
    for image_id in ids:
        db.refresh_search_text(conn, image_id)
    conn.commit()
    return n


# ---- 寵物操作 -------------------------------------------------------------------

def list_pets(conn: sqlite3.Connection, include_hidden: bool = False) -> list[dict]:
    rows = conn.execute(
        f"""SELECT p.*, COUNT(DISTINCT d.image_id) AS photos
            FROM pets p JOIN pet_detections d ON d.pet_id = p.id
            {'' if include_hidden else 'WHERE p.hidden = 0'}
            GROUP BY p.id ORDER BY (p.name IS NULL OR p.name = ''), photos DESC"""
    ).fetchall()
    return [{"id": r["id"], "name": r["name"] or "", "kind": r["kind"], "kind_label": KIND_LABELS.get(r["kind"], ""),
             "count": r["photos"], "cover": r["cover_id"], "hidden": bool(r["hidden"])} for r in rows]


def pet_image_ids(conn: sqlite3.Connection, pet_id: int) -> list[int]:
    return [r[0] for r in conn.execute("SELECT DISTINCT image_id FROM pet_detections WHERE pet_id = ?", (pet_id,))]


def _touch(conn: sqlite3.Connection, pet_id: int) -> None:
    for image_id in pet_image_ids(conn, pet_id):
        db.refresh_search_text(conn, image_id)


def rename_pet(conn: sqlite3.Connection, pet_id: int, name: str) -> None:
    conn.execute("UPDATE pets SET name = ?, updated_at = ? WHERE id = ?", (name.strip() or None, db.now_iso(), pet_id))
    _touch(conn, pet_id)
    conn.commit()


def merge_pets(conn: sqlite3.Connection, target: int, sources: list[int]) -> None:
    sources = [s for s in sources if s != target]
    if not sources:
        return
    marks = ",".join("?" * len(sources))
    conn.execute(f"UPDATE pet_detections SET pet_id = ?, manual = 1 WHERE pet_id IN ({marks})", [target, *sources])
    conn.execute(f"DELETE FROM pets WHERE id IN ({marks})", sources)
    refresh_covers(conn)
    _touch(conn, target)
    conn.commit()


def set_hidden(conn: sqlite3.Connection, pet_id: int, hidden: bool) -> None:
    conn.execute("UPDATE pets SET hidden = ?, updated_at = ? WHERE id = ?", (int(hidden), db.now_iso(), pet_id))
    conn.commit()


def remove_images(conn: sqlite3.Connection, pet_id: int, image_ids: list[int]) -> int:
    """這些照片裡的不是這隻：標記排除，之後重新分群也不會再歸進來。"""
    if not image_ids:
        return 0
    marks = ",".join("?" * len(image_ids))
    cur = conn.execute(
        f"UPDATE pet_detections SET pet_id = NULL, excluded = 1 WHERE pet_id = ? AND image_id IN ({marks})", [pet_id, *image_ids]
    )
    refresh_covers(conn)
    for image_id in image_ids:
        db.refresh_search_text(conn, image_id)
    conn.commit()
    return cur.rowcount


def image_pets(conn: sqlite3.Connection, image_id: int) -> list[dict]:
    rows = conn.execute(
        """SELECT d.id, d.kind, d.pet_id, p.name FROM pet_detections d LEFT JOIN pets p ON p.id = d.pet_id
           WHERE d.image_id = ? ORDER BY d.x1""", (image_id,)
    ).fetchall()
    return [{"detection": r["id"], "kind": r["kind"], "kind_label": KIND_LABELS.get(r["kind"], ""),
             "pet_id": r["pet_id"], "name": r["name"] or ""} for r in rows]
