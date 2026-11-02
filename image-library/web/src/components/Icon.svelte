<script>
  let { path, size = 24, title = "", class: cls = "" } = $props();
</script>

<svg class={cls} width={size} height={size} viewBox="0 0 24 24" aria-hidden={title ? undefined : "true"} role={title ? "img" : undefined}>
  {#if title}<title>{title}</title>{/if}
  <path d={path} fill="currentColor" />
</svg>

<style>
  svg { display: block; flex-shrink: 0; }
</style>
