<script>
  /** 快速篩選列：星等、顏色標籤、檔案類型。 */
  import Icon from "./Icon.svelte";
  import { filter, filterActive, clearFilter } from "../lib/filter.svelte.js";
  import { LABEL_COLORS, LABEL_NAMES, LABEL_KEYS } from "../lib/format.js";
  import { mdiStar, mdiFlagRemove, mdiClose } from "../lib/icons.js";

  let { kinds = true } = $props();
  const setRating = (n) => (filter.rating = filter.rating === n ? 0 : n);
  const setLabel = (k) => (filter.label = filter.label === k ? "" : k);
  const setKind = (k) => (filter.kind = filter.kind === k ? "" : k);
</script>

<div class="fbar" role="toolbar" aria-label="快速篩選">
  <div class="grp" aria-label="星等">
    {#each [1, 2, 3, 4, 5] as n (n)}
      <button class="star" class:on={filter.rating > 0 && n <= filter.rating} onclick={() => setRating(n)} title="{n} 星以上">
        <Icon path={mdiStar} size={18} />
      </button>
    {/each}
    <button class="star rej" class:on={filter.rating === -1} onclick={() => setRating(-1)} title="只看拒絕的"><Icon path={mdiFlagRemove} size={18} /></button>
  </div>
  <div class="grp" aria-label="顏色標籤">
    {#each LABEL_KEYS as k (k)}
      <button class="dot" class:on={filter.label === k} style:--c={LABEL_COLORS[k]} onclick={() => setLabel(k)} title="{LABEL_NAMES[k]}色標籤" aria-label="{LABEL_NAMES[k]}色標籤"></button>
    {/each}
  </div>
  {#if kinds}
    <div class="grp seg" aria-label="檔案類型">
      {#each [["raw", "RAW"], ["jpeg", "JPEG"], ["video", "影片"]] as [k, label] (k)}
        <button class:on={filter.kind === k} onclick={() => setKind(k)}>{label}</button>
      {/each}
    </div>
  {/if}
  {#if filterActive()}
    <button class="clear" onclick={clearFilter}><Icon path={mdiClose} size={16} />清除篩選</button>
  {/if}
</div>

<style>
  .fbar { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; margin: 6px 0 4px; }
  .grp { display: flex; align-items: center; gap: 2px; }
  .star { border: 0; background: none; color: var(--line); padding: 3px; cursor: pointer; display: flex; border-radius: 6px; }
  .star:hover { color: var(--muted); }
  .star.on { color: #e3a008; }
  .star.rej.on { color: var(--danger); }
  .dot { width: 16px; height: 16px; border-radius: 50%; border: 0; background: var(--c); opacity: .35; margin: 0 3px; cursor: pointer; padding: 0; }
  .dot:hover { opacity: .7; }
  .dot.on { opacity: 1; box-shadow: 0 0 0 2px var(--bg), 0 0 0 4px var(--c); }
  .seg { border: 1px solid var(--line); border-radius: 999px; overflow: hidden; gap: 0; }
  .seg button { border: 0; background: none; color: var(--muted); padding: 3px 12px; font-size: 13px; cursor: pointer; }
  .seg button + button { border-left: 1px solid var(--line); }
  .seg button.on { background: var(--primary-soft); color: var(--primary); font-weight: 600; }
  .clear { display: flex; align-items: center; gap: 4px; border: 0; background: var(--primary-soft); color: var(--primary); border-radius: 999px; padding: 4px 12px; font-size: 13px; cursor: pointer; }
</style>
