/**
 * 動態：時長與曲線的唯一來源（程式這一側），以及共用的 Svelte 轉場。
 * 數值和 styles/app-tokens.css 的 --dur-*、--ease-*、--spring-* 相同（pnpm check 會核對），
 * 都取自 Liquid Glass 設計系統元件實際使用的值。其他檔案不要自己寫毫秒數或曲線。
 */
import { cubicOut } from "svelte/easing";

/** 時長（毫秒） */
export const DUR = { fast: 150, quick: 200, base: 250, move: 300, slow: 350 };
/** 曲線：out 平滑減速（大面積移動）；spring 系列帶一點回彈（玻璃控制項） */
export const EASE = {
  standard: "ease",
  out: "cubic-bezier(.2, .9, .3, 1)",
  springSoft: "cubic-bezier(.2, .9, .3, 1.1)",
  spring: "cubic-bezier(.2, .9, .3, 1.15)",
  springPress: "cubic-bezier(.2, .9, .3, 1.3)",
};

const reduced = () => typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

// easing-emphasized-decelerate cubic-bezier(0.05, 0.7, 0.1, 1) 的近似
const decel = (t) => 1 - Math.pow(1 - t, 4);
const accel = (t) => t * t * t;

/**
 * 換頁：新頁面直接出現並快速淡入（從半透明開始，不從全透明開始），不延遲、不縮放。
 * 以前先等 90ms、從 0 開始淡入又整頁縮放：換頁時會有一段空白，固定位置的元件（日期標籤、捲動軸）也會跟著跳。
 */
export function fadeThrough(node, { duration = DUR.fast } = {}) {
  if (reduced()) return { duration: 0 };
  return { duration, easing: decel, css: (t) => `opacity:${0.4 + 0.6 * t}` };
}

/** 浮層進場：由上方或錨點長出（減速、250ms） */
export function popIn(node, { y = -12, scale = 0.92, duration = DUR.base } = {}) {
  if (reduced()) return { duration: DUR.fast, css: (t) => `opacity:${t}` };
  return {
    duration, easing: decel,
    css: (t) => `opacity:${Math.min(1, t * 2)}; transform: translateY(${(1 - t) * y}px) scale(${scale + (1 - scale) * t})`,
  };
}

/** 浮層離場：比進場短（150ms） */
export function popOut(node, { y = -8, scale = 0.96, duration = DUR.fast } = {}) {
  if (reduced()) return { duration: DUR.fast, css: (t) => `opacity:${t}` };
  return {
    duration, easing: accel,
    css: (t) => `opacity:${t}; transform: translateY(${(1 - t) * y}px) scale(${scale + (1 - scale) * t})`,
  };
}

/** 由下往上滑入（Snackbar） */
export function riseIn(node, { y = 24, duration = DUR.move } = {}) {
  if (reduced()) return { duration: DUR.fast, css: (t) => `opacity:${t}` };
  return { duration, easing: cubicOut, css: (t) => `opacity:${t}; transform: translateY(${(1 - t) * y}px)` };
}

/** 遮罩淡入淡出 */
export function scrim(node, { duration = DUR.base } = {}) {
  return { duration: reduced() ? DUR.fast : duration, css: (t) => `opacity:${t}` };
}
