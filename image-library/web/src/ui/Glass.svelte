<script>
  /** Liquid Glass 材質：只用在浮在內容上方的控制層（側邊欄、工具列、選單），不用在內容本身。 */
  let { variant = "regular", shape = "rounded", dim = false, interactive = false, as = "div", class: cls = "", children, ...rest } = $props();
</script>

<svelte:element this={as} class="lg-glass lg-glass-{variant} lg-shape-{shape} {cls}" class:lg-glass-dimmed={dim} class:lg-glass-interactive={interactive} {...rest}>
  {@render children?.()}
</svelte:element>
