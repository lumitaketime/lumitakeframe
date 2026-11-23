/**
 * 資料層：自動分類。分類只記在目錄裡，不改硬碟上的檔名或位置。
 * 本人設定的永遠優先；設定資料夾時，名稱相近的資料夾先問「要一起分嗎？」，同意了才照這樣分。
 */
import { api } from "../lib/api.js";
import { loadCatalog } from "./catalog.svelte.js";

/** 「要一起分嗎？」的提示：{folder, category, similar, sample} */
export const categoryPrompt = $state({ ask: null });

export const loadCategories = () => api("/api/categories", { quiet: true });
/** 一個資料夾或檔案目前的分類、是誰分的、為什麼：target 是 {folder} 或 {file} */
export const categoryOf = (target) => api("/api/category/of", { params: target, quiet: true });
export const loadReview = () => api("/api/category/review", { quiet: true });
export const acceptReview = (folders) => api("/api/category/review/accept", { body: { folders } });
/** 第一次（或首次使用的教學）本人決定要不要自動分類 */
export const classifyConsent = (opts) => api("/api/classify/consent", { body: opts });
/** 立即分類：ai＝false 只用規則；true 連 AI 一起（不等夜間） */
export const runClassify = (ai = false) => api("/api/classify/run", { body: { ai } });
/** 讓 AI 重新看一遍：要看幾個資料夾、大約幾秒 */
export const reviewEstimate = () => api("/api/classify/review/estimate", { quiet: true });
/** 讓這台電腦上的 AI 在背景逐一看資料夾並分類（看完的建議放在計畫卡上） */
export const runReview = (categories) => api("/api/classify/run", { body: { review: true, categories } });
/** 還沒確認的分類計畫卡 */
export const loadPlans = () => api("/api/category/plans", { quiet: true });
/** 新增、改名、刪除、加回預設分類：{action: add|rename|delete|restore, key, name} */
export const editCategory = (body) => api("/api/categories/edit", { body });

/** 分類顯示的名稱：本人改過名字就用本人的，否則依介面語言 */
export const categoryName = (c, t) => (c ? c.name || t(`cat.${c.key}`) : "");
export const CATEGORY_ICONS = {
  school: "book", work: "briefcase", travel: "airplane", life: "house", finance: "document", creative: "paintbrush",
  hobby: "music-note", software: "gear", other: "folder",
};

/**
 * 本人設定分類。category：分類代號／null＝不分類／"auto"＝回到自動。
 * 設定資料夾時：有名稱相近的資料夾就先問；沒有就直接記住這個習慣（之後新掃到的照這樣分）。
 */
export async function setCategory(target, category) {
  const out = await api("/api/category/set", { body: { ...target, category } });
  if (target.folder != null && category && category !== "auto") {
    if (out.similar > 0) categoryPrompt.ask = { folder: target.folder, category, similar: out.similar, sample: out.sample };
    else await api("/api/category/learn", { body: { folder: target.folder, category } }).catch(() => {});
  }
  loadCatalog();
  return out;
}
/** 本人同意「名稱相近的也照這樣分」 */
export async function learnCategory(folder, category) {
  const out = await api("/api/category/learn", { body: { folder, category } });
  loadCatalog();
  return out;
}
