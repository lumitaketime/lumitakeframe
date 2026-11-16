/** 資料層：重複項目。這裡只查詢與啟動「比對內容」；比對只讀取檔案，不刪除任何東西。 */
import { api } from "../lib/api.js";

/** 還要比對多少、重複資料夾與重複檔案各有幾組、可釋出多少 */
export const loadDupesSummary = () => api("/api/dupes/summary", { quiet: true });
export const loadDupeFolders = (offset = 0, limit = 100) => api("/api/dupes/folders", { params: { offset, limit }, quiet: true });
export const loadDupeFiles = (offset = 0, limit = 100, pending = false) =>
  api("/api/dupes/files", { params: { offset, limit, pending: pending ? "true" : undefined }, quiet: true });
/** 開始比對內容；large＝連 1GB 以上的大檔案也讀 */
export const startCompare = (large = false) => api("/api/jobs", { body: { kind: "compare", large: large || undefined } });
export const stopCompare = (id) => api("/api/jobs/stop", { body: { id } });

/** 粗估讀完要多久（秒）：外接硬碟以每秒 120MB 估算，實際會依硬碟與連接方式不同 */
export const estimateSeconds = (bytes) => bytes / 120_000_000;
