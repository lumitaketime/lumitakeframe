<script>
  /** 列表：以文字為主的資料列，可分群組並有頁首頁尾。裡面放 ListRow。內容層元件，不用玻璃。 */
  import { usePlatform, providePlatform, TYPE } from "./platform.js";

  let { appearance = "insetGrouped", header = "", footer = "", alternating = false, platform: p = "", class: cls = "", children } = $props();
  // svelte-ignore state_referenced_locally（平台在元件建立時決定，之後不變）
  const platform = usePlatform(p);
  providePlatform(platform);
</script>

<section class="lg-list lg-list-{appearance} lg-list-{platform} {cls}" class:lg-list-alt={alternating}>
  {#if header}<div class="lg-list-header {platform === 'ios' ? 'ios-footnote' : 'mac-headline'}">{header}</div>{/if}
  <div class="lg-list-body" role="list">{@render children?.()}</div>
  {#if footer}<div class="lg-list-footer {TYPE[platform].footnote}">{footer}</div>{/if}
</section>
