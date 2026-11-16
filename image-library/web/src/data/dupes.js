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

// ---- 待刪除：標記只寫 Re'memor 的資料庫；清理要使用者在介面上確認後才會執行 ----

/** 把 remove 標記為待刪除，keep 是要保留的（至少一份）。只做標記，不刪除檔案 */
export const markItems = (kind, keep, remove) => api("/api/dupes/mark", { body: { kind, keep, remove } });
export const unmarkItems = (ids) => api("/api/dupes/unmark", { body: { ids } });
/** 待刪除清單，依硬碟分組 */
export const loadPending = () => api("/api/pending", { quiet: true });
/** 移到垃圾桶：只在使用者按下確認後呼叫。引擎會逐項再驗證，不符的跳過並回報原因 */
export const trashPending = (ids) => api("/api/pending/trash", { body: { ids, confirm: true } });
/** 唯讀的硬碟（NTFS）：把清單存成文字檔，存在 Mac 上 */
export const exportPending = (drive) => api("/api/pending/export", { body: { drive } });
