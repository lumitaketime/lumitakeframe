/**
 * 矩形樹狀圖（squarified treemap）：面積代表大小，盡量讓每格接近正方形。
 * 每一列的總和、最大、最小都邊走邊算，幾千個項目也是線性時間（不必每加一個就重算整列）。
 */
export function squarify(values, x, y, w, h) {
  const n = values.length;
  const out = new Array(n).fill(null);
  let total = 0;
  for (const v of values) total += Math.max(v, 0);
  if (!total || w <= 0 || h <= 0) return out;
  const scale = (w * h) / total;
  let rx = x, ry = y, rw = w, rh = h;
  let row = [];
  let sum = 0, max = 0, min = Infinity;

  const worst = (s, mx, mn, side) => (s ? Math.max((side * side * mx) / (s * s), (s * s) / (side * side * mn)) : Infinity);

  const layout = () => {
    if (rw >= rh) {
      const cw = sum / rh;
      let cy = ry;
      for (const i of row) {
        const ch = (Math.max(values[i], 0) * scale) / cw;
        out[i] = { x: rx, y: cy, w: cw, h: ch };
        cy += ch;
      }
      rx += cw;
      rw -= cw;
    } else {
      const ch = sum / rw;
      let cx = rx;
      for (const i of row) {
        const cw = (Math.max(values[i], 0) * scale) / ch;
        out[i] = { x: cx, y: ry, w: cw, h: ch };
        cx += cw;
      }
      ry += ch;
      rh -= ch;
    }
    row = [];
    sum = 0;
    max = 0;
    min = Infinity;
  };

  for (let i = 0; i < n; i++) {
    const a = Math.max(values[i], 0) * scale;
    if (a <= 0) continue;
    const side = Math.min(rw, rh);
    if (row.length) {
      const before = worst(sum, max, min, side);
      const after = worst(sum + a, Math.max(max, a), Math.min(min, a), side);
      if (after > before) layout();
    }
    row.push(i);
    sum += a;
    max = Math.max(max, a);
    min = Math.min(min, a);
  }
  if (row.length) layout();
  return out;
}
