"""設定：資料目錄、地端模型位址與模型名稱。

優先順序：命令列參數 > 環境變數 > 資料目錄下的 config.json > 預設值。
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path

DEFAULTS = {
    "ollama_url": "http://127.0.0.1:11434",
    # 視覺模型：負責描述圖片、產生關鍵字、辨識圖中文字
    "vision_model": "qwen2.5vl:7b",
    # 向量模型：選用，用於語意搜尋（輸入「海邊夕陽」也能找到描述為「黃昏的沙灘」的照片）
    "embed_model": "",
    # 模型輸出語言
    "language": "zh-TW",
    # 送進模型前把長邊縮到這個像素，越大越慢但細節越多
    "analyze_max_side": 1024,
    # 縮圖高度（像素）；時間軸以等高列排版
    "thumb_size": 360,
    "request_timeout": 300,
    "port": 8765,
    # 1 = 允許同一個 Wi-Fi 下的手機／平板連線（需要設定密碼）
    "lan": 0,
    # 啟動時自動掃描新增的檔案
    "scan_on_start": 1,
    # 人臉辨識
    "face_enabled": 0,
    "face_model": "buffalo_l",
    "face_similarity": 50,  # 相似度門檻（百分比），越高越嚴格
    "face_min_faces": 3,  # 出現幾次以上才建立人物
    # 跨語言搜尋：用模型把查詢翻譯並擴充成中英文關鍵字
    "query_rewrite": 1,
    # 多語言 CLIP 圖像搜尋（文字直接比對畫面）
    "clip_enabled": 0,
    "clip_model": "xlm-roberta-base-vit-b32",
}

ENV_PREFIX = "LUMILIB_"


@dataclass
class Config:
    home: Path
    ollama_url: str = DEFAULTS["ollama_url"]
    vision_model: str = DEFAULTS["vision_model"]
    embed_model: str = DEFAULTS["embed_model"]
    language: str = DEFAULTS["language"]
    analyze_max_side: int = DEFAULTS["analyze_max_side"]
    thumb_size: int = DEFAULTS["thumb_size"]
    request_timeout: int = DEFAULTS["request_timeout"]
    port: int = DEFAULTS["port"]
    lan: int = DEFAULTS["lan"]
    scan_on_start: int = DEFAULTS["scan_on_start"]
    face_enabled: int = DEFAULTS["face_enabled"]
    face_model: str = DEFAULTS["face_model"]
    face_similarity: int = DEFAULTS["face_similarity"]
    face_min_faces: int = DEFAULTS["face_min_faces"]
    query_rewrite: int = DEFAULTS["query_rewrite"]
    clip_enabled: int = DEFAULTS["clip_enabled"]
    clip_model: str = DEFAULTS["clip_model"]

    @property
    def db_path(self) -> Path:
        return self.home / "library.db"

    @property
    def thumbs_dir(self) -> Path:
        return self.home / "thumbs"

    @property
    def auth_file(self) -> Path:
        return self.home / "auth.json"

    @property
    def config_file(self) -> Path:
        return self.home / "config.json"

    def save_setting(self, key: str, value) -> None:
        """只寫入指定的那一項，不把環境變數或一次性參數存進 config.json。"""
        self.home.mkdir(parents=True, exist_ok=True)
        data = {}
        if self.config_file.exists():
            try:
                data = json.loads(self.config_file.read_text(encoding="utf-8"))
            except ValueError:
                data = {}
        data[key] = _coerce(key, value)
        setattr(self, key, data[key])
        self.config_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def as_dict(self) -> dict:
        data = asdict(self)
        data["home"] = str(self.home)
        return data


def default_home() -> Path:
    env = os.environ.get(ENV_PREFIX + "HOME")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".lumilib"


def _coerce(name: str, value):
    if isinstance(DEFAULTS[name], int):
        return int(value)
    return str(value)


def load_config(home: str | Path | None = None, **overrides) -> Config:
    home_path = Path(home).expanduser() if home else default_home()
    values: dict = {}
    cfg_file = home_path / "config.json"
    if cfg_file.exists():
        try:
            stored = json.loads(cfg_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            stored = {}
        values.update({k: v for k, v in stored.items() if k in DEFAULTS})
    for name in DEFAULTS:
        env = os.environ.get(ENV_PREFIX + name.upper())
        if env is not None:
            values[name] = env
    for name, value in overrides.items():
        if name in DEFAULTS and value is not None:
            values[name] = value
    values = {k: _coerce(k, v) for k, v in values.items()}
    return Config(home=home_path, **values)


CONFIG_KEYS = [f.name for f in fields(Config) if f.name != "home"]
