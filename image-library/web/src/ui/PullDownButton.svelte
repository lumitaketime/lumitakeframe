<script>
  /** 下拉按鈕：按下後顯示一組動作（要選一個值請用 PopUpButton）。 */
  import Button from "./Button.svelte";
  import Icon from "./Icon.svelte";
  import Menu from "./Menu.svelte";
  import { dismiss } from "./platform.js";

  let { label, icon = "", items = [], variant = "bordered", size = "regular", iconOnly = false, disabled = false, menuWidth = 220, align = "start", class: cls = "" } = $props();
  let open = $state(false);
  let btn = $state();
  // 選單不能超出視窗：右邊放不下就改成和按鈕右緣對齊；下面放不下就限制高度、在選單裡捲動
  let side = $state("start");
  let maxH = $state(null);
  function toggle() {
    if (!open && btn) {
      const r = btn.getBoundingClientRect();
      side = align === "end" || r.left + menuWidth > innerWidth - 8 ? "end" : "start";
      maxH = Math.max(160, innerHeight - r.bottom - 16);
    }
    open = !open;
  }
  function close(refocus = true) {
    open = false;
    if (refocus) btn?.focus();
  }
</script>

<span class="lg-dropdown {cls}" use:dismiss={() => open && close(false)}>
  <Button bind:el={btn} {variant} {size} {icon} {iconOnly} {disabled} aria-haspopup="menu" aria-expanded={open} aria-label={iconOnly ? label : undefined} onclick={toggle}>
    {label}<Icon name="chevron-down" size={11} weight="semibold" class="lg-btn-trailing" />
  </Button>
  {#if open}
    <Menu {items} width={menuWidth} autofocus onclose={() => close()} onselect={() => close()} class="lg-dropdown-menu {side === 'end' ? 'lg-align-end' : ''}"
      style={maxH ? `max-height: ${maxH}px; overflow-y: auto;` : ""} />
  {/if}
</span>
