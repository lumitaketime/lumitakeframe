<script>
  /**
   * 工具列：（窄視窗或側邊欄收起時的選單鈕）、上一頁／下一頁、標題、檢視切換、搜尋、資訊欄開關。
   * 按鈕群組是膠囊形玻璃；工具列本身不墊色塊。
   */
  import { Toolbar, SegmentedControl, Slider, PullDownButton } from "../ui/index.js";
  import { prefs, viewFor, viewsFor, setView, setIconSize, chooseSort, setDesc, setGroup, SORTS, GROUPS, ALL_VIEWS, ICON_MIN, ICON_MAX } from "../views/prefs.svelte.js";
  import SearchBox from "../components/SearchBox.svelte";
  import FilterButton from "../components/FilterButton.svelte";
  import { filterUI } from "../lib/filter.svelte.js";
  import { t } from "../i18n/index.svelte.js";
  import { route } from "../lib/router.svelte.js";
  import { frame, toggleSidebar } from "./frame.svelte.js";

  let { title = "", compact = false, place = "", infoOpen = false, ontoggleinfo } = $props();
  let searchOpen = $state(false);

  // 依工具列實際可用的寬度分段（側邊欄、資訊欄、紅綠燈都會吃掉寬度，所以量工具列本身，不看視窗）：
  // full：全部顯示；mid：排序只剩圖示、收起縮圖滑桿；small：再收起標題（路徑列已經有位置）；
  // tiny：檢視切換改成下拉選單、搜尋改成圖示。每一段都確保按鈕不會互相重疊。
  let width = $state(1200);
  const extra = $derived(compact || !frame.sidebar ? 48 : 0); // 選單鈕或「顯示側邊欄」鈕
  const room = $derived(width - extra);
  const tier = $derived(!place ? (room < 520 ? "tiny" : "full") : room >= 1060 ? "full" : room >= 760 ? "mid" : room >= 580 ? "small" : "tiny");
  const narrowSearch = $derived(tier === "tiny");

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
  // 直欄、樹狀、佔比只有在資料夾裡能用；類型與標籤是跨硬碟的平面清單
  const views = $derived(ALL_VIEWS.map((v) => ({ value: v, icon: VIEW_ICONS[v], ariaLabel: t(`toolbar.view.${v}`), disabled: !viewsFor(place).includes(v) })));
  const view = $derived(place ? viewFor(place) : "");
  const viewItems = $derived([
    { header: t("toolbar.view") },
    ...views.map((v, i) => ({ label: t(`toolbar.view.${v.value}`), checked: v.value === view, disabled: v.disabled, shortcut: `⌘${i + 1}`,
      onSelect: () => setView(place, v.value) })),
  ]);
  // 排序方式：所有檢視共用（佔比圖固定依大小，所以不顯示）
  // 分組只在圖像與列表；其他檢視顯示但不能選
  const canGroup = $derived(view === "icons" || view === "list");
  const grouped = $derived(canGroup && prefs.group !== "none");
  const sortItems = $derived([
    { header: t("group.by") },
    ...GROUPS.map((key) => ({ label: t(`group.${key}`), checked: prefs.group === key, disabled: !canGroup, onSelect: () => setGroup(key) })),
    { separator: true },
    { header: t("sort.by") },
    ...SORTS.map((key) => ({ label: t(`sort.${key}`), checked: prefs.sort === key, onSelect: () => chooseSort(key) })),
    { separator: true },
    { label: t("sort.asc"), checked: !prefs.desc, onSelect: () => setDesc(false) },
    { label: t("sort.desc"), checked: prefs.desc, onSelect: () => setDesc(true) },
  ]);

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

<div class="tbwrap" bind:clientWidth={width}>
<Toolbar platform="mac" title={(searchOpen && narrowSearch) || tier === "small" || tier === "tiny" ? "" : title} {leading} {trailing} edgeEffect={false}
  class="app-toolbar tier-{tier}">
  {#snippet centerExtra()}
    {#if place}
      {#if tier === "tiny"}
        <PullDownButton label={t("toolbar.view")} icon={VIEW_ICONS[view] || "grid"} iconOnly variant="glass" items={viewItems} menuWidth={200} />
      {:else}
        <SegmentedControl segments={views} value={view} onchange={(v) => setView(place, v)} ariaLabel={t("toolbar.view")} />
      {/if}
      {#if view !== "treemap" && place !== "roots"}
        <PullDownButton label={grouped ? t("group.button", { by: t(`group.${prefs.group}`) }) : t("sort.button", { by: t(`sort.${prefs.sort}`) })} icon="sort" iconOnly={tier !== "full"} variant="glass" items={sortItems} menuWidth={260} />
      {/if}
      {#if view === "icons" && tier === "full"}
        <div class="size"><Slider value={prefs.iconSize} min={ICON_MIN} max={ICON_MAX} step={8} onchange={setIconSize} ariaLabel={t("view.iconSize")} /></div>
      {/if}
    {/if}
  {/snippet}
  {#snippet trailingExtra()}
    <div class="search" class:narrow={narrowSearch}><SearchBox narrow={narrowSearch} bind:expanded={searchOpen} /></div>
    {#if filterUI.pages && !(searchOpen && narrowSearch)}<FilterButton />{/if}
  {/snippet}
</Toolbar>
</div>

<style>
  .tbwrap { min-width: 0; }
  :global(.app-toolbar) { flex: none; padding-top: env(safe-area-inset-top); }
  /* 標題可以縮短，但不會把按鈕擠到重疊；各區塊不縮小到比內容窄 */
  :global(.app-toolbar .lg-zone-center), :global(.app-toolbar .lg-zone-trailing) { flex: none; }
  :global(.app-toolbar .lg-toolbar-titles) { min-width: 0; overflow: hidden; }
  :global(.app-toolbar .lg-zone-leading > .lg-tool-group) { flex: none; }
  .search { display: flex; justify-content: flex-end; width: clamp(180px, 26vw, 360px); }
  :global(.tier-mid) .search, :global(.tier-small) .search { width: 180px; }
  .search.narrow { width: auto; }
  /* 縮圖大小滑桿：設計系統的滑桿預設最少 200 寬，在工具列上會蓋到搜尋欄，這裡固定成 110 */
  .size { width: 110px; flex: none; margin: 0 var(--space-3) 0 var(--space-2); }
  .size :global(.lg-slider) { min-width: 0; width: 100%; }
</style>
