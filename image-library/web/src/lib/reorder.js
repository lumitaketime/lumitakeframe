/**
 * 卡片長按拖曳排序（相簿、資料夾）：按住約 0.35 秒，卡片浮起來跟著手指／滑鼠走，
 * 經過其他卡片時即時讓位（搭配 animate:flip），放開後存下新順序。
 * 用法：<div use:reorder={{ onmove(fromKey, toKey), ondrop() }}>，每張卡片加 data-reorder-key。
 * 一開始就移動（例如捲動頁面）就不算拖曳；拖曳結束後吃掉那一次點擊，不會誤開卡片。
 */
const HOLD = 350;

export function reorder(node, opts) {
  let o = opts;
  let timer = 0;
  let start = null;
  let active = null; // { el, key, ghost, dx, dy }

  const itemOf = (t) => t?.closest?.("[data-reorder-key]");

  function down(e) {
    if (e.button > 0 || o?.disabled) return;
    if (e.target.closest("button, input, [data-no-drag]")) return; // 卡片上的按鈕（收藏星號）照常按
    const el = itemOf(e.target);
    if (!el || !node.contains(el)) return;
    start = { x: e.clientX, y: e.clientY, el, id: e.pointerId };
    clearTimeout(timer);
    timer = setTimeout(() => begin(e), HOLD);
  }

  function begin(e) {
    if (!start) return;
    const el = start.el;
    const r = el.getBoundingClientRect();
    const ghost = el.cloneNode(true);
    ghost.classList.add("reorder-ghost");
    Object.assign(ghost.style, { position: "fixed", left: `${r.left}px`, top: `${r.top}px`, width: `${r.width}px`, height: `${r.height}px`, margin: 0, zIndex: 300, pointerEvents: "none" });
    document.body.appendChild(ghost);
    el.classList.add("reorder-src");
    active = { el, key: el.dataset.reorderKey, ghost, dx: start.x - r.left, dy: start.y - r.top };
    try { node.setPointerCapture?.(start.id); } catch { /* 已經放開 */ }
    navigator.vibrate?.(15);
    document.body.classList.add("reordering");
  }

  function move(e) {
    if (!start) return;
    if (!active) {
      // 還沒長按到就移動：當作一般捲動或拖曳，不排序
      if (Math.hypot(e.clientX - start.x, e.clientY - start.y) > 8) cancel();
      return;
    }
    e.preventDefault();
    active.ghost.style.left = `${e.clientX - active.dx}px`;
    active.ghost.style.top = `${e.clientY - active.dy}px`;
    const over = document.elementsFromPoint(e.clientX, e.clientY).map(itemOf).find((x) => x && x !== active.el && node.contains(x));
    if (over && over.dataset.reorderKey !== active.key) o?.onmove?.(active.key, over.dataset.reorderKey);
  }

  function up() {
    clearTimeout(timer);
    if (active) {
      const { ghost, el } = active;
      const r = el.getBoundingClientRect();
      // 浮起來的卡片飛回它的新位置
      const a = ghost.animate([{ left: ghost.style.left, top: ghost.style.top }, { left: `${r.left}px`, top: `${r.top}px` }],
        { duration: DUR.quick, easing: EASE.out });
      a.finished.catch(() => {}).then(() => {
        ghost.remove();
        el.classList.remove("reorder-src");
      });
      active = null;
      document.body.classList.remove("reordering");
      const swallow = (ev) => { ev.preventDefault(); ev.stopPropagation(); };
      window.addEventListener("click", swallow, { capture: true, once: true });
      setTimeout(() => window.removeEventListener("click", swallow, { capture: true }), 50);
      o?.ondrop?.();
    }
    start = null;
  }

  function cancel() {
    clearTimeout(timer);
    start = null;
  }

  // 觸控時：長按啟動後要擋掉頁面捲動
  const touchMove = (e) => active && e.preventDefault();
  node.addEventListener("pointerdown", down);
  node.addEventListener("pointermove", move);
  node.addEventListener("pointerup", up);
  node.addEventListener("pointercancel", () => { if (active) up(); else cancel(); });
  node.addEventListener("touchmove", touchMove, { passive: false });
  node.addEventListener("contextmenu", (e) => itemOf(e.target) && (start || active) && e.preventDefault());

  return {
    update(next) { o = next; },
    destroy() {
      clearTimeout(timer);
      active?.ghost.remove();
      node.removeEventListener("pointerdown", down);
      node.removeEventListener("pointermove", move);
      node.removeEventListener("pointerup", up);
      node.removeEventListener("touchmove", touchMove);
    },
  };
}

/**
 * 卡片排序：mode = updated（最近更新）／name（名稱）／created（建立日期）／count（照片數量）／custom（拖曳排的順序）。
 * get(item) 回傳 { name, updated, created, count, position }。
 */
const collator = new Intl.Collator(undefined, { numeric: true, sensitivity: "base" });
export function sortCards(list, mode, get) {
  const out = [...list];
  const by = {
    name: (a, b) => collator.compare(get(a).name || "", get(b).name || ""),
    updated: (a, b) => (get(b).updated || "").localeCompare(get(a).updated || ""),
    created: (a, b) => (get(b).created || "").localeCompare(get(a).created || ""),
    count: (a, b) => (get(b).count || 0) - (get(a).count || 0),
    custom: (a, b) => {
      const pa = get(a).position, pb = get(b).position;
      if (pa == null && pb == null) return collator.compare(get(a).name || "", get(b).name || "");
      if (pa == null) return 1;
      if (pb == null) return -1;
      return pa - pb;
    },
  }[mode] || (() => 0);
  return out.sort(by);
}

/** 把 from 移到 to 的位置（拖曳時即時讓位用） */
export function moveKey(keys, from, to) {
  const list = keys.filter((k) => k !== from);
  const i = list.indexOf(to);
  const j = keys.indexOf(to) > keys.indexOf(from) ? i + 1 : i;
  list.splice(j < 0 ? list.length : j, 0, from);
  return list;
}
