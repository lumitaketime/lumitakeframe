/** 資料層：瀏覽頁用到的引擎呼叫（目前位置的資訊、開啟檔案、記住按兩下的動作）。 */
import { api } from "../lib/api.js";
import { app } from "../lib/state.svelte.js";

/** 目前位置：所在硬碟、每一層的名稱、總檔案數與大小 */
export const loadLocation = (root, path) => api("/api/location", { params: { root, path }, quiet: true });

/** action："open"＝用預設的 App 打開；"reveal"＝在 Finder 中顯示。只讀取檔案，硬碟要接著 */
export const openItem = (item, action) => api("/api/items/open", { body: { root_id: item.root_id, path: item.path, action } });

/** 記住按兩下檔案時要做什麼（之後可以在設定更改） */
export async function saveOpenAction(action) {
  await api("/api/settings", { body: { open_action: action } });
  if (app.server?.ui) app.server.ui.open_action = action;
}

/** 快速預覽：可以直接播放或顯示的原檔（音樂、PDF）的網址；只讀取，硬碟要接著 */
export const rawUrl = (item) => `/api/items/raw?root=${item.root_id}&path=${encodeURIComponent(item.path)}`;

/** 快速預覽：文字檔開頭的一段 */
export const loadText = (item) => api("/api/items/text", { params: { root: item.root_id, path: item.path }, quiet: true });

/** 顏色標籤：只存在 Re'memor 的目錄裡，不寫到硬碟。label 為 null＝拿掉 */
export function setLabel(items, label) {
  return api("/api/items/label", { body: {
    files: items.filter((i) => i.type === "file").map((i) => i.id),
    folders: items.filter((i) => i.type === "folder" && typeof i.id === "number").map((i) => i.id),
    label,
  } });
}

/** 喜好項目：把資料夾釘在側邊欄，或從側邊欄移除（只影響顯示） */
export const pinFolder = (rootId, path, on) => api("/api/folders/prefs", { body: { root_id: rootId, path, favorite: on } });
/** 喜好項目的順序：items 是 [{root_id, path}] */
export const orderPins = (items) => api("/api/folders/order", { body: { items } });

/** 拖曳資料夾時帶著的資料類型（拖到側邊欄就釘選） */
export const DRAG_FOLDER = "application/x-rememor-folder";

/** 佔比圖（方塊圖、環狀圖）：目前層與下一層的大小 */
export const loadUsage = (root, path) => api("/api/usage", { params: { root, path }, quiet: true });
/** 資訊欄：這個資料夾（含子資料夾）裡各類型佔多少 */
export const loadKinds = (root, path) => api("/api/location/kinds", { params: { root, path }, quiet: true }).then((d) => d.kinds);
