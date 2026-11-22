/**
 * 資料層：目錄的硬碟清單與類型統計（手冊：所有 API 呼叫集中在資料層，頁面與外框不直接呼叫 API）。
 * 只讀取引擎的目錄資料庫；硬碟沒接上也有資料。
 */
import { api } from "../lib/api.js";

export const catalog = $state({
  drives: [], // 每顆硬碟：名稱、容量、已編目的檔案數與大小、是否連線、是否掃描中
  kinds: [], // 每種類型的檔案數與總大小
  labels: [], // 每個顏色標籤有幾個項目
  pending: 0, // 標記為待刪除的項目數
  smart: [], // 智慧資料夾（儲存起來的搜尋）
  categories: [], // 自動分類：每類幾個資料夾、多少檔案
  categoryReview: 0, // AI 沒把握、請本人確認的資料夾數
  loaded: false,
  error: "",
});

let pending = null;
/** 重新讀取；同時間只會有一個請求 */
export function loadCatalog() {
  pending ??= Promise.all([api("/api/drives"), api("/api/smart-folders", { quiet: true }).catch(() => [])])
    .then(([data, smart]) => {
      catalog.smart = smart;
      catalog.drives = data.drives;
      catalog.kinds = data.kinds;
      catalog.labels = data.labels || [];
      catalog.pending = data.pending || 0;
      catalog.categories = data.categories || [];
      catalog.categoryReview = data.category_review || 0;
      catalog.error = "";
    })
    .catch((e) => {
      catalog.error = e.message;
    })
    .finally(() => {
      catalog.loaded = true;
      pending = null;
    });
  return pending;
}

/** 所有硬碟合計 */
export function catalogTotals() {
  return catalog.drives.reduce((sum, d) => ({ files: sum.files + d.files, bytes: sum.bytes + d.bytes }), { files: 0, bytes: 0 });
}

/** 這個資料夾來源（root）所在的硬碟 */
export function driveOfRoot(rootId) {
  return catalog.drives.find((d) => d.roots.some((r) => r.id === rootId)) || null;
}
