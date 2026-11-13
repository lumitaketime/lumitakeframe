<script>
  /**
   * 右側時間捲動欄：年份標籤＋月份刻度，滑過或拖曳時顯示「年月 · 張數」。
   * marks：[{ label, year, top, size, count }]，top／size 是 0–1 的比例。
   */
  import { count as fmt } from "../lib/format.js";

  let { marks = [], active = -1, onjump, dragging = $bindable(false) } = $props();

  let el = $state();
  let height = $state(0);
  let hover = $state(null);

  const years = $derived.by(() => {
    const out = [];
    let lastPx = -100;
    for (const m of marks) {
      if (out.length && out[out.length - 1].year === m.year) continue;
      const px = m.top * height;
      const hidden = px - lastPx < 22;
      if (!hidden) lastPx = px;
      out.push({ year: m.year, top: m.top, hidden });
    }
    return out;
  });

  // 月份刻度：間距太密就略過，避免糊成一條線
  const ticks = $derived.by(() => {
    const out = [];
    let lastPx = -100;
    marks.forEach((m, i) => {
      const px = m.top * height;
      if (px - lastPx >= 5) {
        out.push({ i, top: m.top });
        lastPx = px;
      }
    });
    return out;
  });

  function indexAt(clientY) {
    const r = el.getBoundingClientRect();
    const f = Math.min(Math.max((clientY - r.top - 12) / (r.height - 24), 0), 0.9999);
    let i = marks.findIndex((m) => f >= m.top && f < m.top + m.size);
    if (i === -1) i = marks.length - 1;
    return i;
  }

  function down(e) {
    dragging = true;
    e.currentTarget.setPointerCapture(e.pointerId);
    onjump?.(indexAt(e.clientY));
  }
  function move(e) {
    const i = indexAt(e.clientY);
    hover = { i, y: e.clientY - el.getBoundingClientRect().top };
    if (dragging && i !== active) onjump?.(i);
  }
  function up() {
    dragging = false;
  }

  const bubble = $derived(hover && marks[hover.i] ? { m: marks[hover.i], y: hover.y }
    : dragging && marks[active] ? { m: marks[active], y: 12 + marks[active].top * (height - 24) } : null);
</script>

<!-- svelte-ignore a11y_no_static_element_interactions -->
<div
  class="scrubber"
  class:dragging
  bind:this={el}
  bind:clientHeight={height}
  onpointerdown={down}
  onpointermove={move}
  onpointerup={up}
  onpointercancel={up}
  onpointerleave={() => (hover = null)}
>
  <div class="track">
    {#each ticks as t (t.i)}<span class="tick" style:top="{t.top * 100}%"></span>{/each}
    {#each years as y (y.year)}
      {#if !y.hidden}<span class="year" style:top="{y.top * 100}%">{y.year}</span>{/if}
    {/each}
    {#if active >= 0 && marks[active]}
      <span class="indicator" style:top="{marks[active].top * 100}%"></span>
    {/if}
  </div>
  {#if bubble}
    <span class="bubble" style:top="{bubble.y}px">{bubble.m.label}{bubble.m.count ? ` · ${fmt(bubble.m.count)} 張` : ""}</span>
  {/if}
</div>

<style>
  .scrubber {
    position: sticky; top: 0; height: calc(100vh - var(--topbar)); height: calc(100dvh - var(--topbar));
    width: 64px; flex-shrink: 0; cursor: row-resize; user-select: none; touch-action: none;
  }
  .track { position: absolute; inset: 12px 0; pointer-events: none; }
  .year {
    position: absolute; right: 16px; transform: translateY(-50%); font-size: var(--text-sub); color: var(--on-surface);
    font-weight: 500; background: var(--surface); padding: 0 2px; font-variant-numeric: tabular-nums;
  }
  .tick { position: absolute; right: 6px; width: 6px; height: 1px; background: var(--on-surface-variant); opacity: .45; }
  .indicator {
    position: absolute; right: 0; width: 26px; height: 2px; background: var(--primary); transition: top .12s;
  }
  .bubble {
    position: absolute; right: 60px; transform: translateY(-50%); background: var(--on-surface); color: var(--surface);
    border-radius: var(--corner-small); padding: 5px 10px; font-size: var(--text-body); white-space: nowrap; pointer-events: none; z-index: 5;
    font-variant-numeric: tabular-nums;
  }
  @media (max-width: 760px) {
    .scrubber { width: 26px; position: fixed; right: 0; top: var(--topbar); bottom: 64px; height: auto; z-index: 10; }
    .year, .tick { display: none; }
    .scrubber.dragging .year { display: block; }
    .indicator { width: 6px; height: 36px; border-radius: var(--radius-xs); right: 3px; transform: translateY(-50%); opacity: .6; }
    .bubble { right: 30px; }
  }
</style>
