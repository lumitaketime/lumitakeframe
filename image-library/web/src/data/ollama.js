/**
 * 資料層：Ollama（在這台電腦上執行 AI 模型的程式）與模型實測比較。
 * 安裝／更新只在本人按下確認後才呼叫：會從 Ollama 官方網站下載 Mac 版，不會送出任何檔案或資料。
 */
import { api } from "../lib/api.js";

/** Ollama 裝了沒、有沒有在執行、版本、能不能在 App 裡一鍵安裝 */
export const loadOllamaStatus = () => api("/api/ollama/status", { quiet: true });
/** 下載並安裝（或更新）Ollama：背景工作，進度在 app.server.jobs 裡（kind = "ollama_install"） */
export const installOllama = () => api("/api/ollama/install", { body: {} });
/** 打開已經安裝的 Ollama */
export const startOllama = () => api("/api/ollama/start", { body: {} });
/** 上一次的實測比較結果（沒有就是 null） */
export const loadCompare = () => api("/api/models/compare", { quiet: true }).then((d) => d.result);
/** 開始實測比較：用 n 張自己的照片讓這些模型各跑一次（不寫進圖庫） */
export const startCompare = (models, n) => api("/api/models/compare", { body: { models, n } });
