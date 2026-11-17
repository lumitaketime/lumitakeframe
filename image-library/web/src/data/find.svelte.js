/**
 * 資料層：搜尋（檔名、資料夾路徑、文件內容、文字辨識、照片描述合在一份結果）、
 * 文件文字與文字辨識的進度、智慧資料夾（儲存起來的搜尋）。只讀資料庫，硬碟沒接上也搜得到。
 */
import { api } from "../lib/api.js";

const PAGE = 50; // 每一段 50 筆：內容命中要附段落，一次不拿太多

/** 搜尋條件裡會送到引擎的欄位（網址上也用同樣的名字）；all＝「所有硬碟」，暫時不看 root／path 但記住從哪裡開始搜尋 */
export const FIND_KEYS = ["q", "root", "path", "kind", "year", "size", "drive"];
const URL_KEYS = [...FIND_KEYS, "all"];

/** 從網址的 query 取出搜尋條件（空的不算） */
export function findParams(query) {
  return Object.fromEntries(URL_KEYS.filter((k) => query[k] !== undefined && query[k] !== "").map((k) => [k, query[k]]));
}

/** 實際送到引擎的條件：選了「所有硬碟」就不限資料夾 */
export function engineParams(query) {
  const p = findParams(query);
  if (p.all) {
    delete p.root;
    delete p.path;
  }
  delete p.all;
  return p;
}

/** 搜尋頁的網址；smart＝從哪個智慧資料夾來的（側邊欄標示目前位置） */
export function findHref(params, smart = null) {
  const qs = new URLSearchParams(findParams(params));
  if (smart) qs.set("smart", smart);
  return `/find${qs.toString() ? `?${qs}` : ""}`;
}

/** 搜尋結果的來源，介面和資料夾的項目來源相同（state.total、get(i)、peek(i)） */
export function createFindSource(params) {
  const state = $state({ total: null, more: false, terms: [], tick: 0, error: "" });
  const pages = new Map();
  const pending = new Set();
  let gen = 0;

  async function load(p) {
    if (pages.has(p) || pending.has(p)) return;
    pending.add(p);
    const mine = gen;
    try {
      const data = await api("/api/find", { params: { ...params, offset: p * PAGE, limit: PAGE }, quiet: true });
      if (mine !== gen) return;
      pages.set(p, data.items);
      state.total = data.total;
      state.more = data.more;
      state.terms = data.terms;
      state.error = "";
    } catch (e) {
      if (mine === gen) state.error = e.message;
    } finally {
      pending.delete(p);
      state.tick++;
    }
  }

  return {
    state,
    get(i) {
      state.tick;
      const p = Math.floor(i / PAGE);
      const items = pages.get(p);
      if (!items) {
        load(p);
        return undefined;
      }
      return items[i - p * PAGE];
    },
    peek(i) {
      const p = Math.floor(i / PAGE);
      return pages.get(p)?.[i - p * PAGE];
    },
    start: () => load(0),
    /** 重新查詢（例如讀完文件文字後，結果會變多） */
    reload() {
      gen++;
      pages.clear();
      pending.clear();
      load(0);
    },
    retry() {
      state.error = "";
      load(0);
    },
    touch: () => state.tick++,
  };
}

/** 還有多少文件要讀取文字、多少掃描檔與截圖要辨識 */
export const loadTextStatus = () => api("/api/text/status", { quiet: true });
/** 開始讀取文件文字（只讀取檔案，結果寫在目錄資料庫） */
export const startExtract = () => api("/api/jobs", { body: { kind: "extract" } });
/** 開始文字辨識（只在 Mac 上可以用） */
export const startOcr = () => api("/api/jobs", { body: { kind: "ocr" } });
export const stopJob = (id) => api("/api/jobs/stop", { body: { id } });

/** 智慧資料夾 */
export const loadSmartFolders = () => api("/api/smart-folders", { quiet: true });
export const saveSmartFolder = (name, query) => api("/api/smart-folders", { body: { name, query } });
export const deleteSmartFolder = (id) => api(`/api/smart-folders/${id}`, { method: "DELETE" });
