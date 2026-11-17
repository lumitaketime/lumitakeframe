<script>
  /**
   * 硬碟總覽：每顆硬碟一張卡片（不論有沒有接上），可以掃描、停止、從目錄移除；
   * 已接上但還沒加入目錄的硬碟只顯示「加入目錄」按鈕，不會自動掃描。
   */
  import { Alert, Button, Icon, ProgressIndicator } from "../ui/index.js";
  import { catalog, loadCatalog } from "../data/catalog.svelte.js";
  import { loadDrivesDetail, scanRoots, stopJob, addRoot, pickFolder, removeRoot } from "../data/drives.js";
  import { setFrame } from "../shell/frame.svelte.js";
  import { t, formatNumber, formatBytes, formatDate } from "../i18n/index.svelte.js";
  import { app, toast, refresh } from "../lib/state.svelte.js";
  import { link } from "../lib/router.svelte.js";

  let detail = $state(null);
  let error = $state("");
  let busy = $state("");
  let removing = $state(null);
  const local = $derived(!!app.server?.local);

  async function load() {
    try {
      detail = await loadDrivesDetail();
      error = "";
    } catch (e) {
      error = e.message;
    }
  }
  // 進頁面、工作結束、有硬碟開始或結束掃描時重新讀取；掃描中的進度直接用側邊欄那份（每幾秒更新、很輕）
  const scanningKeys = $derived(catalog.drives.filter((d) => d.scanning).map((d) => d.key).join(","));
  const onlineKeys = $derived(catalog.drives.filter((d) => d.online).map((d) => d.key).join(","));
  $effect(() => {
    app.refreshKey;
    scanningKeys;
    onlineKeys;
    load();
  });
  const live = (d) => catalog.drives.find((x) => x.key === d.key) || d;
  $effect(() => {
    setFrame({ crumbs: [], status: "", location: null, info: null });
  });

  const GROUP = { raw: "photo", package: "other" };
  function segments(d) {
    const sums = {};
    for (const k of d.kinds || []) sums[GROUP[k.kind] || k.kind] = (sums[GROUP[k.kind] || k.kind] || 0) + k.bytes;
    const base = d.capacity || d.bytes || 1;
    return Object.entries(sums).filter(([, b]) => b > 0).sort((a, b) => b[1] - a[1]).map(([kind, bytes]) => ({ kind, bytes, pct: (bytes / base) * 100 }));
  }
  async function act(key, fn, done) {
    busy = key;
    try {
      await fn();
      if (done) toast(done);
      await Promise.all([loadCatalog(), load()]);
      refresh();
    } catch (e) {
      toast(e.message, "error");
    } finally {
      busy = "";
    }
  }
  const scan = (d) => act(d.key, () => scanRoots(d.roots.map((r) => r.name)), t("drives.scanStarted", { name: d.name }));
  const stop = (d) => act(d.key, () => stopJob(detail?.scan_job), t("drives.stopped"));
  const add = (v) => act(v.path, () => addRoot(v.path, v.name), t("drives.added", { name: v.name }));
  async function addFolder(key) {
    busy = key;
    try {
      const path = await pickFolder();
      if (path) await act(key, () => addRoot(path), t("drives.addedFolder"));
    } catch (e) {
      toast(e.message, "error");
    } finally {
      busy = "";
    }
  }
  async function confirmRemove() {
    const d = removing;
    removing = null;
    await act(d.key, async () => { for (const r of d.roots) await removeRoot(r.id); }, t("drives.removed", { name: d.name }));
  }
</script>

<div class="drives">
  <header class="top">
    <span class="grow"></span>
    {#if local}<Button variant="bordered" icon="plus" disabled={!!busy} onclick={() => addFolder("pick")}>{t("drives.addFolder")}</Button>{/if}
  </header>

  {#if error}
    <div class="state" role="alert"><h2 class="mac-title-3">{t("view.error")}</h2><p class="mac-body">{error}</p><Button onclick={load}>{t("view.retry")}</Button></div>
  {:else if !detail}
    <div class="state"><ProgressIndicator kind="spinner" label={t("view.loading")} /></div>
  {:else}
    {#if detail.new.length}
      <h2 class="mac-headline section">{t("drives.newTitle")}</h2>
      <div class="cards">
        {#each detail.new as v (v.path)}
          <article class="card new">
            <div class="head">
              <span class="glyph"><Icon name="external-drive-fill" size={22} weight="medium" /></span>
              <div class="titles"><h3 class="mac-headline">{v.name}</h3>
                <p class="mac-callout sub">{[v.fs_label, v.capacity ? formatBytes(v.capacity) : ""].filter(Boolean).join(" · ")}{#if v.read_only}<span class="badge">{t("drive.readOnly")}</span>{/if}</p></div>
            </div>
            <p class="mac-callout sub">{t("drives.newHint")}</p>
            <div class="actions">
              <Button variant="borderedProminent" loading={busy === v.path} disabled={!!busy} onclick={() => add(v)}>{t("drives.add")}</Button>
              <Button variant="borderless" disabled={!!busy} onclick={() => addFolder(v.path)}>{t("drives.addOnlyFolder")}</Button>
            </div>
          </article>
        {/each}
      </div>
      {#if detail.drives.length}<h2 class="mac-headline section">{t("drives.catalogTitle")}</h2>{/if}
    {/if}

    {#if !detail.drives.length && !detail.new.length}
      <div class="state">
        <h2 class="mac-title-3">{t("drive.noDrives")}</h2>
        {#if local}<Button variant="borderedProminent" onclick={() => addFolder("pick")}>{t("drives.addFolder")}</Button>{:else}<p class="mac-body">{t("drives.addOnMac")}</p>{/if}
      </div>
    {/if}

    <div class="cards">
      {#each detail.drives as d0 (d0.key)}
        {@const d = { ...d0, ...live(d0), kinds: d0.kinds }}
        {@const segs = segments(d)}
        <article class="card" class:offline={!d.online}>
          <div class="head">
            <span class="glyph"><Icon name={d.online ? "external-drive-fill" : "external-drive"} size={22} weight="medium" /></span>
            <div class="titles">
              <h3 class="mac-headline"><a href={`/folders/${d.roots[0].id}`} use:link>{d.name}</a></h3>
              <p class="mac-callout sub">
                {[d.fs_label, d.capacity ? formatBytes(d.capacity) : ""].filter(Boolean).join(" · ")}
                {#if d.read_only || d.fs_label === "NTFS"}<span class="badge">{t("drive.readOnly")}</span>{/if}
              </p>
            </div>
            <span class="mac-callout state-tag" class:on={d.online}>
              {#if d.scanning}
                <ProgressIndicator kind="circular" size="small" value={d.progress ?? undefined} label={t("drive.scanning")} />
                {d.progress != null ? t("drive.scanningPercent", { percent: Math.round(d.progress * 100) }) : t("drive.scanning")}
              {:else}{d.online ? t("drive.online") : t("drive.offline")}{/if}
            </span>
          </div>

          <div class="bar" role="img" aria-label={t("drives.barLabel", { used: formatBytes(d.bytes) || "0", total: d.capacity ? formatBytes(d.capacity) : "—" })}>
            {#each segs as s (s.kind)}<i style:width="{Math.max(0.6, s.pct)}%" style:background="var(--kind-{s.kind})"></i>{/each}
          </div>
          <p class="mac-callout sub">{d.capacity ? t("drive.capacity", { used: formatBytes(d.bytes) || "0 KB", total: formatBytes(d.capacity) }) : formatBytes(d.bytes)} · {t("status.filesOnly", { files: formatNumber(d.files) })}</p>
          {#if segs.length}
            <ul class="legend mac-callout">
              {#each segs.slice(0, 6) as s (s.kind)}
                <li><i class="dot" style:background="var(--kind-{s.kind})" aria-hidden="true"></i>{t(`kind.${s.kind}`)} <span class="sub">{formatBytes(s.bytes)}</span></li>
              {/each}
            </ul>
          {/if}
          <p class="mac-callout sub">
            {d.last_scan ? t("drive.lastScan", { date: formatDate(new Date(d.last_scan)) }) : t("drive.neverScanned")}{#if d.last_scan && !d.complete} · {t("drive.incomplete")}{/if}
          </p>

          <div class="actions">
            {#if d.scanning}
              <Button variant="bordered" loading={busy === d.key} disabled={!!busy} onclick={() => stop(d)}>{t("drives.stop")}</Button>
            {:else}
              <Button variant="bordered" loading={busy === d.key} disabled={!!busy || !d.online} onclick={() => scan(d)}>{d.last_scan ? t("drives.rescan") : t("drives.scan")}</Button>
            {/if}
            <span class="grow"></span>
            <Button variant="borderless" role="destructive" disabled={!!busy || d.scanning} onclick={() => (removing = d)}>{t("drives.remove")}</Button>
          </div>
          {#if !d.online && !d.scanning}<p class="mac-callout sub">{t("drives.connectToScan", { name: d.name })}</p>{/if}
        </article>
      {/each}
    </div>
  {/if}
</div>

{#if removing}
  <div class="backdrop">
    <Alert title={t("drives.removeTitle", { name: removing.name })} message={t("drives.removeMessage", { files: formatNumber(removing.files) })} actions={[
      { label: t("drives.remove"), role: "destructive", onPress: confirmRemove },
      { label: t("common.cancel"), role: "cancel", onPress: () => (removing = null) },
    ]} />
  </div>
{/if}

<style>
  .drives { padding: var(--space-4) var(--space-6) var(--space-8); max-width: 1200px; color: var(--label-primary); }
  .top { display: flex; align-items: center; justify-content: space-between; gap: var(--space-3); margin-bottom: var(--space-4); }
  h2, h3, p { margin: 0; }
  .section { margin: var(--space-5) 0 var(--space-3); color: var(--label-secondary); }
  .cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: var(--space-4); }
  .card { display: flex; flex-direction: column; gap: var(--space-3); padding: var(--space-4); border-radius: var(--radius-lg); background: var(--fill-quaternary);
    box-shadow: inset 0 0 0 1px var(--separator); }
  .head { display: flex; align-items: flex-start; gap: var(--space-3); }
  .glyph { display: inline-flex; color: var(--accent); margin-top: 2px; }
  .card.offline .glyph { color: var(--label-secondary); }
  .titles { flex: 1; min-width: 0; }
  .titles h3 { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .titles a { color: inherit; text-decoration: none; border-radius: var(--radius-xs); }
  .titles a:hover { text-decoration: underline; }
  .sub { color: var(--label-secondary); }
  .badge { display: inline-block; margin-left: var(--space-2); padding: 0 var(--space-2); border-radius: var(--radius-capsule); box-shadow: inset 0 0 0 1px var(--separator); color: var(--label-primary); }
  .state-tag { flex: none; display: inline-flex; align-items: center; gap: var(--space-1); color: var(--label-secondary); }
  .state-tag.on { color: var(--label-primary); }
  .bar { display: flex; gap: 1px; height: var(--space-2); border-radius: var(--radius-capsule); overflow: hidden; background: var(--fill-secondary); }
  .bar i { display: block; height: 100%; }
  .legend { list-style: none; margin: 0; padding: 0; display: flex; flex-wrap: wrap; gap: var(--space-1) var(--space-4); }
  .legend li { display: inline-flex; align-items: center; gap: var(--space-1); }
  .dot { width: var(--space-2); height: var(--space-2); border-radius: var(--radius-capsule); flex: none; }
  .actions { display: flex; align-items: center; gap: var(--space-2); margin-top: auto; }
  .grow { flex: 1; }
  .state { display: flex; flex-direction: column; align-items: center; gap: var(--space-3); padding: var(--space-10) var(--space-6); text-align: center; color: var(--label-secondary); }
  .state h2 { color: var(--label-primary); }
  .backdrop { position: fixed; inset: 0; z-index: 320; display: flex; align-items: center; justify-content: center; background: var(--media-scrim-light); }
</style>
