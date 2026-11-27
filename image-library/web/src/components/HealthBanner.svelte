<script>
  /** 每一頁最上面的提醒：有硬碟可能有狀況，Re'memor 先不處理它，請到「待辦」決定怎麼處理。 */
  import { Icon } from "../ui/index.js";
  import { t } from "../i18n/index.svelte.js";
  import { link } from "../lib/router.svelte.js";

  let { alerts } = $props();
  const names = $derived(alerts.map((a) => `「${a.name}」`).join("、"));
  const fail = $derived(alerts.some((a) => a.status === "fail"));
</script>

<div class="banner mac-callout" class:fail role="status">
  <Icon name="exclamation-triangle" size={14} />
  <span>{t("health.banner", { names })}</span>
  <a href="/inbox" use:link>{t("health.bannerAction")}</a>
</div>

<style>
  .banner { display: flex; align-items: center; gap: var(--space-2); flex-wrap: wrap; margin: var(--space-2) var(--space-4) 0; padding: var(--space-2) var(--space-3);
    border-radius: var(--radius-md); background: color-mix(in srgb, var(--system-orange) 14%, transparent); color: var(--label-primary); }
  .banner.fail { background: color-mix(in srgb, var(--system-red) 12%, transparent); }
  .banner > :global(svg) { flex: none; color: var(--system-orange); }
  .banner.fail > :global(svg) { color: var(--system-red); }
  a { color: var(--accent); font-weight: 600; }
</style>
