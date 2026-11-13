<script>
  import { slider } from "../lib/slider.js";
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
    <div class="grp seg" aria-label="檔案類型" use:slider>
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
  .fbar { display: flex; align-items: center; gap: 16px; flex-wrap: wrap; margin: 6px 0 4px; }
  .grp { display: flex; align-items: center; gap: 2px; }
  .star { border: 0; background: none; color: var(--outline-variant); padding: 4px; cursor: pointer; display: flex; border-radius: 50%; }
  .star:hover { color: var(--on-surface-variant); background: color-mix(in srgb, var(--on-surface) 8%, transparent); }
  .star.on { color: var(--system-yellow); }
  .star.rej.on { color: var(--error); }
  .dot { width: 18px; height: 18px; border-radius: 50%; border: 0; background: var(--c); opacity: .35; margin: 0 4px; cursor: pointer; padding: 0; transition: opacity var(--dur-fast), box-shadow var(--dur-fast); }
  .dot:hover { opacity: .7; }
  .dot.on { opacity: 1; box-shadow: 0 0 0 2px var(--surface-container-low), 0 0 0 4px var(--c); }
  .seg { border: 1px solid var(--outline); border-radius: var(--corner-full); overflow: hidden; gap: 0; }
  .seg button { border: 0; background: none; color: var(--on-surface); padding: 0 14px; height: 32px; font-size: var(--text-body); font-weight: 500; cursor: pointer; }
  .seg button + button { border-left: 1px solid var(--outline); }
  .seg button.on { background: var(--secondary-container); color: var(--on-secondary-container); }
  .clear { display: flex; align-items: center; gap: 4px; border: 0; background: none; color: var(--primary); border-radius: var(--corner-full); padding: 0 12px; height: 32px; font-size: var(--text-body); font-weight: 500; cursor: pointer; }
  .clear:hover { background: color-mix(in srgb, var(--primary) 8%, transparent); }
</style>
