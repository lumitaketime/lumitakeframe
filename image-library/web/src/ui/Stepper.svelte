<script>
  /** 步進器：小幅增減一個數值，一定放在它改變的數值旁邊。Mac 上按住 Shift 一次加減十倍。 */
  import Icon from "./Icon.svelte";
  import { t } from "../i18n/index.svelte.js";
  import { usePlatform, TYPE } from "./platform.js";

  let { value = $bindable(0), min = -Infinity, max = Infinity, step = 1, onchange, label = "", format = (x) => String(x), class: cls = "" } = $props();
  const platform = usePlatform();
  function bump(dir, e) {
    const mult = platform === "mac" && e?.shiftKey ? 10 : 1;
    value = Math.max(min, Math.min(max, value + dir * step * mult));
    onchange?.(value);
  }
</script>

<div class="lg-stepper-row {cls}">
  {#if label}<span class="lg-stepper-label {TYPE[platform].body}">{label}</span>{/if}
  {#if platform === "ios"}
    <output class="lg-stepper-value {TYPE.ios.body}" aria-live="polite">{format(value)}</output>
    <div class="lg-stepper-ios" role="group" aria-label={label || undefined}>
      <button type="button" aria-label={t("common.decrease")} disabled={value <= min} onclick={(e) => bump(-1, e)}><Icon name="minus" size={17} weight="semibold" /></button>
      <span class="lg-stepper-div"></span>
      <button type="button" aria-label={t("common.increase")} disabled={value >= max} onclick={(e) => bump(1, e)}><Icon name="plus" size={17} weight="semibold" /></button>
    </div>
  {:else}
    <span class="lg-stepper-field"><output class="lg-stepper-value {TYPE.mac.body}" aria-live="polite">{format(value)}</output></span>
    <div class="lg-stepper-mac" role="group" aria-label={label || undefined}>
      <button type="button" aria-label={t("common.increase")} disabled={value >= max} onclick={(e) => bump(1, e)}><svg viewBox="0 0 10 6" aria-hidden="true"><path d="M1.5 5L5 1.5 8.5 5" /></svg></button>
      <button type="button" aria-label={t("common.decrease")} disabled={value <= min} onclick={(e) => bump(-1, e)}><svg viewBox="0 0 10 6" aria-hidden="true"><path d="M1.5 1L5 4.5 8.5 1" /></svg></button>
    </div>
  {/if}
</div>
