<script>
  /** 下拉按鈕：按下後顯示一組動作（要選一個值請用 PopUpButton）。 */
  import Button from "./Button.svelte";
  import Icon from "./Icon.svelte";
  import Menu from "./Menu.svelte";
  import { dismiss } from "./platform.js";

  let { label, icon = "", items = [], variant = "bordered", size = "regular", iconOnly = false, disabled = false, menuWidth = 220, align = "start", class: cls = "" } = $props();
  let open = $state(false);
  let btn = $state();
  function close(refocus = true) {
    open = false;
    if (refocus) btn?.focus();
  }
</script>

<span class="lg-dropdown {cls}" use:dismiss={() => open && close(false)}>
  <Button bind:el={btn} {variant} {size} {icon} {iconOnly} {disabled} aria-haspopup="menu" aria-expanded={open} aria-label={iconOnly ? label : undefined} onclick={() => (open = !open)}>
    {label}<Icon name="chevron-down" size={11} weight="semibold" class="lg-btn-trailing" />
  </Button>
  {#if open}
    <Menu {items} width={menuWidth} autofocus onclose={() => close()} onselect={() => close()} class="lg-dropdown-menu {align === 'end' ? 'lg-align-end' : ''}" />
  {/if}
</span>
