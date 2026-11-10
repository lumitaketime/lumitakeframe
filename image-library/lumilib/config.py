"""設定：資料目錄、地端模型位址與模型名稱。

優先順序：命令列參數 > 環境變數 > 資料目錄下的 config.json > 預設值。

Re'memor 和 Lumitake Library 分開住：資料目錄預設 ~/.rememor、連接埠 8766、環境變數以 REMEMOR_ 開頭，
所以兩個 App 可以同時使用，不會讀寫到對方的資料庫。
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path

DEFAULTS = {
    "ollama_url": "http://127.0.0.1:11434",
    # 視覺模型：負責描述圖片、產生關鍵字、辨識圖中文字
    "vision_model": "gemma4:e4b",
    # 向量模型：選用，用於語意搜尋（輸入「海邊夕陽」也能找到描述為「黃昏的沙灘」的照片）
    "embed_model": "",
    # 文字模型：搜尋詞翻譯、描述翻譯用（空白＝使用視覺模型）
    "text_model": "",
    # 自訂 AI 描述提示詞（空白＝使用內建提示詞）
    "analysis_prompt": "",
    # 模型輸出語言
    "language": "zh-TW",
    # 送進模型前把長邊縮到這個像素，越大越慢但細節越多
    "analyze_max_side": 1024,
    # 縮圖高度（像素）；時間軸以等高列排版
    "thumb_size": 360,
    "request_timeout": 300,
    "port": 8766,
    # 1 = 允許同一個 Wi-Fi 下的手機／平板連線（需要設定密碼）
    "lan": 0,
    # 啟動時自動掃描新增的檔案
    "scan_on_start": 1,
    # 掃描後自動用 AI 分析新照片（預設關閉：檔案量大時不逐一交給 AI，需要時再手動開始或在設定開啟）
    "auto_analyze": 0,
    # AI 描述的詳細程度：standard 標準、fast 快速（描述較短、關鍵字較少，約快一倍）
    "analysis_detail": "standard",
    # AI 分析時段：always 隨時、ac 只在接電源、night 只在夜間、ac_night 兩者都要
    "analyze_schedule": "always",
    "night_start": 22,
    "night_end": 7,
    "schedule_days": "1234567",  # 星期一＝1 … 星期日＝7
    "schedule_start": "22:00",
    "schedule_end": "07:00",  # 和開始相同代表全天
    "schedule_ac": 1,  # 只在接上電源時
    "schedule_idle": 0,  # 電腦閒置幾分鐘以上（0＝不限）
    "schedule_battery": 0,  # 電量高於幾 %（0＝不限）
    # 檢視照片時，下方顯示星等與顏色標籤列
    "viewer_rating_bar": 1,
    # 左側選單隱藏的功能（逗號分隔的路徑，例如 /map,/duplicates）
    "nav_hidden": "",
    "pinned_tools": "",
    # 照片格呈現方式：aspect＝依照片比例（等高列）、square＝正方形裁切
    "grid_style": "aspect",
    # 第一次開啟的設定引導是否已完成
    "onboarded": 0,
    # 圖庫開著時避免 Mac 閒置睡眠（接電源時），手機才能持續連線
    "keep_awake": 1,
    # RAW+JPEG 與連拍疊放
    "dup_threshold": 6,  # 重複照片的相似度門檻（越小越嚴格）
    "screen_png_rule": 1,  # 沒有相機資訊的 PNG 視為截圖
    "large_files_limit": 200,  # 大檔案列出幾個
    "album_sort": "updated",  # 相簿排序：updated／name／created／count／custom（拖曳排的順序）
    "folder_sort": "name",  # 資料夾排序：name／updated／count／custom
    "stack_enabled": 1,
    "burst_seconds": 2,
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
    # 自訂 CLIP：Hugging Face 上 Immich 格式（visual/、textual/ ONNX）的儲存庫，例如 immich-app/ViT-B-16-SigLIP2__webli
    "clip_custom_repo": "",
    # 自訂人臉模型：InsightFace 格式的 zip 網址與其中的偵測／特徵檔名
    "face_custom_url": "",
    "face_custom_det": "",
    "face_custom_rec": "",
}

ENV_PREFIX = "REMEMOR_"


@dataclass
class Config:
    home: Path
    ollama_url: str = DEFAULTS["ollama_url"]
    vision_model: str = DEFAULTS["vision_model"]
    embed_model: str = DEFAULTS["embed_model"]
    text_model: str = DEFAULTS["text_model"]
    analysis_prompt: str = DEFAULTS["analysis_prompt"]
    language: str = DEFAULTS["language"]
    analyze_max_side: int = DEFAULTS["analyze_max_side"]
    thumb_size: int = DEFAULTS["thumb_size"]
    request_timeout: int = DEFAULTS["request_timeout"]
    port: int = DEFAULTS["port"]
    lan: int = DEFAULTS["lan"]
    scan_on_start: int = DEFAULTS["scan_on_start"]
    auto_analyze: int = DEFAULTS["auto_analyze"]
    analysis_detail: str = DEFAULTS["analysis_detail"]
    analyze_schedule: str = DEFAULTS["analyze_schedule"]
    night_start: int = DEFAULTS["night_start"]
    night_end: int = DEFAULTS["night_end"]
    schedule_days: str = DEFAULTS["schedule_days"]
    schedule_start: str = DEFAULTS["schedule_start"]
    schedule_end: str = DEFAULTS["schedule_end"]
    schedule_ac: int = DEFAULTS["schedule_ac"]
    schedule_idle: int = DEFAULTS["schedule_idle"]
    schedule_battery: int = DEFAULTS["schedule_battery"]
    viewer_rating_bar: int = DEFAULTS["viewer_rating_bar"]
    nav_hidden: str = DEFAULTS["nav_hidden"]
    pinned_tools: str = DEFAULTS["pinned_tools"]
    grid_style: str = DEFAULTS["grid_style"]
    onboarded: int = DEFAULTS["onboarded"]
    keep_awake: int = DEFAULTS["keep_awake"]
    dup_threshold: int = DEFAULTS["dup_threshold"]
    screen_png_rule: int = DEFAULTS["screen_png_rule"]
    large_files_limit: int = DEFAULTS["large_files_limit"]
    album_sort: str = DEFAULTS["album_sort"]
    folder_sort: str = DEFAULTS["folder_sort"]
    stack_enabled: int = DEFAULTS["stack_enabled"]
    burst_seconds: int = DEFAULTS["burst_seconds"]
    face_enabled: int = DEFAULTS["face_enabled"]
    face_model: str = DEFAULTS["face_model"]
    face_similarity: int = DEFAULTS["face_similarity"]
    face_min_faces: int = DEFAULTS["face_min_faces"]
    query_rewrite: int = DEFAULTS["query_rewrite"]
    clip_enabled: int = DEFAULTS["clip_enabled"]
    clip_model: str = DEFAULTS["clip_model"]
    clip_custom_repo: str = DEFAULTS["clip_custom_repo"]
    face_custom_url: str = DEFAULTS["face_custom_url"]
    face_custom_det: str = DEFAULTS["face_custom_det"]
    face_custom_rec: str = DEFAULTS["face_custom_rec"]

    @property
    def search_model(self) -> str:
        """搜尋詞翻譯與描述翻譯用的模型。"""
        return self.text_model.strip() or self.vision_model

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
    return Path.home() / ".rememor"


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
