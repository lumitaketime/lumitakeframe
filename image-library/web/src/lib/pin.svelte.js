/**
 * 長按工具卡片，拖到左側「工具」就能加入側邊欄。
 * 滑鼠與觸控都用同一套：按住 350ms 才開始拖，期間移動太多就當成一般捲動或點擊。
 */
import { api } from "./api.js";
import { app, toast } from "./state.svelte.js";
import { pinnedKeys, toolByKey } from "./toolkit.js";

export const drag = $state({ key: null, x: 0, y: 0, over: false });

const HOLD_MS = 350;

export async function savePinned(keys) {
  const value = [...new Set(keys)].join(",");
  await api("/api/settings", { body: { pinned_tools: value } });
  if (app.server?.ui) app.server.ui.pinned_tools = value;
}

export async function pin(key) {
  const keys = pinnedKeys(app.server);
  const tool = toolByKey(key);
  if (keys.includes(key)) {
    toast(`「${tool.label}」已經在側邊欄`);
    return;
  }
  try {
    await savePinned([...keys, key]);
    toast(`已把「${tool.label}」加到側邊欄`, "info", 6000, { label: "復原", run: () => unpin(key, true) });
  } catch (e) {
    toast(e.message, "error");
  }
}

export async function unpin(key, quiet = false) {
  try {
    await savePinned(pinnedKeys(app.server).filter((k) => k !== key));
    if (!quiet) toast(`已從側邊欄移除「${toolByKey(key)?.label}」`, "info", 6000, { label: "復原", run: () => pin(key) });
  } catch (e) {
    toast(e.message, "error");
  }
}

function overDrop(x, y) {
  const el = document.elementFromPoint(x, y);
  return !!el?.closest?.("[data-pin-drop]");
}

/** Svelte action：use:pinnable={"screens"} */
export function pinnable(node, key) {
  let timer = null;
  let start = null;
  let dragging = false;
  let suppressClick = false;

  function cancel() {
    clearTimeout(timer);
    timer = null;
  }

  function down(e) {
    if (e.button !== 0) return;
    start = { x: e.clientX, y: e.clientY, id: e.pointerId };
    timer = setTimeout(() => begin(e), HOLD_MS);
  }

  function begin(e) {
    timer = null;
    dragging = true;
    suppressClick = true;
    drag.key = key;
    drag.x = start.x;
    drag.y = start.y;
    drag.over = false;
    node.classList.add("pin-lifting");
    try {
      node.setPointerCapture(start.id);
    } catch {
      /* 有些瀏覽器不支援 */
    }
    navigator.vibrate?.(15);
  }

  function move(e) {
    if (timer && start && Math.hypot(e.clientX - start.x, e.clientY - start.y) > 8) cancel();
    if (!dragging) return;
    e.preventDefault();
    drag.x = e.clientX;
    drag.y = e.clientY;
    drag.over = overDrop(e.clientX, e.clientY);
  }

  function up(e) {
    cancel();
    if (!dragging) return;
    dragging = false;
    node.classList.remove("pin-lifting");
    const hit = overDrop(e.clientX, e.clientY);
    drag.key = null;
    drag.over = false;
    if (hit) pin(key);
    else toast("拖到左側「工具」放開，就能加入側邊欄");
  }

  function click(e) {
    if (suppressClick) {
      e.preventDefault();
      e.stopImmediatePropagation();
      suppressClick = false;
    }
  }

  const noNative = (e) => e.preventDefault();
  // 按住後開始拖曳時，阻止手機把手勢當成捲動
  const noScroll = (e) => dragging && e.cancelable && e.preventDefault();
  node.addEventListener("touchmove", noScroll, { passive: false });
  node.setAttribute("draggable", "false");
  node.addEventListener("pointerdown", down);
  node.addEventListener("pointermove", move);
  node.addEventListener("pointerup", up);
  node.addEventListener("pointercancel", up);
  node.addEventListener("click", click, true);
  node.addEventListener("dragstart", noNative);
  node.addEventListener("contextmenu", (e) => dragging && e.preventDefault());
  return {
    update(k) {
      key = k;
    },
    destroy() {
      cancel();
      node.removeEventListener("pointerdown", down);
      node.removeEventListener("pointermove", move);
      node.removeEventListener("pointerup", up);
      node.removeEventListener("pointercancel", up);
      node.removeEventListener("click", click, true);
      node.removeEventListener("dragstart", noNative);
      node.removeEventListener("touchmove", noScroll);
    },
  };
}
