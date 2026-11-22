<script>
  /**
   * 設定 → 目錄 → 備份與管理：
   * - 備份：選存放位置（建議另一顆磁碟），立即備份；每週自動備份，只保留最近幾份自動備份（本人按的不會被拿掉）。
   * - 還原：改用某一份備份；目前這份收進「還原前的目錄」，不刪除；Re'memor 會重新開啟。
   * - 舊的目錄：搬移、還原後留下的那幾份，可以在 Finder 中查看或移到垃圾桶。
   * - 整理：清掉用不到的縮圖、整理資料庫；刪除整份目錄、從頭開始（移到垃圾桶，不是直接刪除）。
   * 全部只動 Re'memor 自己的目錄，不碰硬碟上的檔案。
   */
  import { Alert, Button, List, ListRow, PopUpButton, ProgressIndicator, Toggle } from "../ui/index.js";
  import { loadBackups, pickBackupFolder, setBackupFolder, backupNow, restoreBackup, trashOldCopy, resetCatalog, cleanCatalog, revealFolder, saveSetting } from "../data/settings.js";
  import { t, formatBytes, formatNumber, formatDateTime } from "../i18n/index.svelte.js";
  import { app, toast, refresh } from "../lib/state.svelte.js";

  let { size = 0 } = $props(); // 目錄現在多大（刪除前的警示用）

  let st = $state(null);
  let error = $state("");
  let busy = $state("");
  let confirm = $state(null); // {kind: restore|trash|reset, item}
  let restarting = $state(false);

  function load() {
    return loadBackups().then((d) => { st = d; error = ""; }).catch((e) => (error = e.message));
  }
  $effect(() => {
    app.refreshKey;
    if (!restarting) load();
  });
  const local = $derived(!!app.server?.local);
  const isMac = $derived(app.server?.platform === "darwin");
  const job = $derived(app.server?.jobs?.active?.find((j) => j.kind === "backup") || null);
  // 備份做完：重新列出
  let wasRunning = false;
  $effect(() => {
    const running = !!job;
    if (wasRunning && !running) load();
    wasRunning = running;
  });

  async function run(key, fn, message) {
    busy = key;
    try {
      const out = await fn();
      if (message) toast(typeof message === "function" ? message(out) : message);
      refresh();
      await load();
      return out;
    } catch (e) {
      toast(e.message, "error");
    } finally {
      busy = "";
    }
  }
  async function pick() {
    const path = await pickBackupFolder().catch((e) => toast(e.message, "error"));
    if (path) run("dir", () => setBackupFolder(path), t("set.backup.dirSet"));
  }
  const toggleAuto = (v) => run("auto", () => saveSetting("backup_auto", v ? 1 : 0));
  const setKeep = (v) => run("keep", () => saveSetting("backup_keep", Number(v)));
  const now = () => run("now", backupNow, t("set.backup.started"));

  /** 還原、重新開始之後 Re'memor 會重新開啟：等它回來再重新載入整個畫面 */
  function waitRestart() {
    restarting = true;
    const started = Date.now();
    const timer = setInterval(async () => {
      if (Date.now() - started < 2500) return;
      try {
        await loadBackups();
        clearInterval(timer);
        location.reload();
      } catch {
        if (Date.now() - started > 120000) {
          clearInterval(timer);
          restarting = false;
        }
      }
    }, 1500);
  }
  async function doConfirm() {
    const c = confirm;
    confirm = null;
    if (c.kind === "restore") {
      if (await run("restore", () => restoreBackup(c.item.path))) waitRestart();
    } else if (c.kind === "trash") {
      await run("trash", () => trashOldCopy(c.item.path), (out) => t("set.backup.trashed", { size: formatBytes(out?.freed || 0) || "0 KB" }));
    } else if (c.kind === "reset") {
      if (await run("reset", resetCatalog)) waitRestart();
    }
  }
  const clean = () => run("clean", cleanCatalog, (out) => t("set.backup.cleaned", { size: formatBytes(out?.freed || 0) || "0 KB" }));
  const when = (iso) => (iso ? formatDateTime(new Date(iso)) : "");
  const reveal = (path) => revealFolder(path).catch((e) => toast(e.message, "error"));
</script>

{#if restarting}
  <List header={t("set.backup.title")}>
    <ListRow title={t("set.catalog.restarting")}>
      {#snippet trailing()}<ProgressIndicator kind="spinner" size="small" label={t("set.catalog.restarting")} />{/snippet}
    </ListRow>
  </List>
{:else if !st}
  <List header={t("set.backup.title")} footer={error}>
    <div class="pad">{#if !error}<ProgressIndicator kind="spinner" size="small" label={t("view.loading")} />{/if}</div>
  </List>
{:else}
  <List header={t("set.backup.title")} footer={t("set.backup.footer")}>
    <ListRow title={t("set.backup.dir")} subtitle={st.dir ? (st.dir_error || st.dir) : t("set.backup.noDir")}
      icon={st.dir && !st.dir_ok ? "exclamation-triangle" : undefined} iconTint="orange">
      {#snippet trailing()}{#if local}<span class="acts">
        {#if st.dir && st.dir_ok}<Button size="small" variant="bordered" onclick={() => reveal(st.dir)}>{t("menu.reveal")}</Button>{/if}
        {#if isMac}<Button size="small" variant={st.dir ? "bordered" : "borderedProminent"} loading={busy === "dir"} disabled={!!busy} onclick={pick}>{st.dir ? t("set.backup.change") : t("set.backup.choose")}</Button>{/if}
      </span>{/if}{/snippet}
    </ListRow>
    <ListRow title={t("set.backup.auto")} subtitle={!st.dir ? t("set.backup.autoNeedsDir") : st.last ? t("set.backup.last", { date: when(st.last) }) : t("set.backup.never")}>
      {#snippet trailing()}<Toggle checked={st.auto} disabled={!!busy} onchange={toggleAuto} aria-label={t("set.backup.auto")} />{/snippet}
    </ListRow>
    {#if st.auto}
      <ListRow title={t("set.backup.keep")} subtitle={t("set.backup.keepHint")}>
        {#snippet trailing()}<PopUpButton value={String(st.keep)} onchange={setKeep}
          options={[2, 4, 8, 12].map((n) => ({ value: String(n), label: t("set.backup.keepN", { n }) }))} />{/snippet}
      </ListRow>
    {/if}
    {#if job}
      <ListRow title={t("set.backup.running")} subtitle={job.message || ""}>
        {#snippet trailing()}<ProgressIndicator kind="circular" size="small" value={job.total ? job.done / job.total : undefined} label={t("set.backup.running")} />{/snippet}
      </ListRow>
    {:else if local}
      <ListRow title={t("set.backup.now")} subtitle={t("set.backup.nowHint")}>
        {#snippet trailing()}<Button size="small" variant="bordered" loading={busy === "now"} disabled={!!busy || !st.dir_ok} onclick={now}>{t("set.backup.nowButton")}</Button>{/snippet}
      </ListRow>
    {/if}
  </List>

  {#if st.backups.length}
    <List header={t("set.backup.list", { n: formatNumber(st.backups.length) })} footer={t("set.backup.restoreHint")}>
      {#each st.backups as b (b.path)}
        <ListRow title={when(b.created_at)} icon={b.auto ? "clock" : "archive"}
          subtitle={[b.auto ? t("set.backup.autoTag") : t("set.backup.manualTag"), formatBytes(b.bytes), b.files != null ? t("set.backup.files", { n: formatNumber(b.files) }) : ""].filter(Boolean).join(" · ")}>
          {#snippet trailing()}{#if local}<Button size="small" variant="bordered" disabled={!!busy || !!job} onclick={() => (confirm = { kind: "restore", item: b })}>{t("set.backup.restore")}</Button>{/if}{/snippet}
        </ListRow>
      {/each}
    </List>
  {/if}

  {#if st.old_copies.length}
    <List header={t("set.backup.old")} footer={t("set.backup.oldHint")}>
      {#each st.old_copies as o (o.path)}
        <ListRow title={o.path.split("/").filter(Boolean).pop()} subtitle={`${o.path} · ${formatBytes(o.bytes) || "0 KB"}`}>
          {#snippet trailing()}{#if local}<span class="acts">
            <Button size="small" variant="bordered" onclick={() => reveal(o.path)}>{t("menu.reveal")}</Button>
            <Button size="small" variant="bordered" role="destructive" disabled={!!busy} onclick={() => (confirm = { kind: "trash", item: o })}>{t("set.backup.toTrash")}</Button>
          </span>{/if}{/snippet}
        </ListRow>
      {/each}
    </List>
  {/if}

  {#if local}
    <List header={t("set.backup.tidy")} footer={t("set.backup.tidyHint")}>
      <ListRow title={t("set.backup.clean")} subtitle={t("set.backup.cleanHint")}>
        {#snippet trailing()}<Button size="small" variant="bordered" loading={busy === "clean"} disabled={!!busy} onclick={clean}>{t("set.backup.cleanButton")}</Button>{/snippet}
      </ListRow>
      <ListRow title={t("set.backup.reset")} subtitle={t("set.backup.resetHint")}>
        {#snippet trailing()}<Button size="small" variant="bordered" role="destructive" disabled={!!busy || !!job} onclick={() => (confirm = { kind: "reset" })}>{t("set.backup.resetButton")}</Button>{/snippet}
      </ListRow>
    </List>
  {/if}
{/if}

{#if confirm}
  <div class="backdrop">
    {#if confirm.kind === "restore"}
      <Alert title={t("set.backup.restoreTitle", { date: when(confirm.item.created_at) })} message={t("set.backup.restoreMessage")} actions={[
        { label: t("set.backup.restore"), role: "default", onPress: doConfirm },
        { label: t("common.cancel"), role: "cancel", onPress: () => (confirm = null) },
      ]} />
    {:else if confirm.kind === "trash"}
      <Alert title={t("set.backup.trashTitle", { size: formatBytes(confirm.item.bytes) || "0 KB" })} message={`${confirm.item.path}\n\n${t("set.backup.trashMessage")}`} actions={[
        { label: t("set.backup.toTrash"), role: "destructive", onPress: doConfirm },
        { label: t("common.cancel"), role: "cancel", onPress: () => (confirm = null) },
      ]} />
    {:else}
      <Alert title={t("set.backup.resetTitle", { size: formatBytes(size) || "0 KB" })} message={t("set.backup.resetMessage")} actions={[
        { label: t("set.backup.toTrash"), role: "destructive", onPress: doConfirm },
        { label: t("common.cancel"), role: "cancel", onPress: () => (confirm = null) },
      ]} />
    {/if}
  </div>
{/if}

<style>
  .pad { padding: var(--space-2) var(--space-3); }
  .acts { display: inline-flex; align-items: center; gap: var(--space-2); }
  .backdrop { position: fixed; inset: 0; z-index: 320; display: flex; align-items: center; justify-content: center; background: var(--media-scrim-light); }
</style>
