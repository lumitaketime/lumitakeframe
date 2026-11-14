/**
 * 資料層：目錄的硬碟清單與類型統計（手冊：所有 API 呼叫集中在資料層，頁面與外框不直接呼叫 API）。
 * 只讀取引擎的目錄資料庫；硬碟沒接上也有資料。
 */
import { api } from "../lib/api.js";

export const catalog = $state({
  drives: [], // 每顆硬碟：名稱、容量、已編目的檔案數與大小、是否連線、是否掃描中
  kinds: [], // 每種類型的檔案數與總大小
  loaded: false,
  error: "",
});

let pending = null;
/** 重新讀取；同時間只會有一個請求 */
export function loadCatalog() {
  pending ??= api("/api/drives")
    .then((data) => {
      catalog.drives = data.drives;
      catalog.kinds = data.kinds;
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
