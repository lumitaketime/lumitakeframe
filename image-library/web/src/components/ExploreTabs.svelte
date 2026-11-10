<script>
  import { slider } from "../lib/slider.js";
  /** 探索頁的分頁：總覽、人物、關鍵字（在「功能與選單」關掉的不顯示）。 */
  import { app } from "../lib/state.svelte.js";
  import { route, link } from "../lib/router.svelte.js";

  const TABS = [
    { href: "/explore", label: "總覽", fixed: true },
    { href: "/people", label: "人物" },
    { href: "/keywords", label: "關鍵字" },
  ];
  const hidden = $derived(new Set((app.server?.ui?.nav_hidden || "").split(",").filter(Boolean)));
  const tabs = $derived(TABS.filter((t) => t.fixed || !hidden.has(t.href)));
  const on = (href) => route.path === href || route.path.startsWith(href + "/");
</script>

{#if tabs.length > 1}
  <nav class="tabs" aria-label="探索分類" use:slider={{ kind: "underline", key: "explore-tabs" }}>
    {#each tabs as t (t.href)}
      <a href={t.href} use:link class:on={on(t.href)} aria-current={on(t.href) ? "page" : undefined}>{t.label}</a>
    {/each}
  </nav>
{/if}

<style>
  .tabs { display: flex; gap: 4px; border-bottom: 1px solid var(--outline-variant); margin: -4px 0 18px; overflow-x: auto; scrollbar-width: none; overscroll-behavior-x: contain; }
  .tabs a {
    padding: 8px 16px 10px; text-decoration: none; color: var(--on-surface-variant); font-weight: 500; white-space: nowrap;
    border-bottom: 2px solid transparent; margin-bottom: -1px;
  }
  .tabs a:hover { color: var(--on-surface); }
  .tabs a.on { color: var(--primary); border-bottom-color: var(--primary); font-weight: 500; }
</style>
