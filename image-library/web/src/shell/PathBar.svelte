<script>
  /** 路徑列：「硬碟 › 資料夾 › 子資料夾」，每一段都可以按；最後一段是目前位置。 */
  import { Icon } from "../ui/index.js";
  import { t } from "../i18n/index.svelte.js";
  import { link } from "../lib/router.svelte.js";

  let { crumbs = [] } = $props();
</script>

<nav class="pathbar mac-callout" aria-label={t("path.label")}>
  <ol>
    {#each crumbs as c, i (i)}
      <li>
        {#if i}<Icon name="chevron-right" size={9} weight="bold" class="sep" />{/if}
        {#if i === crumbs.length - 1}
          <span class="here" aria-current="page">{#if c.icon}<Icon name={c.icon} size={13} weight="medium" />{/if}{c.label}</span>
        {:else}
          <a href={c.href} use:link>{#if c.icon}<Icon name={c.icon} size={13} weight="medium" />{/if}{c.label}</a>
        {/if}
      </li>
    {/each}
  </ol>
</nav>

<style>
  .pathbar { min-height: var(--target-mac); display: flex; align-items: center; padding: 0 var(--space-4); border-bottom: 1px solid var(--separator); overflow-x: auto; scrollbar-width: none; }
  ol { display: flex; align-items: center; gap: var(--space-1); list-style: none; margin: 0; padding: 0; white-space: nowrap; }
  li { display: flex; align-items: center; gap: var(--space-1); color: var(--label-secondary); }
  a, .here { display: inline-flex; align-items: center; gap: var(--space-1); padding: 2px var(--space-1); border-radius: var(--radius-xs); color: inherit; text-decoration: none; }
  a:hover { background: var(--fill-quaternary); color: var(--label-primary); }
  .here { color: var(--label-primary); font-weight: 600; }
  li :global(.sep) { color: var(--label-tertiary); flex: none; }
</style>
