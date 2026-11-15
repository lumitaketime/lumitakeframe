<script>
  /**
   * 工具列：（窄視窗或側邊欄收起時的選單鈕）、上一頁／下一頁、標題、檢視切換、搜尋、資訊欄開關。
   * 按鈕群組是膠囊形玻璃；工具列本身不墊色塊。
   */
  import { Toolbar, SegmentedControl, Slider } from "../ui/index.js";
  import { prefs, viewFor, setView, setIconSize, VIEWS, ALL_VIEWS, ICON_MIN, ICON_MAX } from "../views/prefs.svelte.js";
  import SearchBox from "../components/SearchBox.svelte";
  import FilterButton from "../components/FilterButton.svelte";
  import { filterUI } from "../lib/filter.svelte.js";
  import { t } from "../i18n/index.svelte.js";
  import { route } from "../lib/router.svelte.js";
  import { frame, toggleSidebar } from "./frame.svelte.js";

  let { title = "", compact = false, narrowSearch = false, place = "", infoOpen = false, ontoggleinfo } = $props();
  let searchOpen = $state(false);

  // 上一頁／下一頁：記住在 App 裡走到過的最遠一步，才知道「下一頁」能不能按
  let idx = $state(history.state?.idx ?? 0);
  let top = $state(history.state?.idx ?? 0);
  $effect(() => {
    route.path;
    route.query;
    const now = history.state?.idx ?? 0;
    if (now > idx) top = now; // 往前走了新的一步：之後的紀錄作廢
    idx = now;
  });

  const VIEW_ICONS = { icons: "grid", list: "list", columns: "columns", tree: "tree", treemap: "treemap" };
  // 圖像與列表可以用；直欄、樹狀、佔比在下一步接上
  const views = $derived(ALL_VIEWS.map((v) => ({ value: v, icon: VIEW_ICONS[v], ariaLabel: t(`toolbar.view.${v}`), disabled: !VIEWS.includes(v) })));
  const view = $derived(place ? viewFor(place) : "");

  const leading = $derived([
    ...(compact ? [[{ icon: "menu", label: t("nav.openMenu"), onClick: () => (frame.drawer = true) }]]
      : !frame.sidebar ? [[{ icon: "sidebar", label: t("nav.showSidebar"), onClick: toggleSidebar }]] : []),
    [
      { icon: "chevron-left", label: t("common.back"), onClick: () => history.back(), disabled: idx <= 0 },
      { icon: "chevron-right", label: t("common.forward"), onClick: () => history.forward(), disabled: idx >= top },
    ],
  ]);
  const trailing = $derived(compact ? [] : [[{ icon: "sidebar-right", label: infoOpen ? t("toolbar.hideInfo") : t("toolbar.showInfo"), onClick: ontoggleinfo }]]);
</script>

<Toolbar platform="mac" title={searchOpen && narrowSearch ? "" : title} {leading} {trailing} edgeEffect={false} class="app-toolbar">
  {#snippet centerExtra()}
    {#if place}
      <SegmentedControl segments={compact ? views.filter((v) => !v.disabled) : views} value={view} onchange={(v) => setView(place, v)} ariaLabel={t("toolbar.view")} />
      {#if view === "icons" && !compact}
        <div class="size"><Slider value={prefs.iconSize} min={ICON_MIN} max={ICON_MAX} step={8} onchange={setIconSize} ariaLabel={t("view.iconSize")} /></div>
      {/if}
    {/if}
  {/snippet}
  {#snippet trailingExtra()}
    <div class="search" class:narrow={narrowSearch}><SearchBox narrow={narrowSearch} bind:expanded={searchOpen} /></div>
    {#if filterUI.pages && !(searchOpen && narrowSearch)}<FilterButton />{/if}
  {/snippet}
</Toolbar>

<style>
  :global(.app-toolbar) { flex: none; padding-top: env(safe-area-inset-top); }
  .search { display: flex; justify-content: flex-end; width: clamp(180px, 26vw, 360px); }
  .search.narrow { width: auto; }
  .size { width: 110px; flex: none; margin: 0 var(--space-2); }
</style>
