/**
 * 可以後悔的動作：合併人物等。
 * 完成後跳出通知（15 秒、滑鼠停在上面時不會消失）附「復原」，也可以按 ⌘Z（Windows：Ctrl+Z）。
 */
import { toast, dismissToast, refresh } from "./state.svelte.js";

const stack = [];

/** message：完成的說明；undo：還原用的函式（async） */
export function undoable(message, undo, { label = "復原", ms = 15000 } = {}) {
  const entry = { message, undo, toastId: null, done: false };
  entry.toastId = toast(message, "info", ms, { label, run: () => runUndo(entry) });
  stack.push(entry);
  while (stack.length > 20) stack.shift();
  return entry;
}

async function runUndo(entry) {
  if (entry.done) return;
  entry.done = true;
  const i = stack.indexOf(entry);
  if (i !== -1) stack.splice(i, 1);
  dismissToast(entry.toastId);
  try {
    await entry.undo();
    toast("已復原");
    refresh();
  } catch (e) {
    toast(e.message || "無法復原", "error");
  }
}

/** ⌘Z：復原最近一次 */
export function undoLast() {
  const entry = stack.pop();
  if (!entry) {
    toast("沒有可以復原的動作");
    return;
  }
  stack.push(entry);
  runUndo(entry);
}
