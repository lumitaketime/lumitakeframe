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
  import { t, formatNumber, formatBytes, formatDuration, formatDate } from "../i18n/index.svelte.js";
  import { openItem } from "../data/browse.js";
  import { app, toast, refresh } from "../lib/state.svelte.js";
  import { route, navigate, link } from "../lib/router.svelte.js";

  const PAGE = 100;
  const tab = $derived(route.query.tab === "files" ? "files" : "folders");
  let summary = $state(null);
  let error = $state("");
  let lists = $state({ folders: null, files: null, pending: null }); // 每個清單：{groups, total}
  let more = $state("");
  let closed = $state({}); // 預設全部展開，直接看得到每一份在哪裡；這裡記使用者收起來的
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
  // 每一份的位置拆成一段一段：（資料夾來源 ›）資料夾 › 子資料夾 › 名稱
  const crumbs = (it) => [...(it.root && it.root !== it.drive ? [it.root] : []), ...it.path.split("/").filter(Boolean)];
  // 這一組分布在哪些硬碟：同一顆硬碟裡的重複是真的多餘；跨硬碟的可能是你刻意留的備份
  function spread(g) {
    const count = new Map();
    for (const it of g.items) count.set(it.drive, (count.get(it.drive) || 0) + 1);
    return { drives: [...count].map(([name, n]) => ({ name, n })), same: count.size === 1 };
  }
  async function reveal(it) {
    try {
      await openItem(it, "reveal");
    } catch (e) {
      toast(e.message, "error");
    }
  }
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
            {@const shown = !closed[g.key]}
            {@const where = spread(g)}
            <li class="group" class:open={shown}>
              <button type="button" class="head mac-body" aria-expanded={shown} onclick={() => (closed[g.key] = shown)}>
                <span class="disc" class:open={shown}><Icon name="chevron-right" size={10} weight="bold" /></span>
                <KindIcon kind={s.kind === "folders" ? "folder" : g.kind} />
                <span class="title">
                  <span class="name" title={g.name}>{g.name}</span>
                  <span class="where mac-callout">
                    {where.same ? t("dupes.sameDrive", { drive: where.drives[0].name, count: formatNumber(g.copies) })
                      : t("dupes.acrossDrives", { drives: where.drives.map((d) => (d.n > 1 ? `${d.name} ×${d.n}` : d.name)).join("、") })}
                  </span>
                </span>
                {#if !g.confirmed}<span class="tag mac-callout">{t("dupes.pending")}</span>{/if}
                {#if g.in_folder}<span class="tag mac-callout" title={t("dupes.inFolderHint")}>{t("dupes.inFolder")}</span>{/if}
                <span class="num">{t("dupes.each", { size: formatBytes(g.size) || "0 KB" })}</span>
                <span class="num">{t("dupes.copies", { count: formatNumber(g.copies) })}</span>
                <span class="num free">{t("dupes.releasable", { size: formatBytes(g.releasable) || "0 KB" })}</span>
              </button>
              {#if shown}
                <ol class="copies mac-body">
                  {#each g.items as it, n (it.id)}
                    {@const parts = crumbs(it)}
                    <li class:off={!it.online}>
                      <span class="no mac-callout" aria-hidden="true">{n + 1}</span>
                      <div class="place">
                        <div class="drive">
                          <Icon name={it.online ? "external-drive-fill" : "external-drive"} size={14} weight="medium" />
                          <b>{it.drive}</b>
                          {#if !it.online}<span class="tag mac-callout">{t("drive.offline")}</span>{/if}
                          {#if it.read_only}<span class="tag mac-callout">{t("drive.readOnly")}</span>{/if}
                          {#if it.mtime}<span class="sub mac-callout">{t("dupes.modified", { date: formatDate(it.mtime) })}</span>{/if}
                        </div>
                        <div class="path mac-callout" title={parts.join(" › ")}>
                          {#each parts as part, k (k)}
                            {#if k}<Icon name="chevron-right" size={8} weight="bold" class="sep" />{/if}<span class:last={k === parts.length - 1}>{part}</span>
                          {/each}
                        </div>
                      </div>
                      <a class="act mac-callout" href={hrefOf(it)} use:link>{t("dupes.show")}</a>
                      {#if app.server?.local}<button type="button" class="act mac-callout" disabled={!it.online} onclick={() => reveal(it)}>{t("menu.reveal")}</button>{/if}
                    </li>
                  {/each}
                </ol>
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
  .title { flex: 1; min-width: 0; display: flex; flex-direction: column; padding: var(--space-2) 0; }
  .name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-weight: 600; }
  .where { color: var(--label-secondary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .tag { flex: none; padding: 0 var(--space-2); border-radius: var(--radius-capsule); box-shadow: inset 0 0 0 1px var(--separator); color: var(--label-secondary); }
  .num { flex: none; min-width: 96px; text-align: right; color: var(--label-secondary); font-feature-settings: "tnum"; }
  .free { color: var(--label-primary); min-width: 130px; }
  /* 每一份一列：第幾份、在哪顆硬碟、完整的位置（一段一段）、可以直接前往 */
  .copies { list-style: none; margin: 0; padding: 0 var(--space-3) var(--space-3) calc(var(--space-3) + var(--space-5)); display: flex; flex-direction: column; gap: var(--space-2); }
  .copies li { display: flex; align-items: center; gap: var(--space-3); padding: var(--space-2) var(--space-3); border-radius: var(--radius-sm); background: var(--fill-quaternary); min-width: 0; }
  .no { flex: none; width: var(--space-5); height: var(--space-5); display: inline-flex; align-items: center; justify-content: center; border-radius: var(--radius-capsule);
    background: var(--fill-secondary); color: var(--label-secondary); font-feature-settings: "tnum"; }
  .place { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
  .drive { display: flex; align-items: center; gap: var(--space-2); min-width: 0; color: var(--accent); }
  .drive b { color: var(--label-primary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .copies li.off .drive { color: var(--label-secondary); }
  .path { display: flex; align-items: center; flex-wrap: wrap; gap: 2px var(--space-1); color: var(--label-secondary); overflow-wrap: anywhere; }
  .path :global(.sep) { flex: none; color: var(--label-tertiary); }
  .path .last { color: var(--label-primary); font-weight: 600; }
  .act { flex: none; padding: 2px var(--space-2); border: 0; border-radius: var(--radius-capsule); background: none; color: var(--accent); font: inherit; text-decoration: none; cursor: pointer; }
  .act:hover:not(:disabled) { background: var(--fill-tertiary); }
  .act:disabled { color: var(--label-tertiary); cursor: default; }
  .more { margin: var(--space-3) 0 0; text-align: center; }
  .state { display: flex; flex-direction: column; align-items: center; gap: var(--space-3); padding: var(--space-10) var(--space-6); text-align: center; color: var(--label-secondary); }
  .state h2 { color: var(--label-primary); }
  @media (max-width: 799px) { .num:not(.free) { display: none; } }
  @media (prefers-reduced-motion: reduce) { .disc { transition: none; } }
</style>
