/**
 * 開關照片時的「放大／縮回」動畫：照片從網格裡的縮圖位置長成全螢幕，關閉時縮回原位（像 Google 相簿）。
 * 做法是蓋一張固定定位的圖片，從起點矩形動到終點矩形，結束後移除。
 */
import { DUR, EASE } from "./motion.js";

const reduce = () => matchMedia("(prefers-reduced-motion: reduce)").matches;

/** 網格裡這張照片的縮圖；不在畫面上時回傳 null */
export function findThumb(id, { scroll = false } = {}) {
  const el = document.querySelector(`.thumb[data-asset="${id}"]`);
  if (!el) return null;
  let r = el.getBoundingClientRect();
  const off = r.bottom < 60 || r.top > innerHeight - 20;
  if (off && scroll) {
    el.scrollIntoView({ block: "center", behavior: "instant" });
    r = el.getBoundingClientRect();
  } else if (off) return null;
  if (!r.width || !r.height) return null;
  const img = el.querySelector("img");
  return { el, rect: r, src: img?.currentSrc || img?.src || "", radius: getComputedStyle(el).borderRadius };
}

/** 把圖片從 from 動到 to；回傳 Promise，動畫結束時完成 */
export function fly({ src, from, to, duration = DUR.move, fromRadius = "0px", toRadius = "0px", easing = EASE.out }) {
  if (!src || !from || !to || reduce()) return Promise.resolve();
  const img = document.createElement("img");
  img.src = src;
  img.alt = "";
  Object.assign(img.style, {
    position: "fixed", zIndex: "200", objectFit: "cover", pointerEvents: "none", margin: "0",
    left: `${to.left}px`, top: `${to.top}px`, width: `${to.width}px`, height: `${to.height}px`, borderRadius: toRadius,
  });
  document.body.appendChild(img);
  const frame = (r, radius) => ({ left: `${r.left}px`, top: `${r.top}px`, width: `${r.width}px`, height: `${r.height}px`, borderRadius: radius });
  const anim = img.animate([frame(from, fromRadius), frame(to, toRadius)], { duration, easing, fill: "forwards" });
  return anim.finished.catch(() => {}).then(() => img);
}

export const heroDuration = DUR.move;
