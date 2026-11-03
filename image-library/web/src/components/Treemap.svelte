<script>
  /**
   * 資料夾矩形樹狀圖：格子越大代表越佔空間。點資料夾往下一層，點「這層的檔案」打開資料夾。
   * 顏色只用一個色相，越大越深；名稱與大小直接寫在格子裡，太小的格子滑過才顯示。
   */
  import { squarify } from "../lib/squarify.js";
  import { bytes, count } from "../lib/format.js";

  let { items = [], total = 0, onopen } = $props();

  let w = $state(0);
  let h = $state(0);
  let hover = $state(null);
  let tip = $state({ x: 0, y: 0 });

  const GAP = 2;
  const shown = $derived(items.filter((it) => it.bytes > 0).slice(0, 40));
  const rects = $derived(squarify(shown.map((it) => it.bytes), 0, 0, w, h));
  const max = $derived(Math.max(1, ...shown.map((it) => it.bytes)));

  function share(it) {
    const p = total ? (it.bytes / total) * 100 : 0;
    return p >= 10 ? `${Math.round(p)}%` : `${p.toFixed(1)}%`;
  }

  function move(e, it) {
    const box = e.currentTarget.parentElement.getBoundingClientRect();
    tip = { x: e.clientX - box.left, y: e.clientY - box.top };
    hover = it;
  }
</script>

<div class="treemap" bind:clientWidth={w} bind:clientHeight={h} role="list" aria-label="資料夾大小">
  {#each shown as it, i (it.path + it.name)}
    {@const r = rects[i]}
    {#if r}
      {@const big = r.w > 96 && r.h > 44}
      <button
        role="listitem"
        class="cell m3-state"
        class:files={!it.folder}
        style:left="{r.x + GAP / 2}px" style:top="{r.y + GAP / 2}px"
        style:width="{Math.max(0, r.w - GAP)}px" style:height="{Math.max(0, r.h - GAP)}px"
        style:--t={0.28 + 0.62 * Math.sqrt(it.bytes / max)}
        onclick={() => onopen?.(it)}
        onpointermove={(e) => move(e, it)}
        onpointerleave={() => (hover = null)}
        aria-label="{it.name}，{bytes(it.bytes)}，佔 {share(it)}，{count(it.files)} 個檔案"
      >
        {#if big}
          <span class="name">{it.name}</span>
          <span class="val">{bytes(it.bytes)} · {share(it)}</span>
        {/if}
      </button>
    {/if}
  {/each}
  {#if hover}
    <div class="tip" style:left="{tip.x}px" style:top="{tip.y}px" class:flip={tip.x > w - 200}>
      <b>{hover.name}</b>
      <span>{bytes(hover.bytes)}（{share(hover)}）</span>
      <span class="muted">{count(hover.files)} 個檔案{hover.folder ? " · 點一下看裡面" : " · 點一下打開資料夾"}</span>
    </div>
  {/if}
</div>

<style>
  .treemap {
    --series-1: #2a78d6;
    position: relative; height: 340px; border-radius: var(--corner-large); overflow: hidden; background: var(--surface);
  }
  @media (prefers-color-scheme: dark) { :global(:root:not([data-theme="light"])) .treemap { --series-1: #3987e5; } }
  :global(:root[data-theme="dark"]) .treemap { --series-1: #3987e5; }
  .cell {
    position: absolute; border: 0; padding: 8px 10px; margin: 0; cursor: pointer; text-align: left; overflow: hidden;
    display: flex; flex-direction: column; justify-content: flex-end; gap: 2px; border-radius: 4px;
    background: color-mix(in srgb, var(--series-1) calc(var(--t) * 100%), var(--surface-container));
    color: var(--on-surface);
    transition: left var(--spring-standard-default-spatial-duration) var(--spring-standard-default-spatial),
      top var(--spring-standard-default-spatial-duration) var(--spring-standard-default-spatial),
      width var(--spring-standard-default-spatial-duration) var(--spring-standard-default-spatial),
      height var(--spring-standard-default-spatial-duration) var(--spring-standard-default-spatial);
    animation: m3-fade var(--duration-medium2) linear;
  }
  .cell.files {
    background: repeating-linear-gradient(45deg, var(--surface-container-high) 0 6px, var(--surface-container-highest) 6px 12px);
  }
  .cell:focus-visible { outline: 2px solid var(--on-surface); outline-offset: -2px; }
  .name, .val {
    max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; width: fit-content;
    background: var(--surface); padding: 1px 6px; border-radius: 4px;
  }
  .name { font-size: 13px; font-weight: 500; }
  .val { font-size: 12px; color: var(--on-surface-variant); font-variant-numeric: tabular-nums; }
  .tip {
    position: absolute; z-index: 3; pointer-events: none; transform: translate(12px, 12px); display: flex; flex-direction: column; gap: 2px;
    background: var(--inverse-surface); color: var(--inverse-on-surface); padding: 8px 12px; border-radius: var(--corner-small);
    font-size: 12px; line-height: 16px; white-space: nowrap; max-width: 280px;
  }
  .tip.flip { transform: translate(calc(-100% - 12px), 12px); }
  .tip b { font-size: 13px; font-weight: 500; overflow: hidden; text-overflow: ellipsis; }
  .tip .muted { color: inherit; opacity: .8; }
  @media (max-width: 760px) { .treemap { height: 260px; } }
</style>
