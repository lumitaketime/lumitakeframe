/**
 * 滑動的選取指示：分段按鈕、分頁底線、設定分類、側邊欄、手機的膠囊列。
 * 換選項時，膠囊（或分頁的底線）用 M3 的 expressive 彈簧滑到新的位置。
 *
 * 順暢的關鍵：
 * - 一按下（pointerdown）就開始滑，不等新頁面建好；換頁時主執行緒很忙，但只動 transform 的動畫由 GPU 處理，不會卡。
 * - 大小一樣時只改 transform（側邊欄每一項一樣大），不動 width／height。
 * - 位置沒變就不重設，動畫途中不會被打斷重來。
 *
 * use:slider                         分段按鈕（直接子元素中 .on、.active、aria-selected、aria-checked、aria-current 的那個）
 * use:slider={{ kind: "underline" }} 分頁底線
 * use:slider={{ selector: "a.active", items: "a" }}  側邊欄（目前頁面在子孫元素裡）
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
  let last = null; // 目前指示的位置 { x, y, w, h }
  let hold = 0; // 按下後先停在按的那一項，等頁面真的換過去

  const visible = (el) => el && el !== ind && el.offsetParent !== null;

  function find() {
    const scope = o.selector ? node.querySelectorAll(o.selector) : [...node.children].filter((c) => c !== ind && c.matches(ACTIVE));
    return [...scope].find(visible) || null;
  }

  function rectOf(el) {
    const nr = node.getBoundingClientRect();
    const r = el.getBoundingClientRect();
    return {
      x: Math.round(r.left - nr.left + node.scrollLeft - node.clientLeft),
      y: Math.round(r.top - nr.top + node.scrollTop - node.clientTop),
      w: Math.round(r.width), h: Math.round(r.height), radius: getComputedStyle(el).borderRadius,
    };
  }

  function apply(r, animate) {
    const underline = o.kind === "underline";
    const h = underline ? 3 : r.h;
    const y = underline ? r.y + r.h - 3 : r.y;
    if (last && last.x === r.x && last.y === y && last.w === r.w && last.h === h) return; // 沒變就不要打斷正在跑的動畫
    const instant = !animate || reduce() || !last;
    if (instant) ind.style.transition = "none";
    ind.style.transform = `translate3d(${r.x}px, ${y}px, 0)`;
    if (!last || last.w !== r.w) ind.style.width = `${r.w}px`;
    if (!last || last.h !== h) ind.style.height = `${h}px`;
    if (!underline && r.radius && r.radius !== "0px") ind.style.borderRadius = r.radius;
    ind.style.opacity = "1";
    if (instant) {
      void ind.offsetWidth; // 先定位，再恢復動畫
      ind.style.transition = "";
    }
    last = { x: r.x, y, w: r.w, h };
  }

  function place(animate = true) {
    raf = 0;
    if (!node.isConnected) return;
    if (!ind.isConnected) node.appendChild(ind); // Svelte 清空清單時會一起拿掉，放回去
    if (hold && Date.now() < hold) return;
    const el = find();
    if (!el) {
      ind.style.opacity = "0";
      last = null;
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

  // 一按下就滑過去（點連結換頁時，新頁面要花一點時間建立，不能等它）
  function onDown(e) {
    if (e.button > 0) return;
    const sel = o.items || (o.selector ? o.selector.replace(/\.(active|on)\b/g, "") : null);
    const item = sel ? e.target.closest(sel) : [...node.children].find((c) => c !== ind && c.contains(e.target));
    if (!item || !node.contains(item) || !visible(item)) return;
    if (!item.matches("a, button, [role=tab], [role=radio]") || item.matches(":disabled, [aria-disabled='true']")) return;
    const inner = e.target.closest("button, input");
    if (inner && inner !== item && item.contains(inner)) return; // 項目裡的小按鈕（例如取消釘選）不算
    const r = rectOf(item);
    apply(r, true);
    if (o.key) memory.set(o.key, r);
    hold = Date.now() + 700;
    setTimeout(() => {
      hold = 0;
      schedule(); // 沒有真的換過去（例如拖走了）就回到原本的位置
    }, 720);
  }

  const mo = new MutationObserver(schedule);
  mo.observe(node, { subtree: true, childList: true, attributes: true, attributeFilter: ["class", "aria-selected", "aria-checked", "aria-current", "hidden"] });
  const ro = new ResizeObserver(() => requestAnimationFrame(() => place(false)));
  ro.observe(node);
  node.addEventListener("pointerdown", onDown, true);
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
      node.removeEventListener("pointerdown", onDown, true);
      ind.remove();
    },
  };
}
