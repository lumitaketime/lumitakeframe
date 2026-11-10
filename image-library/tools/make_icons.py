"""從 Re'memor 圖示母版（2048×2048，圓角外是白色）產生各平台需要的圖示。

用法（在 image-library 資料夾）：python3 tools/make_icons.py "../docs/brand/圖示母版 1024.png" <輸出資料夾>
產生後把輸出資料夾裡的檔案複製到 web/public、desktop/src-tauri/icons、desktop/splash、android 的 mipmap 資料夾。
"""

import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

src, out = Path(sys.argv[1]), Path(sys.argv[2])
out.mkdir(parents=True, exist_ok=True)
m = np.asarray(Image.open(src).convert("RGB"), dtype=np.float64)
H, W, _ = m.shape
ys, xs = np.mgrid[0:H, 0:W]

# 1) 背景漸層：在不含玻璃盤的背景區域，用「顏色 = a + b·x + c·y」擬合（設計稿是線性漸層）
bg = np.zeros((H, W), bool)
bg[180:H - 180, 180:W - 180] = True
bg[380:1600, 300:1700] = False  # 玻璃盤與橘點所在
white = (m > 250).all(axis=2)
bg &= ~white
A = np.stack([np.ones(bg.sum()), xs[bg] / W, ys[bg] / H], axis=1)
coef, *_ = np.linalg.lstsq(A, m[bg], rcond=None)
pred = A @ coef
rms = np.sqrt(((pred - m[bg]) ** 2).mean())
print(f"漸層擬合誤差（0–255）：{rms:.2f}")


def gradient(x0, y0, x1, y1, size):
    """在母版座標 (x0,y0)–(x1,y1) 的範圍產生 size×size 的漸層背景。"""
    gx = np.linspace(x0, x1, size)[None, :] / W
    gy = np.linspace(y0, y1, size)[:, None] / H
    img = coef[0] + coef[1] * gx[..., None] + coef[2] * gy[..., None]
    # 設計稿的漸層到了終點色就不再變化：限制在 海藍 #2A6FC0 與 藏青 #0B2346 之間
    img = np.clip(img, (11, 35, 70), (42, 111, 192))
    return Image.fromarray(np.clip(img, 0, 255).astype(np.uint8), "RGB")


# 2) 圓角遮罩：和四個角相連的白色是外面；邊緣半透明的像素依「和白色混合的比例」還原透明度
outside = np.zeros((H, W), bool)
from collections import deque  # noqa: E402

q = deque([(0, 0), (0, W - 1), (H - 1, 0), (H - 1, W - 1)])
near_white = (m > 245).all(axis=2)
while q:
    y, x = q.popleft()
    if y < 0 or x < 0 or y >= H or x >= W or outside[y, x] or not near_white[y, x]:
        continue
    outside[y, x] = True
    q.extend(((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)))
full = np.asarray(gradient(0, 0, W - 1, H - 1, W), dtype=np.float64)
band = np.asarray(Image.fromarray((outside * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(9))) > 0
alpha = np.ones((H, W))
alpha[outside] = 0
edge = band & ~outside
# 邊緣像素 = a·背景色 + (1-a)·白色  →  a = (255 - 像素) / (255 - 背景色)
a = ((255 - m[edge]) / np.maximum(1, 255 - full[edge])).mean(axis=1)
alpha[edge] = np.clip(a, 0, 1)
rgb = m.copy()
rgb[edge] = full[edge]  # 邊緣像素用背景色，透明度另外記
rounded = Image.fromarray(np.dstack([np.clip(rgb, 0, 255), alpha * 255]).astype(np.uint8), "RGBA")
rounded.save(out / "master-rounded.png")

# 3) 滿版正方形（角落補上漸層）：給 iOS、PWA maskable、Android 圓形圖示用
square = gradient(0, 0, W - 1, H - 1, W).convert("RGBA")
square.alpha_composite(rounded)
square.save(out / "master-square.png")


def padded_square(scale: float, size: int) -> Image.Image:
    """整個畫面縮小到 scale，周圍補上同一個漸層（讓玻璃盤落在安全範圍內）。"""
    pad = (1 / scale - 1) / 2
    big = gradient(-pad * W, -pad * H, (1 + pad) * W - 1, (1 + pad) * H - 1, size).convert("RGBA")
    inner = square.resize((round(size * scale),) * 2, Image.LANCZOS)
    off = (size - inner.width) // 2
    big.alpha_composite(inner, (off, off))
    return big


def mac_grid(size: int) -> Image.Image:
    """macOS 圖示格線：1024 畫布中央 824×824，四周留白（和系統其他 App 一樣大）。"""
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    body = round(size * 824 / 1024)
    off = (size - body) // 2
    canvas.alpha_composite(rounded.resize((body, body), Image.LANCZOS), (off, off))
    return canvas


def save(img: Image.Image, rel: str, size: int | None = None, mode: str | None = None):
    path = out / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    if size:
        img = img.resize((size, size), Image.LANCZOS)
    if mode:
        img = img.convert(mode)
    img.save(path, optimize=True)


# 網頁（PWA）
save(rounded, "web/icon.png", 256)
save(rounded, "web/icons/icon-192.png", 192)
save(rounded, "web/icons/icon-512.png", 512)
save(square, "web/icons/apple-touch-icon.png", 180, "RGB")
save(padded_square(0.82, 512), "web/icons/maskable-512.png", None, "RGB")

# Mac App（Tauri）
mac = mac_grid(1024)
save(mac, "tauri/source.png")
save(mac, "tauri/icon.png", 512)
save(mac, "tauri/128x128@2x.png", 256)
save(mac, "tauri/128x128.png", 128)
save(mac, "tauri/32x32.png", 32)
mac.save(out / "tauri/icon.icns", sizes=[(16, 16), (32, 32), (64, 64), (128, 128), (256, 256), (512, 512), (1024, 1024)])

# 選單列：單色模板影像（黑色＋透明，系統自動處理淺色與深色）：三層疊起來的盤
S = 44 * 8
tray = Image.new("L", (S, S), 0)
d = ImageDraw.Draw(tray)
w = round(S * 0.07)
left, right, rh = S * 0.16, S * 0.84, S * 0.11  # 盤的左右邊、橢圓的半高
tops = (S * 0.27, S * 0.47, S * 0.67)  # 每層盤面的中心高度
d.ellipse([left, tops[0] - rh, right, tops[0] + rh], outline=255, width=w)  # 最上層：完整的盤面
for y in tops[1:]:  # 下面兩層：只看得到前緣的弧線
    d.arc([left, y - rh, right, y + rh], start=0, end=180, fill=255, width=w)
for x in (left + w / 2, right - w / 2):  # 兩側的邊
    d.line([x, tops[0], x, tops[-1]], fill=255, width=w)
tray = tray.resize((44, 44), Image.LANCZOS)
Image.merge("RGBA", (Image.new("L", (44, 44), 0),) * 3 + (tray,)).save(out / "tauri/tray.png", optimize=True)

# Android：一般圖示（圓角）與圓形圖示
for name, px in (("mdpi", 48), ("hdpi", 72), ("xhdpi", 96), ("xxhdpi", 144), ("xxxhdpi", 192)):
    canvas = Image.new("RGBA", (px, px), (0, 0, 0, 0))
    body = round(px * 0.92)
    canvas.alpha_composite(rounded.resize((body, body), Image.LANCZOS), ((px - body) // 2,) * 2)
    save(canvas, f"android/mipmap-{name}/ic_launcher.png")
    circle = padded_square(0.86, px * 4)
    mask = Image.new("L", circle.size, 0)
    ImageDraw.Draw(mask).ellipse([0, 0, circle.width - 1, circle.height - 1], fill=255)
    circle.putalpha(mask)
    save(circle, f"android/mipmap-{name}/ic_launcher_round.png", px)

# 啟動畫面
save(rounded, "splash/icon.png", 256)
print("完成：", sorted(str(p.relative_to(out)) for p in out.rglob("*.*")))
