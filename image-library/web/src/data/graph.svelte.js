/**
 * 資料層：樹狀檢視的「節點連線圖」。目前資料夾在最左邊，按一下資料夾就往右展開它的下一層。
 * 每個資料夾一次只取它的下一層（引擎的佔比查詢，順便帶回再下一層，展開時不必再等）；
 * 子資料夾與每個「檔案」都是一個節點。每一層先畫 40 個最大的，其餘合併成「其他」，按一下「其他」再多顯示 40 個。
 *
 * 節點只會增加、不會刪除（收合只是藏起來），所以「第幾個節點」不會變，選取可以沿用一般清單的方式。
 * 介面和 items.svelte.js 的來源相同：state.total、get(i)。
 */
import { loadUsageTree } from "./browse.js";

const MAX_CHILDREN = 40;

/** 引擎的扁平樹 → 第一層的區塊（每個資料夾帶著它的下一層），格式和展開時用的相同 */
function blocksOf(data) {
  const n = data.nodes;
  const count = n.parent.length;
  const blocks = new Array(count);
  const paths = new Array(count);
  paths[0] = data.path;
  const top = [];
  for (let k = 1; k < count; k++) {
    const parent = n.parent[k];
    const type = n.type[k];
    paths[k] = type === 0 ? n.path[k] : type === 1 ? (paths[parent] ? `${paths[parent]}/${n.name[k]}` : n.name[k]) : paths[parent];
    const b = type === 0 ? { type: "folder", id: n.id[k], name: n.name[k], path: n.path[k], bytes: n.bytes[k], files: n.files[k], kind: n.kind[k] }
      : type === 1 ? { type: "file", id: n.id[k], name: n.name[k], path: paths[k], folder: paths[parent], bytes: n.bytes[k], files: 1, kind: n.kind[k] }
        : { type: "rest", bytes: n.bytes[k], files: n.files[k], count: Number(n.name[k]) || 0 };
    blocks[k] = b;
    if (parent === 0) top.push(b);
    else if (blocks[parent]) (blocks[parent].children ||= []).push(b);
  }
  return top;
}
const loadLevel = (root, path) => loadUsageTree(root, path, { depth: 2, px: 20_000_000, maxNodes: 8000 }).then((d) => ({ ...d, children: blocksOf(d) }));

export function createGraph(root, path, t, formatNumber) {
  const nodes = $state([]);
  const state = $state({ total: null, folders: 0, tick: 0, error: "" });

  /** 引擎的一塊（資料夾、某一類的檔案、其他）→ 節點 */
  function toNode(b, parent, depth, here) {
    const base = { parent, depth, open: false, loading: false, children: null, root_id: root, size: b.bytes, files: b.files };
    if (b.type === "folder") {
      return { ...base, type: "folder", id: b.id, name: b.name, path: b.path, kind: "folder", mainKind: b.kind,
        children: null, leaf: b.children !== undefined && !b.children.length, pre: b.children };
    }
    if (b.type === "file") {
      return { ...base, type: "file", id: b.id, name: b.name, path: b.path, folder: b.folder, kind: b.kind, leaf: true };
    }
    if (b.type === "kind") {
      return { ...base, type: "group", kind: b.kind, name: t(`kind.${b.kind}`), kindLabel: t("usage.filesHere"), path: b.path ?? here, leaf: true, note: "" };
    }
    return { ...base, type: "group", rest: true, kind: "other", name: t("usage.rest", { count: formatNumber(b.count || 0) }),
      kindLabel: t(b.more ? "usage.restMoreHint" : "usage.restKind"), path: here, leaf: true, more: b.more };
  }

  /** 放進子節點：最大的 12 個，其餘合併成一個「其他」 */
  function attach(i, blocks, drop = -1) {
    const p = nodes[i];
    const sorted = [...blocks].sort((a, b) => b.bytes - a.bytes);
    let keep = sorted.slice(0, MAX_CHILDREN);
    const rest = sorted.slice(MAX_CHILDREN);
    if (rest.length) {
      const merged = { type: "rest", bytes: rest.reduce((n, b) => n + b.bytes, 0), files: rest.reduce((n, b) => n + (b.files || 0), 0),
        count: rest.reduce((n, b) => n + (b.type === "rest" ? b.count || 1 : 1), 0), more: rest };
      keep = [...keep.filter((b) => b.type !== "rest"), merged, ...keep.filter((b) => b.type === "rest")];
    }
    const ids = p.children ? p.children.filter((c) => c !== drop) : []; // 「再多顯示」：換掉按下的那個「其他」
    for (const b of keep) {
      if (!b.bytes) continue;
      ids.push(nodes.length);
      nodes.push(toNode(b, i, p.depth + 1, p.path));
    }
    p.children = ids;
    if (!ids.length) p.leaf = true;
  }

  async function load(i) {
    const n = nodes[i];
    if (n.children || n.leaf || n.loading) return;
    if (n.pre) { // 上一層已經順便帶回來了
      attach(i, n.pre);
      n.pre = undefined;
      return;
    }
    n.loading = true;
    try {
      const u = await loadLevel(root, n.path);
      attach(i, u.children || []);
    } catch (e) {
      state.error = e.message;
    } finally {
      n.loading = false;
      state.tick++;
    }
  }

  async function start() {
    if (nodes.length) return;
    try {
      const u = await loadLevel(root, path);
      nodes.push({ type: "folder", id: 0, name: u.name, path: u.path, kind: "folder", root_id: root, size: u.bytes, files: u.files,
        parent: -1, depth: 0, open: true, loading: false, children: null, leaf: false, mainKind: null, isRoot: true });
      attach(0, u.children || []);
      state.total = nodes.length;
    } catch (e) {
      state.error = e.message;
      state.total = 0;
    }
    state.tick++;
  }

  return {
    state,
    nodes,
    get(i) {
      state.tick;
      return nodes[i];
    },
    peek: (i) => nodes[i],
    start,
    retry() {
      state.error = "";
      nodes.length = 0;
      start();
    },
    touch: () => state.tick++,
    /** 展開（需要時才向引擎要下一層） */
    async expand(i) {
      const n = nodes[i];
      if (!n || n.type !== "folder" || n.leaf) return;
      n.open = true;
      await load(i);
      state.total = nodes.length;
      state.tick++;
    },
    /** 「其他」：再多顯示 40 個（換掉這個「其他」節點） */
    more(i) {
      const r = nodes[i];
      if (!r?.rest || !r.more || r.parent < 0) return;
      const blocks = r.more;
      r.more = undefined;
      attach(r.parent, blocks, i);
      state.total = nodes.length;
      state.tick++;
    },
    collapse(i) {
      const n = nodes[i];
      if (!n || n.isRoot) return;
      n.open = false;
      state.tick++;
    },
    /** 看得到的節點（祖先都展開的），依畫面上由上到下的順序 */
    visible() {
      state.tick;
      const out = [];
      const walk = (i) => {
        out.push(i);
        const n = nodes[i];
        if (n.open && n.children) for (const c of n.children) walk(c);
      };
      if (nodes.length) walk(0);
      return out;
    },
  };
}
