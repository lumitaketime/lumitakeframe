/** 資料層：硬碟總覽用到的引擎呼叫。掃描只讀取硬碟；「從目錄移除」只刪 Re'memor 的紀錄，不動硬碟上的檔案。 */
import { api } from "../lib/api.js";

/** 每顆硬碟（含各類型佔多少）、已接上但還沒加入目錄的硬碟、進行中的掃描工作 */
export const loadDrivesDetail = () => api("/api/drives", { params: { detail: "true" }, quiet: true });
/** 掃描這些資料夾來源（名稱） */
export const scanRoots = (names) => api("/api/jobs", { body: { kind: "scan", roots: names } });
export const stopJob = (id) => api("/api/jobs/stop", { body: { id } });
/** 加入目錄並開始掃描 */
export const addRoot = (path, name) => api("/api/roots", { body: { path, name } });
/** 在這台 Mac 上跳出「選擇資料夾」視窗；取消時回傳 null */
export const pickFolder = () => api("/api/pick-folder", { body: {} }).then((d) => d.path || null);
/** 從目錄移除一個資料夾來源：只刪目錄紀錄、縮圖與分析結果 */
export const removeRoot = (id) => api(`/api/roots/${id}`, { method: "DELETE" });
