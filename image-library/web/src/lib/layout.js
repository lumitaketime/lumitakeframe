/**
 * 等高列排版（justified layout），像 Google 相簿／Immich 的時間軸。
 * 回傳 [{ height, items: [{ asset, index, width }] }]
 */
export function justify(assets, width, target, gap = 4) {
  const rows = [];
  if (!width || !assets.length) return rows;
  let row = [];
  let sum = 0;
  const flush = (last) => {
    const gaps = gap * (row.length - 1);
    let h = (width - gaps) / sum;
    if (last && h > target * 1.15) h = target; // 最後一列不要撐滿
    rows.push({ height: h, items: row.map((x) => ({ ...x, width: x.ar * h })) });
    row = [];
    sum = 0;
  };
  assets.forEach((asset, index) => {
    const ar = Math.min(Math.max((asset.w || 1) / (asset.h || 1), 0.45), 3.2);
    row.push({ asset, index, ar });
    sum += ar;
    if (sum * target + gap * (row.length - 1) >= width) flush(false);
  });
  if (row.length) flush(true);
  return rows;
}

/** 一列排完時的自然寬度（小的日期群組可以並排） */
export function naturalWidth(assets, target, gap = 4) {
  let sum = 0;
  for (const a of assets) sum += Math.min(Math.max((a.w || 1) / (a.h || 1), 0.45), 3.2);
  return sum * target + gap * (assets.length - 1);
}

/** 手機上的正方形網格 */
export function squares(assets, width, cols, gap = 2) {
  const size = (width - gap * (cols - 1)) / cols;
  const rows = [];
  for (let i = 0; i < assets.length; i += cols) {
    rows.push({
      height: size,
      items: assets.slice(i, i + cols).map((asset, j) => ({ asset, index: i + j, width: size })),
    });
  }
  return rows;
}

/** 依列寬估計高度（尚未載入的月份用） */
export function estimateHeight(count, width, target, gap = 4) {
  if (!width) return count * 40;
  if (width < 640) {
    const cols = width < 420 ? 3 : 4;
    return Math.ceil(count / cols) * (width / cols);
  }
  const perRow = Math.max(1, width / (target * 1.35));
  return Math.ceil(count / perRow) * (target + gap);
}
