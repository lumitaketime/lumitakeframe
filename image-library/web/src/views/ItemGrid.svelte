<script>
  /**
   * 圖像檢視：縮圖格狀。照片與影片顯示掃描時產生的小縮圖（不讀原檔），其他顯示類型圖示。
   * 只畫出看得到的幾列；每列高度固定、位置用 transform。
   */
  import KindIcon from "./KindIcon.svelte";
  import { handleViewKey } from "./keys.js";
  import { prefs } from "./prefs.svelte.js";
  import { thumbUrl } from "../lib/api.js";
  import { t } from "../i18n/index.svelte.js";

  let { source, sel, onopen, onpreview, oncontext } = $props();

  const GAP = 12;
  const PAD = 16;
  const LABEL = 40; // 兩行檔名
  const OVERSCAN = 2;

  let body = $state();
  let scrollTop = $state(0);
  let height = $state(600);
  let width = $state(800);
  const size = $derived(prefs.iconSize);
  const total = $derived(source.state.total ?? 0);
  const perRow = $derived(Math.max(1, Math.floor((width - PAD * 2 + GAP) / (size + GAP))));
  const rowH = $derived(size + LABEL + GAP);
  const rowCount = $derived(Math.ceil(total / perRow));
  const firstRow = $derived(Math.max(0, Math.floor(scrollTop / rowH) - OVERSCAN));
  const lastRow = $derived(Math.min(rowCount, Math.ceil((scrollTop + height) / rowH) + OVERSCAN));
  // 畫面上的格子重複利用（同列表檢視）
  const slots = $derived((Math.ceil(height / rowH) + OVERSCAN * 2 + 2) * perRow);
  const cells = $derived.by(() => {
    const out = [];
    for (let i = firstRow * perRow; i < Math.min(total, lastRow * perRow); i++) out.push({ i, item: source.get(i) });
    return out;
  });

  let raf = 0;
  function onscroll() {
    if (raf) return;
    raf = requestAnimationFrame(() => {
      raf = 0;
      if (body) scrollTop = body.scrollTop;
    });
  }
  $effect(() => {
    const f = sel.focus;
    if (f < 0 || !body) return;
    const top = Math.floor(f / perRow) * rowH;
    if (top < body.scrollTop) body.scrollTop = top;
    else if (top + rowH > body.scrollTop + body.clientHeight) body.scrollTop = top + rowH - body.clientHeight + PAD;
  });
  function onkeydown(e) {
    handleViewKey(e, { sel, total, perRow, perPage: Math.max(1, Math.floor(height / rowH)), onopen, onpreview });
  }
</script>

<!-- svelte-ignore a11y_no_noninteractive_tabindex -->
<div class="grid mac-callout" bind:this={body} bind:clientHeight={height} bind:clientWidth={width} {onscroll} {onkeydown} tabindex="0"
  role="listbox" aria-multiselectable="true" aria-label={t("view.items")} aria-activedescendant={sel.focus >= 0 ? `item-${sel.focus}` : undefined}
  style:--size="{size}px">
  <div class="space" style:height="{rowCount * rowH + PAD}px">
    {#each cells as { i, item } (i % slots)}
      <!-- svelte-ignore a11y_click_events_have_key_events -->
      <div class="cell" class:on={sel.has(i)} id="item-{i}" role="option" aria-selected={sel.has(i)} aria-setsize={total} aria-posinset={i + 1} tabindex="-1"
        style:transform="translate({PAD + (i % perRow) * (size + GAP)}px, {PAD + Math.floor(i / perRow) * rowH}px)"
        onclick={(e) => sel.click(i, e)} ondblclick={() => onopen?.(i)}
        oncontextmenu={(e) => { e.preventDefault(); sel.context(i); oncontext?.(e, i); }} title={item?.name}>
        <span class="pic">
          {#if !item}
            <i class="ph"></i>
          {:else if item.image_id}
            <img src={thumbUrl({ id: item.image_id })} alt="" loading="lazy" decoding="async" draggable="false" />
          {:else}
            <KindIcon kind={item.icon || (item.type === "folder" ? "folder" : item.kind)} size={Math.round(size * 0.5)} />
          {/if}
          {#if item?.label}<i class="label" style:background="var(--label-{item.label})"></i>{/if}
        </span>
        <span class="name">{item?.name || ""}</span>
      </div>
    {/each}
  </div>
</div>

<style>
  .grid { height: 100%; overflow-y: auto; overflow-x: hidden; position: relative; outline: none; overscroll-behavior: contain; color: var(--label-primary); }
  .grid:focus-visible { box-shadow: inset var(--focus-ring); }
  .space { position: relative; }
  .cell { position: absolute; left: 0; top: 0; width: var(--size); display: flex; flex-direction: column; align-items: center; gap: var(--space-1);
    cursor: default; user-select: none; -webkit-user-select: none; }
  .pic { position: relative; width: var(--size); height: var(--size); display: flex; align-items: center; justify-content: center;
    border-radius: var(--radius-md); background: var(--fill-quaternary); overflow: hidden; }
  .pic img { width: 100%; height: 100%; object-fit: cover; display: block; }
  .cell.on .pic { box-shadow: 0 0 0 3px var(--selection); }
  .name { max-width: 100%; padding: 1px var(--space-1); border-radius: var(--radius-xs); text-align: center; overflow: hidden;
    display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; overflow-wrap: anywhere; line-height: 1.25; }
  .cell.on .name { background: var(--selection); color: var(--on-accent); }
  .label { position: absolute; right: var(--space-1); bottom: var(--space-1); width: var(--space-3); height: var(--space-3); border-radius: var(--radius-capsule);
    box-shadow: 0 0 0 1.5px var(--control-bg); }
  .ph { width: 40%; height: 40%; border-radius: var(--radius-md); background: var(--fill-tertiary); }
</style>
