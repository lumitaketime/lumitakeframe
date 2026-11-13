<script>
  /** 分段控制：等寬的幾段，選一個檢視或選項。每段用文字或圖示，不要混用；純圖示要給 ariaLabel。 */
  import Icon from "./Icon.svelte";
  import { usePlatform } from "./platform.js";

  let { segments = [], value = $bindable(), onchange, momentary = false, fullWidth = false, size = "regular", ariaLabel = "", class: cls = "" } = $props();
  const platform = usePlatform();
  let el;
  const current = $derived(value !== undefined ? value : segments[0]?.value);
  const index = $derived(segments.findIndex((s) => s.value === current));
  const n = $derived(segments.length || 1);
  function set(v) {
    if (!momentary) value = v;
    onchange?.(v);
  }
  function onkeydown(e) {
    if (momentary) return;
    const d = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
    if (!d) return;
    e.preventDefault();
    let k = index;
    for (let step = 0; step < n; step++) {
      k = (k + d + n) % n;
      if (!segments[k].disabled) break;
    }
    set(segments[k].value);
    el.querySelectorAll("button")[k]?.focus();
  }
</script>

<div bind:this={el} role={momentary ? "group" : "radiogroup"} aria-label={ariaLabel || undefined}
  class="lg-seg lg-seg-{platform} lg-seg-{size} {cls}" class:lg-seg-full={fullWidth} class:lg-seg-momentary={momentary}
  style:grid-template-columns="repeat({n}, 1fr)" {onkeydown}>
  {#if !momentary && index >= 0}<span class="lg-seg-thumb" style:width="calc((100% - 4px) / {n})" style:transform="translateX({index * 100}%)"></span>{/if}
  {#each segments as s, i (s.value)}
    {@const sel = !momentary && i === index}
    <button type="button" role={momentary ? undefined : "radio"} aria-checked={momentary ? undefined : sel} tabindex={momentary || sel ? 0 : -1}
      aria-label={s.icon && !s.label ? s.ariaLabel || s.value : undefined} title={s.icon && !s.label ? s.ariaLabel : undefined} disabled={s.disabled}
      class="lg-seg-btn {platform === 'ios' ? 'ios-subheadline' : 'mac-body'}" class:lg-on={sel} onclick={() => set(s.value)}>
      {#if s.icon}<Icon name={s.icon} size={platform === "ios" ? 17 : 14} weight="medium" />{:else}{s.label}{/if}
    </button>
  {/each}
</div>
