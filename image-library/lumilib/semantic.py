"""用意思找文件（跨語言、同義詞）：搜「預算」也找得到 budget.xlsx、寫著「經費」的文件。

做法：
- 在這台電腦上用 Ollama 的向量模型（預設 bge-m3，支援中英日韓等一百多種語言）把每份文件的「檔名＋開頭一段文字」
  轉成一串數字（向量），存在 Re'memor 的資料庫；意思接近的文件，向量也接近。沒有讀到文字的文件只用檔名。
- 搜尋時把搜尋的字也轉成向量，找出最接近的文件，排在字面相符的結果後面，標成「意思相近」。
- 全部在這台電腦上執行（核心原則二）；只有第一次下載模型要連網，而且要本人按下確認。
- 只讀資料庫裡已經讀好的文字，不碰硬碟（核心原則七）。背景工作分批寫入，可以隨時停止，下次接著做（核心原則六）。

存法：每個向量先調成長度 1，再壓成 8 位元整數（每份文件約 1 KB）；十萬份文件約 100 MB。
搜尋時第一次把向量讀進記憶體，之後直接計算（十萬份約幾十毫秒）。
"""

from __future__ import annotations

import sqlite3
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import db

DEFAULT_MODEL = "bge-m3"
TEXT_CHARS = 800  # 每份文件取開頭這麼多字（加上檔名）
BATCH = 32
MIN_SIMILARITY = 0.5  # 低於這個相似度的不列出
SPREAD = 0.12  # 只列出和最接近的那份差不到這麼多的
MAX_RESULTS = 200


_gen = 0  # 寫入新向量就加一；記憶體裡的向量跟著重新讀
_cache: dict = {}
_cache_lock = threading.Lock()


def model_of(cfg) -> str:
    return getattr(cfg, "doc_embed_model", "") or DEFAULT_MODEL


# ---- 向量的存放 ----

def pack(vec) -> bytes:
    import numpy as np

    v = np.asarray(vec, dtype=np.float32)
    n = float(np.linalg.norm(v)) or 1.0
    q = np.clip(np.round(v / n * 127), -127, 127).astype(np.int8)
    return q.tobytes()


def _text_for(name: str, body: str) -> str:
    stem = name.rsplit(".", 1)[0] if "." in name else name
    return f"{stem}\n{(body or '')[:TEXT_CHARS]}".strip()


def _candidates_sql(model: str) -> str:
    """要建立向量的文件：文件類型、還沒有向量，或文件改過、文字讀好了（之前只用檔名）、換了模型。"""
    return ("FROM files f LEFT JOIN file_vectors v ON v.file_id = f.id LEFT JOIN file_text t ON t.file_id = f.id "
            "AND t.size = f.size AND t.mtime = f.mtime AND t.status = 'ok' AND t.source != 'archive' "
            "WHERE f.status = 'ok' AND f.kind = 'document' "
            f"AND (v.file_id IS NULL OR v.model != '{model.replace(chr(39), '')}' OR v.size != f.size OR v.mtime != f.mtime "
            "OR (v.has_text = 0 AND t.file_id IS NOT NULL))")


def plan(conn: sqlite3.Connection, model: str) -> dict:
    todo = conn.execute(f"SELECT COUNT(*) {_candidates_sql(model)}").fetchone()[0]
    done = conn.execute("SELECT COUNT(*) FROM file_vectors v JOIN files f ON f.id = v.file_id "
                        "WHERE v.model = ? AND f.status = 'ok' AND v.size = f.size AND v.mtime = f.mtime", (model,)).fetchone()[0]
    return {"todo": todo, "done": done}


@dataclass
class EmbedResult:
    done: int = 0
    stopped: bool = False
    error: str = ""
    errors: list[str] = field(default_factory=list)


def run_embed(conn: sqlite3.Connection, client, model: str, progress=None, stop=None) -> EmbedResult:
    """替還沒有向量的文件建立向量。只讀資料庫裡的文字，不碰硬碟；可以隨時停止。"""
    global _gen
    from . import textindex

    result = EmbedResult()
    rows = conn.execute(f"SELECT f.id, f.name, f.size, f.mtime, t.file_id IS NOT NULL AS has_text {_candidates_sql(model)} "
                        "ORDER BY f.id").fetchall()
    total = len(rows)
    last = 0.0
    for start in range(0, total, BATCH):
        if stop is not None and stop.is_set():
            result.stopped = True
            break
        batch = rows[start:start + BATCH]
        texts = [_text_for(r["name"], textindex.body(conn, r["id"]) if r["has_text"] else "") for r in batch]
        try:
            vectors = client.embed(model, texts)
        except Exception as exc:  # noqa: BLE001  模型沒開或沒下載：停下來說明，下次接著做
            result.error = str(exc)
            break
        if len(vectors) != len(batch):
            result.error = "模型沒有回傳向量"
            break
        conn.executemany("INSERT OR REPLACE INTO file_vectors (file_id, model, size, mtime, has_text, vec) VALUES (?, ?, ?, ?, ?, ?)",
                         [(r["id"], model, r["size"], r["mtime"], int(bool(r["has_text"])), pack(v)) for r, v in zip(batch, vectors)])
        conn.commit()
        _gen += 1
        result.done += len(batch)
        now = time.monotonic()
        if progress and now - last > 0.5:
            last = now
            progress(result.done, total, batch[-1]["name"])
    if progress:
        progress(result.done, total, "")
    return result


def describe(r: EmbedResult) -> str:
    text = f"替 {r.done:,} 份文件建立了「用意思找」的索引"
    if r.stopped:
        text += "（已暫停，下次接著做）"
    if r.error:
        text += f"；停下來了：{r.error}"
    return text


def reset(conn: sqlite3.Connection) -> int:
    global _gen
    n = conn.execute("DELETE FROM file_vectors").rowcount
    conn.commit()
    _gen += 1
    return n


# ---- 搜尋 ----

def _matrix(conn: sqlite3.Connection, model: str):
    """記憶體裡的向量（file_id 陣列、int8 矩陣）。資料庫有新的向量才重新讀。"""
    import numpy as np

    key = (conn.execute("PRAGMA database_list").fetchone()[2], model)
    with _cache_lock:
        hit = _cache.get(key)
        if hit and hit[0] == _gen:
            return hit[1], hit[2]
        rows = conn.execute("SELECT file_id, vec FROM file_vectors WHERE model = ?", (model,)).fetchall()
        if not rows:
            ids, mat = np.zeros(0, dtype=np.int64), np.zeros((0, 0), dtype=np.int8)
        else:
            ids = np.fromiter((r[0] for r in rows), dtype=np.int64, count=len(rows))
            mat = np.frombuffer(b"".join(r[1] for r in rows), dtype=np.int8).reshape(len(rows), -1)
        _cache.clear()
        _cache[key] = (_gen, ids, mat)
        return ids, mat


def nearest(conn: sqlite3.Connection, client, model: str, text: str) -> list[tuple[int, float]]:
    """和 text 意思最接近的文件 [(file_id, 相似度)]，由近到遠。沒有向量或模型沒開時回傳空的。"""
    import numpy as np

    ids, mat = _matrix(conn, model)
    if not len(ids) or not text.strip():
        return []
    try:
        vec = client.embed(model, [text])
    except Exception:  # noqa: BLE001  模型沒開：只用字面搜尋
        return []
    if not vec:
        return []
    q = np.asarray(vec[0], dtype=np.float32)
    q /= float(np.linalg.norm(q)) or 1.0
    if mat.shape[1] != q.shape[0]:
        return []
    scores = np.empty(len(ids), dtype=np.float32)
    for s in range(0, len(ids), 20_000):  # 分段算，不一次占用太多記憶體
        scores[s:s + 20_000] = mat[s:s + 20_000].astype(np.float32) @ q / 127.0
    k = min(MAX_RESULTS, len(scores))
    top = np.argpartition(-scores, k - 1)[:k]
    top = top[np.argsort(-scores[top])]
    if not len(top):
        return []
    best = float(scores[top[0]])
    cut = max(MIN_SIMILARITY, best - SPREAD)
    return [(int(ids[i]), float(scores[i])) for i in top if scores[i] >= cut]


def model_ready(client, model: str) -> bool:
    from .models import same_model

    try:
        return any(same_model(model, n) for n in client.list_models())
    except Exception:  # noqa: BLE001
        return False


__all__ = ["run_embed", "nearest", "plan", "describe", "reset", "model_of", "model_ready", "DEFAULT_MODEL"]
