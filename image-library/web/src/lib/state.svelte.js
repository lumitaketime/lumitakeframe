/** 在 Mac App（Tauri）或 Android App 外殼中執行時，User-Agent 會帶上標記 */
export const isMacApp = navigator.userAgent.includes("LumitakeApp");
export const isAndroidApp = navigator.userAgent.includes("LumitakeAndroid");

import { SvelteSet } from "svelte/reactivity";

/** 全域狀態 */
export const app = $state({
  server: null, // /api/server
  needLogin: false,
  authChecked: false,
  refreshKey: 0, // 背景工作結束或檔案異動後 +1，讓頁面重新載入
  toasts: [],
  context: null, // 目前頁面的情境，例如 { album: 3 }
  sidebarOpen: false,
});

export const selection = new SvelteSet();

/** 檢視器：list 是目前頁面的項目，index 是正在看的那一張 */
export const viewer = $state({ open: false, list: [], index: 0 });

export function openViewer(list, index) {
  viewer.list = list;
  viewer.index = index;
  viewer.open = true;
}

let toastId = 0;
export function toast(message, kind = "info", ms = 3500) {
  const id = ++toastId;
  app.toasts.push({ id, message, kind });
  setTimeout(() => {
    const i = app.toasts.findIndex((t) => t.id === id);
    if (i !== -1) app.toasts.splice(i, 1);
  }, ms);
}

export function refresh() {
  app.refreshKey += 1;
}

/** 對話框：confirm / album / move，由 App 統一顯示 */
export const dialogs = $state({ current: null });

export function showDialog(kind, props = {}) {
  return new Promise((resolve) => {
    dialogs.current = { kind, props, resolve };
  });
}

export function closeDialog(value) {
  const d = dialogs.current;
  dialogs.current = null;
  d?.resolve(value);
}
