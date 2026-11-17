<script>
  /**
   * 樹狀檢視（節點連線圖）：目前資料夾在最左邊，往右一層層展開。
   * 方塊的顏色是裡面佔最多空間的類型；連線越粗，表示佔上一層越多空間；方塊下方的細條是佔上一層的比例。
   * 按一下選取並展開資料夾；按右邊的圓鈕收合；按兩下進入那個資料夾。
   * 方向鍵：上下在同一層移動、→ 展開或往下一層、← 收合或回上一層；空白鍵快速預覽、Enter 開啟。
   */
  import { Icon } from "../ui/index.js";
  import KindIcon from "./KindIcon.svelte";
  import { t, formatBytes, formatNumber } from "../i18n/index.svelte.js";

  let { graph, sel, onopen, onpreview, oncontext } = $props();

  const W = 208, H = 52, HGAP = 72, VGAP = 10, PAD = 24;
  let box = $state();

  // ---- 版面：葉子由上往下排，父節點和它的第一個子節點同高 ----
  // （展開時被按的那個節點留在原地，底下的節點往下讓位；按兩下的第二下才不會點到別的地方）
  const layout = $derived.by(() => {
    graph.state.tick;
    const pos = new Map();
    let y = PAD;
    let maxDepth = 0;
    const place = (i) => {
      const n = graph.nodes[i];
      maxDepth = Math.max(maxDepth, n.depth);
      const kids = n.open && n.children?.length ? n.children : null;
      if (!kids) {
        pos.set(i, { x: PAD + n.depth * (W + HGAP), y });
        y += H + VGAP;
        return;
      }
      for (const c of kids) place(c);
      pos.set(i, { x: PAD + n.depth * (W + HGAP), y: pos.get(kids[0]).y });
    };
    if (graph.nodes.length) place(0);
    return { pos, width: PAD * 2 + (maxDepth + 1) * W + maxDepth * HGAP, height: y - VGAP + PAD };
  });
  const shown = $derived([...layout.pos.keys()]);
  const share = (n) => {
    const p = n.parent >= 0 ? graph.nodes[n.parent] : null;
    return p && p.size ? Math.min(1, n.size / p.size) : 1;
  };
  const color = (n) => `var(--kind-${n.rest ? "other" : n.type === "folder" ? n.mainKind || "folder" : n.kind === "raw" ? "photo" : n.kind === "package" ? "other" : n.kind})`;
  const links = $derived(shown.filter((i) => graph.nodes[i].parent >= 0).map((i) => {
    const n = graph.nodes[i], a = layout.pos.get(n.parent), b = layout.pos.get(i);
    // 像組織圖：從父節點往右一小段，沿一條直線往下，再轉進每個子節點（轉角是圓的）
    const x1 = a.x + W, y1 = a.y + H / 2, x2 = b.x, y2 = b.y + H / 2, mx = x1 + HGAP / 2;
    const r = Math.min(10, (y2 - y1) / 2);
    const d = y2 - y1 < 1 ? `M${x1},${y1} H${x2}`
      : `M${x1},${y1} H${mx - r} Q${mx},${y1} ${mx},${y1 + r} V${y2 - r} Q${mx},${y2} ${mx + r},${y2} H${x2}`;
    return { i, d, w: 1.5 + share(n) * 12, c: color(n) };
  }));

  // ---- 操作 ----
  async function pick(i, e) {
    sel.click(i, e);
    const n = graph.nodes[i];
    if (n.rest && n.more) return graph.more(i); // 「其他」：再多顯示 40 個
    if (n.type === "folder" && !n.open && !e?.metaKey && !e?.shiftKey) {
      await graph.expand(i);
      reveal(i, true);
    }
  }
  function toggle(e, i) {
    e.stopPropagation();
    const n = graph.nodes[i];
    if (n.open) graph.collapse(i);
    else graph.expand(i).then(() => reveal(i, true));
  }
  /** 把節點（展開時連同它的子節點）捲進畫面 */
  function reveal(i, withKids = false) {
    requestAnimationFrame(() => {
      const p = layout.pos.get(i);
      if (!p || !box) return;
      const right = withKids ? p.x + W * 2 + HGAP : p.x + W;
      if (right > box.scrollLeft + box.clientWidth) box.scrollLeft = right - box.clientWidth + PAD;
      if (p.x < box.scrollLeft) box.scrollLeft = p.x - PAD;
      if (p.y < box.scrollTop) box.scrollTop = p.y - PAD;
      else if (p.y + H > box.scrollTop + box.clientHeight) box.scrollTop = p.y + H - box.clientHeight + PAD;
    });
  }
  function move(i) {
    sel.moveTo(i, graph.nodes.length);
    reveal(i);
  }
  function onkeydown(e) {
    const i = sel.focus >= 0 ? sel.focus : 0;
    const n = graph.nodes[i];
    if (!n) return;
    const siblings = n.parent >= 0 ? graph.nodes[n.parent].children : [0];
    const at = siblings.indexOf(i);
    const keys = {
      ArrowDown: () => at < siblings.length - 1 && move(siblings[at + 1]),
      ArrowUp: () => at > 0 && move(siblings[at - 1]),
      ArrowRight: async () => {
        if (n.type !== "folder" || n.leaf) return;
        if (!n.open) await graph.expand(i);
        if (n.children?.length) move(n.children[0]);
      },
      ArrowLeft: () => (n.open && !n.isRoot ? graph.collapse(i) : n.parent >= 0 && move(n.parent)),
      Enter: () => onopen?.(i),
      " ": () => onpreview?.(i),
      Escape: () => sel.clear(),
    };
    if (keys[e.key]) {
      e.preventDefault();
      if (sel.focus < 0) return move(0);
      keys[e.key]();
    }
  }
</script>

<!-- svelte-ignore a11y_no_noninteractive_tabindex -->
<div class="graph mac-callout" bind:this={box} tabindex="0" role="tree" aria-label={t("view.items")} {onkeydown}
  aria-activedescendant={sel.focus >= 0 ? `item-${sel.focus}` : undefined}>
  <div class="space" style:width="{layout.width}px" style:height="{layout.height}px">
    <svg width={layout.width} height={layout.height} aria-hidden="true">
      {#each links as l (l.i)}<path d={l.d} stroke={l.c} stroke-width={l.w} />{/each}
    </svg>
    {#each shown as i (i)}
      {@const n = graph.nodes[i]}
      {@const p = layout.pos.get(i)}
      {@const pct = share(n)}
      <!-- svelte-ignore a11y_click_events_have_key_events -->
      <div class="node" class:on={sel.has(i)} class:root={n.isRoot} id="item-{i}" role="treeitem" tabindex="-1" aria-selected={sel.has(i)}
        aria-level={n.depth + 1} aria-expanded={n.type === "folder" && !n.leaf ? n.open : undefined}
        style:transform="translate({p.x}px, {p.y}px)" style:--c={color(n)} title={`${n.name} · ${formatBytes(n.size) || "0 KB"}${n.files != null ? ` · ${t("status.filesOnly", { files: formatNumber(n.files) })}` : ""}`}
        onclick={(e) => pick(i, e)} ondblclick={() => onopen?.(i)}
        oncontextmenu={(e) => { e.preventDefault(); sel.context(i); oncontext?.(e, i); }}>
        <KindIcon kind={n.rest ? "other" : n.type === "folder" ? "folder" : n.kind} size={16} />
        <span class="text">
          <b class="mac-body">{n.name}</b>
          <span class="sub">{formatBytes(n.size) || "0 KB"}{#if !n.isRoot} · {pct >= 0.995 ? "100" : (pct * 100).toFixed(pct < 0.1 ? 1 : 0)}%{/if}</span>
          {#if !n.isRoot}<span class="bar" aria-hidden="true"><i style:width="{pct * 100}%"></i></span>{/if}
        </span>
        {#if n.type === "folder" && !n.leaf && !n.isRoot}
          <button type="button" class="disc" tabindex="-1" aria-label={n.open ? t("view.collapse") : t("view.expand")} onclick={(e) => toggle(e, i)}>
            {#if n.loading}<span class="dots">…</span>{:else}<Icon name={n.open ? "minus" : "plus"} size={11} weight="bold" />{/if}
          </button>
        {/if}
      </div>
    {/each}
  </div>
</div>

<style>
  .graph { height: 100%; overflow: auto; position: relative; outline: none; overscroll-behavior: contain; color: var(--label-primary); background: var(--control-bg); }
  .graph:focus-visible { box-shadow: inset var(--focus-ring); }
  .space { position: relative; }
  svg { position: absolute; inset: 0; pointer-events: none; }
  path { fill: none; stroke-opacity: .4; stroke-linecap: round; stroke-linejoin: round; }
  .node { position: absolute; left: 0; top: 0; width: 208px; height: 52px; box-sizing: border-box; display: flex; align-items: center; gap: var(--space-2);
    padding: 0 var(--space-2) 0 var(--space-3); border-radius: var(--radius-md); background: var(--control-bg); cursor: default; user-select: none; -webkit-user-select: none;
    box-shadow: inset 0 0 0 1px var(--separator), inset 4px 0 0 var(--c); }
  .node:hover { background: var(--fill-quaternary); }
  .node.root { box-shadow: inset 0 0 0 1.5px var(--c), inset 4px 0 0 var(--c); }
  .node.on { box-shadow: 0 0 0 3px var(--selection), inset 4px 0 0 var(--c); }
  .text { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 1px; }
  .text b { font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .sub { color: var(--label-secondary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-feature-settings: "tnum"; }
  .bar { display: block; height: 3px; margin-top: 2px; border-radius: var(--radius-capsule); background: var(--fill-tertiary); overflow: hidden; }
  .bar i { display: block; height: 100%; border-radius: inherit; background: var(--c); }
  .disc { flex: none; width: var(--control-small); height: var(--control-small); display: inline-flex; align-items: center; justify-content: center; border: 0;
    border-radius: var(--radius-capsule); background: var(--fill-tertiary); color: var(--label-primary); cursor: pointer; }
  .disc:hover { background: var(--fill-secondary); }
  .dots { line-height: 1; }
</style>
