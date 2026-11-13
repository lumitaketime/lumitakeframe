<script>
  /** 圖庫空間依類型分：一條分段長條＋圖例（名稱、大小、比例、數量）。點圖例可篩選下方清單。 */
  import { bytes, count } from "../lib/format.js";

  let { kinds = [], selected = "all", onpick } = $props();

  const total = $derived(kinds.reduce((s, k) => s + k.bytes, 0));
  const pct = (b) => (total ? (b / total) * 100 : 0);
  const fmt = (p) => (p >= 10 ? `${Math.round(p)}%` : `${p.toFixed(1)}%`);
</script>

<div class="kindbar">
  <div class="head"><b>{bytes(total) || "0 KB"}</b><span class="muted small">圖庫照片與影片共佔</span></div>
  <div class="bar" role="img" aria-label={kinds.map((k) => `${k.label} ${bytes(k.bytes)}`).join("，")}>
    {#each kinds as k (k.key)}
      {#if k.bytes}<span class="seg {k.key}" class:dim={selected !== "all" && selected !== k.key} style:flex-grow={k.bytes} title="{k.label}：{bytes(k.bytes)}（{fmt(pct(k.bytes))}）"></span>{/if}
    {/each}
  </div>
  <div class="legend">
    {#each kinds as k (k.key)}
      <button class="item m3-state" class:on={selected === k.key} onclick={() => onpick?.(selected === k.key ? "all" : k.key)} aria-pressed={selected === k.key}>
        <span class="sw {k.key}"></span>
        <span class="lbl">{k.label}</span>
        <span class="v">{bytes(k.bytes) || "0 KB"} · {fmt(pct(k.bytes))}</span>
        <span class="n">{count(k.files)} 個</span>
      </button>
    {/each}
  </div>
</div>

<style>
  .kindbar {
    --c-video: var(--kind-video); --c-raw: var(--kind-raw); --c-photo: var(--kind-photo);
    background: var(--surface-container-low); border-radius: var(--corner-large); padding: 16px 20px; margin-bottom: 16px;
    display: flex; flex-direction: column; gap: 10px;
  }
  .head { display: flex; align-items: baseline; gap: 8px; }
  .head b { font-size: var(--text-title-1); font-weight: 500; font-variant-numeric: tabular-nums; }
  .bar { display: flex; gap: 2px; height: 14px; border-radius: var(--corner-small); overflow: hidden; background: var(--surface-container-highest); }
  .seg { min-width: 3px; transition: opacity var(--spring-effects-fast-duration) var(--spring-effects-fast); }
  .seg.dim { opacity: .3; }
  .video { background: var(--c-video); } .raw { background: var(--c-raw); } .photo { background: var(--c-photo); }
  .legend { display: flex; flex-wrap: wrap; gap: 4px 8px; margin: 0 -8px; }
  .item {
    display: grid; grid-template-columns: 12px auto; column-gap: 8px; align-items: center; border: 0; background: none; color: var(--on-surface);
    padding: 6px 10px; border-radius: var(--corner-medium); cursor: pointer; text-align: left;
  }
  .item.on { background: var(--secondary-container); color: var(--on-secondary-container); }
  .sw { width: 12px; height: 12px; border-radius: var(--radius-xs); grid-row: span 3; align-self: start; margin-top: 4px; }
  .lbl { font-size: var(--text-body); font-weight: 500; }
  .v { font-size: var(--text-body); font-variant-numeric: tabular-nums; }
  .n { font-size: var(--text-callout); color: var(--on-surface-variant); }
</style>
