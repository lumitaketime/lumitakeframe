<script>
  /** 彈出式按鈕：顯示一組互斥選項中目前的選擇，按下後開啟選單更換。 */
  import Icon from "./Icon.svelte";
  import Menu from "./Menu.svelte";
  import { usePlatform, TYPE, uid, dismiss } from "./platform.js";

  let { options = [], value = $bindable(), onchange, label = "", disabled = false, width = undefined, menuWidth = undefined, class: cls = "" } = $props();
  const platform = usePlatform();
  const id = uid("popup");
  let open = $state(false);
  let btn = $state();
  const current = $derived(value !== undefined ? value : options[0]?.value);
  const sel = $derived(options.find((o) => o.value === current));
  function pick(o) {
    value = o.value;
    onchange?.(o.value);
    open = false;
    btn?.focus();
  }
</script>

<span class="lg-popup-wrap {cls}">
  {#if label}<span {id} class="lg-field-label {TYPE[platform].body}">{label}</span>{/if}
  <span class="lg-dropdown" use:dismiss={() => (open = false)}>
    <button bind:this={btn} type="button" class="lg-popup lg-popup-{platform} {TYPE[platform].body}" style:width={width ? `${width}px` : null} {disabled}
      aria-haspopup="listbox" aria-expanded={open} aria-labelledby={label ? id : undefined} onclick={() => (open = !open)}>
      <span class="lg-popup-value">{sel ? sel.label : ""}</span>
      <span class="lg-popup-glyph"><Icon name="chevron-up-down" size={platform === "ios" ? 15 : 12} weight="semibold" /></span>
    </button>
    {#if open}
      <Menu autofocus onclose={() => { open = false; btn?.focus(); }} width={menuWidth || width} class="lg-dropdown-menu"
        items={options.map((o) => ({ label: o.label, checked: o.value === current, disabled: o.disabled, onSelect: () => pick(o) }))} />
    {/if}
  </span>
</span>
