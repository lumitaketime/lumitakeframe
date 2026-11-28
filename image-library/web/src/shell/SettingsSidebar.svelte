<script>
  /**
   * 設定的側邊欄（像 Mac 的「系統設定」）：進入設定時取代 App 的側邊欄。
   * 最上面是「搜尋設定」，下面是各分類（彩色圓角圖示）；搜尋時改列出符合的項目，點一下就跳到那一頁並標出那一項。
   * 最下面「返回」回到進設定前看的那一頁（和 App 側邊欄的「設定」在同一個位置）。
   */
  import { Icon, SearchField } from "../ui/index.js";
  import { t } from "../i18n/index.svelte.js";
  import { route, navigate } from "../lib/router.svelte.js";
  import { CATS, resolveCat, searchSettings } from "../lib/settings.js";
  import { frame } from "./frame.svelte.js";

  let { width = 240, onpick = () => {} } = $props();

  let query = $state("");
  const current = $derived(resolveCat(route.path.split("/").filter(Boolean)[1] || "") || (frame.compact ? "" : "general"));
  const results = $derived(searchSettings(query, t));
  const tint = (c) => (/^gray/.test(c) ? `var(--${c})` : `var(--system-${c})`);
  const catOf = (id) => CATS.find((c) => c.id === id) || CATS[0];

  function open(id, sub = "", label = "") {
    frame.settingsFocus = label;
    navigate(`/settings/${id}${sub ? `/${sub}` : ""}`);
    onpick();
  }
  function back() {
    navigate(frame.back || "/overview");
    onpick();
  }
  function onkeydown(e) {
    if (e.key === "Enter" && results.length) { e.preventDefault(); const r = results[0]; open(r.cat, r.sub, r.whole ? "" : r.label); }
    if (e.key === "Escape" && query) { e.preventDefault(); query = ""; }
  }
</script>

<nav class="lg-sidebar lg-sidebar-mac lg-sidebar-inline set-side" style:width="{width}px" aria-label={t("set.categories")}>
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div class="lg-side-top top" {onkeydown}>
    <SearchField bind:value={query} placeholder={t("set.search")} />
  </div>
  <div class="scroll">
    {#if query.trim()}
      {#if results.length}
        <ul class="lg-side-list" aria-label={t("set.searchResults")}>
          {#each results as r (r.cat + r.sub + r.label)}
            {@const c = catOf(r.cat)}
            <li><button type="button" class="lg-side-item row result" onclick={() => open(r.cat, r.sub, r.whole ? "" : r.label)}>
              <span class="tile" style:background={tint(c.tint)} aria-hidden="true"><Icon name={c.icon} size={12} weight="medium" /></span>
              <span class="text"><span class="mac-body label">{r.label}</span>{#if !r.whole}<span class="mac-caption-1 where">{r.pane}</span>{/if}</span>
            </button></li>
          {/each}
        </ul>
      {:else}
        <p class="none mac-callout">{t("set.searchNone", { q: query.trim() })}</p>
      {/if}
    {:else}
      <ul class="lg-side-list">
        {#each CATS as c (c.id)}
          {#if c.id === "about"}<li class="gap" aria-hidden="true"></li>{/if}
          <li><button type="button" class="lg-side-item row" class:lg-on={current === c.id} aria-current={current === c.id ? "page" : undefined} onclick={() => open(c.id)}>
            <span class="tile" style:background={tint(c.tint)} aria-hidden="true"><Icon name={c.icon} size={12} weight="medium" /></span>
            <span class="mac-body label">{t(`set.cat.${c.id}`)}</span>
          </button></li>
        {/each}
      </ul>
    {/if}
  </div>
  <ul class="lg-side-list bottom">
    <li><button type="button" class="lg-side-item row" onclick={back}>
      <span class="back-icon" aria-hidden="true"><Icon name="chevron-left" size={13} weight="semibold" /></span>
      <span class="mac-body label">{t("set.back")}</span>
    </button></li>
  </ul>
</nav>

<style>
  .set-side { height: 100%; gap: var(--space-2); }
  .top { padding: 0 var(--space-1) var(--space-1); }
  .scroll { flex: 1; min-height: 0; overflow-y: auto; }
  .row { height: 32px; gap: var(--space-2); padding: 0 var(--space-2) 0 var(--space-1); }
  .row.lg-on { font-weight: 400; }
  .row.lg-on .label { font-weight: 600; }
  .result { height: auto; min-height: 36px; padding-top: var(--space-1); padding-bottom: var(--space-1); }
  .tile { flex: none; width: 22px; height: 22px; display: inline-flex; align-items: center; justify-content: center; border-radius: var(--radius-sm); color: var(--on-accent);
    box-shadow: var(--shadow-rim); }
  .text { flex: 1; min-width: 0; display: flex; flex-direction: column; }
  .label { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .where { color: var(--label-secondary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .gap { height: var(--space-3); }
  .none { margin: var(--space-3) var(--space-2); color: var(--label-secondary); }
  .bottom { border-top: 1px solid var(--separator); padding-top: var(--space-2); }
  .back-icon { flex: none; width: 22px; display: inline-flex; justify-content: center; color: var(--accent); }
</style>
