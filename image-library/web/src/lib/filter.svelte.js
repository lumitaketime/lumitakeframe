/** 照片的快速篩選（星等、顏色標籤、檔案類型），時間軸、資料夾、相簿共用。 */
export const filter = $state({ rating: 0, label: "", kind: "" });

export function filterActive() {
  return !!(filter.rating || filter.label || filter.kind);
}

export function filterParams() {
  const p = {};
  if (filter.rating) p.rating = filter.rating;
  if (filter.label) p.label = filter.label;
  if (filter.kind) p.kind = filter.kind;
  return p;
}

export function clearFilter() {
  filter.rating = 0;
  filter.label = "";
  filter.kind = "";
}

/** 已載入的照片清單用（資料夾、相簿） */
export function matches(a) {
  if (filter.rating > 0 && (a.rating || 0) < filter.rating) return false;
  if (filter.rating < 0 && a.rating !== -1) return false;
  if (filter.label && a.label !== filter.label) return false;
  if (filter.kind === "raw" && !a.raw) return false;
  if (filter.kind === "video" && a.type !== "video") return false;
  if (filter.kind === "jpeg" && (a.raw || a.type !== "photo" || !/\.jpe?g$/i.test(a.name || ""))) return false;
  return true;
}
