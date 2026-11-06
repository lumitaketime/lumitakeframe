"""多語言 CLIP 圖像搜尋：文字與畫面放進同一個向量空間，「穿紅衣服的小孩」不需要事先有標籤也找得到。

模型使用 Immich 專案在 Hugging Face 上提供的 ONNX 版本（visual/、textual/ 兩個模型），
以 onnxruntime 在本機執行，不需要 PyTorch。圖像特徵從已產生的縮圖計算，不必重新讀原檔。
"""

from __future__ import annotations

import json
import sqlite3
import threading
import urllib.request
from collections import OrderedDict
from pathlib import Path
from typing import Callable

import numpy as np
from PIL import Image

from . import net
from .config import Config
from .media import MediaError, thumb_path

HF = "https://huggingface.co"

CLIP_MODELS = {
    "xlm-roberta-base-vit-b32": {
        "repo": "immich-app/XLM-Roberta-Base-ViT-B-32__laion5b_s13b_b90k",
        "label": "XLM-RoBERTa Base ViT-B/32（多語言，推薦）",
        "multilingual": True,
        "note": "支援中文、英文等多國語言直接搜尋畫面內容，速度快。",
    },
    "xlm-roberta-large-vit-b16plus": {
        "repo": "immich-app/XLM-Roberta-Large-Vit-B-16Plus",
        "label": "XLM-RoBERTa Large ViT-B/16+（多語言，較準）",
        "multilingual": True,
        "note": "準確度較高，下載較大、建立索引較慢。",
    },
    "vit-b32-openai": {
        "repo": "immich-app/ViT-B-32__openai",
        "label": "OpenAI ViT-B/32（英文）",
        "multilingual": False,
        "note": "只懂英文；中文查詢會先由 AI 翻譯成英文再搜尋。檔案最小。",
    },
}

def repo_for(cfg: Config, name: str) -> str | None:
    if name == "custom":
        return cfg.clip_custom_repo.strip() or None
    info = CLIP_MODELS.get(name)
    return info["repo"] if info else None


KEEP_FILES = {
    "": {"config.json"},
    "visual": {"model.onnx", "preprocess_cfg.json"},
    "textual": {"model.onnx", "tokenizer.json", "tokenizer_config.json", "special_tokens_map.json"},
}


def model_dir(cfg: Config, name: str) -> Path:
    return cfg.home / "models" / "clip" / name


def model_installed(cfg: Config, name: str) -> bool:
    d = model_dir(cfg, name)
    return all((d / p).exists() for p in ("visual/model.onnx", "textual/model.onnx", "textual/tokenizer.json"))


def _list_files(repo: str, sub: str) -> list[dict]:
    url = f"{HF}/api/models/{repo}/tree/main" + (f"/{sub}" if sub else "")
    with net.urlopen(url, timeout=30) as resp:
        items = json.loads(resp.read().decode("utf-8"))
    out = []
    for it in items:
        if it.get("type") != "file":
            continue
        name = Path(it["path"]).name
        # 大型模型的權重可能另存在 model.onnx_data 之類的外部檔
        if name in KEEP_FILES[sub] or (name.startswith("model.onnx") and name != "model.onnx" and "." in name):
            size = (it.get("lfs") or {}).get("size") or it.get("size") or 0
            out.append({"path": it["path"], "size": int(size)})
    return out


def download_model(cfg: Config, name: str, progress: Callable[[str, int, int], None] | None = None,
                   stop: threading.Event | None = None) -> None:
    repo = repo_for(cfg, name)
    if not repo:
        raise ValueError("尚未設定自訂圖像搜尋模型的 Hugging Face 儲存庫")
    if name == "custom":  # 換了儲存庫就重新下載
        import shutil

        marker = model_dir(cfg, name) / "repo.txt"
        if marker.exists() and marker.read_text().strip() != repo:
            shutil.rmtree(model_dir(cfg, name), ignore_errors=True)
    target = model_dir(cfg, name)
    files = [f for sub in KEEP_FILES for f in _list_files(repo, sub)]
    total = sum(f["size"] for f in files)
    done = 0
    for f in files:
        dest = target / f["path"]
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists() and f["size"] and dest.stat().st_size == f["size"]:
            done += f["size"]
            continue
        tmp = dest.with_name(dest.name + ".part")
        with net.urlopen(f"{HF}/{repo}/resolve/main/{f['path']}", timeout=60) as resp, open(tmp, "wb") as out:
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
        tmp.replace(dest)
    if not model_installed(cfg, name):
        raise RuntimeError("下載的檔案不完整（這個儲存庫可能不是 Immich 格式），請重試或換一個")
    if name == "custom":
        (target / "repo.txt").write_text(repo)


def delete_model(cfg: Config, name: str) -> None:
    import shutil

    shutil.rmtree(model_dir(cfg, name), ignore_errors=True)


# ---- 模型 ---------------------------------------------------------------------

def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


class ClipModel:
    def __init__(self, directory: Path):
        import onnxruntime as ort
        from tokenizers import Tokenizer

        opts = ort.SessionOptions()
        opts.log_severity_level = 3
        self.visual = ort.InferenceSession(str(directory / "visual" / "model.onnx"), opts, providers=["CPUExecutionProvider"])
        self.textual = ort.InferenceSession(str(directory / "textual" / "model.onnx"), opts, providers=["CPUExecutionProvider"])

        config = _read_json(directory / "config.json")
        pre = _read_json(directory / "visual" / "preprocess_cfg.json")
        size = pre.get("size", 224)
        self.size = int(size[0] if isinstance(size, list) else size)
        self.mean = np.array(pre.get("mean", [0.48145466, 0.4578275, 0.40821073]), dtype=np.float32)
        self.std = np.array(pre.get("std", [0.26862954, 0.26130258, 0.27577711]), dtype=np.float32)
        self.resize_mode = pre.get("resize_mode", "shortest")

        self.context = int((config.get("text_cfg") or {}).get("context_length", 77))
        tok_cfg = _read_json(directory / "textual" / "tokenizer_config.json")
        special = _read_json(directory / "textual" / "special_tokens_map.json")
        pad = tok_cfg.get("pad_token") or special.get("pad_token") or "<pad>"
        if isinstance(pad, dict):
            pad = pad.get("content", "<pad>")
        self.tokenizer = Tokenizer.from_file(str(directory / "textual" / "tokenizer.json"))
        pad_id = self.tokenizer.token_to_id(pad)
        if pad_id is None:
            pad_id = 0
        self.tokenizer.enable_padding(length=self.context, pad_token=pad, pad_id=pad_id)
        self.tokenizer.enable_truncation(max_length=self.context)

        self.visual_input = self.visual.get_inputs()[0].name
        self.text_inputs = self.textual.get_inputs()
        self._text_cache: OrderedDict[str, np.ndarray] = OrderedDict()
        self.lock = threading.Lock()

    @staticmethod
    def _norm(v: np.ndarray) -> np.ndarray:
        v = v.astype(np.float32).reshape(-1)
        return v / (np.linalg.norm(v) or 1.0)

    def preprocess(self, img: Image.Image) -> np.ndarray:
        img = img.convert("RGB")
        s = self.size
        if self.resize_mode == "squash":
            img = img.resize((s, s), Image.Resampling.BICUBIC)
        else:
            w, h = img.size
            scale = s / min(w, h)
            img = img.resize((max(s, round(w * scale)), max(s, round(h * scale))), Image.Resampling.BICUBIC)
            w, h = img.size
            left, top = (w - s) // 2, (h - s) // 2
            img = img.crop((left, top, left + s, top + s))
        arr = (np.asarray(img, dtype=np.float32) / 255.0 - self.mean) / self.std
        return arr.transpose(2, 0, 1)[None]

    def encode_image(self, img: Image.Image) -> np.ndarray:
        with self.lock:
            out = self.visual.run(None, {self.visual_input: self.preprocess(img)})[0]
        return self._norm(out[0])

    def encode_text(self, text: str) -> np.ndarray:
        key = text.strip()
        if key in self._text_cache:
            self._text_cache.move_to_end(key)
            return self._text_cache[key]
        enc = self.tokenizer.encode(key)
        feeds = {}
        for inp in self.text_inputs:
            dtype = np.int64 if "int64" in inp.type else np.int32
            source = enc.attention_mask if "mask" in inp.name.lower() else enc.ids
            feeds[inp.name] = np.array([source], dtype=dtype)
        with self.lock:
            out = self.textual.run(None, feeds)[0]
        vec = self._norm(out[0])
        self._text_cache[key] = vec
        if len(self._text_cache) > 256:
            self._text_cache.popitem(last=False)
        return vec


_models: dict[str, ClipModel] = {}
_models_lock = threading.Lock()


def get_model(cfg: Config, name: str | None = None) -> ClipModel:
    name = name or cfg.clip_model
    with _models_lock:
        if name not in _models:
            if not model_installed(cfg, name):
                raise MediaError(f"圖像搜尋模型 {name} 尚未下載，請到設定頁下載")
            _models[name] = ClipModel(model_dir(cfg, name))
        return _models[name]


# ---- 建立索引 ---------------------------------------------------------------------

def index_images(conn: sqlite3.Connection, cfg: Config, model: ClipModel | None = None,
                 progress: Callable[[int, int, str], None] | None = None,
                 stop: threading.Event | None = None) -> int:
    model = model or get_model(cfg)
    rows = conn.execute(
        "SELECT id, fingerprint, rel_path FROM images WHERE status = 'ok' AND thumb_ok = 1 "
        "AND clip_model IS NOT ? ORDER BY sort_at DESC",
        (cfg.clip_model,),
    ).fetchall()
    done = 0
    for n, row in enumerate(rows, 1):
        if stop is not None and stop.is_set():
            break
        path = thumb_path(cfg.thumbs_dir, row["fingerprint"])
        if not path.exists():
            continue
        try:
            with Image.open(path) as img:
                vec = model.encode_image(img)
        except (OSError, ValueError) as exc:
            if progress:
                progress(n, len(rows), f"略過 {row['rel_path']}：{exc}")
            continue
        conn.execute("INSERT OR REPLACE INTO image_vectors (image_id, kind, model, vec) VALUES (?, 'clip', ?, ?)",
                     (row["id"], cfg.clip_model, vec.astype(np.float32).tobytes()))
        conn.execute("UPDATE images SET clip_model = ? WHERE id = ?", (cfg.clip_model, row["id"]))
        done += 1
        if n % 100 == 0:
            conn.commit()
            if progress:
                progress(n, len(rows), row["rel_path"])
    conn.commit()
    invalidate()
    return done


# ---- 搜尋用的記憶體索引 -----------------------------------------------------------------

_index: dict = {}
_index_lock = threading.Lock()


def invalidate() -> None:
    with _index_lock:
        _index.clear()


def matrix(conn: sqlite3.Connection, model_name: str) -> tuple[np.ndarray, np.ndarray]:
    """回傳 (ids, 向量矩陣)。圖庫有變動時自動重新載入。"""
    sig = conn.execute(
        "SELECT COUNT(*), COALESCE(MAX(i.id), 0) FROM image_vectors v JOIN images i ON i.id = v.image_id "
        "WHERE v.kind = 'clip' AND i.status = 'ok' AND v.model = ?",
        (model_name,),
    ).fetchone()
    key = (model_name, sig[0], sig[1])
    with _index_lock:
        if _index.get("key") == key:
            return _index["ids"], _index["mat"]
    ids, vecs = [], []
    for row in conn.execute(
        "SELECT v.image_id AS id, v.vec AS clip FROM image_vectors v JOIN images i ON i.id = v.image_id "
        "WHERE v.kind = 'clip' AND i.status = 'ok' AND v.model = ?", (model_name,)
    ):
        ids.append(row["id"])
        vecs.append(np.frombuffer(row["clip"], dtype=np.float32))
    ids_a = np.array(ids, dtype=np.int64)
    mat = np.vstack(vecs) if vecs else np.zeros((0, 1), dtype=np.float32)
    with _index_lock:
        _index.update(key=key, ids=ids_a, mat=mat)
    return ids_a, mat


def rank(conn: sqlite3.Connection, cfg: Config, texts: list[str], allowed: set[int] | None = None,
         limit: int = 1000) -> list[tuple[int, float]]:
    """依文字找最相似的圖片，回傳 [(image_id, 相似度)]。多個文字（原文＋翻譯）取平均。"""
    model = get_model(cfg)
    ids, mat = matrix(conn, cfg.clip_model)
    if not len(ids):
        return []
    q = np.mean([model.encode_text(t) for t in texts if t.strip()], axis=0)
    q /= np.linalg.norm(q) or 1.0
    sims = mat @ q
    order = np.argsort(-sims)
    out = []
    for i in order:
        image_id = int(ids[i])
        if allowed is not None and image_id not in allowed:
            continue
        out.append((image_id, float(sims[i])))
        if len(out) >= limit:
            break
    return out


def is_multilingual(name: str, cfg: Config | None = None) -> bool:
    if name == "custom" and cfg is not None:
        repo = cfg.clip_custom_repo.lower()
        return any(k in repo for k in ("xlm", "multilingual", "siglip2", "nllb"))
    return bool(CLIP_MODELS.get(name, {}).get("multilingual"))


def remove_index(conn: sqlite3.Connection) -> None:
    conn.execute("UPDATE images SET clip = NULL, clip_model = NULL")
    conn.execute("DELETE FROM image_vectors WHERE kind = 'clip'")
    conn.commit()
    invalidate()

