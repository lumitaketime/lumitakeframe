/** 極簡路由：使用一般網址（伺服器對未知路徑回傳 index.html） */
import { tick } from "svelte";

export const route = $state({ path: location.pathname, query: Object.fromEntries(new URLSearchParams(location.search)) });

function sync() {
  route.path = location.pathname;
  route.query = Object.fromEntries(new URLSearchParams(location.search));
}

const main = () => document.querySelector("main");

/**
 * 捲動位置：新頁面從頂端開始；按返回時回到離開時的位置。
 * 都要等新頁面畫好之後再捲，不然舊頁面會先跳一下（看起來像閃爍）。
 */
async function scrollAfterRender(top) {
  await tick();
  requestAnimationFrame(() => {
    const m = main();
    if (!m) return;
    m.scrollTop = top;
    // 內容還在載入、高度不夠時，等一下再補一次
    if (top && Math.abs(m.scrollTop - top) > 2) setTimeout(() => (m.scrollTop = top), 300);
  });
}

window.addEventListener("popstate", () => {
  sync();
  scrollAfterRender(history.state?.scroll || 0);
});
// 記錄在這個 App 裡走了幾步，返回鍵才知道能不能「回上一頁」
if (typeof history.state?.idx !== "number") history.replaceState({ ...(history.state || {}), idx: 0 }, "");

/** 可以回到 App 裡的上一頁（不是從外部連結直接打開） */
export function canGoBack() {
  return (history.state?.idx ?? 0) > 0;
}

/** 返回：有上一頁就回上一頁，否則到上一層 */
export function goBack(fallback = "/") {
  if (canGoBack()) history.back();
  else navigate(fallback, { replace: true });
}

export function navigate(to, { replace = false } = {}) {
  if (to === location.pathname + location.search) return;
  const idx = history.state?.idx ?? 0;
  if (!replace) history.replaceState({ ...(history.state || {}), scroll: main()?.scrollTop || 0 }, ""); // 記下離開時的位置
  history[replace ? "replaceState" : "pushState"]({ idx: replace ? idx : idx + 1 }, "", to);
  sync();
  if (!replace) scrollAfterRender(0); // 同一頁換條件（replace）不動捲動位置
}

export function link(node) {
  const handler = (e) => {
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
    // 卡片裡的按鈕（例如收藏星號）自己處理，不要換頁
    const inner = e.target.closest?.("button, input, select, textarea");
    if (inner && node.contains(inner)) {
      e.preventDefault();
      return;
    }
    e.preventDefault();
    navigate(node.getAttribute("href"));
  };
  node.addEventListener("click", handler);
  return { destroy: () => node.removeEventListener("click", handler) };
}
