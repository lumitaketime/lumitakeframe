<script>
  /** 狀態列：左邊是目前內容的數量與大小，右邊是所在硬碟（或全部硬碟）的連線狀態。 */
  import { Icon } from "../ui/index.js";
  import { t, formatNumber, formatBytes } from "../i18n/index.svelte.js";
  import { catalog, catalogTotals } from "../data/catalog.svelte.js";

  let { status = "", location = null } = $props();
  const totals = $derived(catalogTotals());
  const fallback = $derived(
    !catalog.loaded ? "" : totals.bytes
      ? t("status.summary", { files: formatNumber(totals.files), size: formatBytes(totals.bytes) })
      : t("status.filesOnly", { files: formatNumber(totals.files) }));
  const online = $derived(catalog.drives.filter((d) => d.online).length);
</script>

<footer class="statusbar mac-callout" aria-label={t("status.label")}>
  <span class="left">{status || fallback}</span>
  <span class="right">
    {#if location}
      <Icon name={location.online ? "external-drive-fill" : "external-drive"} size={13} weight="medium" />
      {location.name} · {location.online ? t("drive.online") : t("drive.offline")}
    {:else if catalog.drives.length}
      {t("drive.count", { count: formatNumber(catalog.drives.length), online: formatNumber(online) })}
    {/if}
  </span>
</footer>

<style>
  .statusbar { min-height: var(--control-small); display: flex; align-items: center; justify-content: space-between; gap: var(--space-4);
    padding: 0 var(--space-4); padding-bottom: env(safe-area-inset-bottom); border-top: 1px solid var(--separator); color: var(--label-secondary); background: var(--control-bg); }
  .left, .right { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; min-width: 0; }
  .right { display: inline-flex; align-items: center; gap: var(--space-1); flex: none; max-width: 60%; }
</style>
