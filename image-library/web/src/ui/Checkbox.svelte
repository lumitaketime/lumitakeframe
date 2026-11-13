<script>
  /** 核取方塊：開、關，或「混合」（checked="mixed"，底下的項目狀態不一致時）。 */
  import Icon from "./Icon.svelte";
  import { usePlatform, TYPE } from "./platform.js";

  let { checked = $bindable(false), onchange, label = "", disabled = false, class: cls = "", ...rest } = $props();
  const platform = usePlatform();
  const mixed = $derived(checked === "mixed");
  function flip() {
    checked = mixed ? true : !checked;
    onchange?.(checked);
  }
</script>

<button type="button" role="checkbox" aria-checked={mixed ? "mixed" : !!checked} {disabled} class="lg-check {cls}" class:lg-on={checked === true || mixed} onclick={flip} {...rest}>
  <span class="lg-check-box">{#if mixed}<Icon name="minus" size={10} weight="bold" />{:else if checked}<Icon name="checkmark" size={10} weight="bold" />{/if}</span>
  {#if label}<span class={TYPE[platform].body}>{label}</span>{/if}
</button>
