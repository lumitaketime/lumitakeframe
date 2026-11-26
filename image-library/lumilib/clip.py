"""多語言 CLIP 圖像搜尋：文字與畫面放進同一個向量空間，「穿紅衣服的小孩」不需要事先有標籤也找得到。

模型使用 Immich 專案在 Hugging Face 上提供的 ONNX 版本（visual/、textual/ 兩個模型），
以 onnxruntime 在本機執行，不需要 PyTorch。圖像特徵從已產生的縮圖計算，不必重新讀原檔。

另可選 Google 的 EmbeddingGemma 2（ONNX 版，format="eg2"）：視覺編碼器把縮圖切成 16×16 的小塊轉成影像 token，
再和文字一起送進文字模型，得到同一個空間的向量。比 CLIP 新、懂中文描述，但建立索引慢很多，
所以設定頁有「比較」：先用最近的照片試建索引，同一句搜尋兩邊結果並排比較，再決定要不要換。
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
    "embeddinggemma-2": {
        "repo": "onnx-community/embeddinggemma-2-ONNX",
        "label": "EmbeddingGemma 2（Google，多語言，試用）",
        "multilingual": True,
        "format": "eg2",
        "size_mb": 540,
        "note": "2026 年的新模型，比較懂中文描述；建立索引比較慢（每張約 0.3–1 秒），建議先用下方的「比較」試試。",
    },
}

# EmbeddingGemma 2：要下載的檔案（8 位元量化版，約 540 MB）
EG2_FILES = (
    "config.json", "tokenizer.json",
    "onnx/model_quantized.onnx", "onnx/model_quantized.onnx_data",
    "onnx/vision_encoder_quantized.onnx", "onnx/vision_encoder_quantized.onnx_data",
)


def format_of(name: str) -> str:
    return (CLIP_MODELS.get(name) or {}).get("format", "immich")

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
    if format_of(name) == "eg2":
        return all((d / p).exists() for p in EG2_FILES)
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


def _list_eg2(repo: str) -> list[dict]:
    out = []
    for sub in ("", "onnx"):
        url = f"{HF}/api/models/{repo}/tree/main" + (f"/{sub}" if sub else "")
        with net.urlopen(url, timeout=30) as resp:
            for it in json.loads(resp.read().decode("utf-8")):
                if it.get("type") == "file" and it["path"] in EG2_FILES:
                    out.append({"path": it["path"], "size": int((it.get("lfs") or {}).get("size") or it.get("size") or 0)})
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
    if format_of(name) == "eg2":
        files = _list_eg2(repo)
    else:
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


class EmbeddingGemma2Model:
    """EmbeddingGemma 2 的圖像與文字向量（和 ClipModel 一樣提供 encode_image／encode_text）。

    圖像：保持比例縮放到約 BUDGET×9 個 16×16 小塊（70 個影像 token，約 400×400，剛好是縮圖的解析度），
    視覺編碼器 → 影像 token；文字模型讀 <|image> + token×N + <image|>。
    文字：加上模型訓練時用的查詢前綴「task: search result | query: 」。
    輸出 768 維，取前 DIM 維重新正規化（Matryoshka，512 維幾乎不損失，索引和 CLIP 一樣大）。
    """

    BUDGET = 70
    DIM = 512
    PATCH = 16
    POOL = 3
    QUERY_PREFIX = "task: search result | query: "

    def __init__(self, directory: Path):
        import onnxruntime as ort
        from tokenizers import Tokenizer

        opts = ort.SessionOptions()
        opts.log_severity_level = 3
        self.vision = ort.InferenceSession(str(directory / "onnx" / "vision_encoder_quantized.onnx"), opts, providers=["CPUExecutionProvider"])
        self.text = ort.InferenceSession(str(directory / "onnx" / "model_quantized.onnx"), opts, providers=["CPUExecutionProvider"])
        self.tokenizer = Tokenizer.from_file(str(directory / "tokenizer.json"))
        config = _read_json(directory / "config.json")
        self.image_token = int(config.get("image_token_id", 258880))
        self.hidden = int((config.get("text_config") or {}).get("hidden_size", 512))
        self._text_cache: OrderedDict[str, np.ndarray] = OrderedDict()
        self.lock = threading.Lock()

    def _norm(self, v: np.ndarray) -> np.ndarray:
        v = v.astype(np.float32).reshape(-1)[: self.DIM]
        return v / (np.linalg.norm(v) or 1.0)

    def _size(self, h: int, w: int, max_patches: int) -> tuple[int, int]:
        import math

        f = math.sqrt(max_patches * self.PATCH ** 2 / (h * w))
        side = self.POOL * self.PATCH
        th = math.floor(f * h / side) * side
        tw = math.floor(f * w / side) * side
        max_side = (max_patches // self.POOL ** 2) * side
        if th == 0:
            th, tw = side, min((w // h) * side, max_side)
        elif tw == 0:
            tw, th = side, min((h // w) * side, max_side)
        return th, tw

    def _encode(self, ids: list[int], image_features: np.ndarray | None = None) -> np.ndarray:
        arr = np.array([ids], dtype=np.int64)
        empty = np.zeros((0, self.hidden), dtype=np.float32)
        with self.lock:
            out = self.text.run(["sentence_embedding"], {
                "input_ids": arr, "attention_mask": np.ones_like(arr),
                "image_features": image_features if image_features is not None else empty,
                "video_features": empty, "audio_features": empty,
            })[0]
        return self._norm(out[0])

    def encode_image(self, img: Image.Image) -> np.ndarray:
        img = img.convert("RGB")
        ps, max_patches = self.PATCH, self.BUDGET * self.POOL ** 2
        th, tw = self._size(img.height, img.width, max_patches)
        if (th, tw) != (img.height, img.width):
            img = img.resize((tw, th), Image.Resampling.BICUBIC)
        a = np.asarray(img, dtype=np.float32) / 255.0
        ph, pw = th // ps, tw // ps
        n = ph * pw
        pixels = np.zeros((max_patches, ps * ps * 3), dtype=np.float32)
        pixels[:n] = a.reshape(ph, ps, pw, ps, 3).transpose(0, 2, 1, 3, 4).reshape(n, ps * ps * 3)
        pos = np.full((max_patches, 2), -1, dtype=np.int64)
        rows, cols = np.divmod(np.arange(n), pw)
        pos[:n, 0], pos[:n, 1] = cols, rows
        with self.lock:
            feats = self.vision.run(["image_features"], {"pixel_values": pixels[None], "pixel_position_ids": pos[None]})[0]
        tokens = feats.shape[0]
        ids = self.tokenizer.encode("<|image>" + "<|image|>" * tokens + "<image|>").ids
        return self._encode(ids, feats.astype(np.float32))

    def encode_text(self, text: str) -> np.ndarray:
        key = text.strip()
        if key in self._text_cache:
            self._text_cache.move_to_end(key)
            return self._text_cache[key]
        vec = self._encode(self.tokenizer.encode(self.QUERY_PREFIX + key).ids)
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
            cls = EmbeddingGemma2Model if format_of(name) == "eg2" else ClipModel
            _models[name] = cls(model_dir(cfg, name))
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



# ---- 比較兩個圖像搜尋模型（試用新模型，不影響現在的索引） -----------------------------------
# 試用的向量存在 image_vectors 的 kind='clip_trial'，和正式的 'clip' 分開；決定換模型時直接沿用。

TRIAL_KIND = "clip_trial"


def _trial_file(cfg: Config) -> Path:
    return cfg.home / "models" / "clip" / "trial.json"


def trial_info(cfg: Config) -> dict:
    return _read_json(_trial_file(cfg))


def _time_model(model, paths: list[Path]) -> float | None:
    """每張照片平均幾毫秒（先跑一張暖機，不計入）。"""
    import time

    imgs = []
    for p in paths:
        try:
            with Image.open(p) as im:
                imgs.append(im.convert("RGB"))
        except OSError:
            continue
    if len(imgs) < 2:
        return None
    model.encode_image(imgs[0])
    t = time.perf_counter()
    for im in imgs[1:]:
        model.encode_image(im)
    return (time.perf_counter() - t) * 1000 / (len(imgs) - 1)


def trial_index(conn: sqlite3.Connection, cfg: Config, name: str, count: int = 1000,
                progress: Callable[[int, int, str], None] | None = None,
                stop: threading.Event | None = None) -> dict:
    """用候選模型替最近的 count 張照片建立試用索引，並量兩個模型每張要多久。"""
    import time

    model = get_model(cfg, name)
    rows = conn.execute(
        "SELECT id, fingerprint, rel_path FROM images WHERE status = 'ok' AND thumb_ok = 1 AND media_type = 'photo' "
        "ORDER BY sort_at DESC LIMIT ?", (int(count),)).fetchall()
    have = {r[0] for r in conn.execute("SELECT image_id FROM image_vectors WHERE kind = ? AND model = ?", (TRIAL_KIND, name))}
    todo = [r for r in rows if r["id"] not in have]
    done, spent, timed = len(rows) - len(todo), 0.0, 0
    for n, row in enumerate(todo, 1):
        if stop is not None and stop.is_set():
            break
        path = thumb_path(cfg.thumbs_dir, row["fingerprint"])
        try:
            with Image.open(path) as img:
                t = time.perf_counter()
                vec = model.encode_image(img)
                spent += time.perf_counter() - t
                timed += 1
        except (OSError, ValueError):
            continue
        conn.execute("INSERT OR REPLACE INTO image_vectors (image_id, kind, model, vec) VALUES (?, ?, ?, ?)",
                     (row["id"], TRIAL_KIND, name, vec.astype(np.float32).tobytes()))
        done += 1
        if n % 20 == 0:
            conn.commit()
        if progress:
            progress(done, len(rows), row["rel_path"])
    conn.commit()
    info = trial_info(cfg) if trial_info(cfg).get("candidate") == name else {}
    if timed:
        info["candidate_ms"] = round(spent * 1000 / timed, 1)
    # 目前的模型用同樣的縮圖量一次速度，數字才能比較
    current = cfg.clip_model
    if current != name and model_installed(cfg, current) and "current_ms" not in info:
        sample = [thumb_path(cfg.thumbs_dir, r["fingerprint"]) for r in rows[:21]]
        ms = _time_model(get_model(cfg, current), sample)
        if ms:
            info["current_ms"] = round(ms, 1)
    info.update(candidate=name, current=current, count=done)
    _trial_file(cfg).parent.mkdir(parents=True, exist_ok=True)
    _trial_file(cfg).write_text(json.dumps(info, ensure_ascii=False))
    return info


def _rank_ids(vectors: list[tuple[int, bytes]], q: np.ndarray, k: int) -> list[tuple[int, float]]:
    if not vectors:
        return []
    ids = np.array([i for i, _ in vectors])
    mat = np.vstack([np.frombuffer(v, dtype=np.float32) for _, v in vectors])
    sims = mat @ q
    order = np.argsort(-sims)[:k]
    return [(int(ids[i]), float(sims[i])) for i in order]


def compare(conn: sqlite3.Connection, cfg: Config, query: str, k: int = 12) -> dict:
    """同一句查詢，在試用的同一批照片裡，兩個模型各自找出最像的 k 張。"""
    import time

    info = trial_info(cfg)
    name = info.get("candidate")
    if not name or not model_installed(cfg, name):
        raise MediaError("還沒有試用索引，請先按「用最近的照片試建索引」")
    trial = conn.execute("SELECT image_id, vec FROM image_vectors WHERE kind = ? AND model = ?", (TRIAL_KIND, name)).fetchall()
    ids = {r[0] for r in trial}
    current = cfg.clip_model
    cur = [r for r in conn.execute("SELECT image_id, vec FROM image_vectors WHERE kind = 'clip' AND model = ?", (current,))
           if r[0] in ids]
    out = {"query": query, "candidate": name, "current": current, "pool": len(ids), "current_pool": len(cur)}
    t = time.perf_counter()
    qc = get_model(cfg, name).encode_text(query)
    out["candidate_ms"] = round((time.perf_counter() - t) * 1000)
    out["candidate_hits"] = _rank_ids([(r[0], r[1]) for r in trial], qc, k)
    if cur and model_installed(cfg, current):
        t = time.perf_counter()
        qo = get_model(cfg, current).encode_text(query)  # 比較時兩邊都用原句（不經過 AI 翻譯）
        out["current_ms"] = round((time.perf_counter() - t) * 1000)
        out["current_hits"] = _rank_ids([(r[0], r[1]) for r in cur], qo, k)
    else:
        out["current_hits"] = []
    return out


def adopt_trial(conn: sqlite3.Connection, cfg: Config) -> int:
    """改用試用中的模型：試用向量直接變成正式索引，其他照片之後再補建。回傳沿用了幾張。"""
    name = trial_info(cfg).get("candidate")
    if not name:
        raise MediaError("沒有試用中的模型")
    rows = conn.execute("SELECT image_id, vec FROM image_vectors WHERE kind = ? AND model = ?", (TRIAL_KIND, name)).fetchall()
    conn.executemany("INSERT OR REPLACE INTO image_vectors (image_id, kind, model, vec) VALUES (?, 'clip', ?, ?)",
                     [(r[0], name, r[1]) for r in rows])
    conn.executemany("UPDATE images SET clip_model = ? WHERE id = ?", [(name, r[0]) for r in rows])
    conn.execute("DELETE FROM image_vectors WHERE kind = ?", (TRIAL_KIND,))
    conn.commit()
    _trial_file(cfg).unlink(missing_ok=True)
    invalidate()
    return len(rows)


def clear_trial(conn: sqlite3.Connection, cfg: Config) -> None:
    conn.execute("DELETE FROM image_vectors WHERE kind = ?", (TRIAL_KIND,))
    conn.commit()
    _trial_file(cfg).unlink(missing_ok=True)
