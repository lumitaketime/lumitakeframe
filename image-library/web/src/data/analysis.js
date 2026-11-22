/** 資料層：檔案分析與關鍵字雲、我的關鍵字規則、本人的身分與習慣（都只讀寫這台電腦上的目錄）。 */
import { api } from "../lib/api.js";

export const loadAnalysis = () => api("/api/analysis", { quiet: true });
/** 重新找出常見的詞（背景工作） */
export const runAnalysis = () => api("/api/analysis/run", { body: {} });
export const loadWord = (w) => api("/api/analysis/word", { params: { w }, quiet: true });
/** 「分到某分類」：先算影響範圍，回傳一個還沒套用的提案（含預覽）；套用用 runAction，復原用 undoAction */
export const proposeRule = (pattern, category, yearFrom, yearTo) =>
  api("/api/category/rule/propose", { body: { pattern, category, year_from: yearFrom || null, year_to: yearTo || null } });
export const loadRules = () => api("/api/category/rules", { quiet: true });
export const deleteRule = (id) => api("/api/category/rules/delete", { body: { id } });
export const loadProfile = () => api("/api/category/profile", { quiet: true });
export const saveProfile = (p) => api("/api/category/profile", { body: p });
