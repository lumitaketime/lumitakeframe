<script>
  /**
   * 載入中的畫面，讓使用者知道系統正在跑，而不是一片空白：
   * - kind="spinner"：M3 圓形進度指示（弧線一邊轉一邊伸縮），可加文字
   * - kind="grid"：照片網格的骨架（依設定是正方形或依比例的圓角色塊）
   * - kind="cards"：相簿、人物等卡片的骨架；round 時是圓形頭像
   * - kind="rows"：設定、清單的骨架
   * 剛開始的 delay 毫秒內不顯示，很快就載入完的頁面不會閃一下。
   */
  import { onMount } from "svelte";
  import { app } from "../lib/state.svelte.js";

  let { kind = "spinner", label = "", count = 0, round = false, delay = 120, size = 40, inline = false } = $props();
  let show = $state(false);
  onMount(() => {
    const t = setTimeout(() => (show = true), delay);
    return () => clearTimeout(t);
  });

  const square = $derived(app.server?.ui?.grid_style === "square" || (typeof innerWidth !== "undefined" && innerWidth < 640));
  // 依比例模式用幾種常見的長寬比，看起來像真的照片排列
  const RATIOS = [1.5, 0.67, 1.33, 1.5, 1, 0.75, 1.78, 1.5, 0.67, 1.33, 1.5, 1.5, 0.75, 1, 1.5, 1.33, 0.67, 1.5];
</script>

{#if show}
  {#if kind === "grid"}
    <div class="skel-grid" class:square role="status" aria-label={label || "載入中"}>
      {#each Array(count || (square ? 24 : 18)) as _, i (i)}
        <span class="skel" style:--r={square ? 1 : RATIOS[i % RATIOS.length]} style:--wave={Math.floor(i / (square ? 6 : 4))}></span>
      {/each}
    </div>
  {:else if kind === "cards"}
    <div class="skel-cards" role="status" aria-label={label || "載入中"}>
      {#each Array(count || 8) as _, i (i)}
        <div class="card-sk" style:--wave={Math.floor(i / 4)}>
          <span class="skel cover" class:round></span>
          <span class="skel line"></span>
          <span class="skel line short"></span>
        </div>
      {/each}
    </div>
  {:else if kind === "rows"}
    <div class="skel-rows" role="status" aria-label={label || "載入中"}>
      {#each Array(count || 4) as _, i (i)}
        <div class="row-sk" style:--wave={i}>
          <span class="skel dot"></span>
          <span class="col"><span class="skel line"></span><span class="skel line short"></span></span>
        </div>
      {/each}
    </div>
  {:else}
    <div class="spin-wrap" class:inline role="status" aria-live="polite">
      <svg class="m3-spin" width={size} height={size} viewBox="0 0 48 48" aria-hidden="true">
        <circle cx="24" cy="24" r="19" />
      </svg>
      {#if label}<span class="lbl">{label}</span>{/if}
    </div>
  {/if}
{/if}

<style>
  .spin-wrap {
    display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 16px; padding: 64px 16px;
    color: var(--on-surface-variant); animation: m3-fade var(--duration-medium2) var(--easing-standard);
  }
  .spin-wrap.inline { flex-direction: row; padding: 12px 0; justify-content: flex-start; gap: 12px; }
  .lbl { font-size: 14px; line-height: 20px; }
  /* M3 圓形不定進度：整體旋轉，弧長在 10%–75% 之間伸縮 */
  .m3-spin { animation: m3-rotate 1.568s linear infinite; }
  .m3-spin circle {
    fill: none; stroke: var(--primary); stroke-width: 4; stroke-linecap: round;
    stroke-dasharray: 119.4; stroke-dashoffset: 107; transform-origin: center;
    animation: m3-arc 1.333s cubic-bezier(.4, 0, .2, 1) infinite;
  }
  @keyframes m3-rotate { to { transform: rotate(360deg); } }
  @keyframes m3-arc {
    0% { stroke-dashoffset: 107; transform: rotate(0deg); }
    50% { stroke-dashoffset: 30; transform: rotate(120deg); }
    100% { stroke-dashoffset: 107; transform: rotate(360deg); }
  }

  /* 一閃一閃、由上往下一波一波（--wave＝第幾列） */
  .skel {
    display: block; border-radius: var(--corner-small); background: var(--surface-container-highest);
    animation: m3-skel-wave 1.5s ease-in-out infinite both;
    animation-delay: calc(var(--wave, 0) * 110ms);
  }

  .skel-grid { display: flex; flex-wrap: wrap; gap: 4px; }
  .skel-grid .skel { height: 200px; flex: var(--r) 1 calc(200px * var(--r)); }
  .skel-grid.square { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); }
  .skel-grid.square .skel { height: auto; aspect-ratio: 1; }
  @media (max-width: 640px) {
    .skel-grid { gap: 2px; }
    .skel-grid.square { grid-template-columns: repeat(3, 1fr); }
  }

  .skel-cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 24px 16px; }
  .card-sk .cover { aspect-ratio: 1; border-radius: var(--corner-large); }
  .card-sk .cover.round { border-radius: 50%; }
  .line { height: 14px; margin-top: 10px; border-radius: var(--corner-full); width: 70%; }
  .line.short { width: 40%; height: 12px; margin-top: 6px; }

  .skel-rows { display: flex; flex-direction: column; gap: 8px; }
  .card-sk .skel, .row-sk .skel { animation-delay: calc(var(--wave, 0) * 110ms); }
  .row-sk { display: flex; align-items: center; gap: 16px; padding: 12px 16px; border-radius: var(--corner-large); background: var(--surface-container-low); }
  .row-sk .dot { width: 40px; height: 40px; border-radius: 50%; flex-shrink: 0; }
  .row-sk .col { flex: 1; }
  .row-sk .line { margin-top: 0; }
  .row-sk .line.short { margin-top: 8px; }

  @media (prefers-reduced-motion: reduce) {
    .skel { animation: none; opacity: .7; }
    .m3-spin, .m3-spin circle { animation-duration: 1.568s !important; animation-iteration-count: infinite !important; }
  }
</style>
