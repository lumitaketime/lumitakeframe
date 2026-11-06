/**
 * 滑動的選取指示：分段按鈕、分頁、單選的膠囊列、側邊欄。
 * 換選項時，底下那顆膠囊（或分頁的底線）會用 M3 的 expressive 彈簧滑到新的位置，而不是直接閃過去。
 *
 * use:slider                         分段按鈕／膠囊列（直接子元素中 .on、.active、aria-selected、aria-checked、aria-current 的那個）
 * use:slider={{ kind: "underline" }} 分頁底線
 * use:slider={{ deep: true, selector: "a.active" }}  側邊欄（目前頁面在子孫元素裡）
 * use:slider={{ key: "explore" }}    頁面切換時元件會重建；用 key 記住上次的位置，讓膠囊從上一頁的位置滑過來
 */
const memory = new Map();
const reduce = () => matchMedia("(prefers-reduced-motion: reduce)").matches;
const ACTIVE = ".on, .active, [aria-selected='true'], [aria-checked='true'], [aria-current='page']";

export function slider(node, opts = {}) {
  let o = opts || {};
  const ind = document.createElement("span");
  ind.className = "slider-ind";
  ind.setAttribute("aria-hidden", "true");
  node.classList.add("has-slider", o.kind === "underline" ? "slider-underline" : "slider-pill");
  if (getComputedStyle(node).position === "static") node.style.position = "relative";
  node.appendChild(ind);

  let raf = 0;
  let placed = false;

  function find() {
    const scope = o.selector ? node.querySelectorAll(o.selector) : o.deep ? node.querySelectorAll(ACTIVE) : [...node.children].filter((c) => c !== ind && c.matches(ACTIVE));
    return [...scope].find((el) => el !== ind && el.offsetParent !== null) || null;
  }

  function rectOf(el) {
    const nr = node.getBoundingClientRect();
    const r = el.getBoundingClientRect();
    return { x: r.left - nr.left + node.scrollLeft - node.clientLeft, y: r.top - nr.top + node.scrollTop - node.clientTop, w: r.width, h: r.height };
  }

  function apply(r, animate) {
    const underline = o.kind === "underline";
    const h = underline ? 3 : r.h;
    const y = underline ? r.y + r.h - 3 : r.y;
    const radius = getComputedStyle(find() || node).borderRadius;
    if (!animate || reduce()) {
      ind.style.transition = "none";
    }
    ind.style.transform = `translate(${r.x}px, ${y}px)`;
    ind.style.width = `${r.w}px`;
    ind.style.height = `${h}px`;
    if (!underline && radius && radius !== "0px") ind.style.borderRadius = radius;
    ind.style.opacity = "1";
    if (!animate || reduce()) {
      void ind.offsetWidth; // 先定位再恢復動畫
      ind.style.transition = "";
    }
  }

  function place(animate = true) {
    raf = 0;
    if (!node.isConnected) return;
    if (!ind.isConnected) node.appendChild(ind); // Svelte 清空清單時會一起拿掉，放回去
    const el = find();
    if (!el) {
      ind.style.opacity = "0";
      return;
    }
    const r = rectOf(el);
    if (!r.w) return;
    if (!placed && o.key && memory.has(o.key)) {
      apply(memory.get(o.key), false); // 從上一次（例如上一頁）的位置開始
      requestAnimationFrame(() => apply(r, true));
    } else {
      apply(r, placed && animate);
    }
    placed = true;
    if (o.key) memory.set(o.key, r);
  }

  const schedule = () => {
    if (!raf) raf = requestAnimationFrame(() => place(true));
  };
  const mo = new MutationObserver(schedule);
  mo.observe(node, { subtree: true, childList: true, attributes: true, attributeFilter: ["class", "aria-selected", "aria-checked", "aria-current", "hidden"] });
  const ro = new ResizeObserver(() => requestAnimationFrame(() => place(false)));
  ro.observe(node);
  requestAnimationFrame(() => place(false));
  document.fonts?.ready?.then(() => place(false));

  return {
    update(next) {
      o = next || {};
      schedule();
    },
    destroy() {
      cancelAnimationFrame(raf);
      mo.disconnect();
      ro.disconnect();
      ind.remove();
    },
  };
}
