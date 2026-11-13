<script>
  /**
   * 按鈕：立即執行一個動作。
   * variant：glassProminent／glass（浮在內容上）、borderedProminent／bordered（內容層）、borderless（文字）。
   * 一個畫面最多一到兩個 prominent；破壞性動作（role="destructive"）不能是主要按鈕。純圖示按鈕一定要給 aria-label。
   */
  import Icon from "./Icon.svelte";
  import ProgressIndicator from "./ProgressIndicator.svelte";
  import { t } from "../i18n/index.svelte.js";
  import { usePlatform } from "./platform.js";

  let {
    variant = "bordered", role = "normal", size = "regular", shape = "capsule", icon = "", iconOnly = false,
    loading = false, loadingLabel = "", disabled = false, platform: p = "", class: cls = "", type = "button", el = $bindable(), children, ...rest
  } = $props();
  // svelte-ignore state_referenced_locally（平台在元件建立時決定，之後不變）
  const platform = usePlatform(p);
  const iconSize = $derived(size === "mini" || size === "small" ? 13 : platform === "ios" ? 19 : 15);
</script>

<button bind:this={el} {type} disabled={disabled || loading} aria-busy={loading || undefined}
  class="lg-btn lg-btn-{variant} lg-btn-{size} lg-btn-{platform} lg-btn-shape-{iconOnly && shape === 'capsule' ? 'circle' : shape} {role !== 'normal' ? `lg-btn-role-${role}` : ''} {cls}"
  class:lg-btn-icononly={iconOnly} {...rest}>
  {#if loading}
    <ProgressIndicator kind="spinner" size="small" label={loadingLabel || t("common.working")} />
  {:else if icon}
    <Icon name={icon} size={iconSize} weight={platform === "ios" ? "medium" : "regular"} />
  {/if}
  {#if !iconOnly}
    <span class="lg-btn-label">{#if loading && loadingLabel}{loadingLabel}{:else}{@render children?.()}{/if}</span>
  {/if}
</button>
