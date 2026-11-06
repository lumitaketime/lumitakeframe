<script>
  /**
   * 可展開的網格（探索頁的人物、事物、場景、地點、年份）：平常只顯示一列，
   * 按「顯示全部」往下展開、「收起」收回（M3 emphasized 曲線）。不用左右拖。
   * min：每格最小寬度（px）；total：總數（顯示在按鈕上）。
   */
  import { onMount, tick } from "svelte";
  import Icon from "./Icon.svelte";
  import { mdiChevronDown } from "../lib/icons.js";

  let { min = 156, gap = 12, total = 0, children } = $props();
  let el;
  let open = $state(false);
  let rowH = $state(0);
  let fullH = $state(0);
  let perRow = $state(0);

  function measure() {
    if (!el) return;
    const first = el.firstElementChild;
    rowH = first ? first.offsetHeight : 0;
    fullH = el.scrollHeight;
    perRow = Math.max(1, Math.floor((el.clientWidth + gap) / (min + gap)));
  }

  onMount(() => {
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    measure();
    return () => ro.disconnect();
  });

  async function toggle() {
    measure();
    open = !open;
    await tick();
    if (!open) el.closest("section")?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }

  const overflow = $derived(fullH > rowH + 4);
  const count = $derived(total || el?.children.length || 0);
</script>

<div class="xg" bind:this={el} style:--min="{min}px" style:--gap="{gap}px"
  style:max-height={rowH ? `${open ? fullH : rowH}px` : null}>
  {@render children?.()}
</div>
{#if overflow}
  <button class="more btn text small" class:open onclick={toggle} aria-expanded={open}>
    {open ? "收起" : `顯示全部${count > perRow ? `（${count}）` : ""}`}<Icon path={mdiChevronDown} size={18} />
  </button>
{/if}

<style>
  .xg {
    display: grid; grid-template-columns: repeat(auto-fill, minmax(var(--min), 1fr)); gap: var(--gap);
    overflow: hidden;
    transition: max-height var(--duration-long2, 500ms) var(--easing-emphasized, cubic-bezier(.2, 0, 0, 1));
  }
  .more { margin: 4px 0 0 -12px; }
  .more :global(svg) { transition: transform var(--duration-medium2, 300ms) var(--easing-emphasized, ease); }
  .more.open :global(svg) { transform: rotate(180deg); }
  @media (prefers-reduced-motion: reduce) { .xg { transition: none; } }
</style>
