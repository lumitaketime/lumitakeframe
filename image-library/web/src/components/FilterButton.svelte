<script>
  /** 頂欄搜尋框旁的篩選按鈕：打開星等、顏色、類型的篩選面板；有條件時按鈕上有小圓點。 */
  import Icon from "./Icon.svelte";
  import FilterBar from "./FilterBar.svelte";
  import { filterUI, filterActive } from "../lib/filter.svelte.js";
  import { mdiFilterVariant } from "../lib/icons.js";

  let root = $state();

  function outside(e) {
    if (filterUI.open && root && !root.contains(e.target)) filterUI.open = false;
  }
  function key(e) {
    if (filterUI.open && e.key === "Escape") filterUI.open = false;
  }
</script>

<svelte:window onpointerdown={outside} onkeydown={key} />

<div class="fb" bind:this={root}>
  <button class="icon-btn" class:active={filterUI.open || filterActive()} onclick={() => (filterUI.open = !filterUI.open)}
    aria-expanded={filterUI.open} aria-haspopup="dialog" aria-label="篩選" title="篩選（星等、顏色、類型）">
    <Icon path={mdiFilterVariant} />
    {#if filterActive()}<span class="badge"></span>{/if}
  </button>
  {#if filterUI.open}
    <div class="panel" role="dialog" aria-label="篩選">
      <FilterBar kinds={filterUI.kinds} />
    </div>
  {/if}
</div>

<style>
  .fb { position: relative; display: flex; flex-shrink: 0; }
  .icon-btn { color: var(--on-surface-variant); position: relative; }
  .badge { position: absolute; top: 8px; right: 8px; width: 8px; height: 8px; border-radius: 50%; background: var(--primary); z-index: 3; }
  .panel {
    position: absolute; top: calc(100% + 8px); right: 0; z-index: 70; padding: 8px 16px; width: max-content; max-width: min(560px, calc(100vw - 24px));
    background: var(--surface-container-high); border: 1px solid var(--outline-variant); border-radius: var(--corner-large);
    transform-origin: top right; animation: panel-in var(--spring-standard-fast-spatial-duration) var(--spring-standard-fast-spatial);
  }
  @keyframes panel-in { from { opacity: 0; transform: scaleY(.8); } }
  @media (max-width: 600px) { .panel { right: -48px; } }
</style>
