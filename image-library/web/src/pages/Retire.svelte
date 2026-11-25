<script>
  /**
   * 淘汰檢查：這顆硬碟上的每個檔案，在別顆硬碟有沒有內容一模一樣的副本。
   * - 長條與圖例：別顆有副本／副本有風險／可能有副本（還沒確認）／只有這一顆有；系統小檔案另外列。
   * - 「確認副本」：先比開頭結尾，一樣的才讀完整內容；兩邊硬碟都要接上，可以暫停。
   * - 依資料夾列出，點開看檔案；可以匯出清單。
   * 全程只讀，不刪除、不搬移任何檔案（核心原則一、七）。
   */
  import { Alert, Button, Icon, List, ListRow, PopUpButton, ProgressIndicator, SegmentedControl, Toggle } from "../ui/index.js";
  import KindIcon from "../views/KindIcon.svelte";
  import ActionCard from "../views/ActionCard.svelte";
  import { loadRetire, loadRetireFolders, loadRetireFiles, retirePlan, startVerify, setPlanned, exportRetire, pickExportFolder,
    proposeConsolidate, loadConsolidations } from "../data/retire.js";
  import { catalog, loadCatalog } from "../data/catalog.svelte.js";
  import { setFrame } from "../shell/frame.svelte.js";
  import { t, formatNumber, formatBytes, formatDateTime, formatDuration } from "../i18n/index.svelte.js";
  import { app, toast, refresh } from "../lib/state.svelte.js";
  import { link, navigate } from "../lib/router.svelte.js";
  import { prettyName } from "../lib/names.js";

  let { rootId } = $props();
  let s = $state(null);
  let error = $state("");
  let tab = $state("only");
  let list = $state(null); // {total, folders}
  let open = $state({}); // 資料夾 id → {total, files}
  let asking = $state(null); // 確認副本前的計畫
  let busy = $state("");
  let tabsWidth = $state(0);
  const local = $derived(!!app.server?.local);
  const isMac = $derived(app.server?.platform === "darwin");

  // 整理計畫：把「只在這顆上」的檔案複製到另一顆
  let cards = $state([]);
  let target = $state("");
  let markSource = $state(false);
  const targets = $derived(catalog.drives.filter((d) => !d.roots.some((r) => r.id === rootId) && !d.read_only && d.fs_label !== "NTFS")
    .map((d) => ({ value: String(d.roots[0].id), label: d.online ? d.name : `${d.name}（${t("drive.offline")}）` })));
  $effect(() => {
    if (!catalog.loaded) loadCatalog();
  });
  async function makePlan() {
    busy = "plan";
    try {
      const a = await proposeConsolidate({ source_root: rootId, target_root: Number(target || targets[0]?.value), mark_source: markSource });
      cards = [a, ...cards.filter((c) => c.id !== a.id)];
    } catch (e) {
      toast(e.message, "error");
    } finally {
      busy = "";
    }
  }
  async function load() {
    loadConsolidations(rootId).then((d) => (cards = d.actions)).catch(() => {});
    try {
      s = await loadRetire(rootId);
      error = "";
    } catch (e) {
      error = e.message;
    }
  }
  async function loadList(more = false) {
    try {
      const d = await loadRetireFolders(rootId, tab, more ? list.folders.length : 0);
      list = more ? { total: d.total, folders: [...list.folders, ...d.folders] } : d;
    } catch (e) {
      toast(e.message, "error");
    }
  }
  $effect(() => {
    app.refreshKey;
    rootId;
    load();
  });
  $effect(() => {
    tab;
    s?.computed_at;
    open = {};
    if (s) loadList();
  });
  // 確認副本做完：重新讀
  const job = $derived(app.server?.jobs?.active?.find((j) => j.kind === "retire_verify" && j.target === `retire:${rootId}`)
    || app.server?.jobs?.queued?.find((j) => j.kind === "retire_verify" && j.target === `retire:${rootId}`) || null);
  let wasRunning = false;
  const copying = $derived(!!app.server?.jobs?.active?.some((j) => j.kind === "consolidate" && cards.some((c) => j.target === `consolidate:${c.id}`)));
  $effect(() => {
    const running = !!job || copying;
    if (wasRunning && !running) load();
    wasRunning = running;
  });
  $effect(() => {
    setFrame({ crumbs: [{ label: t("nav.drives"), href: "/drives" }, { label: s ? t("retire.title", { name: s.name }) : t("retire.short") }], status: "", location: null, info: null });
  });

  const ORDER = ["copy", "risky", "maybe", "only"];
  const pct = (b) => (s?.total.bytes ? (b / s.total.bytes) * 100 : 0);
  const pctText = (b) => {
    const p = pct(b);
    return p > 0 && p < 1 ? "<1%" : `${Math.round(p)}%`;
  };
  const unsafe = $derived(s ? s.states.only.files + s.states.maybe.files + s.states.risky.files : 0);

  async function toggleFolder(f) {
    if (open[f.id]) {
      const { [f.id]: _, ...rest } = open;
      open = rest;
      return;
    }
    try {
      open = { ...open, [f.id]: await loadRetireFiles(rootId, tab, f.id) };
    } catch (e) {
      toast(e.message, "error");
    }
  }
  async function moreFiles(f) {
    const cur = open[f.id];
    try {
      const d = await loadRetireFiles(rootId, tab, f.id, cur.files.length);
      open = { ...open, [f.id]: { total: d.total, files: [...cur.files, ...d.files] } };
    } catch (e) {
      toast(e.message, "error");
    }
  }
  async function askVerify() {
    try {
      asking = await retirePlan(rootId);
    } catch (e) {
      toast(e.message, "error");
    }
  }
  async function verify() {
    asking = null;
    try {
      await startVerify(rootId);
      toast(t("retire.started"));
      refresh();
    } catch (e) {
      toast(e.message, "error");
    }
  }
  async function plan(on) {
    try {
      await setPlanned(rootId, on);
      await load();
    } catch (e) {
      toast(e.message, "error");
    }
  }
  async function doExport() {
    busy = "export";
    try {
      const dir = isMac ? await pickExportFolder() : null;
      if (isMac && !dir) return;
      const out = await exportRetire(rootId, dir);
      toast(t("retire.exported", { path: out.path }), "info", 10000);
    } catch (e) {
      toast(e.message, "error");
    } finally {
      busy = "";
    }
  }
  const folderHref = (rootIdArg, path) => `/folders/${rootIdArg}${path ? `?path=${encodeURIComponent(path)}` : ""}`;
  const when = (iso) => (iso ? formatDateTime(new Date(iso)) : "");
  const mins = (bytes) => Math.max(60, Math.round(bytes / 150e6)); // 老硬碟大約每秒 150 MB
</script>

<div class="retire">
  {#if error}
    <div class="state" role="alert"><h2 class="mac-title-3">{t("view.error")}</h2><p class="mac-body">{error}</p><Button onclick={load}>{t("view.retry")}</Button></div>
  {:else if !s}
    <div class="state"><ProgressIndicator kind="spinner" label={t("view.loading")} /></div>
  {:else}
    <header class="top">
      <Icon name={s.online ? "external-drive-fill" : "external-drive"} size={26} weight="medium" />
      <div class="titles">
        <h1 class="mac-title-2">{t("retire.title", { name: s.name })}</h1>
        <p class="mac-callout sub">{t("status.filesOnly", { files: formatNumber(s.total.files) })} · {formatBytes(s.total.bytes) || "0 KB"}
          · {s.online ? t("drive.online") : t("drive.offline")}{#if s.last_scan} · {t("drive.lastScan", { date: when(s.last_scan) })}{/if}</p>
      </div>
    </header>

    {#if !s.total.files}
      <div class="state"><h2 class="mac-title-3">{t("retire.empty")}</h2><p class="mac-body">{t("retire.emptyHint")}</p></div>
    {:else}
      <section class="verdict" class:ready={s.ready}>
        <Icon name={s.ready ? "checkmark" : "exclamation-triangle"} size={20} />
        <div>
          <h2 class="mac-headline">{s.ready ? t("retire.ready") : t("retire.notReady")}</h2>
          <p class="mac-callout">{s.ready ? t("retire.readyHint")
            : [s.states.only.files ? t("retire.why.only", { n: formatNumber(s.states.only.files), size: formatBytes(s.states.only.bytes) || "0 KB" }) : "",
              s.states.maybe.files ? t("retire.why.maybe", { n: formatNumber(s.states.maybe.files) }) : "",
              s.states.risky.files ? t("retire.why.risky", { n: formatNumber(s.states.risky.files) }) : ""].filter(Boolean).join(t("retire.why.sep")) + t("retire.why.end")}</p>
        </div>
      </section>

      <div class="bar" role="img" aria-label={ORDER.map((k) => `${t(`retire.state.${k}`)} ${pctText(s.states[k].bytes)}`).join("，")}>
        {#each ORDER as k (k)}{#if s.states[k].bytes}<i class="seg s-{k}" style:width="{Math.max(0.8, pct(s.states[k].bytes))}%"></i>{/if}{/each}
      </div>
      <ul class="legend mac-callout">
        {#each ORDER.filter((k) => s.states[k].files) as k (k)}
          <li><i class="dot s-{k}" aria-hidden="true"></i><b>{t(`retire.state.${k}`)}</b>
            <span class="sub">{pctText(s.states[k].bytes)} · {t("retire.filesBytes", { n: formatNumber(s.states[k].files), size: formatBytes(s.states[k].bytes) || "0 KB" })}</span></li>
        {/each}
      </ul>
      {#if s.risky_on.length}
        <p class="mac-callout note warn">{t("retire.riskyOn", { drives: s.risky_on.map((d) => `「${d.name}」`).join("、"), size: formatBytes(s.states.risky.bytes) })}</p>
      {/if}
      {#if s.states.junk.files}
        <p class="mac-callout note sub">{t("retire.junk", { n: formatNumber(s.states.junk.files) })}</p>
      {/if}

      <List header={t("retire.actions")}>
        {#if job}
          <ListRow title={t("retire.verifying")} subtitle={job.message || ""} icon="duplicate">
            {#snippet trailing()}<span class="acts"><ProgressIndicator kind="circular" size="small" value={job.total ? job.done / job.total : undefined} label={t("retire.verifying")} />
              {#if job.eta}<span class="mac-caption-1 sub">{t("activity.eta", { time: formatDuration(job.eta) })}</span>{/if}</span>{/snippet}
          </ListRow>
        {:else if s.states.maybe.files}
          <ListRow title={t("retire.verify")} subtitle={t("retire.verifyHint", { n: formatNumber(s.states.maybe.files) })} icon="duplicate">
            {#snippet trailing()}<Button size="small" variant="borderedProminent" onclick={askVerify}>{t("retire.verifyButton")}</Button>{/snippet}
          </ListRow>
        {/if}
        {#if s.states.only.files}
          <ListRow title={t("retire.copy")} subtitle={targets.length ? t("retire.copyHint", { n: formatNumber(s.states.only.files), size: formatBytes(s.states.only.bytes) || "0 KB" }) : t("retire.copyNoTarget")} icon="folder" />
          {#if targets.length}
            <!-- 目標硬碟另外一列：窄螢幕上說明文字才不會被擠成一長條 -->
            <ListRow title={t("retire.target")}>
              {#snippet trailing()}<span class="acts">
                <PopUpButton value={target || targets[0].value} onchange={(v) => (target = v)} options={targets} />
                <Button size="small" variant="bordered" loading={busy === "plan"} onclick={makePlan}>{t("retire.copyButton")}</Button>
              </span>{/snippet}
            </ListRow>
            <ListRow title={t("retire.markSource")} subtitle={t("retire.markSourceHint")}>
              {#snippet trailing()}<Toggle checked={markSource} onchange={(v) => (markSource = v)} aria-label={t("retire.markSource")} />{/snippet}
            </ListRow>
          {/if}
        {/if}
        <ListRow title={t("retire.plan")} subtitle={t("retire.planHint")} icon="tag">
          {#snippet trailing()}<Toggle checked={!!s.planned} onchange={plan} aria-label={t("retire.plan")} />{/snippet}
        </ListRow>
        {#if local && unsafe}
          <ListRow title={t("retire.export")} subtitle={t("retire.exportHint")} icon="share">
            {#snippet trailing()}<Button size="small" variant="bordered" loading={busy === "export"} onclick={doExport}>{t("retire.exportButton")}</Button>{/snippet}
          </ListRow>
        {/if}
      </List>

      {#each cards as _, k (cards[k].id)}
        <ActionCard bind:action={cards[k]} />
      {/each}

      <!-- 窄螢幕放不下四個分段：改成下拉選單 -->
      <div class="tabs" bind:clientWidth={tabsWidth}>
        {#if tabsWidth && tabsWidth < 560}
          <PopUpButton value={tab} onchange={(v) => (tab = v)}
            options={["only", "maybe", "risky", "copy"].map((v) => ({ value: v, label: `${t(`retire.tab.${v}`)}（${formatNumber(s.states[v].files)}）` }))} />
        {:else}
          <SegmentedControl value={tab} onchange={(v) => (tab = v)} ariaLabel={t("retire.listLabel")}
            segments={["only", "maybe", "risky", "copy"].map((v) => ({ value: v, label: `${t(`retire.tab.${v}`)}（${formatNumber(s.states[v].files)}）` }))} />
        {/if}
      </div>
      <p class="mac-callout sub hint">{t(`retire.tabHint.${tab}`)}</p>

      {#if list && !list.folders.length}
        <p class="mac-body sub empty">{t("retire.noneHere")}</p>
      {:else if list}
        <ul class="folders mac-body">
          {#each list.folders as f (f.id)}
            <li>
              <button type="button" class="frow" aria-expanded={!!open[f.id]} onclick={() => toggleFolder(f)}>
                <Icon name={open[f.id] ? "chevron-down" : "chevron-right"} size={11} />
                <KindIcon kind="folder" size={16} />
                <span class="path" title={f.path}>{f.path ? prettyName(f.path) : t("retire.top")}</span>
                <span class="sub num">{t("retire.filesBytes", { n: formatNumber(f.files), size: formatBytes(f.bytes) || "0 KB" })}</span>
              </button>
              {#if open[f.id]}
                <ul class="files">
                  {#each open[f.id].files as x (x.id)}
                    <li><KindIcon kind={x.kind} size={14} /><span class="fname" title={x.name}>{prettyName(x.name)}</span>
                      <span class="sub num">{formatBytes(x.size) || "0 KB"}</span>
                      <span class="sub num date">{x.mtime ? formatDateTime(new Date(x.mtime * 1000)) : ""}</span></li>
                  {/each}
                  <li class="foot">
                    <a href={folderHref(rootId, f.path)} use:link>{t("retire.openFolder")}</a>
                    {#if open[f.id].files.length < open[f.id].total}<button type="button" class="more" onclick={() => moreFiles(f)}>{t("act.more", { n: formatNumber(open[f.id].total - open[f.id].files.length) })}</button>{/if}
                  </li>
                </ul>
              {/if}
            </li>
          {/each}
        </ul>
        {#if list.folders.length < list.total}
          <button type="button" class="more mac-callout" onclick={() => loadList(true)}>{t("retire.moreFolders", { n: formatNumber(list.total - list.folders.length) })}</button>
        {/if}
      {/if}
      <p class="mac-caption-1 sub foot-note">{t("retire.footer")}</p>
    {/if}
  {/if}
</div>

{#if asking}
  <div class="backdrop">
    <Alert title={t("retire.verifyTitle", { n: formatNumber(asking.files) })}
      message={[t("retire.verifyMessage", { size: formatBytes(asking.bytes) || "0 KB", min: formatNumber(Math.ceil(mins(asking.bytes) / 60)) }),
        !asking.online ? t("retire.needSelf", { name: s.name }) : "",
        asking.need.length ? t("retire.needOthers", { drives: asking.need.map((d) => `「${d.name}」`).join("、") }) : ""].filter(Boolean).join("\n\n")}
      actions={[
        { label: t("retire.verifyButton"), role: "default", onPress: verify, disabled: !asking.files },
        { label: t("common.cancel"), role: "cancel", onPress: () => (asking = null) },
      ]} />
  </div>
{/if}

<style>
  .retire { padding: var(--space-4) var(--space-6) var(--space-8); max-width: 1100px; color: var(--label-primary); display: flex; flex-direction: column; gap: var(--space-3); }
  h1, h2, p { margin: 0; }
  .sub { color: var(--label-secondary); }
  .top { display: flex; align-items: center; gap: var(--space-3); }
  .top > :global(svg) { color: var(--accent); flex: none; }
  .titles { min-width: 0; }
  .verdict { display: flex; align-items: flex-start; gap: var(--space-3); padding: var(--space-3) var(--space-4); border-radius: var(--radius-md);
    background: color-mix(in srgb, var(--system-orange) 12%, transparent); }
  .verdict > :global(svg) { flex: none; color: var(--system-orange); margin-top: 2px; }
  .verdict.ready { background: color-mix(in srgb, var(--system-green) 14%, transparent); }
  .verdict.ready > :global(svg) { color: var(--system-green); }
  .bar { display: flex; height: var(--space-3); border-radius: var(--radius-capsule); overflow: hidden; background: var(--fill-tertiary); gap: 1px; }
  .seg { display: block; height: 100%; }
  .s-copy { background: var(--system-green); }
  .s-risky { background: var(--system-orange); }
  .s-maybe { background: var(--system-yellow); }
  .s-only { background: var(--system-red); }
  .legend { list-style: none; margin: 0; padding: 0; display: flex; flex-wrap: wrap; gap: var(--space-2) var(--space-5); }
  .legend li { display: flex; align-items: center; gap: var(--space-2); }
  .dot { width: var(--space-2); height: var(--space-2); border-radius: var(--radius-capsule); flex: none; }
  .note.warn { color: var(--system-orange); }
  .acts { display: inline-flex; align-items: center; gap: var(--space-2); }
  .tabs { margin-top: var(--space-2); max-width: 100%; }
  .hint { margin-top: calc(-1 * var(--space-1)); }
  .empty { padding: var(--space-4) 0; }
  .folders, .files { list-style: none; margin: 0; padding: 0; }
  .folders > li { border-bottom: 1px solid var(--separator); }
  .frow { width: 100%; display: flex; align-items: center; gap: var(--space-2); min-height: var(--control-large); padding: var(--space-1) var(--space-2);
    border: 0; background: none; color: inherit; font: inherit; text-align: left; cursor: pointer; border-radius: var(--radius-sm); }
  .frow:hover { background: var(--fill-quaternary); }
  .frow > :global(svg:first-child) { flex: none; color: var(--label-secondary); }
  .path, .fname { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .num { flex: none; font-feature-settings: "tnum"; }
  .date { min-width: 9em; text-align: right; }
  .files { padding: 0 0 var(--space-2) var(--space-8); }
  .files li { display: flex; align-items: center; gap: var(--space-2); min-height: var(--control-regular, 28px); }
  .files li:nth-child(even) { background: var(--row-alt); }
  .foot { gap: var(--space-4) !important; }
  .foot a { color: var(--accent); text-decoration: none; }
  .more { align-self: flex-start; border: 0; padding: 0; background: none; color: var(--accent); font: inherit; cursor: pointer; }
  .foot-note { margin-top: var(--space-4); }
  .state { display: flex; flex-direction: column; align-items: center; gap: var(--space-3); padding: var(--space-10) var(--space-6); text-align: center; color: var(--label-secondary); }
  .state h2 { color: var(--label-primary); }
  .backdrop { position: fixed; inset: 0; z-index: 320; display: flex; align-items: center; justify-content: center; background: var(--media-scrim-light); }
</style>
