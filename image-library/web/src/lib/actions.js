import { api } from "./api.js";
import { app, refresh, selection, showDialog, toast } from "./state.svelte.js";

export function confirm(title, message, { ok = "確定", danger = false } = {}) {
  return showDialog("confirm", { title, message, ok, danger });
}

export async function setFavorite(ids, on) {
  await api("/api/assets/bulk", { body: { ids, action: on ? "favorite" : "unfavorite" } });
  const n = ids.length > 1 ? ` ${ids.length} 個項目` : "";
  toast(on ? `已將${n}加入我的最愛`.replace("已將加入", "已加入") : `已從我的最愛移除${n}`);
  refresh();
}

export async function addToAlbum(ids) {
  const choice = await showDialog("album", { count: ids.length });
  if (!choice) return null;
  const res = await api("/api/assets/bulk", {
    body: { ids, action: "add_to_album", album_id: choice.id || undefined, name: choice.name },
  });
  toast(`已加入相簿「${choice.name}」`);
  refresh();
  return res.album_id;
}

export async function removeFromAlbum(albumId, ids) {
  await api("/api/assets/bulk", { body: { ids, action: "remove_from_album", album_id: albumId } });
  toast(`已從相簿移除 ${ids.length} 個項目（檔案不受影響）`);
  refresh();
}

export async function trashAssets(ids) {
  const ok = await confirm(
    `移到垃圾桶？`,
    `${ids.length} 個檔案會移到 macOS 的垃圾桶（外接硬碟則是該硬碟的垃圾桶），清空前都可以還原。同名的 .xmp、.aae 附屬檔會一起移動。`,
    { ok: "移到垃圾桶", danger: true },
  );
  if (!ok) return [];
  const res = await api("/api/assets/bulk", { body: { ids, action: "trash" } });
  if (res.errors?.length) toast(`有 ${res.errors.length} 個檔案無法刪除：${res.errors[0]}`, "error", 6000);
  else toast(`已移到垃圾桶：${res.done} 個檔案`);
  for (const id of res.ids || []) selection.delete(id);
  refresh();
  return res.ids || [];
}

export async function analyzeAssets(ids, redo = true) {
  await api("/api/assets/bulk", { body: { ids, action: "analyze", redo } });
  toast(`已排入 AI 分析：${ids.length} 個項目，可在右上角查看進度`);
}

export async function reveal(id, mode = "reveal") {
  try {
    await api(`/api/assets/${id}/reveal`, { body: { mode } });
    if (!app.server?.local) toast("已在 Mac 上打開");
  } catch (e) {
    toast(e.message, "error");
  }
}

export async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    toast("已複製");
  } catch {
    showDialog("confirm", { title: "複製這段文字", message: text, ok: "關閉", noCancel: true });
  }
}
