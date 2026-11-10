<script>
  /**
   * Re'memor 文字標誌：Manrope Bold、字距 −3.5%，撇號用記憶橘（#FF8D28）。
   * 淺色背景用藏青（#0B2346）、深色背景用白色，跟著系統的淺色／深色外觀切換。
   */
  let { size = 22 } = $props();
</script>

<span class="wordmark" style:font-size="{size}px" aria-label="Re'memor">Re<span class="apos" aria-hidden="true">’</span>memor</span>

<style>
  .wordmark {
    font-family: "Manrope", var(--font-family, system-ui), sans-serif; font-weight: 700; letter-spacing: -0.035em;
    line-height: 1; white-space: nowrap; color: var(--brand-ink, #0b2346);
  }
  .apos { color: #ff8d28; }
</style>
