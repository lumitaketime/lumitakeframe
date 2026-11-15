/**
 * 資料層：列表與圖像檢視的項目來源。只向引擎要「看得到的那一段」（每段 200 筆），
 * 拿過的留在記憶體裡；捲到很遠的地方時，把離得最遠的段落丟掉，十萬個項目也不會佔滿記憶體。
 *
 * 五種檢視吃同一個介面：source.state.total（總數，null 表示還在讀）、source.get(i)（第 i 個項目，還沒讀到回傳 undefined）。
 */
import { api } from "../lib/api.js";

const PAGE = 200;
const KEEP_PAGES = 40;

/** scope：{root, path}＝資料夾內容；{kind}＝跨硬碟的類型；{label}＝有這個顏色標籤的項目 */
export function createItemSource(scope, sort = "name", desc = false) {
  const state = $state({ total: null, folders: 0, tick: 0, error: "" });
  const pages = new Map();
  const pending = new Set();

  async function load(p) {
    if (pages.has(p) || pending.has(p)) return;
    pending.add(p);
    try {
      const data = await api("/api/items", { params: { ...scope, offset: p * PAGE, limit: PAGE, sort, desc: desc ? "true" : undefined }, quiet: true });
      pages.set(p, data.items);
      state.total = data.total;
      state.folders = data.folders;
      state.error = "";
      if (pages.size > KEEP_PAGES) {
        const far = [...pages.keys()].sort((a, b) => Math.abs(b - p) - Math.abs(a - p))[0];
        pages.delete(far);
      }
    } catch (e) {
      state.error = e.message;
    } finally {
      pending.delete(p);
      state.tick++;
    }
  }

  return {
    state,
    /** 第 i 個項目；還沒讀到就開始讀並回傳 undefined（讀到後 state.tick 會變，畫面跟著更新） */
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
    /** 已經在記憶體裡才回傳，不觸發讀取 */
    peek(i) {
      const p = Math.floor(i / PAGE);
      return pages.get(p)?.[i - p * PAGE];
    },
    start: () => load(0),
    retry() {
      state.error = "";
      load(0);
    },
    /** 項目的內容改了（例如換了標籤）：請畫面重畫 */
    touch: () => state.tick++,
  };
}

/** 已經在手上的一小串項目（例如「所有檔案」最上層的硬碟清單），介面和上面相同 */
export function createStaticSource(items) {
  const state = $state({ total: items.length, folders: items.length, tick: 0, error: "" });
  return { state, get: (i) => (state.tick, items[i]), peek: (i) => items[i], start() {}, retry() {}, touch: () => state.tick++ };
}
