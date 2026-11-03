/** M3 動態：以設計系統的時長與曲線做成 Svelte 轉場。 */
import { cubicOut } from "svelte/easing";

const reduced = () => typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

// easing-emphasized-decelerate cubic-bezier(0.05, 0.7, 0.1, 1) 的近似
const decel = (t) => 1 - Math.pow(1 - t, 4);
const accel = (t) => t * t * t;

/** 淡出再淡入（換頁）：新內容在舊內容淡出 90ms 後，用 210ms 淡入並微微放大 */
export function fadeThrough(node, { delay = 90, duration = 210 } = {}) {
  if (reduced()) return { duration: 80, css: (t) => `opacity:${t}` };
  return {
    delay, duration, easing: decel,
    css: (t) => `opacity:${t}; transform: scale(${0.98 + 0.02 * t})`,
  };
}

/** 浮層進場：由上方或錨點長出（emphasized-decelerate、400ms） */
export function popIn(node, { y = -12, scale = 0.92, duration = 400 } = {}) {
  if (reduced()) return { duration: 100, css: (t) => `opacity:${t}` };
  return {
    duration, easing: decel,
    css: (t) => `opacity:${Math.min(1, t * 2)}; transform: translateY(${(1 - t) * y}px) scale(${scale + (1 - scale) * t})`,
  };
}

/** 浮層離場：比進場短（emphasized-accelerate、200ms） */
export function popOut(node, { y = -8, scale = 0.96, duration = 200 } = {}) {
  if (reduced()) return { duration: 80, css: (t) => `opacity:${t}` };
  return {
    duration, easing: accel,
    css: (t) => `opacity:${t}; transform: translateY(${(1 - t) * y}px) scale(${scale + (1 - scale) * t})`,
  };
}

/** 由下往上滑入（Snackbar） */
export function riseIn(node, { y = 24, duration = 400 } = {}) {
  if (reduced()) return { duration: 100, css: (t) => `opacity:${t}` };
  return { duration, easing: cubicOut, css: (t) => `opacity:${t}; transform: translateY(${(1 - t) * y}px)` };
}

/** 遮罩淡入淡出 */
export function scrim(node, { duration = 250 } = {}) {
  return { duration: reduced() ? 80 : duration, css: (t) => `opacity:${t}` };
}
