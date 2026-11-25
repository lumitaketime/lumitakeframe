<script>
  /**
   * 圖像檢視：縮圖格狀。照片與影片顯示掃描時產生的小縮圖（不讀原檔），其他顯示類型圖示。
   * 只畫出看得到的幾列；每列高度固定、位置用 transform。
   */
  import KindIcon from "./KindIcon.svelte";
  import { handleViewKey } from "./keys.js";
  import { sectionOf } from "./sections.js";
  import { prefs } from "./prefs.svelte.js";
  import { thumbUrl } from "../lib/api.js";
  import { t, formatNumber } from "../i18n/index.svelte.js";

  let { source, sel, sections = null, onopen, onpreview, oncontext, ondragitem } = $props();

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
  // 每一段（沒有分組時整個清單就是一段）：從哪一個項目開始、有幾個、在畫面上的高度位置。分組時段前面有一列標題
  const HEAD = 34;
  const blocks = $derived.by(() => {
    const list = sections?.length ? sections : [{ start: 0, count: total, label: "" }];
    let y = PAD;
    return list.map((s) => {
      const head = sections?.length ? HEAD : 0;
      const b = { ...s, y, head, rows: Math.ceil(s.count / perRow) };
      y += head + b.rows * rowH;
      return b;
    });
  });
  const contentH = $derived(blocks.length ? blocks[blocks.length - 1].y + blocks[blocks.length - 1].head + blocks[blocks.length - 1].rows * rowH : PAD);
  /** 第 i 個項目在畫面上的位置 */
  function place(i) {
    const b = blocks[sections?.length ? sectionOf(blocks, i) : 0];
    const local = i - b.start;
    return { x: PAD + (local % perRow) * (size + GAP), y: b.y + b.head + Math.floor(local / perRow) * rowH };
  }
  // 畫面上的格子重複利用（同列表檢視）
  const slots = $derived((Math.ceil(height / rowH) + OVERSCAN * 2 + 2) * perRow);
  const view = $derived.by(() => {
    const top = scrollTop - OVERSCAN * rowH, bottom = scrollTop + height + OVERSCAN * rowH;
    const cells = [], heads = [];
    for (const b of blocks) {
      const end = b.y + b.head + b.rows * rowH;
      if (end < top || b.y > bottom) continue;
      if (b.head && b.y + b.head >= top) heads.push(b);
      const r0 = Math.max(0, Math.floor((top - b.y - b.head) / rowH));
      const r1 = Math.min(b.rows, Math.ceil((bottom - b.y - b.head) / rowH));
      for (let i = b.start + r0 * perRow; i < Math.min(b.start + b.count, b.start + r1 * perRow); i++) {
        const p = place(i);
        cells.push({ i, item: source.get(i), x: p.x, y: p.y });
      }
    }
    return { cells, heads };
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
    const top = place(f).y - PAD;
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
  <div class="space" style:height="{contentH + PAD}px">
    {#each view.heads as h (h.start)}
      <div class="ghead mac-callout" role="presentation" style:transform="translateY({h.y}px)">
        <b>{h.label}</b><span>{t("group.count", { count: formatNumber(h.count) })}</span>
      </div>
    {/each}
    {#each view.cells as { i, item, x, y } (i % slots)}
      <!-- svelte-ignore a11y_click_events_have_key_events -->
      <div class="cell" class:on={sel.has(i)} id="item-{i}" role="option" aria-selected={sel.has(i)} aria-setsize={total} aria-posinset={i + 1} tabindex="-1"
        style:transform="translate({x}px, {y}px)"
        onclick={(e) => sel.click(i, e)} ondblclick={() => onopen?.(i)}
          draggable={item?.type === "folder" || item?.type === "file" ? "true" : undefined} ondragstart={(e) => ondragitem?.(e, item)}
        oncontextmenu={(e) => { e.preventDefault(); sel.context(i); oncontext?.(e, i); }} title={item?.name}>
        <span class="pic">
          {#if !item}
            <i class="ph"></i>
          {:else if item.image_id}
            <img src={thumbUrl({ id: item.image_id })} alt="" loading="lazy" decoding="async" draggable="false" />
          {:else if item.cover}
            <!-- 文件封面（PDF 第一頁、電子書封面…）：掃描後在背景做好，存在 Re'memor 的資料目錄 -->
            <img class="cover" src={`/api/files/${item.id}/cover`} alt="" loading="lazy" decoding="async" draggable="false" />
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
  .ghead { position: absolute; left: var(--space-4); right: var(--space-4); top: 0; height: 26px; display: flex; align-items: flex-end; gap: var(--space-2);
    padding-bottom: var(--space-1); border-bottom: 1px solid var(--separator); color: var(--label-secondary); }
  .ghead b { color: var(--label-primary); font-weight: 600; }
  .cell { position: absolute; left: 0; top: 0; width: var(--size); display: flex; flex-direction: column; align-items: center; gap: var(--space-1);
    cursor: default; user-select: none; -webkit-user-select: none; }
  .pic { position: relative; width: var(--size); height: var(--size); display: flex; align-items: center; justify-content: center;
    border-radius: var(--radius-md); background: var(--fill-quaternary); overflow: hidden; }
  .pic img { width: 100%; height: 100%; object-fit: cover; display: block; }
  /* 文件封面：整頁看得到，不裁切；像一張紙放在格子裡 */
  .pic img.cover { width: auto; height: auto; max-width: 82%; max-height: 92%; object-fit: contain; border-radius: var(--radius-xs);
    box-shadow: 0 0 0 1px var(--separator), var(--shadow-knob); background: var(--bg-primary); }
  .cell.on .pic { box-shadow: 0 0 0 3px var(--selection); }
  .name { max-width: 100%; padding: 1px var(--space-1); border-radius: var(--radius-xs); text-align: center; overflow: hidden;
    display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; overflow-wrap: anywhere; line-height: 1.25; }
  .cell.on .name { background: var(--selection); color: var(--on-accent); }
  .label { position: absolute; right: var(--space-1); bottom: var(--space-1); width: var(--space-3); height: var(--space-3); border-radius: var(--radius-capsule);
    box-shadow: 0 0 0 1.5px var(--control-bg); }
  .ph { width: 40%; height: 40%; border-radius: var(--radius-md); background: var(--fill-tertiary); }
</style>
