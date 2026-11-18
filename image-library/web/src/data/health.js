/** 資料層：硬碟健康。只讀取硬碟的自我檢測；有狀況時由本人決定怎麼處理。 */
import { api } from "../lib/api.js";

/** 每顆硬碟的健康（最近看過的直接用上次的結果） */
export const loadHealth = () => api("/api/health", { quiet: true });
/** 重新看一次某顆硬碟的自我檢測 */
export const recheckHealth = (rootId) => api("/api/health/check", { body: { root_id: rootId } });
/** 本人的決定：pause（先暫停）／light（只記錄檔名、不讀內容）／continue（照常進行） */
export const decideHealth = (key, decision) => api("/api/health/decide", { body: { key, decision } });
