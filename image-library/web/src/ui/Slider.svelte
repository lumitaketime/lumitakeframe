<script>
  /** 滑桿：從一段範圍選一個值；最小值在前、最大值在後。 */
  import Icon from "./Icon.svelte";
  import { usePlatform, TYPE, uid } from "./platform.js";

  let { value = $bindable(50), min = 0, max = 100, step = 1, onchange, ticks = 0, minIcon = "", maxIcon = "", label = "", valueLabel = undefined, disabled = false, class: cls = "" } = $props();
  const platform = usePlatform();
  const id = uid("slider");
  const pct = $derived(((value - min) / (max - min)) * 100);
</script>

<div class="lg-slider lg-slider-{platform} {cls}" class:lg-disabled={disabled}>
  {#if label}<label for={id} class="lg-field-label {TYPE[platform].body}">{label}</label>{/if}
  <div class="lg-slider-row">
    {#if minIcon}<Icon name={minIcon} size={platform === "ios" ? 17 : 13} class="lg-slider-end" />{/if}
    <div class="lg-slider-track-wrap">
      <input {id} type="range" {min} {max} {step} bind:value {disabled} aria-valuetext={valueLabel ? valueLabel(value) : undefined}
        oninput={() => onchange?.(value)} style:--lg-pct="{pct}%" style:--pct="{pct}%" class="lg-range" />
      {#if ticks > 1}<div class="lg-ticks" aria-hidden="true">{#each Array(ticks) as _, i (i)}<i></i>{/each}</div>{/if}
    </div>
    {#if maxIcon}<Icon name={maxIcon} size={platform === "ios" ? 17 : 13} class="lg-slider-end" />{/if}
  </div>
</div>
