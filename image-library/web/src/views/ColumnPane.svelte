<script>
  /** 直欄檢視的一欄：一個資料夾的內容，只畫看得到的列。activePath＝往下一欄走的那個資料夾（反白表示路徑）。 */
  import { Icon } from "../ui/index.js";
  import KindIcon from "./KindIcon.svelte";
  import { t } from "../i18n/index.svelte.js";

  let { source, sel = null, activePath = null, label = "", onpick, onopen, oncontext, ondragitem, onkeydown, focusable = false } = $props();

  const touch = typeof matchMedia === "function" && matchMedia("(pointer: coarse)").matches;
  const ROW = touch ? 44 : 28;
  const OVERSCAN = 6;
  let body = $state();
  let scrollTop = $state(0);
  let height = $state(500);
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
    const f = sel ? sel.focus : -1;
    if (f < 0 || !body) return;
    const top = f * ROW;
    if (top < body.scrollTop) body.scrollTop = top;
    else if (top + ROW > body.scrollTop + body.clientHeight) body.scrollTop = top + ROW - body.clientHeight;
  });
  export function focus() {
    body?.focus();
  }
</script>

<!-- svelte-ignore a11y_no_noninteractive_tabindex -->
<div class="pane mac-body" bind:this={body} bind:clientHeight={height} {onscroll} {onkeydown} tabindex={focusable ? 0 : -1} role="listbox" aria-label={label}
  aria-multiselectable={sel ? "true" : undefined} aria-activedescendant={sel && sel.focus >= 0 ? `item-${sel.focus}` : undefined} style:--row="{ROW}px">
  <div class="space" style:height="{total * ROW}px">
    {#each rows as { i, item } (i % slots)}
      {@const on = sel ? sel.has(i) : false}
      {@const trail = !!item && item.type === "folder" && item.path === activePath}
      <!-- svelte-ignore a11y_click_events_have_key_events -->
      <div class="row" class:on class:trail id={sel ? `item-${i}` : undefined} role="option" aria-selected={on || trail} tabindex="-1" style:transform="translateY({i * ROW}px)"
        onclick={(e) => item && onpick?.(i, item, e)} ondblclick={() => item && onopen?.(i, item)}
        oncontextmenu={(e) => { if (!item) return; e.preventDefault(); oncontext?.(e, i, item); }}
        draggable={item?.type === "folder" ? "true" : undefined} ondragstart={(e) => ondragitem?.(e, item)} title={item?.name}>
        {#if item}
          <KindIcon kind={item.icon || (item.type === "folder" ? "folder" : item.kind)} />
          <span class="text">{item.name}</span>
          {#if item.label}<i class="label" style:background="var(--label-{item.label})" title={t(`label.${item.label}`)}></i>{/if}
          {#if item.type === "folder"}<Icon name="chevron-right" size={9} weight="bold" class="go" />{/if}
        {:else}<i class="ph"></i>{/if}
      </div>
    {/each}
  </div>
</div>

<style>
  .pane { height: 100%; overflow-y: auto; overflow-x: hidden; position: relative; outline: none; overscroll-behavior: contain; color: var(--label-primary); }
  .pane:focus-visible { box-shadow: inset var(--focus-ring); }
  .space { position: relative; }
  .row { position: absolute; left: var(--space-1); right: var(--space-1); top: 0; height: var(--row); display: flex; align-items: center; gap: var(--space-2);
    padding: 0 var(--space-2); border-radius: var(--radius-sm); cursor: default; user-select: none; -webkit-user-select: none; }
  .row.trail { background: var(--selection-muted); }
  .row.on { background: var(--selection); color: var(--on-accent); }
  .text { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .row :global(.go) { flex: none; color: var(--label-tertiary); }
  .row.on :global(.go), .row.on :global(.kind) { color: inherit !important; }
  .label { flex: none; width: var(--space-2); height: var(--space-2); border-radius: var(--radius-capsule); }
  .ph { display: block; width: 60%; height: var(--space-2); border-radius: var(--radius-capsule); background: var(--fill-tertiary); }
</style>
