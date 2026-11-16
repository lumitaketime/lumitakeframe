<script>
  /**
   * 直欄檢視：一層一欄向右展開，最右邊一欄是選取項目的預覽。
   * 上下鍵在欄內移動；→ 進入資料夾、← 回上一層。按一下資料夾就往右展開下一欄。
   */
  import ColumnPane from "./ColumnPane.svelte";
  import KindIcon from "./KindIcon.svelte";
  import { handleViewKey } from "./keys.js";
  import { prefs, setColumnWidth } from "./prefs.svelte.js";
  import { createItemSource } from "../data/items.svelte.js";
  import { thumbUrl } from "../lib/api.js";
  import { t, formatBytes, formatDate, formatNumber } from "../i18n/index.svelte.js";

  let { root, path = "", source, sel, onnavigate, onopen, onpreview, oncontext, ondragitem } = $props();

  // 從最上層到目前資料夾，每一層一欄；前面幾欄各自讀自己的內容（讀過的留著，來回切換不重讀）
  const cache = new Map();
  const ancestors = $derived.by(() => {
    const parts = path ? path.split("/") : [];
    const out = [];
    for (let k = 0; k < parts.length; k++) {
      const p = parts.slice(0, k).join("/");
      const key = `${root}:${p}:${prefs.sort}:${prefs.desc}`;
      if (!cache.has(key)) {
        const src = createItemSource({ root, path: p }, prefs.sort, prefs.desc);
        src.start();
        cache.set(key, src);
      }
      out.push({ path: p, next: parts.slice(0, k + 1).join("/"), source: cache.get(key) });
    }
    return out;
  });
  const total = $derived(source.state.total ?? 0);
  const picked = $derived(sel.size === 1 ? source.get(sel.indexes()[0]) : null);

  let wrap = $state();
  let lastPane = $state();
  // 換資料夾後捲到最右邊，並把鍵盤焦點放在目前這一欄
  $effect(() => {
    path;
    ancestors.length;
    requestAnimationFrame(() => {
      if (wrap) wrap.scrollLeft = wrap.scrollWidth;
      if (document.activeElement === document.body || wrap?.contains(document.activeElement)) lastPane?.focus();
    });
  });

  const parentOf = (p) => (p.includes("/") ? p.slice(0, p.lastIndexOf("/")) : "");
  function pickLast(i, item, e) {
    if (item.type === "folder" && !e.metaKey && !e.ctrlKey && !e.shiftKey) return onnavigate?.(item.path);
    sel.click(i, e);
  }
  function onkeydown(e) {
    const item = sel.focus >= 0 ? source.peek(sel.focus) : null;
    if (e.key === "ArrowRight" && item?.type === "folder") {
      e.preventDefault();
      return onnavigate?.(item.path);
    }
    if (e.key === "ArrowLeft" && path) {
      e.preventDefault();
      return onnavigate?.(parentOf(path));
    }
    handleViewKey(e, { sel, total, onopen, onpreview });
  }
  function startResize(e) {
    e.preventDefault();
    const x0 = e.clientX;
    const w0 = prefs.columnWidth;
    const move = (ev) => setColumnWidth(w0 + (ev.clientX - x0));
    const up = () => {
      removeEventListener("pointermove", move);
      removeEventListener("pointerup", up);
    };
    addEventListener("pointermove", move);
    addEventListener("pointerup", up);
  }
</script>

<div class="columns" bind:this={wrap} style:--col="{prefs.columnWidth}px">
  {#each ancestors as a (a.path)}
    <div class="col">
      <ColumnPane source={a.source} activePath={a.next} label={a.path || t("view.items")} {ondragitem}
        onpick={(i, item) => onnavigate?.(item.type === "folder" ? item.path : a.path)}
        oncontext={() => {}} />
      <!-- svelte-ignore a11y_no_static_element_interactions -->
      <span class="grip" onpointerdown={startResize}></span>
    </div>
  {/each}
  <div class="col">
    <ColumnPane bind:this={lastPane} {source} {sel} focusable label={t("view.items")} {onkeydown} {ondragitem}
      onpick={pickLast} onopen={(i) => onopen?.(i)} oncontext={(e, i) => { sel.context(i); oncontext?.(e, i); }} />
    <!-- svelte-ignore a11y_no_static_element_interactions -->
    <span class="grip" onpointerdown={startResize}></span>
  </div>
  <aside class="preview mac-body" aria-label={t("view.preview")}>
    {#if picked}
      <div class="pic">
        {#if picked.image_id}<img src={thumbUrl({ id: picked.image_id })} alt="" draggable="false" />
        {:else}<KindIcon kind={picked.type === "folder" ? "folder" : picked.kind} size={72} />{/if}
      </div>
      <h3 class="mac-headline">{picked.name}</h3>
      <dl class="mac-callout">
        <div><dt>{t("info.kind")}</dt><dd>{picked.type === "folder" ? t("info.kind.folder") : t(`kind.${picked.kind}`)}</dd></div>
        {#if picked.size}<div><dt>{t("info.size")}</dt><dd>{formatBytes(picked.size)}</dd></div>{/if}
        {#if picked.type === "folder" && picked.files != null}<div><dt>{t("info.files")}</dt><dd>{formatNumber(picked.files)}</dd></div>{/if}
        {#if picked.mtime}<div><dt>{t("info.modified")}</dt><dd>{formatDate(picked.mtime)}</dd></div>{/if}
      </dl>
    {:else if total !== null}
      <p class="mac-callout hint">{sel.size > 1 ? t("view.selected", { count: formatNumber(sel.size) }) : t("view.count", { count: formatNumber(total) })}</p>
    {/if}
  </aside>
</div>

<style>
  .columns { display: flex; height: 100%; min-height: 0; overflow-x: auto; overflow-y: hidden; overscroll-behavior: contain; }
  .col { position: relative; flex: none; width: var(--col); height: 100%; border-right: 1px solid var(--separator); }
  .grip { position: absolute; top: 0; bottom: 0; right: -4px; width: 8px; cursor: col-resize; z-index: 2; touch-action: none; }
  .preview { flex: 1; min-width: 240px; padding: var(--space-5); overflow-y: auto; display: flex; flex-direction: column; align-items: center; gap: var(--space-3);
    color: var(--label-primary); }
  .pic { width: min(220px, 100%); aspect-ratio: 1; display: flex; align-items: center; justify-content: center; border-radius: var(--radius-md);
    background: var(--fill-quaternary); overflow: hidden; flex: none; }
  .pic img { width: 100%; height: 100%; object-fit: contain; }
  h3 { margin: 0; text-align: center; overflow-wrap: anywhere; }
  dl { margin: 0; width: min(260px, 100%); display: flex; flex-direction: column; gap: var(--space-1); }
  dl div { display: flex; justify-content: space-between; gap: var(--space-3); }
  dt { color: var(--label-secondary); }
  dd { margin: 0; text-align: right; }
  .hint { color: var(--label-secondary); margin: auto; }
</style>
