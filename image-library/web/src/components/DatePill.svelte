<script>
  /** 捲動時在畫面上方中央浮出目前位置的日期，停止捲動約一秒後淡出。 */
  import { onMount } from "svelte";

  let el;
  let label = $state("");
  let show = $state(false);
  let pos = $state({ top: 0, left: 0 });
  let timer;
  let frame = 0;

  onMount(() => {
    const scroller = el.closest("main");
    if (!scroller) return;
    function update() {
      frame = 0;
      if (scroller.scrollTop < 120) {
        show = false;
        return;
      }
      const r = scroller.getBoundingClientRect();
      pos = { top: r.top + 12, left: r.left + r.width / 2 };
      let found = "";
      for (const fx of [0.06, 0.25, 0.5]) {
        const hit = document.elementFromPoint(r.left + r.width * fx, r.top + 56);
        const target = hit?.closest?.("[data-label]");
        if (target) {
          found = target.dataset.label;
          break;
        }
      }
      if (found) {
        label = found;
        show = true;
      }
      clearTimeout(timer);
      timer = setTimeout(() => (show = false), 1100);
    }
    const onScroll = () => {
      if (!frame) frame = requestAnimationFrame(update);
    };
    scroller.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      scroller.removeEventListener("scroll", onScroll);
      clearTimeout(timer);
      if (frame) cancelAnimationFrame(frame);
    };
  });
</script>

<div bind:this={el} class="pill" class:show style:top="{pos.top}px" style:left="{pos.left}px" aria-hidden="true">{label}</div>

<style>
  .pill {
    position: fixed; transform: translate(-50%, -6px); z-index: 25; pointer-events: none;
    background: var(--on-surface); color: var(--surface); border-radius: var(--corner-full); padding: 6px 16px; font-size: 14px; font-weight: 500;
    opacity: 0; transition: opacity .25s, transform .25s; white-space: nowrap;
  }
  .pill.show { opacity: .92; transform: translate(-50%, 0); }
  @media (prefers-reduced-motion: reduce) { .pill { transition: none; } }
</style>
