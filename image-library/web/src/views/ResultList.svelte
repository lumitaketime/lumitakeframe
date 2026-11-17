<script>
  /**
   * 搜尋結果清單：每一筆三行——檔名（命中的字加粗）與命中的地方、命中的段落、所在位置。
   * 右邊是大小與修改日期。和列表檢視一樣只畫出看得到的列，列高固定，捲動時重複利用 DOM 節點。
   * 命中的字用粗體標示，不只靠顏色（手冊：全文檢索的結果）。
   */
  import { Icon } from "../ui/index.js";
  import KindIcon from "./KindIcon.svelte";
  import { handleViewKey } from "./keys.js";
  import { t, formatBytes, formatDate } from "../i18n/index.svelte.js";

  let { source, sel, onopen, onpreview, oncontext } = $props();

  const touch = typeof matchMedia === "function" && matchMedia("(pointer: coarse)").matches;
  const ROW = touch ? 76 : 66;
  const OVERSCAN = 6;

  let body = $state();
  let scrollTop = $state(0);
  let height = $state(600);
  const total = $derived(source.state.total ?? 0);
  const first = $derived(Math.max(0, Math.floor(scrollTop / ROW) - OVERSCAN));
  const last = $derived(Math.min(total, Math.ceil((scrollTop + height) / ROW) + OVERSCAN));
  const slots = $derived(Math.ceil(height / ROW) + OVERSCAN * 2 + 2);
  const rows = $derived.by(() => {
    const out = [];
    for (let i = first; i < last; i++) out.push({ i, item: source.get(i) });
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
  function onkeydown(e) {
    handleViewKey(e, { sel, total, perPage: Math.max(1, Math.floor(height / ROW) - 1), onopen, onpreview });
  }
  // 所在位置：硬碟 › 資料夾來源（和硬碟同名就省略）› 資料夾
  function where(item) {
    return [item.drive, item.root !== item.drive ? item.root : "", ...(item.folder ? item.folder.split("/") : [])].filter(Boolean).join(" › ");
  }
</script>

<!-- svelte-ignore a11y_no_noninteractive_tabindex -->
<div class="results mac-body" bind:this={body} bind:clientHeight={height} {onscroll} {onkeydown} tabindex="0" style:--row="{ROW}px"
  role="listbox" aria-multiselectable="true" aria-label={t("find.results")}
  aria-activedescendant={sel.focus >= 0 ? `hit-${sel.focus}` : undefined}>
  <div class="space" style:height="{total * ROW}px">
    {#each rows as { i, item } (i % slots)}
      <!-- svelte-ignore a11y_click_events_have_key_events -->
      <div class="row" class:on={sel.has(i)} id="hit-{i}" role="option" aria-selected={sel.has(i)} aria-setsize={total} aria-posinset={i + 1}
        tabindex="-1" style:transform="translateY({i * ROW}px)"
        onclick={(e) => sel.click(i, e)} ondblclick={() => onopen?.(i)}
        oncontextmenu={(e) => { e.preventDefault(); sel.context(i); oncontext?.(e, i); }}>
        {#if item}
          <span class="icon"><KindIcon kind={item.kind} size={22} /></span>
          <span class="main">
            <span class="line name" title={item.name}>
              <span class="text">{#each item.name_parts as p, k (k)}{#if p.hit}<b>{p.text}</b>{:else}{p.text}{/if}{/each}</span>
              {#if item.label}<i class="label" style:background="var(--label-{item.label})" title={t(`label.${item.label}`)}></i>{/if}
              {#if item.match !== "filter"}<span class="badge mac-caption-1">{t(`find.match.${item.match}`)}</span>{/if}
            </span>
            {#if item.snippet?.length}
              <span class="line snippet mac-callout">{#each item.snippet as p, k (k)}{#if p.hit}<b>{p.text}</b>{:else}{p.text}{/if}{/each}</span>
            {/if}
            <span class="line where mac-callout" title={where(item)}><Icon name="folder" size={11} /><span class="text">{where(item)}</span></span>
          </span>
          <span class="meta mac-callout">
            <span>{item.size ? formatBytes(item.size) : "—"}</span>
            <span>{item.mtime ? formatDate(item.mtime) : ""}</span>
          </span>
        {:else}
          <span class="icon"><i class="ph sq"></i></span>
          <span class="main"><i class="ph"></i><i class="ph short"></i></span>
        {/if}
      </div>
    {/each}
  </div>
</div>

<style>
  .results { height: 100%; min-height: 0; overflow-y: auto; overflow-x: hidden; position: relative; outline: none; overscroll-behavior: contain; color: var(--label-primary); }
  .results:focus-visible { box-shadow: inset var(--focus-ring); }
  .space { position: relative; }
  .row { position: absolute; left: var(--space-2); right: var(--space-2); top: 0; height: calc(var(--row) - 2px); display: flex; align-items: center; gap: var(--space-3);
    padding: 0 var(--space-3); border-radius: var(--radius-md); cursor: default; user-select: none; -webkit-user-select: none; }
  .row:hover { background: var(--row-alt); }
  .row.on { background: var(--selection); color: var(--on-accent); }
  .icon { flex: none; display: flex; width: 28px; justify-content: center; }
  .main { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 1px; }
  .line { display: flex; align-items: center; gap: var(--space-2); min-width: 0; white-space: nowrap; overflow: hidden; }
  .text { overflow: hidden; text-overflow: ellipsis; min-width: 0; }
  .name b, .snippet b { font-weight: 700; color: var(--label-primary); }
  .snippet { display: block; text-overflow: ellipsis; color: var(--label-secondary); }
  /* 位置用次要文字色（第三層灰在淺色模式太淡，看不清楚），前面加資料夾圖示和段落區分 */
  .where { gap: var(--space-1); color: var(--label-secondary); }
  .where :global(svg) { flex: none; opacity: .8; }
  .badge { flex: none; padding: 0 var(--space-2); border-radius: var(--radius-capsule); background: var(--fill-tertiary); color: var(--label-secondary); }
  .label { flex: none; width: var(--space-2); height: var(--space-2); border-radius: var(--radius-capsule); }
  .meta { flex: none; display: flex; flex-direction: column; align-items: flex-end; gap: 2px; color: var(--label-secondary); font-feature-settings: "tnum"; }
  .row.on .snippet, .row.on .where, .row.on .meta, .row.on b, .row.on .badge { color: inherit; }
  .row.on .badge { background: var(--fill-secondary); }
  .row.on :global(.kind) { color: inherit !important; }
  .ph { display: block; width: 50%; height: var(--space-2); margin: var(--space-1) 0; border-radius: var(--radius-capsule); background: var(--fill-tertiary); }
  .ph.short { width: 30%; }
  .ph.sq { width: 22px; height: 22px; border-radius: var(--radius-xs); }
  @media (max-width: 600px) { .meta { display: none; } }
</style>
