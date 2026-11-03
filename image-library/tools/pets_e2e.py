"""寵物辨識真實模型測試（GitHub Actions 執行）：下載模型、偵測、比較同一隻與不同隻的相似度。

用法：python tools/pets_e2e.py <模型名稱> <照片資料夾>
資料夾裡要有 dog.jpg（YOLOX 範例照片）與 samoyed.jpg（另一隻狗）。
"""

import sys
import tempfile
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageEnhance, ImageOps

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lumilib.config import load_config  # noqa: E402
from lumilib.petid import PetEngine, download_model  # noqa: E402


def main() -> int:
    name, folder = sys.argv[1], Path(sys.argv[2])
    cfg = load_config(Path(tempfile.mkdtemp()) / "home")
    cfg.pet_model = name
    t = time.time()
    download_model(cfg, name, lambda s, d, tot: None)
    print(f"下載 {name}：{time.time() - t:.1f}s")
    eng = PetEngine.load(cfg, name)
    print("特徵輸出：", eng.emb_output, [o.shape for o in eng.emb.get_outputs()])

    dog = Image.open(folder / "dog.jpg").convert("RGB")
    other = Image.open(folder / "samoyed.jpg").convert("RGB")
    # 同一隻狗的「另一張照片」：裁切、翻轉、調亮
    w, h = dog.size
    same = ImageEnhance.Brightness(ImageOps.mirror(dog.crop((40, 60, w, h)))).enhance(1.25)

    vecs = {}
    for label, img in (("dog", dog), ("same", same), ("other", other)):
        img.thumbnail((1280, 1280))
        t = time.time()
        animals = eng.analyze(img)
        dt = time.time() - t
        print(f"{label}: {[(a.kind, round(a.score, 2), [int(v) for v in a.box]) for a in animals]}  {dt:.2f}s")
        # 小模型偶爾把狗認成貓；分群只看長相，所以這裡只要求找到動物
        if not animals:
            print(f"錯誤：{label} 沒有找到貓狗")
            return 1
        vecs[label] = max(animals, key=lambda a: a.score).embedding

    s_same = float(np.dot(vecs["dog"], vecs["same"]))
    s_other = float(np.dot(vecs["dog"], vecs["other"]))
    print(f"相似度 同一隻 {s_same:.3f}　不同隻 {s_other:.3f}　預設門檻 {cfg.pet_similarity / 100:.2f}")
    if not s_same > s_other:
        print("錯誤：同一隻的相似度沒有比較高")
        return 1
    if s_same < cfg.pet_similarity / 100:
        print("警告：同一隻的相似度低於預設門檻，門檻可能需要調低")
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
