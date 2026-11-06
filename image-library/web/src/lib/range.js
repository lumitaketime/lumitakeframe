/**
 * 滑桿的已選範圍：WebKit 不能直接畫出「已選的那一段」，用 --pct 讓 CSS 畫。
 * 使用者拖曳（input 事件）、程式改值（value 設定）、新的滑桿出現時都會更新。
 */
function sync(el) {
  if (!(el instanceof HTMLInputElement) || el.type !== "range") return;
  const min = Number(el.min || 0);
  const max = Number(el.max || 100);
  const pct = max > min ? ((Number(el.value) - min) / (max - min)) * 100 : 0;
  el.style.setProperty("--pct", `${Math.min(100, Math.max(0, pct))}%`);
}

export function installRangeFill() {
  document.addEventListener("input", (e) => sync(e.target), true);
  // 程式直接設定 value（例如 Svelte 的 bind:value）時也更新
  const desc = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value");
  if (desc?.set) {
    Object.defineProperty(HTMLInputElement.prototype, "value", {
      ...desc,
      set(v) {
        desc.set.call(this, v);
        if (this.type === "range") sync(this);
      },
    });
  }
  const scan = (root) => root.querySelectorAll?.('input[type="range"]').forEach(sync);
  scan(document);
  new MutationObserver((muts) => {
    for (const m of muts) {
      for (const n of m.addedNodes) {
        if (n.nodeType !== 1) continue;
        if (n.matches?.('input[type="range"]')) sync(n);
        else scan(n);
      }
      if (m.type === "attributes") sync(m.target);
    }
  }).observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ["min", "max", "value"] });
}
