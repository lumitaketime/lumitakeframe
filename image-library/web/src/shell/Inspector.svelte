<script>
  /** 資訊欄：目前位置（硬碟或資料夾）的資訊；沒有特定位置時顯示整個資料庫的摘要。內容不透明，不用玻璃。 */
  import { t, formatNumber, formatBytes } from "../i18n/index.svelte.js";
  import { catalog, catalogTotals } from "../data/catalog.svelte.js";

  let { info = null } = $props();
  const totals = $derived(catalogTotals());
  const shown = $derived(info || {
    title: t("info.library"), kind: "",
    rows: [
      [t("info.files"), formatNumber(totals.files)],
      [t("info.size"), formatBytes(totals.bytes)],
      [t("info.drives"), t("drive.count", { count: formatNumber(catalog.drives.length), online: formatNumber(catalog.drives.filter((d) => d.online).length) })],
    ],
    kinds: catalog.kinds,
  });
  const kinds = $derived((shown.kinds || []).filter((k) => k.files > 0).sort((a, b) => b.bytes - a.bytes));
  const kindTotal = $derived(kinds.reduce((n, k) => n + k.bytes, 0) || 1);
</script>

<aside class="inspector" aria-label={t("info.title")}>
  <header>
    <h2 class="mac-headline">{shown.title}</h2>
    {#if shown.kind}<p class="mac-callout kind">{shown.kind}</p>{/if}
  </header>
  {#if !info && catalog.loaded && !totals.files}
    <p class="mac-body empty">{t("info.empty")}</p>
  {:else}
    <dl class="mac-body">
      {#each shown.rows.filter((r) => r[1]) as [label, value] (label)}
        <div><dt>{label}</dt><dd>{value}</dd></div>
      {/each}
    </dl>
    {#if kinds.length}
      <h3 class="mac-subheadline">{t("info.byKind")}</h3>
      <div class="bar" aria-hidden="true">
        {#each kinds as k (k.kind)}<i style:width="{(k.bytes / kindTotal) * 100}%" style:background="var(--kind-{k.kind === 'package' ? 'other' : k.kind})"></i>{/each}
      </div>
      <ul class="mac-body">
        {#each kinds as k (k.kind)}
          <li>
            <i class="dot" style:background="var(--kind-{k.kind === 'package' ? 'other' : k.kind})" aria-hidden="true"></i>
            <span class="name">{t(`kind.${k.kind}`)}</span>
            <span class="num">{formatNumber(k.files)}</span>
            <span class="num size">{formatBytes(k.bytes)}</span>
          </li>
        {/each}
      </ul>
    {/if}
  {/if}
</aside>

<style>
  .inspector { box-sizing: border-box; width: 100%; height: 100%; overflow-y: auto; padding: var(--space-4); background: var(--control-bg); color: var(--label-primary); }
  header { padding-bottom: var(--space-3); border-bottom: 1px solid var(--separator); }
  h2 { margin: 0; overflow-wrap: anywhere; }
  .kind { margin: 2px 0 0; color: var(--label-secondary); }
  .empty { color: var(--label-secondary); }
  dl { margin: var(--space-3) 0 0; display: flex; flex-direction: column; gap: var(--space-2); }
  dl div { display: flex; gap: var(--space-3); justify-content: space-between; }
  dt { color: var(--label-secondary); flex: none; }
  dd { margin: 0; text-align: right; overflow-wrap: anywhere; min-width: 0; }
  h3 { margin: var(--space-5) 0 var(--space-2); color: var(--label-secondary); font-weight: 600; }
  .bar { display: flex; height: var(--space-2); border-radius: var(--radius-capsule); overflow: hidden; gap: 1px; background: var(--fill-quaternary); }
  .bar i { display: block; min-width: 2px; }
  ul { list-style: none; margin: var(--space-3) 0 0; padding: 0; display: flex; flex-direction: column; gap: var(--space-2); }
  li { display: flex; align-items: center; gap: var(--space-2); }
  .dot { width: var(--space-2); height: var(--space-2); border-radius: var(--radius-capsule); flex: none; }
  .name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .num { color: var(--label-secondary); font-feature-settings: "tnum"; flex: none; }
  .size { min-width: 64px; text-align: right; }
</style>
