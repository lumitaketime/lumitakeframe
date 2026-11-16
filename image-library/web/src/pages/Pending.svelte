<script>
  /**
   * 待刪除：在「重複項目」標記的多餘副本，依硬碟分組。這裡的項目只是標記，硬碟上還沒有任何變動，可以個別取消。
   * 一般硬碟：「移到垃圾桶」，要在警示視窗確認；引擎會逐項再驗證一次，不符的跳過並說明原因。
   * 唯讀的硬碟（NTFS）：改成「匯出清單」，存一個文字檔到 Mac，不寫入那顆硬碟。
   */
  import { Alert, Button, Icon, ProgressIndicator } from "../ui/index.js";
  import KindIcon from "../views/KindIcon.svelte";
  import { loadPending, unmarkItems, trashPending, exportPending } from "../data/dupes.js";
  import { loadCatalog } from "../data/catalog.svelte.js";
  import { setFrame } from "../shell/frame.svelte.js";
  import { t, formatNumber, formatBytes } from "../i18n/index.svelte.js";
  import { app, toast, refresh } from "../lib/state.svelte.js";
  import { link } from "../lib/router.svelte.js";

  let data = $state(null);
  let error = $state("");
  let busy = $state("");
  let asking = $state(null); // 要移到垃圾桶的那顆硬碟
  let skipped = $state({}); // 硬碟 → 上次被跳過的項目與原因
  const local = $derived(!!app.server?.local);

  async function load() {
    try {
      data = await loadPending();
      error = "";
    } catch (e) {
      error = e.message;
    }
  }
  $effect(() => {
    app.refreshKey;
    load();
  });
  $effect(() => {
    setFrame({ crumbs: [], location: null, info: null,
      status: data?.count ? t("pending.total", { count: formatNumber(data.count), size: formatBytes(data.bytes) || "0 KB" }) : "" });
  });
  async function after() {
    await Promise.all([load(), loadCatalog()]);
  }
  async function unmark(ids) {
    try {
      await unmarkItems(ids);
      await after();
    } catch (e) {
      toast(e.message, "error");
    }
  }
  async function trash() {
    const d = asking;
    asking = null;
    busy = d.drive;
    try {
      const res = await trashPending(d.items.filter((it) => !it.stale).map((it) => it.id));
      skipped[d.drive] = res.skipped;
      toast(res.trashed.length
        ? t("pending.trashed", { count: formatNumber(res.trashed.length), size: formatBytes(res.bytes) || "0 KB" })
        : t("pending.noneTrashed"), res.trashed.length ? "info" : "error", 8000);
      await after();
      refresh();
    } catch (e) {
      toast(e.message, "error");
    } finally {
      busy = "";
    }
  }
  async function exportList(d) {
    busy = d.drive;
    try {
      const res = await exportPending(d.drive);
      toast(t("pending.exported", { path: res.path }), "info", 10000);
    } catch (e) {
      toast(e.message, "error");
    } finally {
      busy = "";
    }
  }
  const hrefOf = (it) => {
    const folder = it.kind === "folder" ? it.path : it.path.includes("/") ? it.path.slice(0, it.path.lastIndexOf("/")) : "";
    return `/folders/${it.root_id}${folder ? `?path=${encodeURIComponent(folder)}` : ""}`;
  };
  const ready = (d) => d.items.filter((it) => !it.stale);
</script>

<div class="pending">
  {#if error}
    <div class="state" role="alert"><h2 class="mac-title-3">{t("view.error")}</h2><p class="mac-body">{error}</p><Button onclick={load}>{t("view.retry")}</Button></div>
  {:else if !data}
    <div class="state"><ProgressIndicator kind="spinner" label={t("view.loading")} /></div>
  {:else if !data.count}
    <div class="state">
      <h2 class="mac-title-3">{t("pending.empty")}</h2>
      <p class="mac-body">{t("pending.emptyHint")}</p>
      <a class="go mac-body" href="/duplicates" use:link>{t("pending.toDupes")}</a>
    </div>
  {:else}
    <p class="mac-body intro">{t("pending.intro")}</p>
    {#each data.drives as d (d.drive)}
      <section class="drive">
        <header>
          <Icon name={d.online ? "external-drive-fill" : "external-drive"} size={18} weight="medium" class={d.online ? "on" : "off"} />
          <div class="titles">
            <h2 class="mac-headline">{d.drive}
              {#if !d.online}<span class="tag mac-callout">{t("drive.offline")}</span>{/if}
              {#if d.read_only}<span class="tag mac-callout">{t("drive.readOnly")}</span>{/if}
            </h2>
            <p class="mac-callout sub">{t("pending.total", { count: formatNumber(d.items.length), size: formatBytes(d.bytes) || "0 KB" })}</p>
          </div>
          <Button variant="borderless" disabled={!!busy} onclick={() => unmark(d.items.map((it) => it.id))}>{t("pending.unmarkAll")}</Button>
          {#if d.read_only}
            <Button variant="bordered" loading={busy === d.drive} disabled={!!busy || !local} onclick={() => exportList(d)}>{t("pending.export")}</Button>
          {:else}
            <Button variant="bordered" role="destructive" loading={busy === d.drive} disabled={!!busy || !local || !d.online || !ready(d).length} onclick={() => (asking = d)}>{t("pending.trash")}</Button>
          {/if}
        </header>
        {#if d.read_only}<p class="mac-callout sub note">{t("pending.readOnlyHint")}</p>
        {:else if !d.online}<p class="mac-callout sub note">{t("pending.offlineHint", { name: d.drive })}</p>
        {:else if !local}<p class="mac-callout sub note">{t("pending.localOnly")}</p>{/if}
        <ul class="items mac-body">
          {#each d.items as it (it.id)}
            {@const why = skipped[d.drive]?.find((x) => x.id === it.id)?.reason}
            <li>
              <KindIcon kind={it.kind === "folder" ? "folder" : "other"} />
              <div class="where">
                <a href={hrefOf(it)} use:link class="path" title={it.path}>{it.root && it.root !== d.drive ? `${it.root} › ` : ""}{it.path.split("/").join(" › ")}</a>
                {#if it.stale}<span class="mac-callout warn">{t("pending.stale")}</span>
                {:else if why}<span class="mac-callout warn">{t("pending.skipped", { reason: why })}</span>{/if}
              </div>
              <span class="size">{formatBytes(it.size) || "0 KB"}</span>
              <button type="button" class="act mac-callout" disabled={!!busy} onclick={() => unmark([it.id])}>{t("pending.unmark")}</button>
            </li>
          {/each}
        </ul>
      </section>
    {/each}
  {/if}
</div>

{#if asking}
  {@const items = ready(asking)}
  <div class="backdrop">
    <Alert title={t("pending.trashTitle", { count: formatNumber(items.length), size: formatBytes(items.reduce((n, it) => n + it.size, 0)) || "0 KB" })}
      message={t("pending.trashMessage", { name: asking.drive })} actions={[
        { label: t("pending.trash"), role: "destructive", onPress: trash },
        { label: t("common.cancel"), role: "cancel", onPress: () => (asking = null) },
      ]} />
  </div>
{/if}

<style>
  .pending { padding: var(--space-4) var(--space-6) var(--space-8); max-width: 1100px; color: var(--label-primary); }
  h2, p { margin: 0; }
  .intro { color: var(--label-secondary); margin-bottom: var(--space-4); }
  .sub { color: var(--label-secondary); }
  .drive { margin-bottom: var(--space-6); border-radius: var(--radius-md); box-shadow: inset 0 0 0 1px var(--separator); overflow: hidden; }
  header { display: flex; align-items: center; gap: var(--space-3); padding: var(--space-3) var(--space-4); background: var(--fill-quaternary); }
  header :global(.on) { color: var(--accent); flex: none; }
  header :global(.off) { color: var(--label-secondary); flex: none; }
  .titles { flex: 1; min-width: 0; }
  .titles h2 { display: flex; align-items: center; gap: var(--space-2); }
  .tag { flex: none; padding: 0 var(--space-2); border-radius: var(--radius-capsule); box-shadow: inset 0 0 0 1px var(--separator); color: var(--label-secondary); font-weight: 400; }
  .note { padding: var(--space-2) var(--space-4) 0; }
  .items { list-style: none; margin: 0; padding: var(--space-2) var(--space-2) var(--space-2); }
  .items li { display: flex; align-items: center; gap: var(--space-3); min-height: var(--control-large); padding: var(--space-1) var(--space-2); border-radius: var(--radius-sm); }
  .items li:nth-child(even) { background: var(--row-alt); }
  .where { flex: 1; min-width: 0; display: flex; flex-direction: column; }
  .path { color: inherit; text-decoration: none; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; border-radius: var(--radius-xs); }
  .path:hover { color: var(--accent); text-decoration: underline; }
  .warn { color: var(--destructive); }
  .size { flex: none; color: var(--label-secondary); font-feature-settings: "tnum"; }
  .act { flex: none; padding: 2px var(--space-2); border: 0; border-radius: var(--radius-capsule); background: none; color: var(--accent); font: inherit; cursor: pointer; }
  .act:hover:not(:disabled) { background: var(--fill-tertiary); }
  .act:disabled { color: var(--label-tertiary); cursor: default; }
  .go { color: var(--accent); }
  .state { display: flex; flex-direction: column; align-items: center; gap: var(--space-3); padding: var(--space-10) var(--space-6); text-align: center; color: var(--label-secondary); }
  .state h2 { color: var(--label-primary); }
  .backdrop { position: fixed; inset: 0; z-index: 320; display: flex; align-items: center; justify-content: center; background: var(--media-scrim-light); }
</style>
