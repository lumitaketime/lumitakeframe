<script>
  /**
   * 載入中的畫面，讓使用者知道系統正在跑，而不是一片空白：
   * - kind="spinner"：M3 圓形進度指示（弧線一邊轉一邊伸縮），可加文字
   * - kind="grid"：照片網格的骨架（依設定是正方形或依比例的圓角色塊），鋪滿 height（預設一個畫面高）；
   *   一道亮光不斷由上往下掃過，用 GPU 動畫，多高都不會變慢
   * - kind="cards"：相簿、人物等卡片的骨架；round 時是圓形頭像
   * - kind="rows"：設定、清單的骨架
   * 剛開始的 delay 毫秒內不顯示，很快就載入完的頁面不會閃一下。
   */
  import { onMount } from "svelte";
  import { app } from "../lib/state.svelte.js";

  let { kind = "spinner", label = "", count = 0, round = false, delay = kind === "spinner" ? 150 : 0, size = 40, inline = false, height = 0 } = $props();
  let show = $state(false);
  onMount(() => {
    const t = setTimeout(() => (show = true), delay);
    return () => clearTimeout(t);
  });

  const square = $derived(app.server?.ui?.grid_style === "square" || (typeof innerWidth !== "undefined" && innerWidth < 640));
  // 依比例模式用幾種常見的長寬比，看起來像真的照片排列
  // 網格的形狀用遮罩畫：兩列一組，依比例模式每列 4 張不同寬度，正方形模式一排排方塊
  const svg = (body, w, h) => `url("data:image/svg+xml,${encodeURIComponent(`<svg xmlns='http://www.w3.org/2000/svg' width='${w}' height='${h}'>${body}</svg>`)}")`;
  const rect = (x, y, w, h = 200) => `<rect x='${x}' y='${y}' width='${w}' height='${h}' rx='8'/>`;
  const JUSTIFIED = svg(
    [[0, 296], [300, 196], [500, 246], [750, 246]].map(([x, w]) => rect(x, 0, w)).join("") +
    [[0, 180], [184, 300], [488, 220], [712, 284]].map(([x, w]) => rect(x, 204, w)).join(""), 1000, 408);
  const SQUARES = (n) => svg([...Array(n)].map((_, i) => rect(i * 204, 0, 200)).join(""), n * 204, 204);
</script>

{#if show}
  {#if kind === "grid"}
    <div class="skel-fill" class:square role="status" aria-label={label || "載入中"}
      style:height={height ? `${height}px` : count ? `${Math.ceil(count / 4) * 204}px` : null}
      style:--mask={square ? SQUARES(10) : JUSTIFIED}></div>
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

  /* 鋪滿的網格骨架：底色＋圓角方塊遮罩，裡面一道亮帶由上往下一直掃（只動 transform，交給 GPU） */
  .skel-fill {
    position: relative; overflow: hidden; height: calc(100vh - 160px); min-height: 204px;
    background: var(--surface-container-highest);
    -webkit-mask-image: var(--mask); mask-image: var(--mask);
    -webkit-mask-size: auto 408px; mask-size: auto 408px;
    -webkit-mask-repeat: repeat; mask-repeat: repeat;
    animation: m3-fade var(--duration-medium2) var(--easing-standard) both;
  }
  .skel-fill.square { -webkit-mask-size: auto 204px; mask-size: auto 204px; }
  .skel-fill::after {
    content: ""; position: absolute; left: 0; right: 0; top: -720px; height: calc(100% + 720px); will-change: transform;
    background: repeating-linear-gradient(to bottom,
      transparent 0, color-mix(in srgb, var(--surface) 75%, transparent) 180px, transparent 360px, transparent 720px);
    animation: skel-band 1.5s linear infinite;
  }
  @keyframes skel-band { from { transform: translateY(0); } to { transform: translateY(720px); } }
  @media (max-width: 640px) {
    .skel-fill.square { -webkit-mask-size: auto 136px; mask-size: auto 136px; }
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
    .skel-fill::after { animation: none; }
    .m3-spin, .m3-spin circle { animation-duration: 1.568s !important; animation-iteration-count: infinite !important; }
  }
</style>
