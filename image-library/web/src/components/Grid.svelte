<script>
  import { onMount } from "svelte";
  import Thumb from "./Thumb.svelte";
  import { justify, squares, squareCols } from "../lib/layout.js";
  import { app, selection, openViewer } from "../lib/state.svelte.js";

  /** list：開啟檢視器時可左右切換的完整清單（預設等於 assets） */
  let { assets = [], list = null, offset = 0, target = 0, layoutWidth = 0 } = $props();
  let width = $state(0);
  let el;

  const lw = $derived(layoutWidth || width);
  const narrow = $derived(lw > 0 && lw < 640);
  // 設定 → 外觀：照片依比例（等高列）或正方形裁切；手機一律正方形
  const square = $derived(narrow || app.server?.ui?.grid_style === "square");
  const rowTarget = $derived(target || (lw > 1600 ? 260 : lw > 1000 ? 230 : 190));
  const rows = $derived(
    square
      ? squares(assets, lw, squareCols(lw, rowTarget), narrow ? 2 : 4)
      : justify(assets, width, rowTarget, 4)
  );
  const gap = $derived(narrow ? 2 : 4);
  const selecting = $derived(selection.size > 0);

  // 每一列的位置；只畫出畫面附近的列，幾萬張的資料夾或相簿也不會一次塞進幾萬個縮圖
  const tops = $derived.by(() => {
    const out = new Array(rows.length);
    let y = 0;
    for (let i = 0; i < rows.length; i++) {
      out[i] = y;
      y += rows[i].height + gap;
    }
    return out;
  });
  const total = $derived(rows.length ? tops[rows.length - 1] + rows[rows.length - 1].height : 0);
  const VIRTUAL_MIN = 30; // 列數少時全部畫出，行為和以前一樣
  let view = $state({ top: 0, bottom: 2400 });
  let pageY = $state(0); // 網格在整頁內容中的位置，用來讓載入中的波浪跨區塊連續
  let near = $state(true);

  function first(y) {
    let lo = 0, hi = rows.length - 1, ans = 0;
    while (lo <= hi) {
      const mid = (lo + hi) >> 1;
      if (tops[mid] + rows[mid].height >= y) {
        ans = mid;
        hi = mid - 1;
      } else lo = mid + 1;
    }
    return ans;
  }
  const shown = $derived.by(() => {
    if (rows.length <= VIRTUAL_MIN) return rows.map((row, i) => ({ row, i }));
    if (!near) return [];
    const a = first(view.top);
    const out = [];
    for (let i = a; i < rows.length && tops[i] <= view.bottom; i++) out.push({ row: rows[i], i });
    return out;
  });

  onMount(() => {
    const scroller = el.closest("main") || document.scrollingElement;
    let raf = 0;
    const measure = () => {
      raf = 0;
      const sr = scroller.getBoundingClientRect?.() || { top: 0, height: innerHeight };
      const gr = el.getBoundingClientRect();
      const h = scroller.clientHeight || innerHeight;
      const y = sr.top - gr.top; // 畫面頂端在網格內的位置
      const py = Math.round((scroller.scrollTop || 0) - y);
      if (Math.abs(py - pageY) > 4) pageY = py;
      // 上下各多畫一個多畫面，快速捲動時才不會看到空白
      const top = y - h * 1.2;
      const bottom = y + h * 2.2;
      if (Math.abs(top - view.top) > 120 || Math.abs(bottom - view.bottom) > 120) view = { top, bottom };
    };
    const onScroll = () => {
      if (!raf) raf = requestAnimationFrame(measure);
    };
    // 整個網格離畫面很遠時不必監聽捲動
    const io = new IntersectionObserver(([e]) => {
      near = e.isIntersecting;
      if (near) {
        measure();
        scroller.addEventListener("scroll", onScroll, { passive: true });
      } else scroller.removeEventListener("scroll", onScroll);
    }, { root: scroller === document.scrollingElement ? null : scroller, rootMargin: "150% 0px" });
    io.observe(el);
    const ro = new ResizeObserver(onScroll);
    ro.observe(scroller);
    measure();
    return () => {
      io.disconnect();
      ro.disconnect();
      scroller.removeEventListener("scroll", onScroll);
      cancelAnimationFrame(raf);
    };
  });

  let anchor = null;

  function open(index) {
    const full = list || assets;
    openViewer(full, offset + index);
  }

  function select(index, e) {
    const id = assets[index].id;
    if (e?.shiftKey && anchor !== null) {
      const [a, b] = [Math.min(anchor, index), Math.max(anchor, index)];
      for (let i = a; i <= b; i++) selection.add(assets[i].id);
    } else if (selection.has(id)) {
      selection.delete(id);
    } else {
      selection.add(id);
    }
    anchor = index;
  }
</script>

<div class="grid" bind:this={el} bind:clientWidth={width} style:height="{total}px">
  {#each shown as { row, i } (i)}
    <div class="row" style:top="{tops[i]}px" style:height="{row.height}px" style:gap="{gap}px" style:--wave={Math.floor((pageY + tops[i]) / 150) % 14}>
      {#each row.items as item (item.asset.id)}
        <Thumb
          asset={item.asset}
          width={item.width}
          height={row.height}
          selected={selection.has(item.asset.id)}
          {selecting}
          onopen={() => open(item.index)}
          onselect={(e) => select(item.index, e)}
        />
      {/each}
    </div>
  {/each}
</div>

<style>
  .grid { position: relative; width: 100%; }
  .row { position: absolute; left: 0; right: 0; display: flex; overflow: hidden; }
</style>
