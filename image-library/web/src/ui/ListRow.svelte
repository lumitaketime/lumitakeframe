<script>
  /**
   * 列表的一列：圖示、標題、副標、右側的說明與附屬物。
   * accessory："disclosure"（進入下一層）、"checkmark"、"info"，或用 trailing 放任何元件（例如 Toggle）。
   */
  import Icon from "./Icon.svelte";
  import { t } from "../i18n/index.svelte.js";
  import { usePlatform, TYPE } from "./platform.js";

  let { title, subtitle = "", detail = "", icon = "", iconTint = "blue", accessory = "none", selected = false, destructive = false, disabled = false,
    onclick = undefined, href = undefined, class: cls = "", trailing } = $props();
  const platform = usePlatform();
  const interactive = $derived(!!(onclick || href));
  const tag = $derived(href ? "a" : interactive ? "button" : "div");
  const tint = $derived(/^gray/.test(iconTint) ? `var(--${iconTint})` : `var(--system-${iconTint})`);
</script>

<div role="listitem" class="lg-row-li">
  <!-- svelte-ignore a11y_no_static_element_interactions（有 onclick 時一定是 button 或 a） -->
  <svelte:element this={tag} {href} type={tag === "button" ? "button" : undefined} {onclick} disabled={tag === "button" ? disabled : undefined} aria-current={selected || undefined}
    class="lg-row {cls}" class:lg-row-interactive={interactive} class:lg-row-selected={selected} class:lg-row-destructive={destructive} class:lg-row-disabled={disabled}>
    {#if icon}<span class="lg-row-icon" style:background={tint}><Icon name={icon} size={platform === "ios" ? 18 : 13} weight="medium" /></span>{/if}
    <span class="lg-row-text">
      <span class="lg-row-title {TYPE[platform].body}">{title}</span>
      {#if subtitle}<span class="lg-row-sub {platform === 'ios' ? 'ios-subheadline' : 'mac-callout'}">{subtitle}</span>{/if}
    </span>
    {#if detail}<span class="lg-row-detail {TYPE[platform].body}">{detail}</span>{/if}
    {#if trailing}
      <span class="lg-row-acc">{@render trailing()}</span>
    {:else if accessory !== "none"}
      <span class="lg-row-acc">
        {#if accessory === "disclosure"}<Icon name="chevron-right" size={platform === "ios" ? 14 : 11} weight="semibold" class="lg-row-chev" />
        {:else if accessory === "checkmark"}<Icon name="checkmark" size={platform === "ios" ? 17 : 13} weight="semibold" class="lg-row-check" title={t("common.selected")} />
        {:else if accessory === "info"}<Icon name="info" size={platform === "ios" ? 22 : 15} class="lg-row-info" title={t("common.moreInfo")} />{/if}
      </span>
    {/if}
  </svelte:element>
</div>
