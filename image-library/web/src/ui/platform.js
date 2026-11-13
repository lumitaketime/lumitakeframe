/**
 * 平台尺寸：滑鼠與觸控板用 macOS 的尺寸與字級（mac），觸控螢幕用 iOS 的（ios）。
 * 元件可以用 platform 屬性指定；沒指定就用上層設定的，或依這台裝置的輸入方式決定。
 */
import { getContext, setContext } from "svelte";

const KEY = "lg-platform";
export const TYPE = {
  mac: { largeTitle: "mac-large-title-em", title2: "mac-title-2", title3: "mac-title-3", headline: "mac-headline", body: "mac-body", bodyEm: "mac-body-em", callout: "mac-callout", sub: "mac-subheadline", footnote: "mac-footnote", caption: "mac-caption-1" },
  ios: { largeTitle: "ios-large-title-em", title2: "ios-title-2-em", title3: "ios-title-3", headline: "ios-headline", body: "ios-body", bodyEm: "ios-body-em", callout: "ios-callout", sub: "ios-subheadline", footnote: "ios-footnote", caption: "ios-caption-2" },
};

export function devicePlatform() {
  return typeof matchMedia === "function" && matchMedia("(pointer: coarse)").matches ? "ios" : "mac";
}
/** 在元件初始化時呼叫 */
export function usePlatform(p) {
  return p || getContext(KEY) || devicePlatform();
}
export function providePlatform(p) {
  setContext(KEY, p);
}
export const cx = (...a) => a.filter(Boolean).join(" ");
let seq = 0;
export const uid = (prefix = "lg") => `${prefix}-${++seq}`;

/** Svelte action：按到元素外面或按 Escape 時呼叫 onclose */
export function dismiss(node, onclose) {
  const down = (e) => { if (!node.contains(e.target)) onclose?.(); };
  const key = (e) => { if (e.key === "Escape") onclose?.(); };
  document.addEventListener("mousedown", down);
  document.addEventListener("keydown", key);
  return {
    update(fn) { onclose = fn; },
    destroy() { document.removeEventListener("mousedown", down); document.removeEventListener("keydown", key); },
  };
}
