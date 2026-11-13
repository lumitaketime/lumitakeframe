<script>
  import Icon from "./Icon.svelte";
  import { thumbUrl } from "../lib/api.js";
  import { duration, LABEL_COLORS } from "../lib/format.js";
  import { mdiCheckCircle, mdiCheckboxBlankCircleOutline, mdiHeart, mdiPlay, mdiImageRemoveOutline, mdiStar, mdiLayers } from "../lib/icons.js";

  let { asset, width, height, selected = false, selecting = false, onopen, onselect } = $props();
  let failed = $state(false);
  let loaded = $state(false);
  let instant = $state(false);

  // 已經在瀏覽器快取裡的縮圖（例如捲回來時重新建立的列）直接顯示，不要再淡入一次（看起來會閃）
  function cached(img) {
    if (img.complete && img.naturalWidth) {
      instant = true;
      loaded = true;
    }
  }
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
  data-asset={asset.id}
  class:selected
  class:selecting
  class:loading={!loaded && !failed}
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
    <img src={thumbUrl(asset)} alt="" loading="lazy" decoding="async" draggable="false" class:loaded class:instant use:cached
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
  {/if}
  {#if asset.rating > 0 || asset.label || asset.raw}
    <span class="corner">
      {#if asset.rating > 0 || asset.label}
        <span class="meta-badge">
          {#if asset.label}<i class="dot" style:background={LABEL_COLORS[asset.label]}></i>{/if}
          {#if asset.rating > 0}<Icon path={mdiStar} size={13} />{asset.rating}{/if}
        </span>
      {/if}
      {#if asset.raw}<span class="raw" title="RAW 檔">RAW</span>{/if}
    </span>
  {/if}
</div>

<style>
  .thumb {
    position: relative; overflow: hidden; background: var(--surface-container); cursor: pointer; flex-shrink: 0;
    -webkit-tap-highlight-color: transparent; user-select: none; -webkit-user-select: none; -webkit-touch-callout: none;
  }
  img {
    width: 100%; height: 100%; object-fit: cover; display: block; opacity: 0;
    transition: opacity var(--spring-effects-default-duration) var(--spring-effects-default),
      transform var(--spring-expressive-fast-spatial-duration) var(--spring-expressive-fast-spatial),
      border-radius var(--spring-expressive-fast-spatial-duration) var(--spring-expressive-fast-spatial);
  }
  img.loaded { opacity: 1; }
  img.instant { transition-property: transform, border-radius; } /* 只是不淡入；選取時的縮放動畫照舊 */
  /* 載入中：和縮圖同形狀的圓角色塊一閃一閃；每一列依它在頁面上的高度延後一點，看起來像一波一波由上往下閃（--wave 由 Grid 算好） */
  .thumb.loading { background: none; }
  .thumb.loading::before {
    content: ""; position: absolute; inset: 0; border-radius: var(--corner-small); pointer-events: none;
    background: var(--surface-container-highest);
    animation: m3-skel-wave 1.5s ease-in-out infinite both;
    animation-delay: calc(var(--wave, 0) * 110ms);
  }
  @media (prefers-reduced-motion: reduce) { .thumb.loading::before { animation: none; } }
  .fallback { width: 100%; height: 100%; display: flex; align-items: center; justify-content: center; color: var(--on-surface-variant); }
  .shade {
    position: absolute; inset: 0; pointer-events: none; opacity: 0; transition: opacity .15s;
    background: linear-gradient(to bottom, var(--media-scrim), transparent 35%);
  }
  .check {
    position: absolute; top: 4px; left: 4px; border: 0; background: none; color: var(--media-fg); padding: 4px; cursor: pointer;
    opacity: 0; transition: opacity .15s; filter: drop-shadow(0 1px 2px var(--media-scrim));
  }
  @media (hover: hover) {
    .thumb:hover .shade, .thumb:hover .check { opacity: 1; }
  }
  .selecting .check { opacity: 1; }
  .selecting .shade { opacity: .6; }
  .selected { background: var(--secondary-container); }
  .selected img { transform: scale(.86); border-radius: var(--corner-medium); }
  .selected .check { opacity: 1; color: var(--primary); filter: none; }
  .selected .shade { opacity: 0; }
  .badge {
    position: absolute; color: var(--media-fg); font-size: var(--text-callout); font-weight: 500; display: flex; align-items: center; gap: 2px;
    text-shadow: 0 1px 3px var(--media-scrim-strong); filter: drop-shadow(0 1px 2px var(--media-scrim));
  }
  .tr { top: 6px; right: 6px; }
  .fav { position: absolute; bottom: 5px; left: 6px; color: var(--media-fg); filter: drop-shadow(0 1px 2px var(--media-scrim)); }
  .missing img { filter: grayscale(1); opacity: .45; }
  .rejected img { opacity: .35; }
  .stack { background: var(--media-scrim); padding: 1px 6px 1px 4px; border-radius: var(--corner-small); font-size: var(--text-sub); }
  .stack.with-video { top: 28px; }
  .corner { position: absolute; right: 5px; bottom: 5px; display: flex; align-items: center; gap: 4px; pointer-events: none; }
  .raw {
    font-size: var(--text-caption); line-height: 14px; font-weight: 500; letter-spacing: .06em; color: var(--media-fg);
    background: var(--media-scrim-light); border: 1px solid var(--media-line); border-radius: var(--corner-extra-small); padding: 0 4px;
  }
  .meta-badge {
    display: flex; align-items: center; gap: 2px; color: var(--media-fg);
    background: var(--media-scrim); border-radius: var(--corner-small); padding: 1px 5px; font-size: var(--text-sub); font-weight: 700;
  }
  .meta-badge :global(svg) { color: var(--system-yellow); }
  .dot { width: 9px; height: 9px; border-radius: 50%; display: inline-block; margin-right: 2px; box-shadow: 0 0 0 1px var(--media-fg-dim); }
  .thumb:focus-visible { outline: 3px solid var(--primary); outline-offset: -3px; }
</style>
