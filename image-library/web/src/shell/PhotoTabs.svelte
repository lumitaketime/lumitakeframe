<script>
  /** 「照片」底下的分頁：沿用照片圖庫的各個頁面（在「設定 → 功能與選單」關掉的不顯示）。 */
  import { t } from "../i18n/index.svelte.js";
  import { app } from "../lib/state.svelte.js";
  import { route, link } from "../lib/router.svelte.js";

  const TABS = [
    { href: "/", key: "photos.timeline", fixed: true, match: [""] },
    { href: "/favorites", key: "photos.favorites", match: ["favorites"] },
    { href: "/videos", key: "photos.videos", match: ["videos"] },
    { href: "/albums", key: "photos.albums", fixed: true, match: ["albums"] },
    { href: "/explore", key: "photos.explore", match: ["explore", "people", "keywords"] },
    { href: "/tools", key: "photos.tools", match: ["tools"] },
  ];
  const hidden = $derived(new Set((app.server?.ui?.nav_hidden || "").split(",").filter(Boolean)));
  const tabs = $derived(TABS.filter((x) => x.fixed || !hidden.has(x.href)));
  const page = $derived(route.path.split("/").filter(Boolean)[0] || "");
</script>

<nav class="tabs mac-body" aria-label={t("photos.tabs")}>
  {#each tabs as x (x.href)}
    {@const on = x.match.includes(page)}
    <a href={x.href} use:link class:on aria-current={on ? "page" : undefined}>{t(x.key)}</a>
  {/each}
</nav>

<style>
  .tabs { min-height: var(--control-large); display: flex; align-items: center; gap: var(--space-1); padding: 0 var(--space-3); border-bottom: 1px solid var(--separator); overflow-x: auto; scrollbar-width: none; }
  a { flex: none; padding: var(--space-1) var(--space-3); border-radius: var(--radius-capsule); color: var(--label-secondary); text-decoration: none; white-space: nowrap;
    transition: background-color var(--dur-fast) var(--ease), color var(--dur-fast) var(--ease); }
  a:hover { background: var(--fill-quaternary); color: var(--label-primary); }
  a.on { background: var(--selection-muted); color: var(--label-primary); font-weight: 600; }
</style>
