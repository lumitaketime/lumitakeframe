<script>
  /**
   * 照片網格的骨架：一格一格的圓角方塊各自一閃一閃，依在頁面上的高度延後一點，看起來像一波一波由上往下。
   * 只畫畫面附近的列（和 Grid 一樣），幾萬張的月份也只有幾十個方塊。
   * height：要鋪滿的高度（0＝一個畫面高）；square：正方形模式。
   */
  import { onMount } from "svelte";

  let { height = 0, square = false } = $props();
  let el;
  let width = $state(0);
  let view = $state({ top: -1, bottom: 2400 });
  let pageY = $state(0);

  const ROW = $derived(width && width < 640 ? 130 : 200);
  const GAP = $derived(width && width < 640 ? 2 : 4);
  const H = $derived(height || (typeof innerHeight !== "undefined" ? innerHeight - 160 : 800));
  const rows = $derived(Math.max(1, Math.ceil(H / (ROW + GAP))));
  // 依比例模式：兩種排法輪流，看起來像真的照片
  const PATTERNS = [[1.5, 1, 1.25, 1.25], [0.9, 1.5, 1.1, 1.4]];
  const cols = $derived(Math.max(2, Math.round(width / 200)));

  function cells(i) {
    if (square) return Array(cols).fill(1);
    return PATTERNS[i % 2];
  }

  const shown = $derived.by(() => {
    const out = [];
    for (let i = 0; i < rows; i++) {
      const top = i * (ROW + GAP);
      if (top + ROW >= view.top && top <= view.bottom) out.push({ i, top });
    }
    return out;
  });

  onMount(() => {
    const scroller = el.closest("main") || document.scrollingElement;
    let raf = 0;
    const measure = () => {
      raf = 0;
      if (!el?.isConnected) return;
      const sr = scroller.getBoundingClientRect?.() || { top: 0 };
      const gr = el.getBoundingClientRect();
      const h = scroller.clientHeight || innerHeight;
      const y = sr.top - gr.top;
      pageY = Math.round((scroller.scrollTop || 0) - y);
      view = { top: y - h, bottom: y + h * 2 };
    };
    const onScroll = () => {
      if (!raf) raf = requestAnimationFrame(measure);
    };
    // 離畫面很遠的月份不監聽捲動、不畫格子
    const io = new IntersectionObserver(([e]) => {
      if (e.isIntersecting) {
        measure();
        scroller.addEventListener("scroll", onScroll, { passive: true });
      } else {
        scroller.removeEventListener("scroll", onScroll);
        view = { top: -2, bottom: -1 };
      }
    }, { root: scroller === document.scrollingElement ? null : scroller, rootMargin: "100% 0px" });
    io.observe(el);
    const ro = new ResizeObserver(() => {
      width = el.clientWidth;
      onScroll();
    });
    ro.observe(el);
    width = el.clientWidth;
    measure();
    return () => {
      scroller.removeEventListener("scroll", onScroll);
      io.disconnect();
      ro.disconnect();
      cancelAnimationFrame(raf);
    };
  });
</script>

<div class="sg" bind:this={el} style:height="{H}px" role="status" aria-label="載入中">
  {#each shown as r (r.i)}
    <div class="row" style:top="{r.top}px" style:height="{ROW}px" style:gap="{GAP}px" style:--wave={Math.floor((pageY + r.top) / (ROW + GAP)) % 12}>
      {#each cells(r.i) as grow, k (k)}<span class="cell" style:flex-grow={grow}></span>{/each}
    </div>
  {/each}
</div>

<style>
  .sg { position: relative; width: 100%; }
  .row { position: absolute; left: 0; right: 0; display: flex; }
  .cell {
    flex: 1 1 0; min-width: 0; border-radius: var(--corner-small); background: var(--surface-container-highest);
    animation: m3-skel-wave 1.5s ease-in-out infinite both;
    animation-delay: calc(var(--wave, 0) * 110ms);
  }
  @media (prefers-reduced-motion: reduce) { .cell { animation: none; opacity: .7; } }
</style>
