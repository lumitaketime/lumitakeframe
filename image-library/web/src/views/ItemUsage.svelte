<script>
  /**
   * 佔比檢視：方塊圖或環狀圖（右上角切換）。一路畫到每個子資料夾、每個「檔案」，小到畫不出來的才合併成「其他」；
   * 「其他」按兩下會列出裡面每一項。面積或角度代表大小、顏色代表檔案類型。
   * 用 Canvas 畫（可以有好幾萬塊），不是幾萬個 DOM 元素。顏色不是唯一線索：方塊裡有文字、下方有圖例、
   * 滑鼠停留時顯示完整路徑、大小、佔整體與佔上一層的百分比。按一下選取、按兩下進入資料夾、方向鍵換上一塊或下一塊。
   */
  import { untrack } from "svelte";
  import { Button, ProgressIndicator, SegmentedControl } from "../ui/index.js";
  import KindIcon from "./KindIcon.svelte";
  import { handleViewKey } from "./keys.js";
  import { squarify } from "../lib/squarify.js";
  import { colorKey } from "./usage.js";
  import { prefs, setChart } from "./prefs.svelte.js";
  import { loadUsageRest } from "../data/browse.js";
  import { t, formatBytes, formatNumber } from "../i18n/index.svelte.js";

  let { usage, tree, sel, onopen, onpreview, oncontext, onopenitem } = $props();

  const GAP = 1;
  const HEAD = 16;
  const RINGS = 6;
  let box = $state();
  let canvas = $state();
  let width = $state(800);
  let height = $state(500);
  let hover = $state(-1);
  let tip = $state({ x: 0, y: 0 });
  let theme = $state(0);
  const units = $derived(tree?.units || []);
  const kids = $derived(tree?.kids || []);
  const top = $derived(tree?.top || []);
  const total = $derived(usage?.bytes || 0);
  const chart = $derived(prefs.chart);

  // ---- 縮放與平移：放大後小塊也看得到名稱；zoom＝倍數，panX／panY＝畫面左上角在放大後的圖上的位置 ----
  const ZMAX = 32;
  let zoom = $state(1);
  let panX = $state(0);
  let panY = $state(0);
  const VW = $derived(width * zoom);
  const VH = $derived(height * zoom);
  $effect(() => {
    tree;
    chart;
    untrack(() => { zoom = 1; panX = 0; panY = 0; }); // 換資料夾或換圖表：回到原來大小
  });
  const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
  /** 以畫面上的 (px, py) 為中心縮放 factor 倍 */
  function zoomAt(factor, px = width / 2, py = height / 2) {
    const z2 = clamp(zoom * factor, 1, ZMAX);
    if (z2 === zoom) return;
    panX = clamp((px + panX) * (z2 / zoom) - px, 0, width * z2 - width);
    panY = clamp((py + panY) * (z2 / zoom) - py, 0, height * z2 - height);
    zoom = z2;
  }
  function panBy(dx, dy) {
    panX = clamp(panX + dx, 0, VW - width);
    panY = clamp(panY + dy, 0, VH - height);
  }
  function resetZoom() {
    zoom = 1;
    panX = 0;
    panY = 0;
  }

  // ---- 幾何：方塊圖是一層一層的矩形，環狀圖是一圈一圈的扇形 ----
  const shapes = $derived.by(() => {
    const out = new Array(units.length).fill(null);
    if (!top.length || width < 20 || height < 20) return out;
    if (chart === "treemap") {
      const place = (list, x, y, w, h) => {
        if (w < 1 || h < 1 || !list.length) return false;
        const rects = squarify(list.map((i) => units[i].size), x, y, w, h);
        let placed = false;
        list.forEach((i, k) => {
          const r = rects[k];
          if (!r || r.w < 0.5 || r.h < 0.5) return;
          placed = true;
          const s = { x: r.x, y: r.y, w: r.w, h: r.h, head: 0, frame: false };
          out[i] = s;
          const ch = kids[i];
          if (ch.length && r.w > 6 && r.h > 6) {
            const head = r.w > 48 && r.h > HEAD + 24 ? HEAD : 0;
            // 裡面的項目都小到畫不出來：這個資料夾就畫成一整塊（依它最大的類型上色），不留空框
            s.frame = place(ch, r.x + GAP, r.y + head + GAP, r.w - GAP * 2, r.h - head - GAP * 2);
            s.head = s.frame ? head : 0;
          }
        });
        return placed;
      };
      place(top, 0, 0, VW, VH);
    } else {
      const R = Math.min(VW, VH) / 2 - 6;
      const r0 = R * 0.2;
      const step = (R - r0) / RINGS;
      const ring = (list, a0, span, d) => {
        if (d > RINGS || span < 0.002) return;
        const sum = list.reduce((n, i) => n + units[i].size, 0) || 1;
        let a = a0;
        for (const i of list) {
          const s = span * (units[i].size / sum);
          if (s >= 0.002) {
            out[i] = { a0: a, a1: a + s, r0: r0 + (d - 1) * step, r1: r0 + d * step - 1, depth: d };
            if (kids[i].length) ring(kids[i], a, s, d + 1);
          }
          a += s;
        }
      };
      ring(top, -Math.PI / 2, Math.PI * 2, 1);
    }
    return out;
  });

  // 找出滑鼠下最深的那一塊：從第一層往下找，每一層只看這個資料夾的子項目
  function hit(x, y) {
    x += panX;
    y += panY;
    if (chart === "treemap") {
      let list = top;
      let found = -1;
      for (;;) {
        const i = list.find((j) => {
          const s = shapes[j];
          return s && x >= s.x && y >= s.y && x <= s.x + s.w && y <= s.y + s.h;
        });
        if (i === undefined) return found;
        found = i;
        if (!kids[i].length || !shapes[i]?.frame) return found;
        list = kids[i];
      }
    }
    const dx = x - VW / 2, dy = y - VH / 2;
    const r = Math.hypot(dx, dy);
    let ang = Math.atan2(dy, dx);
    if (ang < -Math.PI / 2) ang += Math.PI * 2;
    let list = top;
    let found = -1;
    for (;;) {
      const i = list.find((j) => { const s = shapes[j]; return s && ang >= s.a0 && ang < s.a1; });
      if (i === undefined) return found;
      const s = shapes[i];
      if (r < s.r0) return found;
      if (r <= s.r1) return i;
      found = -1;
      list = kids[i];
      if (!list.length) return -1;
    }
  }

  // ---- 繪製 ----
  function colors() {
    const css = getComputedStyle(box);
    const v = (name) => css.getPropertyValue(name).trim();
    const map = { rest: v("--gray-1") };
    for (const k of ["video", "photo", "document", "audio", "archive", "other", "folder", "raw", "package"]) map[k] = v(`--kind-${k}`) || v("--kind-other");
    return { map, bg: v("--control-bg"), frame: v("--fill-tertiary"), line: v("--separator"), text: v("--label-primary"), sub: v("--label-secondary"),
      onMedia: v("--on-media"), dark: v("--brand-navy"), selection: v("--selection"), font: v("--font-sans") };
  }
  const lum = new Map();
  function luminance(color) {
    if (lum.has(color)) return lum.get(color);
    const probe = document.createElement("canvas").getContext("2d");
    probe.fillStyle = color;
    probe.fillRect(0, 0, 1, 1);
    const [r, g, b] = [...probe.getImageData(0, 0, 1, 1).data].slice(0, 3).map((v) => {
      const x = v / 255;
      return x <= 0.03928 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4;
    });
    const value = 0.2126 * r + 0.7152 * g + 0.0722 * b;
    lum.set(color, value);
    return value;
  }
  function fit(ctx, text, max) {
    if (max < 12) return "";
    if (ctx.measureText(text).width <= max) return text;
    let lo = 0, hi = text.length;
    while (lo < hi) { // 二分搜尋：長檔名也不會一個字一個字量
      const mid = (lo + hi + 1) >> 1;
      if (ctx.measureText(text.slice(0, mid) + "…").width <= max) lo = mid;
      else hi = mid - 1;
    }
    return lo > 0 ? text.slice(0, lo) + "…" : "";
  }
  function draw() {
    if (!canvas || !box) return;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = Math.round(width * dpr);
    canvas.height = Math.round(height * dpr);
    const ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, width, height);
    ctx.save();
    ctx.translate(-panX, -panY);
    const x0 = panX, y0 = panY, x1 = panX + width, y1 = panY + height;
    const c = colors();
    ctx.textBaseline = "middle";
    const paint = (i) => c.map[colorKey(units[i])] || c.map.other;
    const ink = (i) => (luminance(paint(i)) > 0.36 ? c.dark : c.onMedia);
    if (chart === "treemap") {
      // 先畫資料夾的框（越深越淡一點），再畫檔案與「其他」
      for (let i = 0; i < shapes.length; i++) {
        const s = shapes[i];
        if (!s || s.x > x1 || s.y > y1 || s.x + s.w < x0 || s.y + s.h < y0) continue; // 不在畫面上的不畫
        const u = units[i];
        if (s.frame) {
          ctx.fillStyle = c.frame;
          ctx.fillRect(s.x, s.y, s.w, s.h);
          ctx.strokeStyle = c.line;
          ctx.lineWidth = 1;
          ctx.strokeRect(s.x + 0.5, s.y + 0.5, s.w - 1, s.h - 1);
          if (s.head) {
            ctx.font = `600 11px ${c.font}`;
            ctx.fillStyle = c.text;
            const size = formatBytes(u.size);
            const sizeW = ctx.measureText(size).width;
            ctx.fillText(fit(ctx, u.name, s.w - sizeW - 16), s.x + 5, s.y + s.head / 2 + 1);
            ctx.font = `11px ${c.font}`;
            ctx.fillStyle = c.sub;
            if (s.w > sizeW + 60) ctx.fillText(size, s.x + s.w - sizeW - 5, s.y + s.head / 2 + 1);
          }
          continue;
        }
        ctx.fillStyle = paint(i);
        ctx.fillRect(s.x, s.y, Math.max(0.6, s.w - (s.w > 3 ? GAP : 0)), Math.max(0.6, s.h - (s.h > 3 ? GAP : 0)));
        if (s.w >= 28 && s.h >= 14) {
          ctx.fillStyle = ink(i);
          ctx.font = `600 11px ${c.font}`;
          const two = s.h >= 32 && s.w >= 50;
          ctx.fillText(fit(ctx, u.name, s.w - 8), s.x + 4, s.y + (two ? 10 : s.h / 2));
          if (two) {
            ctx.font = `11px ${c.font}`;
            ctx.fillText(fit(ctx, formatBytes(u.size), s.w - 8), s.x + 4, s.y + 24);
          }
        }
      }
      for (const i of [...sel.picked, hover]) {
        const s = shapes[i];
        if (!s) continue;
        ctx.lineWidth = sel.has(i) ? 3 : 2;
        ctx.strokeStyle = sel.has(i) ? c.selection : c.text;
        ctx.strokeRect(s.x + 1, s.y + 1, Math.max(1, s.w - 2), Math.max(1, s.h - 2));
      }
    } else {
      const cx = VW / 2, cy = VH / 2;
      const mark = (i, lw, color) => {
        const s = shapes[i];
        ctx.beginPath();
        ctx.arc(cx, cy, s.r1, s.a0, s.a1);
        ctx.arc(cx, cy, s.r0, s.a1, s.a0, true);
        ctx.closePath();
        ctx.lineWidth = lw;
        ctx.strokeStyle = color;
        ctx.stroke();
      };
      for (let i = 0; i < shapes.length; i++) {
        const s = shapes[i];
        if (!s) continue;
        ctx.beginPath();
        ctx.arc(cx, cy, s.r1, s.a0, s.a1);
        ctx.arc(cx, cy, s.r0, s.a1, s.a0, true);
        ctx.closePath();
        ctx.fillStyle = paint(i);
        ctx.fill();
        if (s.a1 - s.a0 > 0.01) {
          ctx.lineWidth = 1;
          ctx.strokeStyle = c.bg;
          ctx.stroke();
        }
        const mid = (s.a0 + s.a1) / 2, rm = (s.r0 + s.r1) / 2;
        const room = Math.min((s.a1 - s.a0) * rm, 120) - 8;
        if (room > 34 && s.r1 - s.r0 > 14) {
          ctx.font = `600 11px ${c.font}`;
          ctx.fillStyle = ink(i);
          const label = fit(ctx, units[i].name, room);
          ctx.fillText(label, cx + Math.cos(mid) * rm - ctx.measureText(label).width / 2, cy + Math.sin(mid) * rm);
        }
      }
      for (const i of sel.picked) if (shapes[i]) mark(i, 3, c.selection);
      if (hover >= 0 && shapes[hover]) mark(hover, 2, c.text);
      const R = Math.min(VW, VH) / 2 - 6;
      const r0 = R * 0.2;
      ctx.textAlign = "center";
      ctx.fillStyle = c.text;
      ctx.font = `600 13px ${c.font}`;
      ctx.fillText(fit(ctx, usage?.name || "", r0 * 1.8), cx, cy - 9);
      ctx.fillStyle = c.sub;
      ctx.font = `12px ${c.font}`;
      ctx.fillText(formatBytes(total), cx, cy + 10);
      ctx.textAlign = "left";
    }
    ctx.restore();
  }
  let frame = 0;
  $effect(() => {
    shapes;
    hover;
    theme;
    panX;
    panY;
    sel.size;
    sel.focus;
    for (const i of sel.picked) i;
    cancelAnimationFrame(frame);
    frame = requestAnimationFrame(draw); // 同一格裡的多次變化只畫一次
  });
  $effect(() => {
    const again = () => theme++;
    const queries = ["(prefers-color-scheme: dark)", "(prefers-contrast: more)"].map((q) => matchMedia(q));
    queries.forEach((q) => q.addEventListener("change", again));
    const obs = new MutationObserver(again);
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => {
      queries.forEach((q) => q.removeEventListener("change", again));
      obs.disconnect();
    };
  });

  // 觸控板捏合（Chrome、Firefox 送出帶 ctrlKey 的滾輪；Safari 送出 gesture 事件）或 ⌘／Ctrl＋滾輪：縮放；
  // 放大後兩指滑動或滾輪：移動畫面；按住拖曳也可以移動
  function onwheel(e) {
    const r = canvas.getBoundingClientRect();
    if (e.ctrlKey || e.metaKey) {
      e.preventDefault();
      zoomAt(clamp(Math.exp(-e.deltaY * 0.01), 0.8, 1.25), e.clientX - r.left, e.clientY - r.top); // 滑鼠滾輪一格最多 1.25 倍；觸控板捏合的量本來就小
    } else if (zoom > 1) {
      e.preventDefault();
      panBy(e.deltaX, e.deltaY);
    }
  }
  $effect(() => {
    if (!canvas) return;
    let base = 1;
    const start = (e) => { e.preventDefault(); base = zoom; };
    const change = (e) => {
      e.preventDefault();
      const r = canvas.getBoundingClientRect();
      zoomAt((base * e.scale) / zoom, (e.clientX ?? r.left + width / 2) - r.left, (e.clientY ?? r.top + height / 2) - r.top);
    };
    canvas.addEventListener("wheel", onwheel, { passive: false });
    canvas.addEventListener("gesturestart", start);
    canvas.addEventListener("gesturechange", change);
    return () => {
      canvas.removeEventListener("wheel", onwheel);
      canvas.removeEventListener("gesturestart", start);
      canvas.removeEventListener("gesturechange", change);
    };
  });
  let drag = null; // { x, y, moved }
  let dragged = false;
  function ondown(e) {
    if (e.button !== 0 || zoom <= 1) return;
    drag = { x: e.clientX, y: e.clientY, moved: false };
  }
  function ondragmove(e) {
    if (!drag) return false;
    const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
    if (!drag.moved && Math.hypot(dx, dy) < 4) return false;
    drag.moved = true;
    panBy(-dx, -dy);
    drag.x = e.clientX;
    drag.y = e.clientY;
    return true;
  }
  function onup() {
    dragged = !!drag?.moved;
    drag = null;
  }

  const at = (e) => {
    const r = canvas.getBoundingClientRect();
    return hit(e.clientX - r.left, e.clientY - r.top);
  };
  let moveRaf = 0;
  function onmove(e) {
    if (ondragmove(e)) return;
    const { clientX, clientY } = e;
    if (moveRaf) return;
    moveRaf = requestAnimationFrame(() => {
      moveRaf = 0;
      const r = canvas.getBoundingClientRect();
      hover = hit(clientX - r.left, clientY - r.top);
      const b = box.getBoundingClientRect();
      tip = { x: Math.min(clientX - b.left + 14, width - 270), y: Math.min(clientY - b.top + 16, height - 80) };
    });
  }
  function open(i) {
    const u = units[i];
    if (u?.rest) return showRest(u);
    onopen?.(i);
  }
  function onkeydown(e) {
    if (rest) return;
    if (!e.metaKey && !e.ctrlKey && (e.key === "+" || e.key === "=" || e.key === "-" || e.key === "0")) {
      e.preventDefault();
      if (e.key === "0") resetZoom();
      else zoomAt(e.key === "-" ? 1 / 1.5 : 1.5);
      return;
    }
    const key = e.key === "ArrowRight" ? "ArrowDown" : e.key === "ArrowLeft" ? "ArrowUp" : e.key;
    handleViewKey(new Proxy(e, { get: (o, k) => (k === "key" ? key : typeof o[k] === "function" ? o[k].bind(o) : o[k]) }),
      { sel, total: units.length, onopen: open, onpreview });
  }
  const legend = $derived([...new Set(units.map(colorKey))].filter((k) => k !== "rest").slice(0, 10));
  const shown = $derived(hover >= 0 ? units[hover] : null);
  const parentSize = (u) => (u.parentUnit >= 0 ? units[u.parentUnit]?.size : total) || 0;
  const pct = (a, b) => (b ? `${Math.max(0.1, (a / b) * 100).toFixed(a / b < 0.1 ? 1 : 0)}%` : "");

  // ---- 「其他」裡面有什麼 ----
  let rest = $state(null); // { unit, items, total, loading, error }
  async function showRest(u) {
    rest = { unit: u, items: [], total: 0, loading: true, error: "" };
    await more();
  }
  async function more() {
    const r = rest;
    r.loading = true;
    try {
      const d = await loadUsageRest(r.unit.folderId, r.unit.below, r.items.length, 200);
      if (rest !== r) return;
      r.items = [...r.items, ...d.items];
      r.total = d.total;
    } catch (e) {
      r.error = e.message;
    } finally {
      r.loading = false;
    }
  }
</script>

<div class="usage">
  <div class="bar mac-callout">
    <ul class="legend">
      {#each legend as k (k)}<li><KindIcon kind={k} size={14} />{k === "folder" ? t("info.kind.folder") : t(`kind.${k}`)}</li>{/each}
      <li class="note">{t("usage.colorNote")}</li>
    </ul>
    <span class="count">{t("usage.blocks", { count: formatNumber(units.length) })}</span>
    <SegmentedControl size="small" value={chart} onchange={setChart} ariaLabel={t("usage.chart")}
      segments={[{ value: "treemap", label: t("usage.treemap") }, { value: "sunburst", label: t("usage.sunburst") }]} />
  </div>
  <!-- svelte-ignore a11y_no_noninteractive_tabindex -->
  <div class="stage" bind:this={box} bind:clientWidth={width} bind:clientHeight={height} tabindex="0" role="listbox" aria-multiselectable="true"
    aria-label={t("usage.label", { name: usage?.name || "" })} aria-activedescendant={sel.focus >= 0 && sel.focus < 400 ? `item-${sel.focus}` : undefined} {onkeydown}>
    <canvas bind:this={canvas} style:width="{width}px" style:height="{height}px" aria-hidden="true"
      class:grab={zoom > 1}
      onpointerdown={ondown} onpointerup={onup} onpointermove={onmove} onpointerleave={() => { hover = -1; drag = null; }}
      onclick={(e) => { if (dragged) { dragged = false; return; } const i = at(e); if (i >= 0) sel.click(i, e); else sel.clear(); }}
      ondblclick={(e) => { const i = at(e); if (i >= 0) open(i); }}
      oncontextmenu={(e) => { e.preventDefault(); const i = at(e); if (i >= 0) { sel.context(i); oncontext?.(e, i); } }}></canvas>
    <div class="zoom" role="group" aria-label={t("usage.zoom")}>
      <Button size="small" variant="glass" icon="minus" iconOnly aria-label={t("usage.zoomOut")} disabled={zoom <= 1} onclick={() => zoomAt(1 / 1.5)} />
      <button type="button" class="zpct mac-caption-1" onclick={resetZoom} title={t("usage.zoomReset")} disabled={zoom === 1}>{Math.round(zoom * 100)}%</button>
      <Button size="small" variant="glass" icon="plus" iconOnly aria-label={t("usage.zoomIn")} disabled={zoom >= ZMAX} onclick={() => zoomAt(1.5)} />
    </div>
    <!-- 給螢幕閱讀器的清單：畫面上看不到；只列最大的前 400 塊，其餘可用方向鍵走到 -->
    <ul class="sr">
      {#each units.slice(0, 400) as u, i (i)}<li id="item-{i}" role="option" aria-selected={sel.has(i)}>{u.name}，{formatBytes(u.size)}</li>{/each}
    </ul>
    {#if shown && !rest}
      <div class="tip mac-callout" style:left="{tip.x}px" style:top="{tip.y}px">
        <b>{shown.name}</b>
        <span class="path">{shown.rest ? shown.path || usage?.name : shown.path}</span>
        <span>{formatBytes(shown.size) || "0 KB"}{#if shown.type === "folder" && shown.files} · {t("status.filesOnly", { files: formatNumber(shown.files) })}{/if}</span>
        <span>{t("usage.shareTotal", { pct: pct(shown.size, total) })}{#if shown.parentUnit >= 0} · {t("usage.shareParent", { pct: pct(shown.size, parentSize(shown)) })}{/if}</span>
        {#if shown.rest}<span class="hint">{t("usage.restOpen")}</span>{/if}
      </div>
    {/if}
    {#if rest}
      <section class="rest mac-callout" aria-label={rest.unit.name}>
        <header>
          <b class="mac-headline">{rest.unit.name}</b>
          <span class="sub">{formatBytes(rest.unit.size)} · {rest.unit.path || usage?.name}</span>
          <Button size="small" variant="borderless" icon="xmark" iconOnly aria-label={t("common.close")} onclick={() => (rest = null)} />
        </header>
        <ul>
          {#each rest.items as it (it.type + it.id)}
            <li>
              <button type="button" ondblclick={() => onopenitem?.({ ...it, root_id: rest.unit.root_id })}>
                <KindIcon kind={it.type === "folder" ? "folder" : it.kind} size={14} />
                <span class="name">{it.name}</span>
                <span class="size">{formatBytes(it.size) || "0 KB"}</span>
                <span class="pct">{pct(it.size, rest.unit.size)}</span>
              </button>
            </li>
          {/each}
        </ul>
        <footer>
          {#if rest.loading}<ProgressIndicator kind="spinner" size="small" label={t("view.loading")} />
          {:else if rest.error}<span class="err">{rest.error}</span>
          {:else if rest.items.length < rest.total}<Button size="small" variant="bordered" onclick={more}>{t("usage.restMore", { count: formatNumber(rest.total - rest.items.length) })}</Button>{/if}
        </footer>
      </section>
    {/if}
  </div>
</div>

<style>
  .usage { display: flex; flex-direction: column; height: 100%; min-height: 0; }
  .bar { flex: none; display: flex; align-items: center; justify-content: space-between; gap: var(--space-4); padding: var(--space-2) var(--space-4); color: var(--label-secondary); }
  .legend { list-style: none; margin: 0; padding: 0; display: flex; flex-wrap: wrap; gap: var(--space-1) var(--space-4); flex: 1; min-width: 0; }
  .legend li { display: inline-flex; align-items: center; gap: var(--space-1); }
  .legend .note { color: var(--label-tertiary); }
  .count { flex: none; color: var(--label-tertiary); }
  .stage { position: relative; flex: 1; min-height: 0; margin: 0 var(--space-4) var(--space-4); outline: none; border-radius: var(--radius-sm); overflow: hidden; }
  .stage:focus-visible { box-shadow: var(--focus-ring); }
  canvas { display: block; touch-action: none; }
  canvas.grab { cursor: grab; }
  canvas.grab:active { cursor: grabbing; }
  .zoom { position: absolute; z-index: 2; right: var(--space-2); bottom: var(--space-2); display: flex; align-items: center; gap: var(--space-1);
    padding: 2px; border-radius: var(--radius-capsule); background: var(--glass-regular); box-shadow: var(--shadow-rim), var(--shadow-glass); }
  .zpct { min-width: 3.4em; border: 0; background: none; color: var(--label-primary); font: inherit; text-align: center; cursor: pointer; font-feature-settings: "tnum"; }
  .zpct:disabled { cursor: default; color: var(--label-secondary); }
  .sr { position: absolute; width: 1px; height: 1px; margin: -1px; padding: 0; overflow: hidden; clip-path: inset(50%); white-space: nowrap; list-style: none; }
  .tip { position: absolute; z-index: 2; pointer-events: none; display: flex; flex-direction: column; gap: 1px; max-width: 260px; padding: var(--space-1) var(--space-2);
    border-radius: var(--radius-sm); background: var(--elevated-primary); color: var(--label-primary); box-shadow: var(--shadow-popover); }
  .tip b, .tip .path { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .tip span { color: var(--label-secondary); }
  .tip .hint { color: var(--accent); }
  .rest { position: absolute; z-index: 3; top: var(--space-2); right: var(--space-2); bottom: var(--space-2); width: min(380px, 80%); display: flex; flex-direction: column;
    border-radius: var(--radius-md); background: var(--window-bg); box-shadow: var(--shadow-popover); color: var(--label-primary); }
  .rest header { display: grid; grid-template-columns: 1fr auto; align-items: center; padding: var(--space-2) var(--space-2) var(--space-2) var(--space-3);
    border-bottom: 1px solid var(--separator); }
  .rest header .sub { grid-column: 1; color: var(--label-secondary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .rest header :global(.lg-btn) { grid-column: 2; grid-row: 1 / span 2; }
  .rest ul { flex: 1; min-height: 0; overflow-y: auto; list-style: none; margin: 0; padding: var(--space-1); }
  .rest li button { width: 100%; display: grid; grid-template-columns: auto 1fr auto 48px; align-items: center; gap: var(--space-2); padding: var(--space-1) var(--space-2);
    border: 0; border-radius: var(--radius-sm); background: none; color: inherit; font: inherit; text-align: left; cursor: default; }
  .rest li button:hover { background: var(--fill-quaternary); }
  .rest .name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .rest .size, .rest .pct { color: var(--label-secondary); text-align: right; font-feature-settings: "tnum"; }
  .rest footer { display: flex; justify-content: center; padding: var(--space-2); }
  .rest .err { color: var(--system-red); }
</style>
