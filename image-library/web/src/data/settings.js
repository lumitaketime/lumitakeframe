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

// ---- 目錄放在哪裡 ----
/** 目錄現在的位置、大小、所在磁碟剩多少空間、搬走前的舊目錄在哪 */
export const loadCatalogLocation = () => api("/api/catalog/location", { quiet: true });
/** 選一個要放目錄的資料夾（Mac 的選擇視窗） */
export const pickCatalogFolder = () => api("/api/pick-folder", { body: { purpose: "catalog" } }).then((d) => d.path || null);
/** 檢查能不能搬到 path：回傳 {target, error} */
export const checkCatalogMove = (path) => api("/api/catalog/location/check", { body: { path } });
/** 開始搬移（背景工作；複製並確認完整後自動重新開啟） */
export const moveCatalog = (path) => api("/api/catalog/move", { body: { path } });
/** 在 Finder 中顯示某個資料夾（例如搬走前的舊目錄） */
export const revealFolder = (path) => api("/api/reveal-path", { body: { path } });

// ---- AI 助理用哪個模型 ----
/** Ollama 已下載的模型、推薦清單（含大小與建議的記憶體） */
export const loadModels = () => api("/api/models", { quiet: true });
/** 試一下現在的設定：請模型回一句話（不送任何檔案資料） */
export const testAssistant = () => api("/api/assistant/test", { body: {} });
/** 一次存好幾個設定（例如助理的服務網址、模型、金鑰），回傳最新的設定（不含金鑰） */
export const saveSettings = (values) => api("/api/settings", { body: values });
