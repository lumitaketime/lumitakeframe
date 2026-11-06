/**
 * 搜尋範圍：在資料夾、相簿、人物、寵物、截圖與文件等頁面打字時，預設只搜尋這一頁的照片。
 * key 會原封不動送到後端 /api/search?scope=…，後端回傳正式名稱（例如相簿名）。
 */
const TOOL_LABELS = { screens: "截圖與文件", blurry: "模糊照片", exposure: "曝光問題" };

export function routeScope(route, server) {
  const seg = route.path.split("/").filter(Boolean);
  const [page, a, b] = seg;
  if (page === "search") return route.query.scope ? { key: route.query.scope, label: route.query.in || "目前範圍" } : null;
  if (page === "folders" && a) {
    const path = route.query.path || "";
    const root = (server?.roots || []).find((r) => String(r.id) === a);
    return { key: `folder:${a}:${path}`, label: path ? path.split("/").pop() : root?.name || "這個資料夾" };
  }
  if (page === "albums" && a === "smart" && b) return { key: `smart:${b}`, label: "這個智慧相簿" };
  if (page === "albums" && a) return { key: `album:${a}`, label: "這個相簿" };
  if (page === "people" && a) return { key: `person:${a}`, label: "這個人物" };
  if (page === "pets" && a === "id" && b) return { key: `pet:${b}`, label: "這隻寵物" };
  if (page === "favorites") return { key: "favorites", label: "我的最愛" };
  if (page === "videos") return { key: "videos", label: "影片" };
  if (page === "tools" && TOOL_LABELS[a]) return { key: `tool:${a}`, label: TOOL_LABELS[a] };
  return null;
}

export function searchHref(text, scope) {
  let href = `/search?q=${encodeURIComponent(text)}`;
  if (scope) href += `&scope=${encodeURIComponent(scope.key)}&in=${encodeURIComponent(scope.label)}`;
  return href;
}
