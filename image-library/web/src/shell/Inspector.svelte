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
  // 小圓環：每個類型一段弧（至少留一點寬度，太小的類型才看得到）
  const CIRC = 2 * Math.PI * 46;
  const arcs = $derived.by(() => {
    let start = 0;
    return kinds.map((k) => {
      const len = Math.max(kinds.length > 1 ? 1.5 : 0, (k.bytes / kindTotal) * CIRC - (kinds.length > 1 ? 1.5 : 0));
      const arc = { kind: k.kind, start, len };
      start += (k.bytes / kindTotal) * CIRC;
      return arc;
    });
  });
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
      <div class="donut">
        <svg viewBox="0 0 120 120" role="img" aria-label={t("info.byKind")}>
          <circle cx="60" cy="60" r="46" class="track" />
          {#each arcs as a (a.kind)}
            <circle cx="60" cy="60" r="46" class="arc" style:stroke="var(--kind-{a.kind === 'package' ? 'other' : a.kind})"
              stroke-dasharray="{a.len} {CIRC - a.len}" stroke-dashoffset={-a.start} transform="rotate(-90 60 60)" />
          {/each}
        </svg>
        <div class="center"><b class="mac-headline">{formatBytes(kindTotal)}</b><span class="mac-caption-1">{formatNumber(kinds.reduce((n, k) => n + k.files, 0))}</span></div>
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
  .donut { position: relative; width: 132px; margin: var(--space-2) auto var(--space-3); }
  .donut svg { display: block; width: 100%; }
  .donut circle { fill: none; stroke-width: 14; }
  .track { stroke: var(--fill-tertiary); }
  .center { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 1px; text-align: center; }
  .center span { color: var(--label-secondary); }
  ul { list-style: none; margin: var(--space-3) 0 0; padding: 0; display: flex; flex-direction: column; gap: var(--space-2); }
  li { display: flex; align-items: center; gap: var(--space-2); }
  .dot { width: var(--space-2); height: var(--space-2); border-radius: var(--radius-capsule); flex: none; }
  .name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .num { color: var(--label-secondary); font-feature-settings: "tnum"; flex: none; }
  .size { min-width: 64px; text-align: right; }
</style>
