<script>
  /**
   * 樹狀檢視：縮排的資料夾樹。每列右邊是總大小，和一條細條表示它佔上一層的比例。
   * 按三角形展開；⌥ 加按展開整個子樹；→ 展開、← 收合或回到上一層的資料夾。
   * 和列表一樣只畫看得到的列。
   */
  import { prettyName } from "../lib/names.js";
  import { Icon } from "../ui/index.js";
  import KindIcon from "./KindIcon.svelte";
  import CopiesMark from "./CopiesMark.svelte";
  import { handleViewKey } from "./keys.js";
  import { t, formatBytes, formatNumber } from "../i18n/index.svelte.js";

  let { source, sel, totalBytes = 0, onopen, onpreview, oncontext, ondragitem } = $props();

  const touch = typeof matchMedia === "function" && matchMedia("(pointer: coarse)").matches;
  const ROW = touch ? 44 : 28;
  const INDENT = 18;
  const OVERSCAN = 8;

  let body = $state();
  let scrollTop = $state(0);
  let height = $state(600);
  const total = $derived(source.state.total ?? 0);
  const first = $derived(Math.max(0, Math.floor(scrollTop / ROW) - OVERSCAN));
  const last = $derived(Math.min(total, Math.ceil((scrollTop + height) / ROW) + OVERSCAN));
  const slots = $derived(Math.ceil(height / ROW) + OVERSCAN * 2 + 2);
  const rows = $derived.by(() => {
    const out = [];
    for (let i = first; i < last; i++) out.push({ i, item: source.get(i), node: source.node(i) });
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
    const top = f * ROW;
    if (top < body.scrollTop) body.scrollTop = top;
    else if (top + ROW > body.scrollTop + body.clientHeight) body.scrollTop = top + ROW - body.clientHeight;
  });

  function toggle(e, i, item) {
    e?.stopPropagation();
    sel.moveTo(i, total); // 展開後底下的列會往下移，選取留在這一列
    if (e?.altKey && !source.isOpen(item)) source.expandAll(item);
    else source.toggle(item);
  }
  function onkeydown(e) {
    const i = sel.focus;
    const item = i >= 0 ? source.peek(i) : null;
    if (item && e.key === "ArrowRight" && item.type === "folder") {
      e.preventDefault();
      if (!source.isOpen(item)) toggle(e.altKey ? e : null, i, item);
      else sel.moveTo(i + 1, total);
      return;
    }
    if (item && e.key === "ArrowLeft") {
      e.preventDefault();
      if (item.type === "folder" && source.isOpen(item)) return toggle(null, i, item);
      const parent = source.node(i)?.parent; // 回到上一層的資料夾那一列
      if (parent) for (let k = i - 1; k >= 0; k--) if (source.peek(k) === parent) return sel.moveTo(k, total);
      return;
    }
    handleViewKey(e, { sel, total, perPage: Math.max(1, Math.floor(height / ROW) - 1), onopen, onpreview });
  }
  // 佔上一層的比例：最上層相對於目前資料夾的總大小，其餘相對於它所在的資料夾
  function share(item, node) {
    const base = node?.parent ? node.parent.size : totalBytes;
    return base > 0 && item.size ? Math.min(1, item.size / base) : 0;
  }
</script>

<div class="tree mac-body" style:--row="{ROW}px">
  <div class="head mac-callout" aria-hidden="true">
    <span class="hname">{t("view.col.name")}</span><span class="hshare">{t("view.col.share")}</span><span class="hsize">{t("view.col.size")}</span>
  </div>
  <!-- svelte-ignore a11y_no_noninteractive_tabindex -->
  <div class="body" bind:this={body} bind:clientHeight={height} {onscroll} {onkeydown} tabindex="0" role="tree" aria-multiselectable="true"
    aria-label={t("view.items")} aria-activedescendant={sel.focus >= 0 ? `item-${sel.focus}` : undefined}>
    <div class="space" style:height="{total * ROW}px">
      {#each rows as { i, item, node } (i % slots)}
        {@const isFolder = item?.type === "folder"}
        {@const opened = isFolder && source.isOpen(item)}
        {@const pct = item ? share(item, node) : 0}
        <!-- svelte-ignore a11y_click_events_have_key_events -->
        <div class="row" class:on={sel.has(i)} class:alt={i % 2 === 1} id="item-{i}" role="treeitem" aria-selected={sel.has(i)} tabindex="-1"
          aria-level={(node?.depth ?? 0) + 1} aria-expanded={isFolder ? opened : undefined} style:transform="translateY({i * ROW}px)"
          onclick={(e) => sel.click(i, e)} ondblclick={() => onopen?.(i)}
          oncontextmenu={(e) => { e.preventDefault(); sel.context(i); oncontext?.(e, i); }}
          draggable={isFolder || item?.type === "file" ? "true" : undefined} ondragstart={(e) => ondragitem?.(e, item)}>
          {#if item}
            <span class="name" style:padding-left="{(node?.depth ?? 0) * INDENT}px" title={item.name}>
              {#if isFolder}
                <button type="button" class="disc" class:open={opened} tabindex="-1" aria-label={opened ? t("view.collapse") : t("view.expand")}
                  onclick={(e) => toggle(e, i, item)} ondblclick={(e) => e.stopPropagation()}><Icon name="chevron-right" size={10} weight="bold" /></button>
              {:else}<span class="disc-space"></span>{/if}
              <KindIcon kind={isFolder ? "folder" : item.kind} />
              <span class="text">{prettyName(item.name)}</span>
              {#if item.label}<i class="label" style:background="var(--label-{item.label})" title={t(`label.${item.label}`)}></i>{/if}
              {#if item.copies}<CopiesMark copies={item.copies} />{/if}
              {#if isFolder && item.files != null}<span class="count mac-callout">{t("status.filesOnly", { files: formatNumber(item.files) })}</span>{/if}
            </span>
            <span class="share"><span class="bar" aria-hidden="true"><i style:width="{pct * 100}%"></i></span><span class="pct">{pct ? `${pct >= 0.995 ? 100 : (pct * 100).toFixed(pct < 0.1 ? 1 : 0)}%` : ""}</span></span>
            <span class="size">{item.size ? formatBytes(item.size) : "—"}</span>
          {:else}
            <span class="name"><i class="ph"></i></span>
          {/if}
        </div>
      {/each}
    </div>
  </div>
</div>

<style>
  .tree { display: flex; flex-direction: column; height: 100%; min-height: 0; color: var(--label-primary); --cols: minmax(220px, 1fr) 160px 90px; }
  .head { flex: none; display: grid; grid-template-columns: var(--cols); align-items: center; padding: 0 var(--space-5); min-height: var(--control-small);
    border-bottom: 1px solid var(--separator); color: var(--label-secondary); }
  .hsize { text-align: right; }
  .hshare { padding: 0 var(--space-2); }
  .body { flex: 1; min-height: 0; overflow-y: auto; overflow-x: hidden; position: relative; outline: none; overscroll-behavior: contain; }
  .body:focus-visible { box-shadow: inset var(--focus-ring); }
  .space { position: relative; }
  .row { position: absolute; left: var(--space-2); right: var(--space-2); top: 0; height: var(--row); display: grid; grid-template-columns: var(--cols);
    align-items: center; padding: 0 var(--space-3); border-radius: var(--radius-sm); cursor: default; user-select: none; -webkit-user-select: none; }
  .row.alt { background: var(--row-alt); }
  .row.on { background: var(--selection); color: var(--on-accent); }
  .name { display: flex; align-items: center; gap: var(--space-2); min-width: 0; }
  .text { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; min-width: 0; }
  .count { flex: none; color: var(--label-secondary); }
  .row.on .count, .row.on .size { color: inherit; }
  .disc, .disc-space { flex: none; width: 16px; height: 16px; }
  .disc { display: inline-flex; align-items: center; justify-content: center; border: 0; padding: 0; background: none; color: var(--label-secondary); cursor: pointer;
    border-radius: var(--radius-xs); transition: transform var(--dur-quick) var(--ease); }
  .disc.open { transform: rotate(90deg); }
  .row.on .disc { color: inherit; }
  /* 佔上一層的比例：細條＋百分比（數字讓比例不只靠長度判斷） */
  .share { display: flex; align-items: center; gap: var(--space-2); margin: 0 var(--space-2); min-width: 0; }
  .bar { flex: 1; display: block; height: 4px; border-radius: var(--radius-capsule); background: var(--fill-tertiary); overflow: hidden; }
  .bar i { display: block; height: 100%; border-radius: inherit; background: var(--accent); }
  .pct { flex: none; width: 3.2em; text-align: right; color: var(--label-secondary); font-feature-settings: "tnum"; }
  .row.on .bar { background: color-mix(in srgb, var(--on-accent) 30%, transparent); }
  .row.on .bar i { background: var(--on-accent); }
  .row.on .pct { color: inherit; }
  .size { text-align: right; color: var(--label-secondary); font-feature-settings: "tnum"; }
  .label { flex: none; width: var(--space-2); height: var(--space-2); border-radius: var(--radius-capsule); }
  .ph { display: block; width: 180px; height: var(--space-2); border-radius: var(--radius-capsule); background: var(--fill-tertiary); }
  .row.on :global(.kind) { color: inherit !important; }
  @media (prefers-reduced-motion: reduce) { .disc { transition: none; } }
</style>
