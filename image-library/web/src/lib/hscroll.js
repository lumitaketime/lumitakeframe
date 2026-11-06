/**
 * 橫向捲動的列（探索的人物、事物、地點、年份，回憶）：
 * - 觸控板斜斜滑動時，以橫向為主就只捲這一列，頁面不會跟著上下跳
 * - 捲到兩端不會帶動整頁（overscroll-behavior）
 * - 用滑鼠時，滑過去會出現左右按鈕（M3 圓形按鈕），一次捲大約一個畫面寬
 * 用法：<div class="hs"><div class="strip" use:hscroll>…</div></div>（.hs 是按鈕的定位容器）
 */
const PREV = "M15.41 16.59 10.83 12l4.58-4.59L14 6l-6 6 6 6z";
const NEXT = "M8.59 16.59 13.17 12 8.59 7.41 10 6l6 6-6 6z";

export function hscroll(node) {
  node.dataset.hscroll = "";
  const wrap = node.parentElement;
  const make = (dir, path, label) => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = `hs-nav ${dir}`;
    b.setAttribute("aria-label", label);
    b.tabIndex = -1; // 鍵盤可以直接 Tab 進列裡的項目
    b.innerHTML = `<svg viewBox="0 0 24 24" width="24" height="24" aria-hidden="true"><path d="${path}" fill="currentColor"/></svg>`;
    b.addEventListener("click", () => node.scrollBy({ left: (dir === "prev" ? -1 : 1) * node.clientWidth * 0.8, behavior: "smooth" }));
    wrap?.appendChild(b);
    return b;
  };
  const prev = make("prev", PREV, "往左");
  const next = make("next", NEXT, "往右");

  function update() {
    const max = node.scrollWidth - node.clientWidth;
    wrap?.classList.toggle("can-prev", node.scrollLeft > 2);
    wrap?.classList.toggle("can-next", node.scrollLeft < max - 2);
  }

  function onWheel(e) {
    // 以橫向為主的滑動：只捲這一列，擋掉縱向的部分（不然頁面會跟著跳）
    if (Math.abs(e.deltaX) > Math.abs(e.deltaY) && node.scrollWidth > node.clientWidth) {
      e.preventDefault();
      node.scrollLeft += e.deltaX;
    }
  }

  node.addEventListener("scroll", update, { passive: true });
  node.addEventListener("wheel", onWheel, { passive: false });
  const ro = new ResizeObserver(update);
  ro.observe(node);
  const mo = new MutationObserver(update);
  mo.observe(node, { childList: true });
  update();

  return {
    destroy() {
      node.removeEventListener("scroll", update);
      node.removeEventListener("wheel", onWheel);
      ro.disconnect();
      mo.disconnect();
      prev.remove();
      next.remove();
    },
  };
}
