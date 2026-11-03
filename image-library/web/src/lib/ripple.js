/**
 * Material 3 漣漪：按下時從按下的位置擴散，放開後淡出。
 * 用一個全域監聽處理所有按鈕、Chip、導覽與卡片，不需要每個元件各自加。
 */
const TARGETS = [
  ".btn", ".icon-btn", ".chip", ".m3-state", ".sidebar a", ".bottom a", ".cats a", ".tabs a",
  ".seg button", ".pill", ".cover-card .cover", ".feature", ".style", ".pick",
].join(",");

const reduced = () => window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

export function installRipple() {
  document.addEventListener(
    "pointerdown",
    (e) => {
      if (e.button !== 0 || reduced()) return;
      const host = e.target.closest?.(TARGETS);
      if (!host || host.disabled || host.getAttribute("aria-disabled") === "true") return;
      // 卡片的漣漪畫在封面上
      const el = host.matches(".cover-card") ? host.querySelector(".cover") || host : host;
      const r = el.getBoundingClientRect();
      const size = Math.hypot(r.width, r.height) * 2;
      const dot = document.createElement("span");
      dot.className = "m3-ripple";
      dot.style.width = dot.style.height = `${size}px`;
      dot.style.left = `${e.clientX - r.left - size / 2}px`;
      dot.style.top = `${e.clientY - r.top - size / 2}px`;
      el.appendChild(dot);
      const release = () => {
        dot.classList.add("out");
        setTimeout(() => dot.remove(), 260);
        window.removeEventListener("pointerup", release);
        window.removeEventListener("pointercancel", release);
      };
      window.addEventListener("pointerup", release);
      window.addEventListener("pointercancel", release);
    },
    { passive: true },
  );
}
