"""推薦模型清單，依這台電腦的記憶體標示「適合」程度。

size_gb：Ollama 下載大小的約略值（實際以下載時顯示為準）。
min_ram：建議的電腦記憶體（GB）；低於這個值也能跑，但會很慢或擠掉其他程式。
quality／speed：1–5，用來排序與挑選推薦。
任何 Ollama 上支援圖片輸入的模型都可以在設定中直接輸入名稱使用。
"""

from __future__ import annotations

import os
import platform
import subprocess
import sys

RECOMMENDED = [
    # ---- 視覺模型（描述照片、產生關鍵字、辨識圖中文字）----
    {
        "name": "gemma4:e2b", "kind": "vision", "family": "Gemma 4", "size_gb": 4.6, "min_ram": 8,
        "quality": 3, "speed": 5, "speed_text": "很快",
        "note": "Gemma 4 輕量版，實測中文描述與圖中文字都正確，速度約 e4b 的兩倍。適合 8GB 的 Mac 或照片很多時先掃一輪。",
    },
    {
        "name": "gemma4:e4b", "kind": "vision", "family": "Gemma 4", "size_gb": 6.6, "min_ram": 16,
        "quality": 5, "speed": 4, "speed_text": "快",
        "note": "實測描述最自然、關鍵字中英對照、圖中文字辨識正確。16GB 的 Mac 首選。",
    },
    {
        "name": "gemma4:26b", "kind": "vision", "family": "Gemma 4", "size_gb": 18, "min_ram": 32,
        "quality": 6, "speed": 3, "speed_text": "中",
        "note": "混合專家（MoE）架構，品質高、速度不錯，需要 32GB 以上記憶體。",
    },
    {
        "name": "gemma4:31b", "kind": "vision", "family": "Gemma 4", "size_gb": 20, "min_ram": 48,
        "quality": 6, "speed": 2, "speed_text": "慢",
        "note": "Gemma 4 最大版，最細緻，適合 48GB 以上的 Mac Studio／MacBook Pro。",
    },
    {
        "name": "qwen3-vl:4b-instruct", "kind": "vision", "family": "Qwen3-VL", "size_gb": 3.3, "min_ram": 8,
        "quality": 3, "speed": 2, "speed_text": "慢",
        "note": "不思考的版本（qwen3-vl:4b 預設會先思考，實測無法輸出結果）。可以用，但比 Gemma 4 慢不少。",
    },
    {
        "name": "qwen3-vl:8b-instruct", "kind": "vision", "family": "Qwen3-VL", "size_gb": 6.1, "min_ram": 16,
        "quality": 4, "speed": 2, "speed_text": "慢",
        "note": "不思考的版本。中文與文字辨識強，但速度比 Gemma 4 慢，建議先用 Gemma 4。",
    },
    {
        "name": "qwen3-vl:30b", "kind": "vision", "family": "Qwen3-VL", "size_gb": 19, "min_ram": 32,
        "quality": 5, "speed": 3, "speed_text": "中",
        "note": "MoE 架構的大模型，品質高，需要 32GB 以上記憶體。",
    },
    {
        "name": "qwen2.5vl:7b", "kind": "vision", "family": "Qwen2.5-VL", "size_gb": 6.0, "min_ram": 16,
        "quality": 3, "speed": 3, "speed_text": "中",
        "note": "上一代的穩定版本，舊版 Ollama 也能用。",
    },
    {
        "name": "gemma3:12b", "kind": "vision", "family": "Gemma 3", "size_gb": 8.1, "min_ram": 24,
        "quality": 4, "speed": 2, "speed_text": "慢",
        "note": "上一代 Gemma，描述細膩但較慢。",
    },
    {
        "name": "minicpm-v:8b", "kind": "vision", "family": "MiniCPM-V", "size_gb": 5.5, "min_ram": 16,
        "quality": 3, "speed": 3, "speed_text": "中",
        "note": "另一個中英文都不錯的選擇。",
    },
    # ---- 語意搜尋向量模型 ----
    {
        "name": "bge-m3", "kind": "embed", "family": "BGE", "size_gb": 1.2, "min_ram": 8,
        "quality": 4, "speed": 5, "speed_text": "很快",
        "note": "語意搜尋用的多語言向量模型，中英文互查效果好。",
    },
    {
        "name": "qwen3-embedding:0.6b", "kind": "embed", "family": "Qwen3", "size_gb": 0.6, "min_ram": 8,
        "quality": 3, "speed": 5, "speed_text": "很快",
        "note": "較小的多語言向量模型。",
    },
]


def same_model(a: str, b: str) -> bool:
    def norm(x: str) -> str:
        return x if ":" in x else f"{x}:latest"

    return bool(a and b) and norm(a) == norm(b)


# ---- 這台電腦 ------------------------------------------------------------------------------

_machine: dict | None = None


def _sysctl(name: str) -> str:
    try:
        return subprocess.run(["sysctl", "-n", name], capture_output=True, text=True, timeout=3).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def machine_info() -> dict:
    """{"ram_gb", "chip", "apple_silicon"}"""
    global _machine
    if _machine is not None:
        return _machine
    ram = 0
    chip = ""
    if sys.platform == "darwin":
        try:
            ram = int(_sysctl("hw.memsize") or 0)
        except ValueError:
            ram = 0
        chip = _sysctl("machdep.cpu.brand_string")
    if not ram:
        try:
            ram = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
        except (ValueError, OSError, AttributeError):
            ram = 0
    chip = chip or platform.processor() or platform.machine()
    _machine = {
        "ram_gb": round(ram / (1024 ** 3)) if ram else 0,
        "chip": chip,
        "apple_silicon": sys.platform == "darwin" and platform.machine() == "arm64",
    }
    return _machine


def fit(model: dict, ram_gb: int) -> str:
    """"good"＝適合、"tight"＝可以跑但吃緊、"too_big"＝不建議。"""
    if not ram_gb:
        return "good"
    if ram_gb >= model["min_ram"]:
        return "good"
    if ram_gb >= model["size_gb"] + 4:
        return "tight"
    return "too_big"


def recommend(ram_gb: int) -> dict:
    """依記憶體挑「品質優先」與「速度優先」的視覺模型、以及向量模型。"""
    def pick(kind: str, key) -> str | None:
        cands = [m for m in RECOMMENDED if m["kind"] == kind and fit(m, ram_gb) == "good"]
        if not cands:
            cands = [min((m for m in RECOMMENDED if m["kind"] == kind), key=lambda m: m["size_gb"])]
        return max(cands, key=key)["name"]

    return {
        "best": pick("vision", lambda m: (m["quality"], m["speed"], -m["size_gb"])),
        "fast": pick("vision", lambda m: (m["speed"], m["quality"], -m["size_gb"])),
        "embed": pick("embed", lambda m: (m["quality"], -m["size_gb"])),
    }


def annotated(ram_gb: int, installed_names: list[str]) -> list[dict]:
    picks = recommend(ram_gb)
    out = []
    for m in RECOMMENDED:
        badge = ""
        if m["name"] == picks["best"]:
            badge = "最適合這台電腦"
        elif m["name"] == picks["fast"]:
            badge = "速度優先"
        elif m["name"] == picks["embed"]:
            badge = "推薦"
        out.append({
            **m, "fit": fit(m, ram_gb), "badge": badge,
            "installed": any(same_model(m["name"], n) for n in installed_names),
        })
    return out
