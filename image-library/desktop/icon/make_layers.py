"""產生 App 圖示的五個圖層（Icon Composer 用），數值照設計稿「Re'memor 標誌與圖示」的 Mark 母版（預設外觀）。

用法：python3 make_layers.py  → layers/ 裡的五個 SVG。
高光、陰影、透明與染色外觀由 macOS 26 的 Liquid Glass 套用，不烘焙進圖層；背景是整張正方形，圓角遮罩由系統加上。
"""
from pathlib import Path

OUT = Path(__file__).parent / "layers"
HEAD = '<svg xmlns="http://www.w3.org/2000/svg" width="1024" height="1024" viewBox="0 0 1024 1024">'
FACE, EDGE, DOT = "#ffffff", "#ffffff", "#ff8d28"
EDGE_OP, SIDE_OP = 0.62, 0.12


def side(c: int) -> str:
    return f"M194 {c} V{c + 44} A318 118 0 0 0 830 {c + 44} V{c} A318 118 0 0 1 194 {c} Z"


def disc(cy: int, face_op: float, top_edge: int, ring_edge_op: float) -> str:
    soft = round(EDGE_OP * 0.55, 3)
    return (f'{HEAD}<path d="{side(cy)}" fill="{FACE}" fill-opacity="{SIDE_OP}" stroke="{EDGE}" stroke-opacity="{soft}" stroke-width="6"/>'
            f'<ellipse cx="512" cy="{cy}" rx="318" ry="118" fill="{FACE}" fill-opacity="{face_op}" stroke="{EDGE}" '
            f'stroke-opacity="{ring_edge_op}" stroke-width="8"/>'
            f'<path d="M194 {cy} A318 118 0 0 1 830 {cy}" fill="none" stroke="{EDGE}" stroke-opacity="{EDGE_OP}" '
            f'stroke-width="{top_edge}" stroke-linecap="round"/></svg>\n')


LAYERS = {
    "1-背景.svg": (f'{HEAD}<defs><linearGradient id="bg" x1="0" y1="0" x2="0.35" y2="1">'
                 '<stop offset="0" stop-color="#2a6fc0"/><stop offset="1" stop-color="#0b2346"/></linearGradient></defs>'
                 '<rect width="1024" height="1024" fill="url(#bg)"/></svg>\n'),
    "2-底層盤.svg": disc(620, 0.16, 10, round(EDGE_OP * 0.55, 3)),
    "3-中層盤.svg": disc(490, 0.24, 10, round(EDGE_OP * 0.55, 3)),
    "4-頂層盤.svg": disc(360, 0.34, 12, EDGE_OP),
    "5-橘點與波紋.svg": (f'{HEAD}<ellipse cx="604" cy="352" rx="172" ry="64" fill="none" stroke="{DOT}" stroke-opacity="0.27" stroke-width="8"/>'
                     f'<ellipse cx="604" cy="352" rx="108" ry="40" fill="none" stroke="{DOT}" stroke-opacity="0.6" stroke-width="10"/>'
                     f'<circle cx="604" cy="346" r="46" fill="{DOT}"/></svg>\n'),
}

if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    for name, svg in LAYERS.items():
        (OUT / name).write_text(svg, encoding="utf-8")
        print(OUT / name)
