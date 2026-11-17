/** 資料層：設定頁用到的引擎呼叫。設定都存在這台電腦的目錄資料夾裡（~/.rememor），不上傳。 */
import { api } from "../lib/api.js";
import { app } from "../lib/state.svelte.js";

export const loadSettings = () => api("/api/settings", { quiet: true });

/** 存一個設定；介面上立即用得到的（例如啟動頁、按兩下的動作）同時更新 app.server.ui */
export async function saveSetting(key, value) {
  const next = await api("/api/settings", { body: { [key]: value } });
  if (app.server?.ui && key in app.server.ui) app.server.ui[key] = value;
  return next;
}

/** 目錄資料夾的位置與大小（資料庫、縮圖） */
export const loadStorage = () => api("/api/storage", { quiet: true });
/** 在 Finder 中顯示目錄資料夾（只在這台 Mac 上） */
export const revealCatalog = () => api("/api/storage/reveal", { body: {} });
/** 清除 Re'memor 存的文件文字與索引（不碰硬碟上的檔案），之後重新讀取 */
export const resetText = (ocrOnly = false) => api("/api/text/reset", { body: { confirm: true, ocr_only: ocrOnly || undefined } });
