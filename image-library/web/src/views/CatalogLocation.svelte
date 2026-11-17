<script>
  /**
   * 目錄放在哪裡（設定 → 目錄、首次使用第二步共用）：顯示位置與大小，可以搬到其他磁碟或搬回這台 Mac。
   * 搬移＝複製並確認完整後才改用，原本那份留著由本人決定要不要刪（永不自動刪除）；搬好後自動重新開啟。
   */
  import { Alert, Button, List, ListRow, ProgressIndicator } from "../ui/index.js";
  import { loadCatalogLocation, pickCatalogFolder, checkCatalogMove, moveCatalog, revealFolder } from "../data/settings.js";
  import { stopJob } from "../data/find.svelte.js";
  import { t, formatBytes, formatDuration } from "../i18n/index.svelte.js";
  import { app, toast, refresh } from "../lib/state.svelte.js";

  let { header = "", showSize = true } = $props();

  let loc = $state(null);
  let error = $state("");
  let asking = $state(null); // { path, target }
  let busy = $state(false);
  let restarting = $state(false);
  function load() {
    return loadCatalogLocation().then((d) => { loc = d; error = ""; return d; }).catch((e) => { error = e.message; });
  }
  $effect(() => {
    app.refreshKey;
    if (!restarting) load();
  });

  const local = $derived(!!app.server?.local);
  const isMac = $derived(app.server?.platform === "darwin");
  const job = $derived(app.server?.jobs?.active?.find((j) => j.kind === "move_catalog") || null);
  const otherJob = $derived(!!app.server?.jobs?.active?.some((j) => j.kind !== "move_catalog"));
  const external = (p) => /^\/Volumes\//.test(p || "");
  // 對話框標題用短名字：「這台 Mac」或磁碟（資料夾）名稱；完整路徑放在說明裡
  function shortName(target) {
    if (target === loc?.default) return t("set.catalog.thisMac");
    const parts = target.split("/").filter(Boolean);
    if (parts[0] === "Volumes" && parts[1]) return parts[1];
    return parts.length > 1 ? parts[parts.length - 2] : target;
  }

  async function choose(path) {
    if (!path) return;
    busy = true;
    try {
      const r = await checkCatalogMove(path);
      if (r.error) toast(r.error, "error");
      else asking = { path, target: r.target };
    } catch (e) {
      toast(e.message, "error");
    } finally {
      busy = false;
    }
  }
  async function pick() {
    try {
      choose(await pickCatalogFolder());
    } catch (e) {
      toast(e.message, "error");
    }
  }
  async function start() {
    const { path } = asking;
    asking = null;
    const before = loc?.home;
    try {
      await moveCatalog(path);
      refresh();
    } catch (e) {
      toast(e.message, "error");
      return;
    }
    // 搬好後伺服器會自己重新開啟；等它回來、位置換了，就重新載入整個畫面
    const timer = setInterval(async () => {
      const running = app.server?.jobs?.active?.some((j) => j.kind === "move_catalog");
      if (running) return;
      restarting = true;
      try {
        const d = await loadCatalogLocation();
        if (d.home !== before) {
          clearInterval(timer);
          location.reload();
        }
      } catch {
        /* 正在重新開啟，等一下再問 */
      }
    }, 2000);
    setTimeout(() => {
      clearInterval(timer);
      restarting = false;
      load();
    }, 120000);
  }
  async function stop() {
    try {
      await stopJob(job?.id);
      refresh();
    } catch (e) {
      toast(e.message, "error");
    }
  }
  function reveal(path) {
    revealFolder(path).catch((e) => toast(e.message, "error"));
  }
</script>

<List header={header || t("set.catalog.where")} footer={error || t("set.catalog.whereHint")}>
  {#if !loc}
    <div class="pad"><ProgressIndicator kind="spinner" size="small" label={t("view.loading")} /></div>
  {:else}
    <ListRow title={t("set.catalog.folder")} subtitle={loc.home}>
      {#snippet trailing()}{#if local}<Button size="small" variant="bordered" onclick={() => reveal(loc.home)}>{t("menu.reveal")}</Button>{/if}{/snippet}
    </ListRow>
    {#if showSize}
      <ListRow title={t("set.catalog.used")} detail={t("set.catalog.usedValue", { size: formatBytes(loc.bytes) || "0 KB", free: formatBytes(loc.free) })} />
    {/if}
    {#if job}
      <ListRow title={t("set.catalog.moving")}
        subtitle={(job.total ? `${formatBytes(job.done) || "0 KB"}／${formatBytes(job.total)}` : t("dupes.waiting")) + (job.eta ? ` · ${t("dupes.remaining", { time: formatDuration(job.eta) })}` : "")}>
        {#snippet trailing()}<span class="row-acts"><ProgressIndicator kind="circular" size="small" value={job.total ? job.done / job.total : undefined} label={t("set.catalog.moving")} /><Button size="small" variant="bordered" onclick={stop}>{t("drives.stop")}</Button></span>{/snippet}
      </ListRow>
    {:else if restarting}
      <ListRow title={t("set.catalog.restarting")}>
        {#snippet trailing()}<ProgressIndicator kind="spinner" size="small" label={t("set.catalog.restarting")} />{/snippet}
      </ListRow>
    {:else if local}
      <ListRow title={t("set.catalog.change")} subtitle={otherJob ? t("set.catalog.waitJobs") : t("set.catalog.changeHint")}>
        {#snippet trailing()}<span class="row-acts">
          {#if loc.moved}<Button size="small" variant="bordered" disabled={busy || otherJob} onclick={() => choose(loc.default)}>{t("set.catalog.backToMac")}</Button>{/if}
          {#if isMac}<Button size="small" variant="bordered" disabled={busy || otherJob} onclick={pick}>{t("set.catalog.choose")}</Button>{/if}
        </span>{/snippet}
      </ListRow>
    {/if}
    {#if loc.old_copy && !job}
      <ListRow title={t("set.catalog.oldCopy")} subtitle={t("set.catalog.oldCopyHint", { path: loc.old_copy })}>
        {#snippet trailing()}{#if local}<Button size="small" variant="bordered" onclick={() => reveal(loc.old_copy)}>{t("menu.reveal")}</Button>{/if}{/snippet}
      </ListRow>
    {/if}
  {/if}
</List>

{#if asking}
  <div class="backdrop">
    <Alert title={t("set.catalog.confirmTitle", { path: shortName(asking.target) })}
      message={`${asking.target}\n\n` + t("set.catalog.confirmMessage", { size: formatBytes(loc?.bytes || 0) || "0 KB" }) + (external(asking.target) ? ` ${t("set.catalog.externalWarn")}` : "")}
      actions={[
        { label: t("set.catalog.move"), role: "default", onPress: start },
        { label: t("common.cancel"), role: "cancel", onPress: () => (asking = null) },
      ]} />
  </div>
{/if}

<style>
  .pad { padding: var(--space-2) var(--space-3); }
  .row-acts { display: inline-flex; align-items: center; gap: var(--space-2); }
  .backdrop { position: fixed; inset: 0; z-index: 320; display: flex; align-items: center; justify-content: center; background: var(--media-scrim-light); }
</style>
