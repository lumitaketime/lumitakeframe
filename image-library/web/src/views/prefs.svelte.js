/**
 * 檢視的偏好：每個位置記住上次用的檢視模式；縮圖大小、排序、列表的欄位與欄寬是全域的。
 * 只存在這台裝置的瀏覽器裡。
 */
function read(key, fallback) {
  try {
    const v = localStorage.getItem(key);
    return v === null ? fallback : JSON.parse(v);
  } catch {
    return fallback;
  }
}
function save(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* 只影響這次 */
  }
}

/** 這一步可以用的檢視（直欄、樹狀、佔比在下一步接上） */
export const VIEWS = ["icons", "list"];
export const ALL_VIEWS = ["icons", "list", "columns", "tree", "treemap"];
export const ICON_MIN = 64;
export const ICON_MAX = 256;
export const COLUMNS = ["name", "size", "kind", "mtime", "drive"];
const WIDTHS = { size: 90, kind: 110, mtime: 120, drive: 150 };

export const prefs = $state({
  views: read("view.byPlace", {}), // 位置 → 檢視模式
  last: read("view.last", "list"),
  iconSize: Math.min(ICON_MAX, Math.max(ICON_MIN, read("view.iconSize", 112))),
  sort: read("view.sort", "name"),
  desc: read("view.desc", false),
  hidden: read("view.hiddenColumns", []), // 不顯示的欄位
  widths: { ...WIDTHS, ...read("view.widths", {}) },
});

export const viewFor = (place) => (VIEWS.includes(prefs.views[place]) ? prefs.views[place] : VIEWS.includes(prefs.last) ? prefs.last : "list");
export function setView(place, view) {
  if (!VIEWS.includes(view)) return;
  prefs.views[place] = view;
  prefs.last = view;
  const keys = Object.keys(prefs.views);
  if (keys.length > 500) delete prefs.views[keys[0]]; // 只記最近的五百個位置
  save("view.byPlace", prefs.views);
  save("view.last", view);
}
export function setIconSize(px) {
  prefs.iconSize = Math.round(Math.min(ICON_MAX, Math.max(ICON_MIN, px)));
  save("view.iconSize", prefs.iconSize);
}
export function setSort(column) {
  if (prefs.sort === column) prefs.desc = !prefs.desc;
  else {
    prefs.sort = column;
    prefs.desc = column === "size" || column === "mtime"; // 大小與日期預設由大到小、由新到舊
  }
  save("view.sort", prefs.sort);
  save("view.desc", prefs.desc);
}
export function toggleColumn(column) {
  if (column === "name") return;
  prefs.hidden = prefs.hidden.includes(column) ? prefs.hidden.filter((c) => c !== column) : [...prefs.hidden, column];
  save("view.hiddenColumns", prefs.hidden);
}
export function setWidth(column, px) {
  prefs.widths[column] = Math.round(Math.min(400, Math.max(60, px)));
  save("view.widths", prefs.widths);
}
