<script>
  /**
   * 可展開的網格（探索頁的人物、事物、場景、地點、年份）：平常只畫第一列，
   * 按「顯示全部」往下展開：位置立刻讓出來，多出來的項目由上往下快速淡入（M3 enter，約 0.2 秒）；
   * 「收起」時快速淡出。不用遮罩裁切高度（裁切會把一列切一半，看起來像圖片疊在一起），也不左右拖。
   * items：資料；item：每一格的 snippet；key：每一格的鍵；min：每格最小寬度（px）。
   */
  import { onMount, tick } from "svelte";
  import { fly, fade } from "svelte/transition";
  import { cubicOut } from "svelte/easing";
  import Icon from "./Icon.svelte";
  import { mdiChevronDown } from "../lib/icons.js";

  let { items = [], item, key = (x, i) => i, min = 156, gap = 12 } = $props();
  let el = $state();
  let open = $state(false);
  let perRow = $state(0);

  function measure() {
    if (el) perRow = Math.max(1, Math.floor((el.clientWidth + gap) / (min + gap)));
  }
  onMount(() => {
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    measure();
    return () => ro.disconnect();
  });

  const shown = $derived(open || !perRow ? items : items.slice(0, perRow));
  const overflow = $derived(perRow > 0 && items.length > perRow);
  const reduce = () => matchMedia("(prefers-reduced-motion: reduce)").matches;

  // 第一列不做動畫；後面的依順序稍微錯開（最多 0.12 秒），一列一列往下長出來
  function enter(node, { index }) {
    if (index < perRow || reduce()) return { duration: 0 };
    return fly(node, { y: -8, duration: 200, delay: Math.min(120, (index - perRow) * 8), easing: cubicOut });
  }
  function leave(node, { index }) {
    if (index < perRow || reduce()) return { duration: 0 };
    return fade(node, { duration: 100 });
  }

  async function toggle() {
    open = !open;
    if (!open) {
      await tick();
      el?.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }
  }
</script>

<div class="xg" bind:this={el} style:--min="{min}px" style:--gap="{gap}px">
  {#each shown as it, i (key(it, i))}
    <div class="cell" in:enter={{ index: i }} out:leave={{ index: i }}>{@render item(it)}</div>
  {/each}
</div>
{#if overflow}
  <button class="more btn text small" class:open onclick={toggle} aria-expanded={open}>
    {open ? "收起" : `顯示全部（${items.length}）`}<Icon path={mdiChevronDown} size={18} />
  </button>
{/if}

<style>
  .xg { display: grid; grid-template-columns: repeat(auto-fill, minmax(var(--min), 1fr)); gap: var(--gap); }
  .cell { min-width: 0; display: flex; flex-direction: column; }
  .cell > :global(*) { flex: 1; }
  .more { margin: 4px 0 0 -12px; }
  .more :global(svg) { transition: transform var(--duration-short4, 200ms) var(--easing-standard, ease); }
  .more.open :global(svg) { transform: rotate(180deg); }
</style>
