/**
 * 資料層：樹狀檢視的「節點連線圖」。目前資料夾在最左邊，按一下資料夾就往右展開它的下一層。
 * 每個資料夾一次只取它的下一層（引擎的佔比查詢，順便帶回再下一層，展開時不必再等）；
 * 每一層最多畫 12 個最大的，其餘合併成「其他」。
 *
 * 節點只會增加、不會刪除（收合只是藏起來），所以「第幾個節點」不會變，選取可以沿用一般清單的方式。
 * 介面和 items.svelte.js 的來源相同：state.total、get(i)。
 */
import { loadUsage } from "./browse.js";

const MAX_CHILDREN = 12;

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
    if (b.type === "kind") {
      return { ...base, type: "group", kind: b.kind, name: t(`kind.${b.kind}`), kindLabel: t("usage.filesHere"), path: b.path ?? here, leaf: true, note: "" };
    }
    return { ...base, type: "group", rest: true, kind: "other", name: t("usage.rest", { count: formatNumber(b.count || 0) }),
      kindLabel: t("usage.restKind"), path: here, leaf: true };
  }

  /** 放進子節點：最大的 12 個，其餘合併成一個「其他」 */
  function attach(i, blocks) {
    const p = nodes[i];
    const sorted = [...blocks].sort((a, b) => b.bytes - a.bytes);
    let keep = sorted.slice(0, MAX_CHILDREN);
    const rest = sorted.slice(MAX_CHILDREN);
    if (rest.length) {
      const merged = { type: "rest", bytes: rest.reduce((n, b) => n + b.bytes, 0), files: rest.reduce((n, b) => n + (b.files || 0), 0),
        count: rest.reduce((n, b) => n + (b.type === "rest" ? b.count || 1 : 1), 0) };
      keep = [...keep.filter((b) => b.type !== "rest"), merged, ...keep.filter((b) => b.type === "rest")];
    }
    const ids = [];
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
      const u = await loadUsage(root, n.path);
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
      const u = await loadUsage(root, path);
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
