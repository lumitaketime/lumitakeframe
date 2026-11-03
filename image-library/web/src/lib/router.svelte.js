/** 極簡路由：使用一般網址（伺服器對未知路徑回傳 index.html） */
export const route = $state({ path: location.pathname, query: Object.fromEntries(new URLSearchParams(location.search)) });

function sync() {
  route.path = location.pathname;
  route.query = Object.fromEntries(new URLSearchParams(location.search));
}

window.addEventListener("popstate", sync);
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
  history[replace ? "replaceState" : "pushState"]({ idx: replace ? idx : idx + 1 }, "", to);
  sync();
  document.querySelector("main")?.scrollTo?.({ top: 0 });
}

export function link(node) {
  const handler = (e) => {
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
    e.preventDefault();
    navigate(node.getAttribute("href"));
  };
  node.addEventListener("click", handler);
  return { destroy: () => node.removeEventListener("click", handler) };
}
