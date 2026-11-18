<script>
  /**
   * 「別的地方也有一模一樣的副本」：只標完整比對過內容的。綠色＝別顆硬碟上也有（可以放心）；灰色＝只在同一顆硬碟上有別份。
   */
  import { Icon } from "../ui/index.js";
  import { t, formatNumber } from "../i18n/index.svelte.js";

  let { copies } = $props();
  const title = $derived(copies.other_drive
    ? t("copies.away", { n: formatNumber(copies.n), drives: copies.drives.join("、") })
    : t("copies.same", { n: formatNumber(copies.n) }));
</script>

<span class="copies" class:away={copies.other_drive} {title} role="img" aria-label={title}><Icon name="duplicate" size={12} /></span>

<style>
  .copies { flex: none; display: inline-flex; color: var(--label-tertiary); }
  .copies.away { color: var(--system-green); }
  :global(.on) .copies, :global([aria-selected="true"]) .copies { color: inherit; }
</style>
