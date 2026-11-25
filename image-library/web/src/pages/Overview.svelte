<script>
  /**
   * 總覽：打開 App 先看到的一頁。
   * - 你的硬碟：總共多少、每種類型佔多少、幾顆接著。
   * - 需要注意：健康檢查有狀況、很久沒掃、沒掃完、等你確認的事。
   * - 可以省下的空間：確認過的重複檔案。
   * - 淘汰檢查：每顆硬碟有多少只在那一顆上（只用算好的結果，不在這裡重算）。
   * - 最近新增：這七天新掃到的檔案。
   * - 分類：每一類有多少。
   * 全部只讀目錄，硬碟沒接上也看得到。
   */
  import { Button, Icon, ProgressIndicator } from "../ui/index.js";
  import KindIcon from "../views/KindIcon.svelte";
  import { catalog, loadCatalog, catalogTotals } from "../data/catalog.svelte.js";
  import { loadDupesSummary } from "../data/dupes.js";
  import { api, thumbUrl } from "../lib/api.js";
  import { categoryName, CATEGORY_ICONS } from "../data/category.svelte.js";
  import { setFrame } from "../shell/frame.svelte.js";
  import { t, formatNumber, formatBytes, formatDate } from "../i18n/index.svelte.js";
  import { app } from "../lib/state.svelte.js";
  import { link, navigate } from "../lib/router.svelte.js";
  import { prettyName } from "../lib/names.js";

  let ov = $state(null);
  let dupes = $state(null);
  let error = $state("");
  let broken = $state(new Set()); // 縮圖讀不到的（例如照片還沒做縮圖）：改顯示類型圖示
  function load() {
    api("/api/overview", { quiet: true }).then((d) => { ov = d; error = ""; }).catch((e) => (error = e.message));
    loadDupesSummary().then((d) => (dupes = d)).catch(() => {});
    if (!catalog.loaded) loadCatalog();
  }
  $effect(() => {
    app.refreshKey;
    load();
  });
  $effect(() => {
    setFrame({ crumbs: [], status: "", location: null, info: null });
  });

  const GROUP = { raw: "photo", package: "other" };
  const totals = $derived(catalogTotals());
  const online = $derived(catalog.drives.filter((d) => d.online).length);
  const kinds = $derived.by(() => {
    const sums = {};
    for (const k of catalog.kinds) {
      const g = GROUP[k.kind] || k.kind;
      sums[g] = sums[g] || { kind: g, files: 0, bytes: 0 };
      sums[g].files += k.files;
      sums[g].bytes += k.bytes;
    }
    return Object.values(sums).filter((k) => k.bytes > 0).sort((a, b) => b.bytes - a.bytes);
  });
  const cats = $derived(catalog.categories.filter((c) => c.top > 0).sort((a, b) => b.bytes - a.bytes).slice(0, 8));
  const releasable = $derived(dupes ? (dupes.files?.releasable || 0) : 0);
  const unchecked = $derived(dupes ? (dupes.plan?.small?.files || 0) + (dupes.plan?.large?.files || 0) : 0);
  const job = $derived(app.server?.jobs?.current || null);
  const pct = (part, whole) => (whole ? Math.max(0, Math.min(100, (part / whole) * 100)) : 0);
  const attentionText = (a) => t(`ov.att.${a.kind}`, { name: a.name || "", n: formatNumber(a.n || 0), detail: a.detail || "",
    date: a.date ? formatDate(new Date(a.date)) : "" });
  const ATT_ICON = { health: "exclamation-triangle", never: "external-drive", partial: "clock", stale: "clock", pending: "trash", review: "exclamation-triangle", plans: "sparkles" };
  const fileHref = (f) => `/folders/${f.root_id}${f.folder ? `?path=${encodeURIComponent(f.folder)}` : ""}`;
</script>

<div class="ov">
  <header class="hero">
    <div>
      <h1 class="mac-large-title">{t("ov.title")}</h1>
      <p class="mac-body sub">{t("ov.lead", { drives: formatNumber(catalog.drives.length), online: formatNumber(online), files: formatNumber(totals.files), size: formatBytes(totals.bytes) || "0 KB" })}</p>
    </div>
    {#if job}
      <a class="job mac-callout" href="/activity" use:link>
        <ProgressIndicator kind="circular" size="small" value={job.total ? job.done / job.total : undefined} label={job.label} />
        <span>{job.label}{job.message ? `：${job.message}` : ""}</span>
      </a>
    {/if}
  </header>

  {#if error}
    <p class="mac-body err" role="alert">{error} <Button size="small" variant="bordered" onclick={load}>{t("view.retry")}</Button></p>
  {/if}

  {#if !catalog.drives.length && catalog.loaded}
    <section class="card empty">
      <Icon name="external-drive" size={28} />
      <h2 class="mac-title-3">{t("ov.noDrives")}</h2>
      <p class="mac-body sub">{t("ov.noDrivesHint")}</p>
      <Button variant="borderedProminent" onclick={() => navigate("/drives")}>{t("ov.toDrives")}</Button>
    </section>
  {:else}
    <section class="card wide">
      <h2 class="mac-headline">{t("ov.space")}</h2>
      <div class="bar" role="img" aria-label={kinds.map((k) => `${t(`kind.${k.kind}`)} ${formatBytes(k.bytes)}`).join("，")}>
        {#each kinds as k (k.kind)}<i style:width="{Math.max(0.6, pct(k.bytes, totals.bytes))}%" style:background="var(--kind-{k.kind})"></i>{/each}
      </div>
      <ul class="legend mac-callout">
        {#each kinds as k (k.kind)}
          <li><a href={`/kind/${k.kind}`} use:link><i class="dot" style:background="var(--kind-{k.kind})" aria-hidden="true"></i>{t(`kind.${k.kind}`)}</a>
            <span class="sub">{formatBytes(k.bytes)} · {formatNumber(k.files)}</span></li>
        {/each}
      </ul>
      <ul class="drives mac-callout">
        {#each catalog.drives as d (d.key)}
          <li>
            <Icon name={d.online ? "external-drive-fill" : "external-drive"} size={15} />
            <a href={`/folders/${d.roots[0]?.id}`} use:link class="dname">{d.name}</a>
            <span class="sub">{formatBytes(d.bytes) || "0 KB"}{d.capacity ? ` / ${formatBytes(d.capacity)}` : ""}</span>
            <span class="sub when">{d.last_scan ? t("drive.lastScan", { date: formatDate(new Date(d.last_scan)) }) : t("drive.neverScanned")}</span>
          </li>
        {/each}
      </ul>
    </section>

    <div class="grid">
      <section class="card">
        <h2 class="mac-headline">{t("ov.attention")}</h2>
        {#if !ov}
          <ProgressIndicator kind="spinner" size="small" label={t("view.loading")} />
        {:else if !ov.attention.length}
          <p class="ok mac-body"><Icon name="checkmark" size={14} />{t("ov.allGood")}</p>
        {:else}
          <ul class="rows mac-callout">
            {#each ov.attention.slice(0, 8) as a, i (i)}
              <li class="lv-{a.level}"><Icon name={ATT_ICON[a.kind] || "info"} size={14} /><a href={a.href} use:link>{attentionText(a)}</a></li>
            {/each}
          </ul>
        {/if}
      </section>

      <section class="card">
        <h2 class="mac-headline">{t("ov.save")}</h2>
        {#if dupes}
          <p class="big mac-title-1">{formatBytes(releasable) || "0 KB"}</p>
          <p class="mac-callout sub">{releasable ? t("ov.saveHint", { n: formatNumber(dupes.files.confirmed) }) : t("ov.saveNone")}</p>
          {#if unchecked}<p class="mac-callout sub">{t("ov.unchecked", { n: formatNumber(unchecked) })}</p>{/if}
          <div class="acts"><Button size="small" variant="bordered" onclick={() => navigate("/duplicates")}>{t("ov.toDupes")}</Button></div>
        {:else}
          <ProgressIndicator kind="spinner" size="small" label={t("view.loading")} />
        {/if}
      </section>

      <section class="card">
        <h2 class="mac-headline">{t("ov.retire")}</h2>
        {#if ov}
          <ul class="retire mac-callout">
            {#each ov.retire as r (r.root_id)}
              <li>
                <a href={`/retire/${r.root_id}`} use:link class="dname">{r.name}</a>
                {#if !r.checked}
                  <span class="sub">{t("ov.retireNotYet")}</span>
                {:else if r.ready}
                  <span class="good">{t("retire.ready")}</span>
                {:else}
                  <span class="minibar" aria-hidden="true">
                    <i class="s-copy" style:width="{pct(r.copy.bytes, r.total.bytes)}%"></i><i class="s-maybe" style:width="{pct(r.maybe.bytes, r.total.bytes)}%"></i><i class="s-only" style:width="{pct(r.only.bytes, r.total.bytes)}%"></i>
                  </span>
                  <span class="sub">{t("ov.retireOnly", { size: formatBytes(r.only.bytes) || "0 KB" })}</span>
                {/if}
              </li>
            {/each}
          </ul>
          <p class="mac-caption-1 sub">{t("ov.retireHint")}</p>
        {/if}
      </section>

      {#if cats.length}
        <section class="card">
          <h2 class="mac-headline">{t("ov.categories")}</h2>
          <ul class="rows mac-callout">
            {#each cats as c (c.key)}
              <li><Icon name={CATEGORY_ICONS[c.key] || "tag"} size={14} /><a href={`/category/${c.key}`} use:link>{categoryName(c, t)}</a>
                <span class="sub num">{formatBytes(c.bytes)} · {t("cat.set.folders", { n: formatNumber(c.top) })}</span></li>
            {/each}
          </ul>
        </section>
      {/if}
    </div>

    {#if ov?.recent.items.length}
      <section class="card wide">
        <h2 class="mac-headline">{t("ov.recent")} <span class="sub mac-callout">{t("ov.recentHint", { n: formatNumber(ov.recent.files), size: formatBytes(ov.recent.bytes) || "0 KB" })}</span></h2>
        <ul class="tiles">
          {#each ov.recent.items as f (f.id)}
            <li>
              <a href={fileHref(f)} use:link title={f.name}>
                <span class="pic">
                  {#if broken.has(f.id)}<KindIcon kind={f.kind} size={36} />
                  {:else if f.image_id}<img src={thumbUrl({ id: f.image_id })} alt="" loading="lazy" onerror={() => (broken = new Set([...broken, f.id]))} />
                  {:else if f.cover}<img class="cover" src={`/api/files/${f.id}/cover`} alt="" loading="lazy" onerror={() => (broken = new Set([...broken, f.id]))} />
                  {:else}<KindIcon kind={f.kind} size={36} />{/if}
                </span>
                <span class="tname mac-caption-1">{prettyName(f.name)}</span>
              </a>
            </li>
          {/each}
        </ul>
      </section>
    {/if}
  {/if}
</div>

<style>
  .ov { padding: var(--space-5) var(--space-6) var(--space-8); max-width: 1200px; color: var(--label-primary); display: flex; flex-direction: column; gap: var(--space-4); }
  h1, h2, p { margin: 0; }
  .sub { color: var(--label-secondary); font-weight: 400; }
  .hero { display: flex; align-items: flex-end; justify-content: space-between; gap: var(--space-4); flex-wrap: wrap; }
  .hero p { margin-top: var(--space-1); }
  .job { display: inline-flex; align-items: center; gap: var(--space-2); padding: var(--space-1) var(--space-3); border-radius: var(--radius-capsule);
    background: var(--fill-quaternary); color: var(--label-primary); text-decoration: none; max-width: 420px; }
  .job span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .err { color: var(--destructive); }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: var(--space-4); }
  .card { display: flex; flex-direction: column; gap: var(--space-2); padding: var(--space-4); border-radius: var(--radius-lg, var(--radius-md));
    background: var(--bg-secondary, var(--fill-quaternary)); box-shadow: inset 0 0 0 1px var(--separator); min-width: 0; }
  .card.empty { align-items: center; text-align: center; padding: var(--space-8); }
  .card.empty > :global(svg) { color: var(--accent); }
  .bar { display: flex; height: var(--space-3); border-radius: var(--radius-capsule); overflow: hidden; background: var(--fill-tertiary); gap: 1px; margin-top: var(--space-1); }
  .bar i { display: block; height: 100%; }
  .legend { list-style: none; margin: 0; padding: 0; display: flex; flex-wrap: wrap; gap: var(--space-1) var(--space-5); }
  .legend li { display: flex; align-items: center; gap: var(--space-2); }
  .legend a { display: inline-flex; align-items: center; gap: var(--space-2); color: var(--label-primary); text-decoration: none; }
  .legend a:hover { color: var(--accent); }
  .dot { width: var(--space-2); height: var(--space-2); border-radius: var(--radius-capsule); flex: none; }
  .drives, .rows, .retire { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: var(--space-2); }
  .drives { margin-top: var(--space-2); padding-top: var(--space-2); border-top: 1px solid var(--separator); }
  .drives li, .rows li, .retire li { display: flex; align-items: center; gap: var(--space-2); min-width: 0; }
  .drives li > :global(svg), .rows li > :global(svg) { flex: none; color: var(--label-secondary); }
  .rows li.lv-warn > :global(svg) { color: var(--system-orange); }
  .rows li.lv-fail > :global(svg) { color: var(--system-red); }
  .rows a, .dname { color: var(--label-primary); text-decoration: none; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; min-width: 0; }
  .rows a:hover, .dname:hover { color: var(--accent); text-decoration: underline; }
  .dname { flex: 0 1 auto; font-weight: 600; }
  .when, .num { margin-left: auto; flex: none; }
  .ok { display: flex; align-items: center; gap: var(--space-2); color: var(--system-green); }
  .big { font-feature-settings: "tnum"; }
  .acts { margin-top: auto; padding-top: var(--space-2); }
  .good { color: var(--system-green); margin-left: auto; }
  .minibar { flex: 1; display: flex; height: var(--space-2); min-width: 60px; border-radius: var(--radius-capsule); overflow: hidden; background: var(--fill-tertiary); }
  .minibar i { display: block; height: 100%; }
  .s-copy { background: var(--system-green); }
  .s-maybe { background: var(--system-yellow); }
  .s-only { background: var(--system-red); }
  .retire li .sub { flex: none; }
  .tiles { list-style: none; margin: 0; padding: 0; display: grid; grid-template-columns: repeat(auto-fill, minmax(104px, 1fr)); gap: var(--space-3); }
  .tiles a { display: flex; flex-direction: column; align-items: center; gap: var(--space-1); color: var(--label-primary); text-decoration: none; min-width: 0; }
  .pic { width: 96px; height: 96px; display: flex; align-items: center; justify-content: center; border-radius: var(--radius-sm); overflow: hidden; background: var(--fill-quaternary); }
  .pic img { width: 100%; height: 100%; object-fit: cover; }
  .pic img.cover { width: auto; height: auto; max-width: 80%; max-height: 90%; object-fit: contain; box-shadow: 0 0 0 1px var(--separator), var(--shadow-knob); background: var(--bg-primary); }
  .tname { max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  @media (max-width: 640px) { .ov { padding: var(--space-4); } }
</style>
