/** 極簡路由：使用一般網址（伺服器對未知路徑回傳 index.html） */
export const route = $state({ path: location.pathname, query: Object.fromEntries(new URLSearchParams(location.search)) });

function sync() {
  route.path = location.pathname;
  route.query = Object.fromEntries(new URLSearchParams(location.search));
}

window.addEventListener("popstate", sync);

export function navigate(to, { replace = false } = {}) {
  if (to === location.pathname + location.search) return;
  history[replace ? "replaceState" : "pushState"]({}, "", to);
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
