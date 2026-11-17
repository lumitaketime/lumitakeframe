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
  // 選單用 fixed 定位，不會被外面有圓角裁切的卡片（List）切掉；右邊放不下就靠右對齊，下面放不下就往上開
  let place = $state("");
  function toggle() {
    if (!open && btn) {
      const r = btn.getBoundingClientRect();
      const w = menuWidth || width || Math.max(r.width, 180);
      const left = r.left + w > innerWidth - 8 ? Math.max(8, r.right - w) : r.left;
      const below = innerHeight - r.bottom - 12;
      const above = r.top - 12;
      const need = options.length * 30 + 12;
      const up = below < need && above > below;
      const room = Math.max(120, up ? above : below);
      place = `position: fixed; left: ${left}px; ${up ? `top: auto; bottom: ${innerHeight - r.top + 4}px` : `top: ${r.bottom + 4}px`}; `
        + `min-width: ${Math.round(r.width)}px; max-height: ${room}px; overflow-y: auto; z-index: 400;`;
    }
    open = !open;
  }
  // 開著的時候捲動或改變視窗大小：選單不會跟著移動，直接關掉
  $effect(() => {
    if (!open) return;
    const close = (e) => { if (!e.target?.closest?.(".lg-menu")) open = false; };
    addEventListener("scroll", close, true);
    addEventListener("resize", close);
    return () => {
      removeEventListener("scroll", close, true);
      removeEventListener("resize", close);
    };
  });
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
      aria-haspopup="listbox" aria-expanded={open} aria-labelledby={label ? id : undefined} onclick={toggle}>
      <span class="lg-popup-value">{sel ? sel.label : ""}</span>
      <span class="lg-popup-glyph"><Icon name="chevron-up-down" size={platform === "ios" ? 15 : 12} weight="semibold" /></span>
    </button>
    {#if open}
      <Menu autofocus onclose={() => { open = false; btn?.focus(); }} width={menuWidth || width} class="lg-dropdown-menu" style={place}
        items={options.map((o) => ({ label: o.label, checked: o.value === current, disabled: o.disabled, onSelect: () => pick(o) }))} />
    {/if}
  </span>
</span>
