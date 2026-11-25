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
    "ocr_scope": "scans",  # 文字辨識範圍：scans＝掃描檔與截圖／all＝再加上所有照片／off
    "ocr_languages": "zh-Hant,zh-Hans,en-US",  # 文字辨識的語言（Apple Vision 的語言代碼）
    "assistant_model": "",  # 檔案管理助理在這台電腦上用的模型（Ollama）；空白＝依這台電腦的記憶體自動挑
    # 助理用哪個服務：ollama＝這台電腦（離線）／claude／gemini／openai／custom（其他 OpenAI 相容的服務，網址自己填）
    "assistant_provider": "ollama",
    "assistant_api_url": "",  # 其他相容服務的網址，例如 http://127.0.0.1:1234/v1（本機的 LM Studio）
    "assistant_api_model": "",
    "assistant_api_key": "",  # 金鑰都只存在這台電腦的設定檔，介面不會顯示
    "assistant_claude_model": "claude-opus-5-5",
    "assistant_claude_key": "",
    "assistant_gemini_model": "",
    "assistant_gemini_key": "",
    "assistant_openai_model": "",
    "assistant_openai_key": "",
    # 助理的權限：1＝只看目錄／2＝可以讀文件內容／3＝可以在 Re'memor 裡整理（標籤、智慧資料夾、待刪除標記）
    # ／4＝可以搬移、改名檔案。每一個動作都要本人在畫面上確認才會執行，而且都可以復原；助理永遠不會刪除檔案。
    "assistant_permission": 2,
    "assistant_cloud_content": 0,  # 用雲端服務時，可不可以把文件內容送過去（關閉時只送檔名與統計）
    "auto_extract": 1,
    # 用意思找文件（跨語言、同義詞）：在這台電腦上用向量模型（預設 bge-m3，要先下載）替文件建立索引
    "doc_semantic": 0,
    "spotlight": 1,  # Mac App：把目錄放進 Spotlight（索引只在這台 Mac）
    "spotlight_internal": 1,
    "scan_parallel": 2,
    # 目錄備份：每週自動做一份（要先選存放位置），只保留最近幾份自動備份；本人按的「立即備份」不會被拿掉
    "backup_auto": 1,
    "backup_dir": "",
    "backup_keep": 4,
    "backup_last": "",
    # 自動分類：第一次先問本人（classify_asked），同意了才自動跑
    "classify_asked": 0,
    "classify_rules_auto": 0,  # 掃描完自動用規則分類
    "classify_ai_auto": 0,  # 規則分不出來的，在「AI 分析排程」允許的時段（預設夜間、接著電源）交給 AI
    "classify_read_text": 1,  # 用這台電腦上的模型時，可以讀文件開頭一小段（用雲端時一律不讀）
    "classify_cloud": 0,  # 助理設成雲端服務時，可不可以用它來分類（會送出資料夾名稱與檔名）  # 同時掃描幾顆硬碟（1–4）：不同硬碟同時掃；同一個 USB 集線器大約 3 顆就到頻寬上限  # 這台 Mac 內建磁碟上的檔案也放（和 Re'memor 的搜尋找得到的一樣；Mac 自己的 Spotlight 可能也列一次）
    "doc_embed_model": "bge-m3",  # 掃描完自動接著讀取文件文字與文字辨識（在背景，可以暫停、隨時拔掉）
    "start_page": "overview",  # 開啟 App 時先看到的頁面：overview＝總覽／folders＝所有檔案／drives＝硬碟／find＝搜尋／photos＝照片
    "open_action": "",  # 按兩下照片以外的檔案：open＝用預設的 App 打開／reveal＝在 Finder 中顯示／空白＝第一次先問
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
    open_action: str = DEFAULTS["open_action"]
    ocr_scope: str = DEFAULTS["ocr_scope"]
    ocr_languages: str = DEFAULTS["ocr_languages"]
    assistant_model: str = DEFAULTS["assistant_model"]
    assistant_provider: str = DEFAULTS["assistant_provider"]
    assistant_api_url: str = DEFAULTS["assistant_api_url"]
    assistant_api_model: str = DEFAULTS["assistant_api_model"]
    assistant_api_key: str = DEFAULTS["assistant_api_key"]
    assistant_claude_model: str = DEFAULTS["assistant_claude_model"]
    assistant_claude_key: str = DEFAULTS["assistant_claude_key"]
    assistant_gemini_model: str = DEFAULTS["assistant_gemini_model"]
    assistant_gemini_key: str = DEFAULTS["assistant_gemini_key"]
    assistant_openai_model: str = DEFAULTS["assistant_openai_model"]
    assistant_openai_key: str = DEFAULTS["assistant_openai_key"]
    doc_semantic: int = DEFAULTS["doc_semantic"]
    spotlight: int = DEFAULTS["spotlight"]
    spotlight_internal: int = DEFAULTS["spotlight_internal"]
    scan_parallel: int = DEFAULTS["scan_parallel"]
    backup_auto: int = DEFAULTS["backup_auto"]
    backup_dir: str = DEFAULTS["backup_dir"]
    backup_keep: int = DEFAULTS["backup_keep"]
    backup_last: str = DEFAULTS["backup_last"]
    classify_asked: int = DEFAULTS["classify_asked"]
    classify_rules_auto: int = DEFAULTS["classify_rules_auto"]
    classify_ai_auto: int = DEFAULTS["classify_ai_auto"]
    classify_read_text: int = DEFAULTS["classify_read_text"]
    classify_cloud: int = DEFAULTS["classify_cloud"]
    doc_embed_model: str = DEFAULTS["doc_embed_model"]
    assistant_permission: int = DEFAULTS["assistant_permission"]
    assistant_cloud_content: int = DEFAULTS["assistant_cloud_content"]
    auto_extract: int = DEFAULTS["auto_extract"]
    start_page: str = DEFAULTS["start_page"]
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
        try:
            os.chmod(self.config_file, 0o600)  # 設定檔裡可能有 API 金鑰：只有自己能讀
        except OSError:
            pass

    def as_dict(self) -> dict:
        data = asdict(self)
        data["home"] = str(self.home)
        return data


def default_home() -> Path:
    """目錄現在的位置：起點（REMEMOR_HOME 或 ~/.rememor），搬到其他磁碟後是 location.json 記的位置。
    那顆磁碟沒接上時丟出 location.CatalogUnavailable。"""
    from .location import current_home

    return current_home()


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
