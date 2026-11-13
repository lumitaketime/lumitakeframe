<script>
  /** 開關：開或關，立即生效。 */
  import { usePlatform, TYPE, uid } from "./platform.js";

  let { checked = $bindable(false), onchange, label = "", size = "regular", disabled = false, platform: p = "", class: cls = "", "aria-label": ariaLabel = undefined } = $props();
  // svelte-ignore state_referenced_locally（平台在元件建立時決定，之後不變）
  const platform = usePlatform(p);
  const id = uid("toggle");
  function flip() {
    checked = !checked;
    onchange?.(checked);
  }
</script>

<span class="lg-toggle-row {cls}">
  {#if label}<label for={id} class="lg-toggle-label {TYPE[platform].body}">{label}</label>{/if}
  <button {id} type="button" role="switch" aria-checked={!!checked} {disabled} aria-label={label ? undefined : ariaLabel}
    class="lg-switch lg-switch-{platform}" class:lg-switch-mini={size === "mini"} class:lg-on={checked} onclick={flip}>
    <span class="lg-switch-knob"></span>
  </button>
</span>
