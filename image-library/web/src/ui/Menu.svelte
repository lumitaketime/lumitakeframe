<script>
  /**
   * 選單面板：items 是 {label, icon, shortcut, checked, disabled, destructive, submenu, onSelect}，
   * 或 {separator: true}、{header: "…"}。上下鍵移動、Enter 或空白鍵選取、Escape 關閉。
   */
  import Icon from "./Icon.svelte";
  import { usePlatform, TYPE } from "./platform.js";

  let { items = [], onselect, onclose, width = undefined, autofocus = false, platform: p = "", class: cls = "", style = "" } = $props();
  // svelte-ignore state_referenced_locally（平台在元件建立時決定，之後不變）
  const platform = usePlatform(p);
  let el;
  const showChecks = $derived(items.some((it) => it && it.checked !== undefined));
  const focusable = () => Array.from(el.querySelectorAll('[role^="menuitem"]:not([aria-disabled="true"])'));

  $effect(() => {
    if (autofocus && el) focusable()[0]?.focus();
  });

  function onkeydown(e) {
    const els = focusable();
    const i = els.indexOf(document.activeElement);
    if (e.key === "ArrowDown") { e.preventDefault(); (els[i + 1] || els[0])?.focus(); }
    if (e.key === "ArrowUp") { e.preventDefault(); (els[i - 1] || els[els.length - 1])?.focus(); }
    if (e.key === "Home") { e.preventDefault(); els[0]?.focus(); }
    if (e.key === "End") { e.preventDefault(); els[els.length - 1]?.focus(); }
    if (e.key === "Escape") onclose?.();
  }
  function act(it) {
    if (it.disabled) return;
    it.onSelect?.(it);
    onselect?.(it);
  }
</script>

<div bind:this={el} role="menu" tabindex="-1" class="lg-menu lg-glass lg-glass-regular lg-menu-{platform} {cls}" style:width={width ? `${width}px` : null} {style} {onkeydown}>
  {#each items as it, i (i)}
    {#if !it}
      <!-- 略過空項目 -->
    {:else if it.separator}
      <div role="separator" class="lg-menu-sep"></div>
    {:else if it.header}
      <div class="lg-menu-header {TYPE[platform].sub}">{it.header}</div>
    {:else}
      <!-- svelte-ignore a11y_no_noninteractive_tabindex -->
      <div role={it.checked !== undefined ? "menuitemcheckbox" : "menuitem"} tabindex={it.disabled ? -1 : 0} aria-disabled={it.disabled || undefined}
        aria-checked={it.checked !== undefined ? !!it.checked : undefined} aria-haspopup={it.submenu ? "menu" : undefined}
        class="lg-menu-item {TYPE[platform].body}" class:lg-menu-destructive={it.destructive} class:lg-menu-disabled={it.disabled}
        onclick={() => act(it)} onkeydown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); act(it); } }}>
        {#if showChecks}<span class="lg-menu-check">{#if it.checked}<Icon name="checkmark" size={platform === "ios" ? 17 : 13} weight="semibold" />{/if}</span>{/if}
        {#if it.icon}<Icon name={it.icon} size={platform === "ios" ? 19 : 15} class="lg-menu-icon" />{/if}
        <span class="lg-menu-label">{it.label}</span>
        {#if it.shortcut}<span class="lg-menu-shortcut">{it.shortcut}</span>{/if}
        {#if it.submenu}<Icon name="chevron-right" size={12} weight="semibold" class="lg-menu-chev" />{/if}
      </div>
    {/if}
  {/each}
</div>
