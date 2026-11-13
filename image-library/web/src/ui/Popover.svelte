<script>
  /** 彈出視窗：暫時性的內容，箭頭指向開啟它的控制項。 */
  import { usePlatform, TYPE } from "./platform.js";

  let { arrow = "top", width = 280, title = "", class: cls = "", children } = $props();
  const platform = usePlatform();
</script>

<div role="dialog" aria-label={title || undefined} class="lg-popover lg-arrow-{arrow} {cls}" style:width="{width}px">
  <span class="lg-popover-arrow lg-glass lg-glass-regular" aria-hidden="true"></span>
  <div class="lg-popover-card lg-glass lg-glass-regular">
    {#if title}<div class="lg-popover-title {TYPE[platform].headline}">{title}</div>{/if}
    {@render children?.()}
  </div>
</div>
