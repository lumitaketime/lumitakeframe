<script>
  /** 全螢幕投影片播放：淡入淡出、可暫停、左右切換、選擇每張秒數。 */
  import { onMount } from "svelte";
  import Icon from "./Icon.svelte";
  import { previewUrl } from "../lib/api.js";
  import { mdiClose, mdiPlay, mdiPause, mdiChevronLeft, mdiChevronRight } from "../lib/icons.js";

  let { items = [], onclose } = $props();

  const photos = $derived(items.filter((a) => a.type !== "video"));
  let index = $state(0);
  let playing = $state(true);
  let seconds = $state(readSeconds());
  let chrome = $state(true);
  let root;
  let timer;
  let hideTimer;

  function readSeconds() {
    try {
      return Number(localStorage.getItem("slideSeconds")) || 5;
    } catch {
      return 5;
    }
  }
  function setSeconds(v) {
    seconds = v;
    try {
      localStorage.setItem("slideSeconds", String(v));
    } catch {
      /* 只影響這次 */
    }
    schedule();
  }

  function schedule() {
    clearTimeout(timer);
    if (playing && photos.length > 1) timer = setTimeout(() => go(1), seconds * 1000);
  }
  function go(d) {
    if (!photos.length) return;
    index = (index + d + photos.length) % photos.length;
    const next = photos[(index + 1) % photos.length];
    if (next) new Image().src = previewUrl(next, 2048);
    schedule();
  }
  function toggle() {
    playing = !playing;
    schedule();
  }
  function wake() {
    chrome = true;
    clearTimeout(hideTimer);
    hideTimer = setTimeout(() => (chrome = false), 2500);
  }
  function exit() {
    clearTimeout(timer);
    if (document.fullscreenElement) document.exitFullscreen?.().catch(() => {});
    onclose?.();
  }
  function onkey(e) {
    if (e.key === "Escape") exit();
    else if (e.key === "ArrowRight") go(1);
    else if (e.key === "ArrowLeft") go(-1);
    else if (e.key === " ") {
      e.preventDefault();
      toggle();
    }
    wake();
  }

  onMount(() => {
    root.requestFullscreen?.().catch(() => {});
    const onFs = () => {
      if (!document.fullscreenElement && root?.isConnected) {
        /* 使用者按 Esc 離開全螢幕：投影片仍保留，可以再按關閉 */
      }
    };
    document.addEventListener("fullscreenchange", onFs);
    schedule();
    wake();
    return () => {
      clearTimeout(timer);
      clearTimeout(hideTimer);
      document.removeEventListener("fullscreenchange", onFs);
    };
  });
</script>

<svelte:window onkeydown={onkey} />

<!-- svelte-ignore a11y_no_static_element_interactions -->
<div class="show" bind:this={root} onpointermove={wake} class:cursorless={!chrome} role="dialog" aria-modal="true" aria-label="投影片播放" tabindex="-1">
  {#each photos as p, i (p.id)}
    {#if Math.abs(i - index) <= 1 || (index === 0 && i === photos.length - 1) || (index === photos.length - 1 && i === 0)}
      <img src={previewUrl(p, 2048)} alt="" class:on={i === index} />
    {/if}
  {/each}
  {#if !photos.length}<p class="none">沒有可以播放的照片</p>{/if}

  <div class="controls" class:hidden={!chrome}>
    <button onclick={() => go(-1)} aria-label="上一張"><Icon path={mdiChevronLeft} /></button>
    <button onclick={toggle} aria-label={playing ? "暫停" : "播放"}><Icon path={playing ? mdiPause : mdiPlay} /></button>
    <button onclick={() => go(1)} aria-label="下一張"><Icon path={mdiChevronRight} /></button>
    <select value={String(seconds)} onchange={(e) => setSeconds(Number(e.currentTarget.value))} aria-label="每張秒數">
      {#each [3, 5, 8, 12] as n (n)}<option value={String(n)}>每張 {n} 秒</option>{/each}
    </select>
    <span class="count">{photos.length ? index + 1 : 0} / {photos.length}</span>
    <button onclick={exit} aria-label="結束播放"><Icon path={mdiClose} /></button>
  </div>
</div>

<style>
  .show { position: fixed; inset: 0; z-index: 70; background: var(--media-bg); }
  .show.cursorless { cursor: none; }
  img { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: contain; opacity: 0; transition: opacity var(--dur-crossfade) var(--ease); }
  img.on { opacity: 1; }
  .none { color: var(--media-fg); text-align: center; margin-top: 40vh; }
  .controls {
    position: absolute; left: 50%; bottom: max(24px, env(safe-area-inset-bottom)); transform: translateX(-50%);
    display: flex; align-items: center; gap: 6px; background: var(--media-scrim); color: var(--media-fg); border-radius: var(--corner-full); padding: 6px 12px;
    transition: opacity var(--dur-move);
  }
  .controls.hidden { opacity: 0; pointer-events: none; }
  .controls button { border: 0; background: none; color: var(--media-fg); display: flex; padding: 6px; border-radius: 50%; cursor: pointer; }
  .controls button:hover { background: var(--media-fill); }
  .controls select { background: transparent; color: var(--media-fg); border: 1px solid var(--media-line); border-radius: var(--corner-full); padding: 3px 8px; font-size: var(--text-body); }
  .controls select option { color: var(--media-bg); }
  .count { font-size: var(--text-body); min-width: 64px; text-align: center; font-variant-numeric: tabular-nums; opacity: .8; }
  @media (prefers-reduced-motion: reduce) { img { transition: none; } }
</style>
