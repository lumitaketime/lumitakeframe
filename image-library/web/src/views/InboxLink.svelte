<script>
  /** 「還有 N 件在待辦」：各頁不再各自列一份等你決定的事，改成一條連到「待辦」的提示。 */
  import { Icon } from "../ui/index.js";
  import { catalog } from "../data/catalog.svelte.js";
  import { t, formatNumber } from "../i18n/index.svelte.js";
  import { link } from "../lib/router.svelte.js";

  let { text = "", tone = "info" } = $props();
</script>

{#if text || catalog.inbox}
  <a class="inbox-link mac-callout tone-{tone}" href="/inbox" use:link>
    <Icon name={tone === "warn" ? "exclamation-triangle" : "checkmark"} size={14} />
    <span>{text || t("inbox.linkText", { n: formatNumber(catalog.inbox) })}</span>
    <Icon name="chevron-right" size={12} />
  </a>
{/if}

<style>
  .inbox-link { display: flex; align-items: center; gap: var(--space-2); padding: var(--space-2) var(--space-3); border-radius: var(--radius-md);
    background: color-mix(in srgb, var(--accent) 10%, transparent); color: var(--label-primary); text-decoration: none; }
  .inbox-link:hover { background: color-mix(in srgb, var(--accent) 16%, transparent); }
  .inbox-link > :global(svg:first-child) { flex: none; color: var(--accent); }
  .inbox-link > :global(svg:last-child) { flex: none; margin-left: auto; color: var(--label-secondary); }
  .inbox-link span { min-width: 0; }
  .tone-warn { background: color-mix(in srgb, var(--system-orange) 14%, transparent); }
  .tone-warn:hover { background: color-mix(in srgb, var(--system-orange) 20%, transparent); }
  .tone-warn > :global(svg:first-child) { color: var(--system-orange); }
</style>
