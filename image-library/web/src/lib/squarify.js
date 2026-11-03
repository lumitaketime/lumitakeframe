/** 矩形樹狀圖（squarified treemap）：面積代表大小，盡量讓每格接近正方形。 */
export function squarify(values, x, y, w, h) {
  const total = values.reduce((s, v) => s + v, 0);
  const out = new Array(values.length);
  if (!total || w <= 0 || h <= 0) return out.fill(null);
  const scale = (w * h) / total;
  const items = values.map((v, i) => ({ i, a: Math.max(v, 0) * scale }));
  let rect = { x, y, w, h };
  let row = [];

  const worst = (r, side) => {
    const s = r.reduce((t, it) => t + it.a, 0);
    if (!s) return Infinity;
    let max = 0, min = Infinity;
    for (const it of r) {
      max = Math.max(max, it.a);
      min = Math.min(min, it.a);
    }
    return Math.max((side * side * max) / (s * s), (s * s) / (side * side * min));
  };

  const layout = (r) => {
    const s = r.reduce((t, it) => t + it.a, 0);
    if (rect.w >= rect.h) {
      const cw = s / rect.h;
      let cy = rect.y;
      for (const it of r) {
        const ch = it.a / cw;
        out[it.i] = { x: rect.x, y: cy, w: cw, h: ch };
        cy += ch;
      }
      rect = { x: rect.x + cw, y: rect.y, w: rect.w - cw, h: rect.h };
    } else {
      const ch = s / rect.w;
      let cx = rect.x;
      for (const it of r) {
        const cw = it.a / ch;
        out[it.i] = { x: cx, y: rect.y, w: cw, h: ch };
        cx += cw;
      }
      rect = { x: rect.x, y: rect.y + ch, w: rect.w, h: rect.h - ch };
    }
  };

  for (const it of items.filter((t) => t.a > 0)) {
    const side = Math.min(rect.w, rect.h);
    if (!row.length || worst([...row, it], side) <= worst(row, side)) row.push(it);
    else {
      layout(row);
      row = [it];
    }
  }
  if (row.length) layout(row);
  return out;
}
