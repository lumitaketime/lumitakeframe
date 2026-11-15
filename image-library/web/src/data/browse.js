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
