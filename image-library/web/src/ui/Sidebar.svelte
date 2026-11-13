<script>
  /**
   * 側邊欄：App 的主要導覽，浮在內容上的玻璃面板；最多兩層。
   * sections：[{title, items: [{value, label, icon, badge, children, muted, trailing}]}]
   * muted：次要文字色（例如未連線的硬碟）；trailing：列尾的文字（例如「未連線」），狀態不能只靠顏色表示。
   */
  import Icon from "./Icon.svelte";
  import { t } from "../i18n/index.svelte.js";
  import { usePlatform, TYPE } from "./platform.js";

  let { sections = [], value = $bindable(), onchange, floating = true, width = 220, class: cls = "", header, footer } = $props();
  const platform = usePlatform();
  let closed = $state({});
  function pick(it) {
    value = it.value;
    onchange?.(it.value, it);
  }
</script>

{#snippet row(it, depth)}
  {@const sel = it.value === value}
  {@const kids = depth === 0 && it.children?.length > 0}
  {@const open = !closed[it.value]}
  <li>
    <button type="button" aria-current={sel ? "page" : undefined} aria-expanded={kids ? open : undefined}
      class="lg-side-item {TYPE[platform].body}" class:lg-on={sel} class:lg-side-sub={depth > 0} onclick={() => pick(it)}>
      {#if kids}
        <!-- svelte-ignore a11y_click_events_have_key_events -->
        <span class="lg-side-disc" class:lg-open={open} role="presentation" onclick={(e) => { e.stopPropagation(); closed[it.value] = open; }}>
          <Icon name="chevron-right" size={10} weight="bold" />
        </span>
      {:else if depth === 0}<span class="lg-side-disc-space"></span>{/if}
      {#if it.icon}<Icon name={it.icon} size={platform === "ios" ? 20 : 15} weight="medium" class="lg-side-icon" />{/if}
      <span class="lg-side-label" style:color={it.muted ? "var(--label-glass-secondary)" : null}>{it.label}</span>
      {#if it.trailing}<span class="lg-side-badge {TYPE[platform].callout}">{it.trailing}</span>{/if}
      {#if it.badge != null}<span class="lg-side-badge {TYPE[platform].callout}">{it.badge}</span>{/if}
    </button>
    {#if kids && open}<ul class="lg-side-list">{#each it.children as k (k.value)}{@render row(k, 1)}{/each}</ul>{/if}
  </li>
{/snippet}

<nav aria-label={t("common.sidebar")} class="lg-sidebar lg-sidebar-{platform} {floating ? 'lg-glass lg-glass-regular lg-sidebar-floating' : 'lg-sidebar-inline'} {cls}" style:width="{width}px">
  {#if header}<div class="lg-side-top">{@render header()}</div>{/if}
  {#each sections as s, i (i)}
    <div class="lg-side-section">
      {#if s.title}<div class="lg-side-heading {platform === 'ios' ? 'ios-title-3' : 'mac-subheadline'}">{s.title}</div>{/if}
      <ul class="lg-side-list">{#each s.items as it (it.value)}{@render row(it, 0)}{/each}</ul>
    </div>
  {/each}
  {#if footer}<div class="lg-side-top">{@render footer()}</div>{/if}
</nav>
