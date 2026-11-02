"""透過 Ollama（地端模型伺服器）分析圖片，產生描述、關鍵字與圖中文字。

圖片只送到本機（或你指定的區網）Ollama 位址，不會上傳到雲端服務。
"""

from __future__ import annotations

import json
import re
import sqlite3
import threading
import urllib.error
import urllib.request
from array import array
from dataclasses import dataclass, field
from typing import Callable, Protocol

from . import db
from .config import Config
from .media import MediaError, analysis_images

RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "description": {"type": "string"},
        "tags": {"type": "array", "items": {"type": "string"}},
        "objects": {"type": "array", "items": {"type": "string"}},
        "scene": {"type": "string"},
        "text_in_image": {"type": "string"},
    },
    "required": ["description", "tags", "objects", "scene", "text_in_image"],
}

PROMPTS = {
    "zh-TW": """你是圖片管理系統的標註助手。請仔細觀察這張圖片，以繁體中文輸出 JSON：
- description：2 到 4 句話完整描述畫面：主體、動作、地點、時間（白天／夜晚）、天氣、氛圍與構圖。
- tags：10 到 25 個方便日後搜尋的關鍵字，涵蓋主體、物品、場景、顏色、活動、風格、季節、情緒。
  每個重要主體同時附上常見英文詞，例如「狗」與「dog」、「海邊」與「beach」。
- objects：畫面中可以辨識的具體物品名稱。
- scene：一個詞描述場景類型，例如：室內、街道、海邊、山區、餐廳、辦公室、文件、螢幕截圖。
- text_in_image：圖片中清楚可讀的文字原文（招牌、文件、螢幕內容），沒有就輸出空字串。
規則：只描述看得到的內容；不要猜測人物的真實身分或姓名。""",
    "en": """You are the tagging assistant of a photo library. Look carefully at the image and output JSON:
- description: 2-4 sentences describing subject, action, place, time of day, weather, mood and composition.
- tags: 10-25 search keywords covering subjects, objects, scene, colors, activities, style, season, mood.
- objects: concrete objects visible in the image.
- scene: one short phrase for the scene type, e.g. indoor, street, beach, mountain, restaurant, document, screenshot.
- text_in_image: legible text in the image verbatim (signs, documents, screens), or an empty string.
Rules: describe only what is visible; never guess the real identity or name of a person.""",
}

VIDEO_HINT = {
    "zh-TW": "\n這是一段影片，依時間順序附上 {n} 個畫面，請描述整段影片的內容與發生的事。",
    "en": "\nThis is a video; {n} frames are attached in chronological order. Describe the whole clip.",
}

PATH_HINT = {
    "zh-TW": "\n參考資訊（可能不準，只在與畫面相符時採用）：檔案路徑「{path}」{date}",
    "en": "\nReference (may be inaccurate, use only if consistent with the image): file path \"{path}\"{date}",
}


class OllamaUnavailable(Exception):
    """連不上 Ollama 或模型不存在：整批停止，而不是把每張圖都標成失敗。"""


class ModelClient(Protocol):
    def describe(self, model: str, prompt: str, images: list[str]) -> dict: ...

    def embed(self, model: str, texts: list[str]) -> list[list[float]]: ...


class OllamaClient:
    def __init__(self, base_url: str, timeout: int = 300):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _post(self, path: str, payload: dict) -> dict:
        req = urllib.request.Request(
            self.base_url + path,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "ignore")
            if exc.code == 404 and "not found" in body:
                raise OllamaUnavailable(
                    f"模型「{payload.get('model')}」尚未下載，請先執行：ollama pull {payload.get('model')}"
                ) from exc
            raise RuntimeError(f"Ollama 回應 {exc.code}：{body[:300]}") from exc
        except (urllib.error.URLError, ConnectionError) as exc:
            raise OllamaUnavailable(
                f"無法連線到 Ollama（{self.base_url}）。請確認已安裝並啟動 Ollama：{exc}"
            ) from exc

    def installed(self) -> list[dict]:
        try:
            with urllib.request.urlopen(self.base_url + "/api/tags", timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, ConnectionError, ValueError, OSError) as exc:
            raise OllamaUnavailable(f"無法連線到 Ollama（{self.base_url}）：{exc}") from exc
        return [
            {
                "name": m.get("name", ""),
                "size": m.get("size", 0),
                "parameter_size": (m.get("details") or {}).get("parameter_size"),
                "families": (m.get("details") or {}).get("families") or [],
                "modified_at": m.get("modified_at"),
            }
            for m in data.get("models", [])
        ]

    def list_models(self) -> list[str]:
        return [m["name"] for m in self.installed()]

    def pull(self, model: str, progress: Callable[[str, int, int], None] | None = None,
             stop: threading.Event | None = None) -> None:
        """下載模型（等同 ollama pull），逐行回報進度。"""
        req = urllib.request.Request(
            self.base_url + "/api/pull",
            data=json.dumps({"model": model, "stream": True}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                for line in resp:
                    if stop is not None and stop.is_set():
                        return
                    if not line.strip():
                        continue
                    event = json.loads(line.decode("utf-8"))
                    if event.get("error"):
                        raise RuntimeError(event["error"])
                    if progress:
                        progress(event.get("status", ""), int(event.get("completed") or 0), int(event.get("total") or 0))
        except (urllib.error.URLError, ConnectionError) as exc:
            raise OllamaUnavailable(f"無法連線到 Ollama（{self.base_url}）：{exc}") from exc

    def delete(self, model: str) -> None:
        req = urllib.request.Request(
            self.base_url + "/api/delete",
            data=json.dumps({"model": model}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="DELETE",
        )
        try:
            with urllib.request.urlopen(req, timeout=30):
                pass
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"刪除失敗：{exc.read().decode('utf-8', 'ignore')[:200]}") from exc
        except (urllib.error.URLError, ConnectionError) as exc:
            raise OllamaUnavailable(f"無法連線到 Ollama（{self.base_url}）：{exc}") from exc

    def describe(self, model: str, prompt: str, images: list[str]) -> dict:
        data = self._post(
            "/api/chat",
            {
                "model": model,
                "stream": False,
                "format": RESULT_SCHEMA,
                "keep_alive": "15m",
                "options": {"temperature": 0.2},
                "messages": [{"role": "user", "content": prompt, "images": images}],
            },
        )
        return parse_model_json(data.get("message", {}).get("content", ""))

    def embed(self, model: str, texts: list[str]) -> list[list[float]]:
        data = self._post("/api/embed", {"model": model, "input": texts, "keep_alive": "15m"})
        return data.get("embeddings", [])


def parse_model_json(content: str) -> dict:
    content = re.sub(r"<think>.*?</think>", "", content, flags=re.S).strip()
    try:
        return json.loads(content)
    except ValueError:
        match = re.search(r"\{.*\}", content, flags=re.S)
        if match:
            try:
                return json.loads(match.group(0))
            except ValueError:
                pass
    raise ValueError(f"模型沒有回傳有效 JSON：{content[:200]}")


def _str_list(value, limit: int) -> list[str]:
    if isinstance(value, str):
        value = re.split(r"[,，、;；\n]", value)
    if not isinstance(value, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = str(item).strip().lstrip("#").strip()
        key = text.lower()
        if text and key not in seen and len(text) <= 60:
            seen.add(key)
            out.append(text)
        if len(out) >= limit:
            break
    return out


def normalize_result(raw: dict) -> dict:
    return {
        "description": str(raw.get("description") or "").strip(),
        "tags": _str_list(raw.get("tags"), 40),
        "objects": _str_list(raw.get("objects"), 40),
        "scene": str(raw.get("scene") or "").strip(),
        "ocr_text": str(raw.get("text_in_image") or "").strip(),
    }


def build_prompt(cfg: Config, image, frames: int = 1) -> str:
    lang = cfg.language if cfg.language in PROMPTS else "zh-TW"
    date = ""
    if image["taken_at"]:
        date = f"，拍攝時間 {image['taken_at'][:10]}" if lang == "zh-TW" else f", taken {image['taken_at'][:10]}"
    prompt = PROMPTS[lang]
    if image["media_type"] == "video":
        prompt += VIDEO_HINT[lang].format(n=frames)
    return prompt + PATH_HINT[lang].format(path=image["rel_path"], date=date)


def embedding_text(image: sqlite3.Row | dict) -> str:
    parts = [
        image["description"] or "",
        " ".join(db.json_list(image["tags"])),
        " ".join(db.json_list(image["user_tags"])),
        " ".join(db.json_list(image["objects"])),
        image["scene"] or "",
        image["note"] or "",
        " ".join(db.json_list(image["keywords"])),
    ]
    return "\n".join(p for p in parts if p)[:4000]


def pack_vector(vec: list[float]) -> bytes:
    return array("f", vec).tobytes()


def unpack_vector(blob: bytes) -> array:
    arr = array("f")
    arr.frombytes(blob)
    return arr


@dataclass
class AnalyzeResult:
    analyzed: int = 0
    failed: int = 0
    embedded: int = 0
    skipped_offline: int = 0
    errors: list[str] = field(default_factory=list)


def _pending_images(conn: sqlite3.Connection, redo: bool, retry_failed: bool, root_id: int | None,
                    ids: list[int] | None = None, folder: str | None = None, album_id: int | None = None):
    where = ["i.status = 'ok'"]
    params: list = []
    scoped = bool(ids or folder is not None or album_id)
    if not redo:
        where.append("i.analyzed_at IS NULL")
        if not retry_failed and not scoped:  # 指定範圍時，先前失敗的也一起重試
            where.append("i.error IS NULL")
    if root_id is not None:
        where.append("i.root_id = ?")
        params.append(root_id)
    if folder is not None:
        where.append("(i.folder = ? OR i.folder LIKE ? ESCAPE '\\')")
        esc = folder.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        params += [folder, f"{esc}/%" if folder else "%"]
    if album_id is not None:
        where.append("i.id IN (SELECT image_id FROM album_items WHERE album_id = ?)")
        params.append(album_id)
    if ids:
        where.append(f"i.id IN ({','.join('?' * len(ids))})")
        params += [int(x) for x in ids]
    return conn.execute(
        f"SELECT i.* FROM images i WHERE {' AND '.join(where)} ORDER BY i.sort_at DESC, i.id",
        params,
    ).fetchall()


def analyze_images(
    conn: sqlite3.Connection,
    cfg: Config,
    client: ModelClient,
    limit: int | None = None,
    redo: bool = False,
    retry_failed: bool = False,
    root_id: int | None = None,
    progress: Callable[[int, int, str], None] | None = None,
    stop: threading.Event | None = None,
    ids: list[int] | None = None,
    folder: str | None = None,
    album_id: int | None = None,
) -> AnalyzeResult:
    result = AnalyzeResult()
    rows = _pending_images(conn, redo, retry_failed, root_id, ids, folder, album_id)
    if limit:
        rows = rows[:limit]
    total = len(rows)
    for index, image in enumerate(rows, 1):
        if stop is not None and stop.is_set():
            break
        path = db.absolute_path(conn, image)
        if not path.exists():
            result.skipped_offline += 1
            continue
        try:
            images = analysis_images(
                path, image["media_type"], bool(image["is_raw"]), cfg.analyze_max_side,
                image["duration"], image["orientation"],
            )
            prompt = build_prompt(cfg, image, len(images))
            parsed = normalize_result(client.describe(cfg.vision_model, prompt, images))
            if not parsed["description"] and not parsed["tags"]:
                raise ValueError("模型回傳空白結果")
        except OllamaUnavailable:
            raise
        except (MediaError, OSError, ValueError, RuntimeError) as exc:
            conn.execute("UPDATE images SET error = ? WHERE id = ?", (str(exc)[:500], image["id"]))
            conn.commit()
            result.failed += 1
            result.errors.append(f"{image['rel_path']}: {exc}")
            if progress:
                progress(index, total, f"失敗 {image['rel_path']}")
            continue

        conn.execute(
            """UPDATE images SET analyzed_at = ?, model = ?, description = ?, tags = ?, objects = ?,
                   scene = ?, ocr_text = ?, error = NULL, embedding = NULL, embed_model = NULL
               WHERE id = ?""",
            (
                db.now_iso(), cfg.vision_model, parsed["description"],
                json.dumps(parsed["tags"], ensure_ascii=False),
                json.dumps(parsed["objects"], ensure_ascii=False),
                parsed["scene"], parsed["ocr_text"], image["id"],
            ),
        )
        db.refresh_search_text(conn, image["id"])
        conn.commit()
        result.analyzed += 1
        if progress:
            progress(index, total, image["rel_path"])

    if cfg.embed_model and not (stop is not None and stop.is_set()):
        result.embedded = embed_images(conn, cfg, client, stop=stop)
    return result


def embed_images(
    conn: sqlite3.Connection,
    cfg: Config,
    client: ModelClient,
    batch_size: int = 16,
    stop: threading.Event | None = None,
) -> int:
    """替已分析的圖片建立語意向量（需要設定 embed_model）。"""
    if not cfg.embed_model:
        return 0
    rows = conn.execute(
        """SELECT * FROM images WHERE status = 'ok' AND analyzed_at IS NOT NULL
           AND (embedding IS NULL OR embed_model IS NOT ?)""",
        (cfg.embed_model,),
    ).fetchall()
    done = 0
    for start in range(0, len(rows), batch_size):
        if stop is not None and stop.is_set():
            break
        batch = rows[start:start + batch_size]
        vectors = client.embed(cfg.embed_model, [embedding_text(r) for r in batch])
        for row, vec in zip(batch, vectors):
            conn.execute(
                "UPDATE images SET embedding = ?, embed_model = ? WHERE id = ?",
                (pack_vector(vec), cfg.embed_model, row["id"]),
            )
            done += 1
        conn.commit()
    return done
