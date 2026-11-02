"""推薦模型清單（以 MacBook Pro M1 Pro 16GB 為基準標註）。

大小為 Ollama 下載大小的約略值；速度為每張照片的大致時間，實際依圖片與設定而異。
任何 Ollama 上支援圖片輸入的模型都可以在設定中直接輸入名稱使用。
"""

RECOMMENDED = [
    {
        "name": "qwen2.5vl:7b", "kind": "vision", "size_gb": 6.0, "speed": "中（約 6–12 秒／張）",
        "badge": "推薦", "fits_16gb": True,
        "note": "中文描述自然、圖中文字辨識強，作品整理的首選。",
    },
    {
        "name": "qwen2.5vl:3b", "kind": "vision", "size_gb": 3.2, "speed": "快（約 3–5 秒／張）",
        "badge": "大量首輪", "fits_16gb": True,
        "note": "速度約快一倍，適合十萬張先快速掃一輪，之後再用大模型補細節。",
    },
    {
        "name": "qwen3-vl:8b", "kind": "vision", "size_gb": 6.1, "speed": "中",
        "badge": "較新", "fits_16gb": True,
        "note": "Qwen 新一代視覺模型，需要較新版 Ollama。",
    },
    {
        "name": "qwen3-vl:4b", "kind": "vision", "size_gb": 3.3, "speed": "快",
        "badge": "", "fits_16gb": True,
        "note": "新一代的輕量版本。",
    },
    {
        "name": "gemma3:12b", "kind": "vision", "size_gb": 8.1, "speed": "慢（約 12–25 秒／張）",
        "badge": "細節多", "fits_16gb": True,
        "note": "描述細膩，但 16GB 記憶體執行時其他程式會變慢。",
    },
    {
        "name": "gemma3:4b", "kind": "vision", "size_gb": 3.3, "speed": "快",
        "badge": "", "fits_16gb": True,
        "note": "Google 的輕量多語言模型。",
    },
    {
        "name": "minicpm-v:8b", "kind": "vision", "size_gb": 5.5, "speed": "中",
        "badge": "", "fits_16gb": True,
        "note": "另一個中英文都不錯的選擇。",
    },
    {
        "name": "llama3.2-vision:11b", "kind": "vision", "size_gb": 7.8, "speed": "慢",
        "badge": "英文", "fits_16gb": True,
        "note": "英文描述好，中文較弱。",
    },
    {
        "name": "bge-m3", "kind": "embed", "size_gb": 1.2, "speed": "很快",
        "badge": "推薦", "fits_16gb": True,
        "note": "語意搜尋用的多語言向量模型，中英文互查效果好。",
    },
    {
        "name": "qwen3-embedding:0.6b", "kind": "embed", "size_gb": 0.6, "speed": "很快",
        "badge": "輕量", "fits_16gb": True,
        "note": "較小的多語言向量模型。",
    },
]


def same_model(a: str, b: str) -> bool:
    def norm(x: str) -> str:
        return x if ":" in x else f"{x}:latest"

    return bool(a and b) and norm(a) == norm(b)
