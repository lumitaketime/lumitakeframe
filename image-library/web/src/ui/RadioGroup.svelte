<script>
  /** 單選：兩到五個互斥的選項。方向鍵切換。 */
  import { usePlatform, TYPE, uid } from "./platform.js";

  let { options = [], value = $bindable(), onchange, label = "", orientation = "vertical", disabled = false, class: cls = "" } = $props();
  const platform = usePlatform();
  const id = uid("radio");
  let el;
  function set(v) {
    value = v;
    onchange?.(v);
  }
  function onkeydown(e) {
    const dir = e.key === "ArrowDown" || e.key === "ArrowRight" ? 1 : e.key === "ArrowUp" || e.key === "ArrowLeft" ? -1 : 0;
    if (!dir) return;
    e.preventDefault();
    const enabled = options.filter((o) => !o.disabled);
    const next = enabled[(enabled.findIndex((o) => o.value === value) + dir + enabled.length) % enabled.length];
    if (!next) return;
    set(next.value);
    el.querySelectorAll('[role="radio"]')[options.indexOf(next)]?.focus();
  }
</script>

<div bind:this={el} role="radiogroup" tabindex="-1" aria-labelledby={label ? id : undefined} class="lg-radios lg-radios-{orientation} {cls}" {onkeydown}>
  {#if label}<span {id} class="lg-field-label {TYPE[platform].body}">{label}</span>{/if}
  {#each options as o, i (o.value)}
    {@const sel = o.value === value}
    <button type="button" role="radio" aria-checked={sel} tabindex={sel || (value === undefined && i === 0) ? 0 : -1} disabled={disabled || o.disabled}
      class="lg-radio" class:lg-on={sel} onclick={() => set(o.value)}>
      <span class="lg-radio-dot"></span><span class={TYPE[platform].body}>{o.label}</span>
    </button>
  {/each}
</div>
