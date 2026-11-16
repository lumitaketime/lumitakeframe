<script>
  /**
   * 重複項目：內容完全相同的資料夾與檔案。上方切換「重複資料夾」與「重複檔案」，依可釋出的空間由大到小。
   * 「已確認」＝每一份都從頭到尾讀過、內容相同；「待確認」＝只知道檔名與大小相同，還不能標記為待刪除。
   * 這一頁只查詢與比對（只讀取），不會刪除或搬移任何東西。
   */
  import { Button, Icon, ProgressIndicator, SegmentedControl } from "../ui/index.js";
  import KindIcon from "../views/KindIcon.svelte";
  import { loadDupesSummary, loadDupeFolders, loadDupeFiles, startCompare, stopCompare, estimateSeconds } from "../data/dupes.js";
  import { setFrame } from "../shell/frame.svelte.js";
  import { t, formatNumber, formatBytes, formatDuration } from "../i18n/index.svelte.js";
  import { app, toast, refresh } from "../lib/state.svelte.js";
  import { route, navigate, link } from "../lib/router.svelte.js";

  const PAGE = 100;
  const tab = $derived(route.query.tab === "files" ? "files" : "folders");
  let summary = $state(null);
  let error = $state("");
  let lists = $state({ folders: null, files: null, pending: null }); // 每個清單：{groups, total}
  let more = $state("");
  let open = $state({});
  let busy = $state(false);

  const job = $derived(app.server?.jobs?.current?.kind === "compare" ? app.server.jobs.current : null);
  const queued = $derived(!!app.server?.jobs?.queued?.some((j) => j.kind === "compare"));

  async function load() {
    try {
      const [s, folders, files, pending] = await Promise.all([loadDupesSummary(), loadDupeFolders(0, PAGE), loadDupeFiles(0, PAGE), loadDupeFiles(0, PAGE, true)]);
      summary = s;
      lists = { folders, files, pending };
      error = "";
    } catch (e) {
      error = e.message;
    }
  }
  // 進頁面、工作結束時重新讀取；比對進行中每 5 秒更新一次，新確認的組別會陸續出現
  $effect(() => {
    app.refreshKey;
    load();
  });
  $effect(() => {
    if (!job) return;
    const timer = setInterval(load, 5000);
    return () => {
      clearInterval(timer);
      load();
    };
  });
  async function loadMore(kind) {
    more = kind;
    try {
      const have = lists[kind].groups.length;
      const next = kind === "folders" ? await loadDupeFolders(have, PAGE) : await loadDupeFiles(have, PAGE, kind === "pending");
      lists[kind] = { ...next, groups: [...lists[kind].groups, ...next.groups] };
    } catch (e) {
      toast(e.message, "error");
    } finally {
      more = "";
    }
  }
  async function compare(large) {
    busy = true;
    try {
      await startCompare(large);
      toast(t("dupes.compareStarted"));
      refresh();
    } catch (e) {
      toast(e.message, "error");
    } finally {
      busy = false;
    }
  }
  async function stop() {
    busy = true;
    try {
      await stopCompare(job?.id);
      refresh();
    } catch (e) {
      toast(e.message, "error");
    } finally {
      busy = false;
    }
  }

  const plan = $derived(summary?.plan);
  const stats = $derived(!summary ? null : tab === "folders"
    ? { groups: summary.folders.confirmed, releasable: summary.folders.releasable, pending: summary.folders.total - summary.folders.confirmed }
    : { groups: summary.files.confirmed, releasable: summary.files.releasable, pending: summary.files.pending });
  $effect(() => {
    setFrame({ crumbs: [], location: null, info: null,
      status: stats ? t("dupes.total", { groups: formatNumber(stats.groups), size: formatBytes(stats.releasable) || "0 KB" }) : "" });
  });
  const sections = $derived(tab === "folders"
    ? [{ kind: "folders", list: lists.folders }]
    : [{ kind: "files", list: lists.files }, { kind: "pending", list: lists.pending, title: t("dupes.pendingTitle"), hint: t("dupes.pendingHint") }]);
  const empty = $derived(sections.every((s) => s.list && !s.list.groups.length));
  const hrefOf = (it) => {
    const folder = it.type === "folder" ? it.path : it.path.includes("/") ? it.path.slice(0, it.path.lastIndexOf("/")) : "";
    return `/folders/${it.root_id}${folder ? `?path=${encodeURIComponent(folder)}` : ""}`;
  };
</script>

<div class="dupes">
  <header class="top">
    <SegmentedControl value={tab} onchange={(v) => navigate(v === "files" ? "/duplicates?tab=files" : "/duplicates", { replace: true })} ariaLabel={t("nav.duplicates")}
      segments={[{ value: "folders", label: t("dupes.folders") }, { value: "files", label: t("dupes.files") }]} />
    {#if stats}
      <p class="mac-body total">
        <b>{t("dupes.total", { groups: formatNumber(stats.groups), size: formatBytes(stats.releasable) || "0 KB" })}</b>
        {#if stats.pending}<span>· {t("dupes.pendingCount", { count: formatNumber(stats.pending) })}</span>{/if}
      </p>
    {/if}
  </header>

  {#if plan}
    <section class="compare mac-body" aria-live="polite">
      {#if job || queued}
        <div class="row">
          <ProgressIndicator kind="circular" size="small" value={job?.total ? job.done / job.total : undefined} label={t("dupes.comparing")} />
          <div class="grow">
            <b>{t("dupes.comparing")}</b>
            <p class="sub">{job?.total ? t("dupes.progress", { done: formatBytes(job.done) || "0 KB", total: formatBytes(job.total) }) : t("dupes.waiting")}{job?.eta ? ` · ${t("dupes.remaining", { time: formatDuration(job.eta) })}` : ""}</p>
            {#if job?.message}<p class="sub file">{job.message}</p>{/if}
          </div>
          <Button variant="bordered" disabled={busy || !job} onclick={stop}>{t("drives.stop")}</Button>
        </div>
        {#if job?.total}<ProgressIndicator value={job.done / job.total} label={t("dupes.comparing")} />{/if}
      {:else if plan.small.files}
        <div class="row">
          <div class="grow">
            <b>{t("dupes.needCompare", { count: formatNumber(plan.small.files), size: formatBytes(plan.small.bytes) })}</b>
            <p class="sub">{t("dupes.compareHint", { time: formatDuration(estimateSeconds(plan.small.bytes)) })}</p>
          </div>
          <Button variant="borderedProminent" disabled={busy} onclick={() => compare(false)}>{t("dupes.compare")}</Button>
        </div>
      {:else if plan.large.files}
        <div class="row">
          <div class="grow">
            <b>{t("dupes.needLarge", { count: formatNumber(plan.large.files), size: formatBytes(plan.large.bytes) })}</b>
            <p class="sub">{t("dupes.largeHint", { time: formatDuration(estimateSeconds(plan.large.bytes)) })}</p>
          </div>
          <Button variant="bordered" disabled={busy} onclick={() => compare(true)}>{t("dupes.compareLarge")}</Button>
        </div>
      {:else if plan.done}
        <p class="sub done"><Icon name="checkmark" size={13} weight="bold" />{t("dupes.allCompared")}</p>
      {/if}
      {#if plan.offline.files}
        <p class="sub">{t("dupes.offline", { count: formatNumber(plan.offline.files), size: formatBytes(plan.offline.bytes) })}</p>
      {/if}
    </section>
  {/if}

  {#if error}
    <div class="state" role="alert"><h2 class="mac-title-3">{t("view.error")}</h2><p class="mac-body">{error}</p><Button onclick={load}>{t("view.retry")}</Button></div>
  {:else if !summary}
    <div class="state"><ProgressIndicator kind="spinner" label={t("view.loading")} /></div>
  {:else if empty}
    <div class="state">
      <h2 class="mac-title-3">{tab === "folders" ? t("dupes.emptyFolders") : t("dupes.emptyFiles")}</h2>
      <p class="mac-body">{plan.small.files || plan.large.files ? t("dupes.emptyHintCompare") : t("dupes.emptyHint")}</p>
    </div>
  {:else}
    {#each sections as s (s.kind)}
      {#if s.list?.groups.length}
        {#if s.title}<h2 class="mac-headline section">{s.title}</h2><p class="mac-callout sub hint">{s.hint}</p>{/if}
        <ul class="groups">
          {#each s.list.groups as g (g.key)}
            {@const shown = !!open[g.key]}
            <li class="group" class:open={shown}>
              <button type="button" class="head mac-body" aria-expanded={shown} onclick={() => (open[g.key] = !shown)}>
                <span class="disc" class:open={shown}><Icon name="chevron-right" size={10} weight="bold" /></span>
                <KindIcon kind={s.kind === "folders" ? "folder" : g.kind} />
                <span class="name" title={g.name}>{g.name}</span>
                {#if !g.confirmed}<span class="tag mac-callout">{t("dupes.pending")}</span>{/if}
                {#if g.in_folder}<span class="tag mac-callout" title={t("dupes.inFolderHint")}>{t("dupes.inFolder")}</span>{/if}
                <span class="num">{t("dupes.each", { size: formatBytes(g.size) || "0 KB" })}</span>
                <span class="num">{t("dupes.copies", { count: formatNumber(g.copies) })}</span>
                <span class="num free">{t("dupes.releasable", { size: formatBytes(g.releasable) || "0 KB" })}</span>
              </button>
              {#if shown}
                <ul class="copies mac-body">
                  {#each g.items as it (it.id)}
                    <li>
                      <Icon name={it.online ? "external-drive-fill" : "external-drive"} size={14} weight="medium" class={it.online ? "on" : "off"} />
                      <span class="drive">{it.drive}{#if !it.online}<span class="sub"> · {t("drive.offline")}</span>{/if}{#if it.read_only}<span class="sub"> · {t("drive.readOnly")}</span>{/if}</span>
                      <a class="path" href={hrefOf(it)} use:link title={it.path}>{it.root === it.drive ? "" : `${it.root}/`}{it.path}</a>
                    </li>
                  {/each}
                </ul>
              {/if}
            </li>
          {/each}
        </ul>
        {#if s.list.groups.length < s.list.total}
          <p class="more"><Button variant="bordered" loading={more === s.kind} onclick={() => loadMore(s.kind)}>{t("dupes.more", { count: formatNumber(s.list.total - s.list.groups.length) })}</Button></p>
        {/if}
      {/if}
    {/each}
  {/if}
</div>

<style>
  .dupes { padding: var(--space-4) var(--space-6) var(--space-8); max-width: 1100px; color: var(--label-primary); }
  h2, p { margin: 0; }
  .top { display: flex; align-items: center; gap: var(--space-4); flex-wrap: wrap; margin-bottom: var(--space-4); }
  .total span { color: var(--label-secondary); }
  .sub { color: var(--label-secondary); }
  .compare { display: flex; flex-direction: column; gap: var(--space-2); padding: var(--space-3) var(--space-4); margin-bottom: var(--space-5);
    border-radius: var(--radius-md); background: var(--fill-quaternary); box-shadow: inset 0 0 0 1px var(--separator); }
  .row { display: flex; align-items: center; gap: var(--space-3); }
  .grow { flex: 1; min-width: 0; }
  .file { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .done { display: flex; align-items: center; gap: var(--space-2); }
  .section { margin: var(--space-6) 0 var(--space-1); }
  .hint { margin-bottom: var(--space-3); }
  .groups { list-style: none; margin: 0; padding: 0; border-radius: var(--radius-md); box-shadow: inset 0 0 0 1px var(--separator); overflow: hidden; }
  .group + .group { border-top: 1px solid var(--separator); }
  .head { width: 100%; display: flex; align-items: center; gap: var(--space-2); min-height: var(--control-large); padding: 0 var(--space-3); border: 0; background: none;
    color: inherit; font: inherit; text-align: left; cursor: pointer; }
  .head:hover { background: var(--fill-quaternary); }
  .head:focus-visible { box-shadow: inset var(--focus-ring); }
  .disc { display: inline-flex; color: var(--label-secondary); transition: transform var(--dur-quick) var(--ease); }
  .disc.open { transform: rotate(90deg); }
  .name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-weight: 600; }
  .tag { flex: none; padding: 0 var(--space-2); border-radius: var(--radius-capsule); box-shadow: inset 0 0 0 1px var(--separator); color: var(--label-secondary); }
  .num { flex: none; min-width: 96px; text-align: right; color: var(--label-secondary); font-feature-settings: "tnum"; }
  .free { color: var(--label-primary); min-width: 130px; }
  .copies { list-style: none; margin: 0; padding: var(--space-1) var(--space-3) var(--space-3) calc(var(--space-3) + var(--space-6)); display: flex; flex-direction: column; gap: var(--space-1); }
  .copies li { display: flex; align-items: center; gap: var(--space-2); min-height: var(--target-mac); min-width: 0; }
  .copies :global(.on) { color: var(--accent); flex: none; }
  .copies :global(.off) { color: var(--label-secondary); flex: none; }
  .drive { flex: none; max-width: 40%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .path { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--label-secondary); text-decoration: none; border-radius: var(--radius-xs); }
  .path:hover { color: var(--accent); text-decoration: underline; }
  .more { margin: var(--space-3) 0 0; text-align: center; }
  .state { display: flex; flex-direction: column; align-items: center; gap: var(--space-3); padding: var(--space-10) var(--space-6); text-align: center; color: var(--label-secondary); }
  .state h2 { color: var(--label-primary); }
  @media (max-width: 799px) { .num:not(.free) { display: none; } }
  @media (prefers-reduced-motion: reduce) { .disc { transition: none; } }
</style>
