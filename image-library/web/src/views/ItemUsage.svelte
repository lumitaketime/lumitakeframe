<script>
  /**
   * 佔比檢視：方塊圖或環狀圖（右上角切換）。面積或角度代表大小、顏色代表檔案類型；一次畫兩層。
   * 用 Canvas 畫（最多 500 塊），不是幾百個 DOM 元素。顏色不是唯一線索：方塊裡有文字、下方有帶圖示的圖例、
   * 滑鼠停留與鍵盤選取時顯示名稱與大小。按一下選取、按兩下進入、方向鍵換上一塊或下一塊。
   */
  import { SegmentedControl } from "../ui/index.js";
  import KindIcon from "./KindIcon.svelte";
  import { handleViewKey } from "./keys.js";
  import { squarify } from "../lib/squarify.js";
  import { colorKey } from "./usage.js";
  import { prefs, setChart } from "./prefs.svelte.js";
  import { t, formatBytes } from "../i18n/index.svelte.js";

  let { usage, units = [], tops = [], sel, onopen, onpreview, oncontext } = $props();

  const GAP = 2;
  const HEAD = 18;
  let box = $state();
  let canvas = $state();
  let width = $state(800);
  let height = $state(500);
  let hover = $state(-1);
  let tip = $state({ x: 0, y: 0 });
  let theme = $state(0); // 系統外觀改變時 +1，重新讀顏色並重畫
  const total = $derived(usage?.bytes || 0);
  const chart = $derived(prefs.chart);

  // ---- 幾何：每個單位在畫面上的形狀（方塊圖是矩形，環狀圖是扇形）----
  const shapes = $derived.by(() => {
    const out = new Array(units.length).fill(null);
    if (!tops.length || width < 20 || height < 20) return out;
    if (chart === "treemap") {
      const rects = squarify(tops.map((x) => x.unit.size), 0, 0, width, height);
      tops.forEach((top, k) => {
        const r = rects[k];
        if (!r) return;
        const outer = { x: r.x + GAP / 2, y: r.y + GAP / 2, w: r.w - GAP, h: r.h - GAP };
        const framed = top.children.length > 0 && outer.w > 40 && outer.h > HEAD + 16;
        out[top.index] = { ...outer, head: framed ? HEAD : 0, frame: top.children.length > 0 };
        if (!top.children.length) return;
        const inner = framed ? { x: outer.x + GAP, y: outer.y + HEAD, w: outer.w - GAP * 2, h: outer.h - HEAD - GAP } : outer;
        const sub = squarify(top.children.map((c) => c.unit.size), inner.x, inner.y, inner.w, inner.h);
        top.children.forEach((c, j) => {
          const s = sub[j];
          if (s) out[c.index] = { x: s.x + GAP / 2, y: s.y + GAP / 2, w: Math.max(0, s.w - GAP), h: Math.max(0, s.h - GAP) };
        });
      });
    } else {
      const R = Math.min(width, height) / 2 - 6;
      const r0 = R * 0.3, r1 = R * 0.66;
      let a = -Math.PI / 2;
      for (const top of tops) {
        const span = total ? (top.unit.size / total) * Math.PI * 2 : 0;
        out[top.index] = { a0: a, a1: a + span, r0, r1: top.children.length ? r1 : R };
        let b = a;
        for (const c of top.children) {
          const s = top.unit.size ? (c.unit.size / top.unit.size) * span : 0;
          out[c.index] = { a0: b, a1: b + s, r0: r1, r1: R };
          b += s;
        }
        a += span;
      }
    }
    return out;
  });

  function hit(x, y) {
    if (chart === "treemap") {
      let frame = -1;
      for (let i = 0; i < shapes.length; i++) {
        const s = shapes[i];
        if (!s || x < s.x || y < s.y || x > s.x + s.w || y > s.y + s.h) continue;
        if (!s.frame) return i; // 內層的方塊優先
        frame = i;
      }
      return frame;
    }
    const dx = x - width / 2, dy = y - height / 2;
    const r = Math.hypot(dx, dy);
    let ang = Math.atan2(dy, dx);
    if (ang < -Math.PI / 2) ang += Math.PI * 2;
    for (let i = 0; i < shapes.length; i++) {
      const s = shapes[i];
      if (s && r >= s.r0 && r <= s.r1 && ang >= s.a0 && ang < s.a1) return i;
    }
    return -1;
  }

  // ---- 繪製 ----
  function colors() {
    const css = getComputedStyle(box);
    const v = (name) => css.getPropertyValue(name).trim();
    const map = { rest: v("--gray-1") };
    for (const k of ["video", "photo", "document", "audio", "archive", "other", "folder"]) map[k] = v(`--kind-${k}`);
    return { map, bg: v("--control-bg"), frame: v("--fill-tertiary"), text: v("--label-primary"), sub: v("--label-secondary"), onMedia: v("--on-media"),
      dark: v("--brand-navy"), selection: v("--selection"), font: v("--font-sans") };
  }
  /** 顏色的相對亮度（0 最暗、1 最亮）；用畫布把任何寫法的顏色換成紅綠藍 */
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
    if (ctx.measureText(text).width <= max) return text;
    let s = text;
    while (s.length > 1 && ctx.measureText(s + "…").width > max) s = s.slice(0, -1);
    return s.length > 1 ? s + "…" : "";
  }
  function draw() {
    if (!canvas || !box) return;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = Math.round(width * dpr);
    canvas.height = Math.round(height * dpr);
    const ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, width, height);
    const c = colors();
    ctx.textBaseline = "middle";
    const paint = (i) => c.map[colorKey(units[i])] || c.map.other;
    // 色塊上的文字：依底色的明暗選深色或白色字（四個主題的類型色深淺不同，對比都要夠）
    const ink = (i) => (luminance(paint(i)) > 0.36 ? c.dark : c.onMedia);
    if (chart === "treemap") {
      shapes.forEach((s, i) => {
        if (!s) return;
        const u = units[i];
        if (s.frame) {
          ctx.fillStyle = c.frame;
          ctx.fillRect(s.x, s.y, s.w, s.h);
          if (s.head) {
            ctx.font = `600 11px ${c.font}`;
            ctx.fillStyle = c.text;
            const size = formatBytes(u.size);
            const sizeW = ctx.measureText(size).width;
            ctx.fillText(fit(ctx, u.name, s.w - sizeW - 20), s.x + 6, s.y + s.head / 2 + 1);
            ctx.font = `11px ${c.font}`;
            ctx.fillStyle = c.sub;
            if (s.w > sizeW + 60) ctx.fillText(size, s.x + s.w - sizeW - 6, s.y + s.head / 2 + 1);
          }
          return;
        }
        ctx.fillStyle = paint(i);
        ctx.fillRect(s.x, s.y, s.w, s.h);
        if (s.w >= 24 && s.h >= 16) { // 小於 24×16 的方塊不顯示文字
          ctx.fillStyle = ink(i);
          ctx.font = `600 11px ${c.font}`;
          const two = s.h >= 34 && s.w >= 50;
          ctx.fillText(fit(ctx, u.name, s.w - 8), s.x + 4, s.y + (two ? 11 : s.h / 2));
          if (two) {
            ctx.font = `11px ${c.font}`;
            ctx.fillText(fit(ctx, formatBytes(u.size), s.w - 8), s.x + 4, s.y + 25);
          }
        }
      });
      for (const i of [...sel.picked, hover]) {
        const s = shapes[i];
        if (!s) continue;
        ctx.lineWidth = sel.has(i) ? 3 : 1.5;
        ctx.strokeStyle = sel.has(i) ? c.selection : c.text;
        ctx.strokeRect(s.x + 1, s.y + 1, s.w - 2, s.h - 2);
      }
    } else {
      const cx = width / 2, cy = height / 2;
      shapes.forEach((s, i) => {
        if (!s || s.a1 - s.a0 <= 0) return;
        ctx.beginPath();
        ctx.arc(cx, cy, s.r1, s.a0, s.a1);
        ctx.arc(cx, cy, s.r0, s.a1, s.a0, true);
        ctx.closePath();
        ctx.fillStyle = paint(i);
        ctx.fill();
        ctx.lineWidth = sel.has(i) ? 3 : i === hover ? 2 : 1.5;
        ctx.strokeStyle = sel.has(i) ? c.selection : i === hover ? c.text : c.bg;
        ctx.stroke();
        // 夠寬的扇形才寫名稱（水平文字，放在扇形中間）
        const mid = (s.a0 + s.a1) / 2, rm = (s.r0 + s.r1) / 2;
        const room = Math.min((s.a1 - s.a0) * rm, 140) - 10;
        if (room > 34 && s.r1 - s.r0 > 18) {
          ctx.font = `600 11px ${c.font}`;
          ctx.fillStyle = ink(i);
          const label = fit(ctx, units[i].name, room);
          ctx.fillText(label, cx + Math.cos(mid) * rm - ctx.measureText(label).width / 2, cy + Math.sin(mid) * rm);
        }
      });
      // 中間：目前的資料夾與總大小
      const r0 = (Math.min(width, height) / 2 - 6) * 0.3;
      ctx.textAlign = "center";
      ctx.fillStyle = c.text;
      ctx.font = `600 13px ${c.font}`;
      ctx.fillText(fit(ctx, usage?.name || "", r0 * 1.7), cx, cy - 9);
      ctx.fillStyle = c.sub;
      ctx.font = `12px ${c.font}`;
      ctx.fillText(formatBytes(total), cx, cy + 10);
      ctx.textAlign = "left";
    }
  }
  $effect(() => {
    shapes;
    hover;
    theme;
    sel.size;
    sel.focus;
    for (const i of sel.picked) i; // 選取變了就重畫
    draw();
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

  const at = (e) => {
    const r = canvas.getBoundingClientRect();
    return hit(e.clientX - r.left, e.clientY - r.top);
  };
  function onmove(e) {
    hover = at(e);
    const r = box.getBoundingClientRect();
    tip = { x: Math.min(e.clientX - r.left + 12, width - 180), y: Math.min(e.clientY - r.top + 14, height - 40) };
  }
  function onkeydown(e) {
    const key = e.key === "ArrowRight" ? "ArrowDown" : e.key === "ArrowLeft" ? "ArrowUp" : e.key;
    handleViewKey(new Proxy(e, { get: (o, k) => (k === "key" ? key : typeof o[k] === "function" ? o[k].bind(o) : o[k]) }),
      { sel, total: units.length, onopen, onpreview });
  }
  const legend = $derived([...new Set(units.map(colorKey))].filter((k) => k !== "rest"));
  const shown = $derived(hover >= 0 ? units[hover] : null);
</script>

<div class="usage">
  <div class="bar mac-callout">
    <ul class="legend">
      {#each legend as k (k)}<li><KindIcon kind={k} size={14} />{k === "folder" ? t("info.kind.folder") : t(`kind.${k}`)}</li>{/each}
      <li class="note">{t("usage.colorNote")}</li>
    </ul>
    <SegmentedControl size="small" value={chart} onchange={setChart} ariaLabel={t("usage.chart")}
      segments={[{ value: "treemap", label: t("usage.treemap") }, { value: "sunburst", label: t("usage.sunburst") }]} />
  </div>
  <!-- svelte-ignore a11y_no_noninteractive_tabindex -->
  <div class="stage" bind:this={box} bind:clientWidth={width} bind:clientHeight={height} tabindex="0" role="listbox" aria-multiselectable="true"
    aria-label={t("usage.label", { name: usage?.name || "" })} aria-activedescendant={sel.focus >= 0 ? `item-${sel.focus}` : undefined} {onkeydown}>
    <canvas bind:this={canvas} style:width="{width}px" style:height="{height}px" aria-hidden="true"
      onpointermove={onmove} onpointerleave={() => (hover = -1)}
      onclick={(e) => { const i = at(e); if (i >= 0) sel.click(i, e); else sel.clear(); }}
      ondblclick={(e) => { const i = at(e); if (i >= 0) onopen?.(i); }}
      oncontextmenu={(e) => { e.preventDefault(); const i = at(e); if (i >= 0) { sel.context(i); oncontext?.(e, i); } }}></canvas>
    <!-- 給螢幕閱讀器的清單：畫面上看不到，內容和圖上的方塊相同 -->
    <ul class="sr">
      {#each units as u, i (i)}<li id="item-{i}" role="option" aria-selected={sel.has(i)}>{u.name}，{formatBytes(u.size)}</li>{/each}
    </ul>
    {#if shown}
      <div class="tip mac-callout" style:left="{tip.x}px" style:top="{tip.y}px">
        <b>{shown.name}</b>{#if shown.note}<span>{shown.note}</span>{/if}
        <span>{formatBytes(shown.size)}{total ? ` · ${Math.max(0.1, (shown.size / total) * 100).toFixed(1)}%` : ""}</span>
      </div>
    {/if}
  </div>
</div>

<style>
  .usage { display: flex; flex-direction: column; height: 100%; min-height: 0; }
  .bar { flex: none; display: flex; align-items: center; justify-content: space-between; gap: var(--space-4); padding: var(--space-2) var(--space-4); color: var(--label-secondary); }
  .legend { list-style: none; margin: 0; padding: 0; display: flex; flex-wrap: wrap; gap: var(--space-1) var(--space-4); }
  .legend li { display: inline-flex; align-items: center; gap: var(--space-1); }
  .legend .note { color: var(--label-tertiary); }
  .stage { position: relative; flex: 1; min-height: 0; margin: 0 var(--space-4) var(--space-4); outline: none; border-radius: var(--radius-sm); overflow: hidden; }
  .stage:focus-visible { box-shadow: var(--focus-ring); }
  canvas { display: block; }
  .sr { position: absolute; width: 1px; height: 1px; margin: -1px; padding: 0; overflow: hidden; clip-path: inset(50%); white-space: nowrap; list-style: none; }
  .tip { position: absolute; z-index: 2; pointer-events: none; display: flex; flex-direction: column; gap: 1px; max-width: 260px; padding: var(--space-1) var(--space-2);
    border-radius: var(--radius-sm); background: var(--elevated-primary); color: var(--label-primary); box-shadow: var(--shadow-popover); }
  .tip b { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .tip span { color: var(--label-secondary); }
</style>
