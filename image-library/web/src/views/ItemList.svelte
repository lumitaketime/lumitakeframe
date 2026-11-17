<script>
  /**
   * 列表檢視：一列一個項目，欄位可排序、可調寬、可顯示或隱藏。
   * 只畫出看得到的列（上下各多畫幾列），列高固定、位置用 transform，十萬個項目也只有幾十個 DOM 節點。
   */
  import { Icon } from "../ui/index.js";
  import KindIcon from "./KindIcon.svelte";
  import { handleViewKey } from "./keys.js";
  import { listLayout } from "./sections.js";
  import { prefs, COLUMNS, setSort, setWidth } from "./prefs.svelte.js";
  import { t, formatBytes, formatDate, formatNumber } from "../i18n/index.svelte.js";

  let { source, sel, sections = null, totalBytes = 0, showDrive = false, driveName = () => "", onopen, onpreview, oncontext, ondragitem, onheadercontext } = $props();

  const touch = typeof matchMedia === "function" && matchMedia("(pointer: coarse)").matches;
  const ROW = touch ? 44 : 28;
  const OVERSCAN = 8;

  let body = $state();
  let scrollTop = $state(0);
  let height = $state(600);
  const total = $derived(source.state.total ?? 0);
  // 分組時每一段前面多一列標題（見 sections.js）
  const layout = $derived(listLayout(sections, total));
  const first = $derived(Math.max(0, Math.floor(scrollTop / ROW) - OVERSCAN));
  const last = $derived(Math.min(layout.rows, Math.ceil((scrollTop + height) / ROW) + OVERSCAN));
  // 畫面上的列重複利用：捲動時同一個 DOM 節點換內容與位置，不必每次刪掉再建（key 用「第幾個除以格數的餘數」）
  const slots = $derived(Math.ceil(height / ROW) + OVERSCAN * 2 + 2);
  const rows = $derived.by(() => {
    const out = [];
    for (let r = first; r < last; r++) {
      const at = layout.at(r);
      out.push(at.section ? { r, section: at.section } : { r, i: at.i, item: source.get(at.i) });
    }
    return out;
  });
  const columns = $derived(COLUMNS.filter((c) => c === "name" || (!prefs.hidden.includes(c) && (c !== "drive" || showDrive))));
  const template = $derived(columns.map((c) => (c === "name" ? "minmax(180px, 1fr)" : `${prefs.widths[c]}px`)).join(" "));

  // 捲動期間用 requestAnimationFrame 合併更新，不在每個 scroll 事件都重算
  let raf = 0;
  function onscroll() {
    if (raf) return;
    raf = requestAnimationFrame(() => {
      raf = 0;
      if (body) scrollTop = body.scrollTop;
    });
  }
  // 鍵盤移動時，把目前的項目捲進畫面
  $effect(() => {
    const f = sel.focus;
    if (f < 0 || !body) return;
    const top = layout.rowOf(f) * ROW;
    if (top < body.scrollTop) body.scrollTop = top;
    else if (top + ROW > body.scrollTop + body.clientHeight) body.scrollTop = top + ROW - body.clientHeight;
  });

  function onkeydown(e) {
    handleViewKey(e, { sel, total, perPage: Math.max(1, Math.floor(height / ROW) - 1), onopen, onpreview });
  }
  function kindLabel(item) {
    return item.type === "folder" ? t("info.kind.folder") : t(`kind.${item.kind}`);
  }
  function startResize(e, col) {
    e.preventDefault();
    e.stopPropagation();
    const x0 = e.clientX;
    const w0 = prefs.widths[col];
    const move = (ev) => setWidth(col, w0 + (ev.clientX - x0));
    const up = () => {
      removeEventListener("pointermove", move);
      removeEventListener("pointerup", up);
    };
    addEventListener("pointermove", move);
    addEventListener("pointerup", up);
  }
</script>

<div class="list mac-body" style:--cols={template} style:--row="{ROW}px">
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div class="head mac-callout" oncontextmenu={(e) => { e.preventDefault(); onheadercontext?.(e); }}>
    {#each columns as c (c)}
      <div class="hcell" class:num={c === "size"}>
        <button type="button" class="hbtn" onclick={() => setSort(c === "drive" ? "name" : c)} disabled={c === "drive"}
          aria-label={t(`view.col.${c}`)} aria-pressed={prefs.sort === c}>
          <span>{t(`view.col.${c}`)}</span>
          {#if prefs.sort === c}<Icon name={prefs.desc ? "sort-down" : "sort-up"} size={11} weight="bold" />{/if}
        </button>
        {#if c !== "name"}
          <!-- svelte-ignore a11y_no_static_element_interactions -->
          <span class="grip" onpointerdown={(e) => startResize(e, c)}></span>
        {/if}
      </div>
    {/each}
  </div>
  <!-- svelte-ignore a11y_no_noninteractive_tabindex -->
  <div class="body" bind:this={body} bind:clientHeight={height} {onscroll} {onkeydown} tabindex="0"
    role="listbox" aria-multiselectable="true" aria-label={t("view.items")}
    aria-activedescendant={sel.focus >= 0 ? `item-${sel.focus}` : undefined}>
    <div class="space" style:height="{layout.rows * ROW}px">
      {#each rows as { r, i, item, section } (r % slots)}
        {#if section}
          <div class="ghead mac-callout" role="presentation" style:transform="translateY({r * ROW}px)">
            <b>{section.label}</b><span>{t("group.count", { count: formatNumber(section.count) })}</span>
          </div>
        {:else}
        <!-- svelte-ignore a11y_click_events_have_key_events -->
        <div class="row" class:on={sel.has(i)} class:alt={i % 2 === 1} id="item-{i}" role="option" aria-selected={sel.has(i)}
          aria-setsize={total} aria-posinset={i + 1} tabindex="-1" style:transform="translateY({r * ROW}px)"
          onclick={(e) => sel.click(i, e)} ondblclick={() => onopen?.(i)}
          draggable={item?.type === "folder" ? "true" : undefined} ondragstart={(e) => ondragitem?.(e, item)}
          oncontextmenu={(e) => { e.preventDefault(); sel.context(i); oncontext?.(e, i); }}>
          {#if item}
            {#each columns as c (c)}
              {#if c === "name"}
                <span class="cell name" title={item.name}>
                  <KindIcon kind={item.icon || (item.type === "folder" ? "folder" : item.kind)} />
                  <span class="text">{item.name}</span>
                  {#if item.label}<i class="label" style:background="var(--label-{item.label})" title={t(`label.${item.label}`)}></i>{/if}
                  {#if item.note}<span class="note mac-callout">{item.note}</span>{/if}
                </span>
              {:else if c === "size"}
                <span class="cell num">
                  {item.size ? formatBytes(item.size) : "—"}
                  {#if totalBytes > 0 && item.size}<i class="share" style:width="{Math.min(100, (item.size / totalBytes) * 100)}%" aria-hidden="true"></i>{/if}
                </span>
              {:else if c === "kind"}
                <span class="cell">{item.kindLabel || kindLabel(item)}</span>
              {:else if c === "mtime"}
                <span class="cell">{item.mtime ? formatDate(item.mtime) : "—"}</span>
              {:else}
                <span class="cell">{driveName(item)}</span>
              {/if}
            {/each}
          {:else}
            <span class="cell"><i class="ph"></i></span>
          {/if}
        </div>
      {/if}
      {/each}
    </div>
  </div>
</div>

<style>
  .list { display: flex; flex-direction: column; height: 100%; min-height: 0; color: var(--label-primary); }
  .head { flex: none; display: grid; grid-template-columns: var(--cols); padding: 0 var(--space-3); min-height: var(--control-small);
    border-bottom: 1px solid var(--separator); color: var(--label-secondary); background: var(--control-bg); }
  .hcell { position: relative; display: flex; align-items: stretch; min-width: 0; }
  .hbtn { flex: 1; min-width: 0; display: flex; align-items: center; gap: var(--space-1); padding: 0 var(--space-2); border: 0; background: none;
    color: inherit; font: inherit; cursor: pointer; text-align: left; border-radius: var(--radius-xs); }
  .hbtn span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .hbtn:hover:not(:disabled) { color: var(--label-primary); }
  .hbtn:disabled { cursor: default; }
  .hbtn[aria-pressed="true"] { color: var(--label-primary); font-weight: 600; }
  .hcell.num .hbtn { justify-content: flex-end; }
  .grip { position: absolute; left: -4px; top: 4px; bottom: 4px; width: 8px; cursor: col-resize; touch-action: none; }
  .grip::after { content: ""; position: absolute; left: 3px; top: 0; bottom: 0; width: 1px; background: var(--separator); }

  .body { flex: 1; min-height: 0; overflow-y: auto; overflow-x: hidden; position: relative; outline: none; overscroll-behavior: contain; }
  .body:focus-visible { box-shadow: inset var(--focus-ring); }
  .space { position: relative; }
  .row { position: absolute; left: var(--space-2); right: var(--space-2); top: 0; height: var(--row); display: grid; grid-template-columns: var(--cols);
    align-items: center; padding: 0 var(--space-1); border-radius: var(--radius-sm); cursor: default; user-select: none; -webkit-user-select: none; }
  .row.alt { background: var(--row-alt); }
  /* 分組的標題列 */
  .ghead { position: absolute; left: var(--space-2); right: var(--space-2); top: 0; height: var(--row); display: flex; align-items: flex-end; gap: var(--space-2);
    padding: 0 var(--space-3) var(--space-1); border-bottom: 1px solid var(--separator); color: var(--label-secondary); }
  .ghead b { color: var(--label-primary); font-weight: 600; }
  .row.on { background: var(--selection); color: var(--on-accent); }
  .row.on .cell, .row.on .note { color: inherit; }
  .cell { min-width: 0; padding: 0 var(--space-2); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--label-secondary); }
  .cell.name { display: flex; align-items: center; gap: var(--space-2); color: var(--label-primary); }
  .cell.num { position: relative; text-align: right; font-feature-settings: "tnum"; }
  /* 大小欄底下的比例條：這個項目佔目前資料夾的多少 */
  .share { position: absolute; right: var(--space-2); bottom: 1px; max-width: calc(100% - var(--space-4)); height: 2px; border-radius: var(--radius-capsule); background: var(--accent); opacity: .55; }
  .row.on .share { background: var(--on-accent); }
  .text { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; min-width: 0; }
  .label { flex: none; width: var(--space-2); height: var(--space-2); border-radius: var(--radius-capsule); }
  .note { flex: none; color: var(--label-secondary); }
  .ph { display: block; width: 40%; height: var(--space-2); border-radius: var(--radius-capsule); background: var(--fill-tertiary); }
  .row.on :global(.kind) { color: inherit !important; }
</style>
