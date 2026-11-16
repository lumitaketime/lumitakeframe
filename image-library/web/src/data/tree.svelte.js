/**
 * 資料層：樹狀檢視的項目來源。把「展開的資料夾」攤平成一條清單，介面和 items.svelte.js 的來源相同
 * （state.total、get(i)），所以選取、鍵盤、右鍵選單都能共用。
 * 每個展開的資料夾各自分段讀取；還沒讀到的列先佔位，畫面上只畫看得到的。
 */
import { createItemSource } from "./items.svelte.js";

export function createTreeSource(root, path, sort = "name", desc = false) {
  const own = $state({ tick: 0 }); // 展開或收合時 +1
  const sources = new Map(); // 資料夾路徑 → 項目來源
  const open = new Set(); // 展開的資料夾路徑
  let flat = []; // [{src, i, depth, parent}]
  let builtAt = -1;

  const sourceOf = (p) => {
    if (!sources.has(p)) {
      const src = createItemSource({ root, path: p }, sort, desc);
      sources.set(p, src);
      src.start();
    }
    return sources.get(p);
  };
  const top = sourceOf(path);

  // 任何一個資料夾讀到新的一段，或展開／收合，都重新攤平
  const stamp = () => {
    let n = own.tick;
    for (const src of sources.values()) n += src.state.tick * 31;
    return n;
  };
  function build() {
    const key = stamp();
    if (key === builtAt) return flat;
    builtAt = key;
    const out = [];
    const walk = (src, depth, parent) => {
      const total = src.state.total ?? 0;
      for (let i = 0; i < total; i++) {
        out.push({ src, i, depth, parent });
        const item = src.peek(i);
        if (item?.type === "folder" && open.has(item.path)) walk(sourceOf(item.path), depth + 1, item);
      }
    };
    walk(top, 0, null);
    flat = out;
    return flat;
  }

  // 和其他來源同樣的介面；讀這些值就會在資料變動時讓畫面更新
  const state = {
    get total() {
      return top.state.total === null ? null : build().length;
    },
    get folders() {
      return top.state.folders;
    },
    get tick() {
      return stamp();
    },
    get error() {
      return top.state.error;
    },
  };
  const api = {
    state,
    get(i) {
      const node = build()[i];
      return node ? node.src.get(node.i) : undefined;
    },
    peek(i) {
      const node = build()[i];
      return node ? node.src.peek(node.i) : undefined;
    },
    /** 第 i 列在樹裡的位置：深度、上一層的資料夾（最上層是 null） */
    node: (i) => build()[i],
    isOpen: (item) => open.has(item.path),
    toggle(item, on = !open.has(item.path)) {
      if (item?.type !== "folder") return;
      if (on) open.add(item.path);
      else for (const p of [...open]) if (p === item.path || p.startsWith(item.path + "/")) open.delete(p);
      if (on) sourceOf(item.path);
      own.tick++;
    },
    /** 展開整個子樹（⌥ 加按）：一層一層往下讀，最多展開 200 個資料夾，避免一次讀進整顆硬碟 */
    async expandAll(item) {
      const queue = [item];
      let n = 0;
      while (queue.length && n < 200) {
        const f = queue.shift();
        open.add(f.path);
        n++;
        const src = sourceOf(f.path);
        for (let tries = 0; src.state.total === null && tries < 100; tries++) await new Promise((r) => setTimeout(r, 30));
        const count = Math.min(src.state.total ?? 0, src.state.folders);
        for (let i = 0; i < count; i++) {
          const child = src.peek(i);
          if (child?.type === "folder") queue.push(child);
        }
        own.tick++;
      }
    },
    start() {},
    retry: () => top.retry(),
    touch: () => own.tick++,
  };
  return api;
}
