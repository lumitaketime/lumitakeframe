<script>
  /**
   * M3 選單：按圖示按鈕打開，點外面或按 Esc 關閉。
   * items：{ label, icon?, run, disabled?, checked?, danger? }，或 { section: "標題" } 分隔。
   */
  import Icon from "./Icon.svelte";
  import { mdiCheck, mdiDotsVertical } from "../lib/icons.js";

  let { items = [], icon = mdiDotsVertical, label = "更多", active = false, badge = false } = $props();
  let open = $state(false);
  let root;

  function outside(e) {
    if (open && root && !root.contains(e.target)) open = false;
  }
  function key(e) {
    if (open && e.key === "Escape") {
      e.stopPropagation();
      open = false;
      root?.querySelector("button")?.focus();
    }
  }
  function pick(it) {
    if (it.disabled) return;
    open = false;
    it.run?.();
  }
</script>

<svelte:window onpointerdown={outside} onkeydown={key} />

<div class="menu-wrap" bind:this={root}>
  <button class="icon-btn trigger" class:active={active || open} onclick={() => (open = !open)} aria-haspopup="menu" aria-expanded={open} aria-label={label} title={label}>
    <Icon path={icon} />
    {#if badge}<span class="badge"></span>{/if}
  </button>
  {#if open}
    <div class="menu" role="menu">
      {#each items as it, i (i)}
        {#if it.section}
          <div class="section" class:first={i === 0}>{it.section}</div>
        {:else}
          <button role={it.checked === undefined ? "menuitem" : "menuitemradio"} aria-checked={it.checked} class:danger={it.danger}
            disabled={it.disabled} onclick={() => pick(it)}>
            <span class="lead">{#if it.checked}<Icon path={mdiCheck} size={20} />{:else if it.icon}<Icon path={it.icon} size={20} />{/if}</span>
            <span>{it.label}</span>
          </button>
        {/if}
      {/each}
    </div>
  {/if}
</div>

<style>
  .menu-wrap { position: relative; display: inline-flex; }
  .trigger { color: var(--on-surface-variant); position: relative; }
  .badge { position: absolute; top: 8px; right: 8px; width: 8px; height: 8px; border-radius: 50%; background: var(--primary); z-index: 3; }
  .menu {
    position: absolute; right: 0; top: calc(100% + 4px); z-index: 120; min-width: 220px; max-width: 320px; padding: 8px 0;
    background: var(--surface-container-high); border-radius: var(--corner-extra-small); border: 1px solid var(--outline-variant);
    transform-origin: top right; animation: menu-in var(--spring-standard-fast-spatial-duration) var(--spring-standard-fast-spatial);
  }
  @keyframes menu-in { from { opacity: 0; transform: scale(.85, .6); } }
  .menu button {
    display: flex; align-items: center; gap: 12px; width: 100%; height: 48px; padding: 0 16px 0 12px; border: 0; background: none;
    color: var(--on-surface); font-size: var(--text-body); text-align: left; cursor: pointer; position: relative;
  }
  .menu button:hover { background: color-mix(in srgb, var(--on-surface) 8%, transparent); }
  .menu button:focus-visible { background: color-mix(in srgb, var(--on-surface) 12%, transparent); outline: none; }
  .menu button:disabled { color: color-mix(in srgb, var(--on-surface) 38%, transparent); cursor: default; background: none; }
  .menu button.danger { color: var(--error); }
  .lead { width: 24px; display: flex; justify-content: center; color: var(--on-surface-variant); }
  .menu button[aria-checked="true"] .lead { color: var(--primary); }
  .section { padding: 12px 16px 4px; font-size: var(--text-callout); font-weight: 500; color: var(--on-surface-variant); border-top: 1px solid var(--outline-variant); margin-top: 8px; }
  .section.first { border-top: 0; margin-top: 0; padding-top: 4px; }
</style>
