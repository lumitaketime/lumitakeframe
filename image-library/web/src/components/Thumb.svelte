<script>
  import Icon from "./Icon.svelte";
  import { thumbUrl } from "../lib/api.js";
  import { duration, LABEL_COLORS } from "../lib/format.js";
  import { mdiCheckCircle, mdiCheckboxBlankCircleOutline, mdiHeart, mdiPlay, mdiImageRemoveOutline, mdiStar, mdiLayers } from "../lib/icons.js";

  let { asset, width, height, selected = false, selecting = false, onopen, onselect } = $props();
  let failed = $state(false);
  let loaded = $state(false);
  let pressTimer;
  let pressed = false;

  function down(e) {
    if (e.pointerType !== "touch") return;
    pressed = false;
    pressTimer = setTimeout(() => {
      pressed = true;
      navigator.vibrate?.(20);
      onselect?.(e);
    }, 450);
  }
  function cancel() {
    clearTimeout(pressTimer);
  }
  function click(e) {
    if (pressed) {
      pressed = false;
      return;
    }
    if (selecting || e.shiftKey || e.metaKey || e.ctrlKey) onselect?.(e);
    else onopen?.(e);
  }
</script>

<div
  class="thumb"
  class:selected
  class:selecting
  class:missing={asset.missing}
  class:rejected={asset.rating === -1}
  style:width="{width}px"
  style:height="{height}px"
  role="button"
  tabindex="0"
  aria-label={asset.name}
  title={asset.name}
  onclick={click}
  onkeydown={(e) => (e.key === "Enter" ? onopen?.(e) : e.key === " " && (e.preventDefault(), onselect?.(e)))}
  onpointerdown={down}
  onpointerup={cancel}
  onpointerleave={cancel}
  onpointermove={(e) => e.pointerType === "touch" && Math.abs(e.movementY) > 2 && cancel()}
  oncontextmenu={(e) => e.pointerType === "touch" && e.preventDefault()}
>
  {#if failed}
    <div class="fallback"><Icon path={mdiImageRemoveOutline} size={28} /></div>
  {:else}
    <img src={thumbUrl(asset)} alt="" loading="lazy" decoding="async" draggable="false" class:loaded
      onload={() => (loaded = true)} onerror={() => (failed = true)} />
  {/if}
  <div class="shade"></div>
  <button
    class="check"
    type="button"
    aria-label={selected ? "取消選取" : "選取"}
    onclick={(e) => { e.stopPropagation(); onselect?.(e); }}
  >
    <Icon path={selected ? mdiCheckCircle : mdiCheckboxBlankCircleOutline} size={22} />
  </button>
  {#if asset.type === "video"}
    <span class="badge tr">{duration(asset.duration)}<Icon path={mdiPlay} size={16} /></span>
  {/if}
  {#if asset.fav}
    <span class="fav"><Icon path={mdiHeart} size={18} /></span>
  {/if}
  {#if asset.stack > 1}
    <span class="badge tr stack" class:with-video={asset.type === "video"}><Icon path={mdiLayers} size={15} />{asset.stack}</span>
  {:else if asset.raw}
    <span class="badge br">RAW</span>
  {/if}
  {#if asset.rating > 0 || asset.label}
    <span class="meta-badge">
      {#if asset.label}<i class="dot" style:background={LABEL_COLORS[asset.label]}></i>{/if}
      {#if asset.rating > 0}<Icon path={mdiStar} size={13} />{asset.rating}{/if}
    </span>
  {/if}
</div>

<style>
  .thumb {
    position: relative; overflow: hidden; background: var(--bg-2); cursor: pointer; flex-shrink: 0;
    -webkit-tap-highlight-color: transparent; user-select: none; -webkit-user-select: none; -webkit-touch-callout: none;
  }
  img {
    width: 100%; height: 100%; object-fit: cover; display: block; opacity: 0;
    transition: opacity var(--spring-effects-default-duration) var(--spring-effects-default),
      transform var(--spring-expressive-fast-spatial-duration) var(--spring-expressive-fast-spatial),
      border-radius var(--spring-expressive-fast-spatial-duration) var(--spring-expressive-fast-spatial);
  }
  img.loaded { opacity: 1; }
  .fallback { width: 100%; height: 100%; display: flex; align-items: center; justify-content: center; color: var(--muted); }
  .shade {
    position: absolute; inset: 0; pointer-events: none; opacity: 0; transition: opacity .15s;
    background: linear-gradient(to bottom, rgba(0,0,0,.45), transparent 35%);
  }
  .check {
    position: absolute; top: 4px; left: 4px; border: 0; background: none; color: #fff; padding: 4px; cursor: pointer;
    opacity: 0; transition: opacity .15s; filter: drop-shadow(0 1px 2px rgba(0,0,0,.5));
  }
  @media (hover: hover) {
    .thumb:hover .shade, .thumb:hover .check { opacity: 1; }
  }
  .selecting .check { opacity: 1; }
  .selecting .shade { opacity: .6; }
  .selected { background: var(--primary-soft); }
  .selected img { transform: scale(.86); border-radius: 10px; }
  .selected .check { opacity: 1; color: var(--primary); filter: none; }
  .selected .shade { opacity: 0; }
  .badge {
    position: absolute; color: #fff; font-size: 12px; font-weight: 600; display: flex; align-items: center; gap: 2px;
    text-shadow: 0 1px 3px rgba(0,0,0,.7); filter: drop-shadow(0 1px 2px rgba(0,0,0,.5));
  }
  .tr { top: 6px; right: 6px; }
  .br { top: 6px; right: 6px; font-size: 10px; letter-spacing: .04em; background: rgba(0,0,0,.45); padding: 0 4px; border-radius: 4px; }
  .fav { position: absolute; bottom: 5px; left: 6px; color: #fff; filter: drop-shadow(0 1px 2px rgba(0,0,0,.6)); }
  .missing img { filter: grayscale(1); opacity: .45; }
  .rejected img { opacity: .35; }
  .stack { background: rgba(0,0,0,.45); padding: 1px 6px 1px 4px; border-radius: 6px; font-size: 11px; }
  .stack.with-video { top: 28px; }
  .meta-badge {
    position: absolute; right: 6px; bottom: 5px; display: flex; align-items: center; gap: 2px; color: #fff;
    background: rgba(0,0,0,.45); border-radius: 6px; padding: 1px 5px; font-size: 11px; font-weight: 700;
  }
  .meta-badge :global(svg) { color: #f5c518; }
  .dot { width: 9px; height: 9px; border-radius: 50%; display: inline-block; margin-right: 2px; box-shadow: 0 0 0 1px rgba(255,255,255,.7); }
  .thumb:focus-visible { outline: 3px solid var(--primary); outline-offset: -3px; }
</style>
