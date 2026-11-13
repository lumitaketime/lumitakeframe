<script>
  /** 搜尋欄：佔位文字說明可以搜尋什麼；可帶篩選標籤（tokens）與範圍（scopes）。glass 用在工具列上。 */
  import Icon from "./Icon.svelte";
  import SegmentedControl from "./SegmentedControl.svelte";
  import { t } from "../i18n/index.svelte.js";
  import { usePlatform, TYPE } from "./platform.js";

  let { placeholder = "", value = $bindable(""), onchange, onsubmit, tokens = [], onremovetoken, scopes = [], scope = $bindable(), onscopechange, glass = false,
    width = undefined, input = $bindable(), class: cls = "" } = $props();
  const platform = usePlatform();
  const ph = $derived(placeholder || t("common.search"));
  const w = $derived(typeof width === "number" ? `${width}px` : width || null);
</script>

<div class="lg-search-wrap {cls}" style:width={w}>
  <!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_noninteractive_element_interactions -->
  <div role="search" class="lg-search lg-search-{platform} {glass ? 'lg-glass lg-glass-regular lg-shape-capsule' : ''}" onclick={() => input?.focus()}>
    <Icon name="magnifyingglass" size={platform === "ios" ? 17 : 13} weight="medium" class="lg-search-glyph" />
    {#each tokens as tk (tk)}
      <span class="lg-token {TYPE[platform].sub}">{tk}
        {#if onremovetoken}<button type="button" aria-label={t("common.removeToken", { name: tk })} onclick={(e) => { e.stopPropagation(); onremovetoken(tk); }}><Icon name="xmark" size={9} weight="bold" /></button>{/if}
      </span>
    {/each}
    <input bind:this={input} type="search" class={TYPE[platform].body} bind:value placeholder={tokens.length ? "" : ph} aria-label={ph}
      oninput={() => onchange?.(value)} onkeydown={(e) => { if (e.key === "Enter") onsubmit?.(value); }} />
    {#if value}
      <button type="button" class="lg-field-clear" aria-label={t("common.clearSearch")} onclick={(e) => { e.stopPropagation(); value = ""; onchange?.(""); input?.focus(); }}>
        <span><Icon name="xmark" size={9} weight="bold" /></span>
      </button>
    {/if}
  </div>
  {#if scopes.length}
    <SegmentedControl fullWidth ariaLabel={t("common.searchScope")} bind:value={scope} onchange={onscopechange} segments={scopes} class="lg-scope" />
  {/if}
</div>
