/**
 * 檢視共用的鍵盤操作：方向鍵移動（⇧ 延伸選取）、Home／End、PageUp／PageDown、
 * Enter 或 ⌘↓ 開啟、空白鍵預覽、⌘A 全選。perRow＝一列有幾個（列表是 1）。
 * 有處理就回傳 true。
 */
export function handleViewKey(e, { sel, total, perRow = 1, perPage = 10, onopen, onpreview }) {
  if (!total) return false;
  const mod = e.metaKey || e.ctrlKey;
  const at = sel.focus < 0 ? -1 : sel.focus;
  let to = null;
  if (e.key === "ArrowDown" && mod) return act(e, () => at >= 0 && onopen?.(at));
  if (e.key === "ArrowDown") to = at < 0 ? 0 : at + perRow;
  else if (e.key === "ArrowUp" && !mod) to = at < 0 ? 0 : at - perRow;
  else if (e.key === "ArrowRight" && perRow > 1) to = at + 1;
  else if (e.key === "ArrowLeft" && perRow > 1) to = at - 1;
  else if (e.key === "Home") to = 0;
  else if (e.key === "End") to = total - 1;
  else if (e.key === "PageDown") to = at + perPage * perRow;
  else if (e.key === "PageUp") to = at - perPage * perRow;
  else if (e.key === "Enter") return act(e, () => at >= 0 && onopen?.(at));
  else if (e.key === " ") return act(e, () => at >= 0 && onpreview?.(at));
  else if (mod && e.key.toLowerCase() === "a") return act(e, () => sel.all(total));
  else if (e.key === "Escape" && sel.size) return act(e, () => sel.clear());
  if (to === null) return false;
  // 上下移動超出範圍時留在原位，不跳到別的欄
  if (perRow > 1 && (e.key === "ArrowDown" || e.key === "ArrowUp") && (to < 0 || to > total - 1)) to = at;
  e.preventDefault();
  sel.moveTo(to, total, e.shiftKey);
  return true;
}
function act(e, fn) {
  e.preventDefault();
  fn();
  return true;
}
