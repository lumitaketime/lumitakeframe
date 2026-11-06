<script>
  /** 設定區塊的標題：說明文字收進 ⓘ，需要時才展開。 */
  import { slide } from "svelte/transition";
  import Icon from "./Icon.svelte";
  import { mdiInformationVariantCircleOutline } from "../lib/icons.js";

  let { icon, title, children } = $props();
  let open = $state(false);
</script>

<h2 class="st-title">
  {#if icon}<Icon path={icon} />{/if}<span>{title}</span>
  {#if children}
    <button class="icon-btn info" class:on={open} onclick={() => (open = !open)} aria-expanded={open} aria-label="{title}的說明" title="說明">
      <Icon path={mdiInformationVariantCircleOutline} size={20} />
    </button>
  {/if}
</h2>
{#if children && open}
  <p class="st-desc" transition:slide={{ duration: 180 }}>{@render children()}</p>
{/if}

<style>
  .st-title { display: flex; align-items: center; gap: 10px; }
  .info { width: 32px; height: 32px; color: var(--on-surface-variant); margin-left: -2px; }
  .info.on { color: var(--primary); }
  .st-desc { margin: -4px 0 12px; font-size: 14px; line-height: 20px; color: var(--on-surface-variant); max-width: 68ch; }
</style>
