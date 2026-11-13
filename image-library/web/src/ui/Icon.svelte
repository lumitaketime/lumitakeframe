<script>
  /** 介面圖示（24×24 格線）。沒有 title 時視為裝飾，不會被螢幕閱讀器讀出。 */
  import { ICONS } from "./icons.js";

  let { name, size = 17, weight = "regular", title = "", class: cls = "", style = "" } = $props();
  const WEIGHT = { regular: 1.7, medium: 1.9, semibold: 2.1, bold: 2.4 };
  const body = $derived(ICONS[name]);
</script>

{#if body}
  <svg class="lg-icon {cls}" {style} width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
    stroke-width={WEIGHT[weight] || WEIGHT.regular} stroke-linecap="round" stroke-linejoin="round"
    role={title ? "img" : undefined} aria-label={title || undefined} aria-hidden={title ? undefined : "true"} focusable="false">
    {#if title}<title>{title}</title>{/if}{@html body}
  </svg>
{/if}
