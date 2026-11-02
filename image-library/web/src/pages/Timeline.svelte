<script>
  import { onMount, tick, untrack } from "svelte";
  import Grid from "../components/Grid.svelte";
  import Icon from "../components/Icon.svelte";
  import { api } from "../lib/api.js";
  import { app, selection } from "../lib/state.svelte.js";
  import { link } from "../lib/router.svelte.js";
  import { dayLabel, monthLabel, count } from "../lib/format.js";
  import { estimateHeight, naturalWidth } from "../lib/layout.js";
  import { mdiCheckCircle, mdiCheckboxBlankCircleOutline } from "../lib/icons.js";

  let { scope = {}, title = "", emptyText = "" } = $props();

  let buckets = $state([]);
  let width = $state(0);
  let ready = $state(false);
  let root;
  let scroller;
  let observer;
  let scrubHover = $state(null);
  let scrubActive = $state(-1);
  let dragging = $state(false);
  let scrubEl = $state();
  let scrubHeight = $state(0);

  const rowTarget = $derived(width > 1600 ? 260 : width > 1000 ? 230 : 190);
  const total = $derived(buckets.reduce((s, b) => s + b.count, 0));

  const flat = $derived.by(() => {
    const out = [];
    const bases = {};
    for (const b of buckets) {
      if (!b.assets) continue;
      bases[b.month] = out.length;
      out.push(...b.assets);
    }
    return { out, bases };
  });

  // 手機：正方形網格，幾張照片的日期並排但仍對齊欄位；桌機：等高列，小群組並排
  const cols = $derived(width < 420 ? 3 : 4);
  function dayWidth(items) {
    if (!width) return "100%";
    if (width < 640) {
      if (items.length >= cols) return "100%";
      const sq = (width - 2 * (cols - 1)) / cols;
      return `${items.length * sq + (items.length - 1) * 2}px`;
    }
    const nat = naturalWidth(items, rowTarget);
    return nat <= width - 2 ? `${Math.max(Math.ceil(nat), 150)}px` : "100%";
  }

  function days(assets) {
    const groups = [];
    let cur = null;
    assets.forEach((a, i) => {
      const day = (a.at || "").slice(0, 10);
      if (!cur || cur.day !== day) {
        cur = { day, items: [], offset: i };
        groups.push(cur);
      }
      cur.items.push(a);
    });
    return groups;
  }

  async function loadBuckets() {
    const list = await api("/api/timeline/buckets", { params: scope });
    const old = new Map(buckets.map((b) => [b.month, b]));
    buckets = list.map((b) => {
      const o = old.get(b.month);
      if (o) {
        o.stale = o.assets !== null;
        o.count = b.count;
        return o;
      }
      return { ...b, assets: null, loading: false, stale: false };
    });
    ready = true;
    await tick();
    for (const b of buckets) if (b.stale) loadBucket(b, true);
    observeAll();
  }

  async function loadBucket(b, force = false) {
    if (b.loading || (b.assets && !force)) return;
    b.loading = true;
    const el = root?.querySelector(`[data-month="${b.month}"]`);
    const before = el?.offsetHeight || 0;
    const above = el && scroller && el.offsetTop + before <= scroller.scrollTop + 1;
    try {
      b.assets = await api("/api/timeline/bucket", { params: { ...scope, month: b.month } });
    } catch {
      /* 下次捲到再試 */
    } finally {
      b.loading = false;
      b.stale = false;
    }
    await tick();
    // 視窗上方的月份載入後高度改變，修正捲動位置避免畫面跳動
    if (above && el && scroller) scroller.scrollTop += el.offsetHeight - before;
  }

  function observeAll() {
    if (!observer || !root) return;
    observer.disconnect();
    root.querySelectorAll("[data-month]").forEach((el) => observer.observe(el));
  }

  onMount(() => {
    scroller = root.closest("main");
    observer = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (!e.isIntersecting) continue;
          const b = buckets.find((x) => x.month === e.target.dataset.month);
          if (b) loadBucket(b);
        }
      },
      { root: scroller, rootMargin: "150% 0px" },
    );
    scroller.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      observer.disconnect();
      scroller.removeEventListener("scroll", onScroll);
    };
  });

  $effect(() => {
    app.refreshKey;
    untrack(() => loadBuckets().catch(() => (ready = true)));
  });

  // ---- 右側時間捲軸 ----
  const marks = $derived.by(() => {
    let acc = 0;
    return buckets.map((b) => {
      const top = total ? acc / total : 0;
      acc += b.count;
      return { month: b.month, year: b.month.slice(0, 4), top, size: total ? b.count / total : 0 };
    });
  });

  const years = $derived.by(() => {
    const out = [];
    let lastPx = -100;
    for (const m of marks) {
      if (out.length && out[out.length - 1].year === m.year) continue;
      const px = m.top * scrubHeight;
      if (px - lastPx < 22) {
        out.push({ year: m.year, top: m.top, hidden: true });
        continue;
      }
      lastPx = px;
      out.push({ year: m.year, top: m.top, hidden: false });
    }
    return out;
  });

  function indexAt(clientY) {
    const r = scrubEl.getBoundingClientRect();
    const f = Math.min(Math.max((clientY - r.top) / r.height, 0), 0.9999);
    let i = marks.findIndex((m) => f >= m.top && f < m.top + m.size);
    if (i === -1) i = marks.length - 1;
    return i;
  }

  function jump(i) {
    const el = root.querySelector(`[data-month="${buckets[i]?.month}"]`);
    if (el && scroller) scroller.scrollTop = el.offsetTop - 8;
  }

  function onScroll() {
    if (dragging || !root) return;
    const top = scroller.scrollTop + 80;
    const els = root.querySelectorAll("[data-month]");
    let idx = 0;
    for (let i = 0; i < els.length; i++) {
      if (els[i].offsetTop <= top) idx = i;
      else break;
    }
    scrubActive = idx;
  }

  function scrubDown(e) {
    dragging = true;
    e.currentTarget.setPointerCapture(e.pointerId);
    const i = indexAt(e.clientY);
    scrubActive = i;
    jump(i);
  }
  function scrubMove(e) {
    const i = indexAt(e.clientY);
    scrubHover = { i, y: e.clientY - scrubEl.getBoundingClientRect().top };
    if (dragging && i !== scrubActive) {
      scrubActive = i;
      jump(i);
    }
  }
  function scrubUp() {
    dragging = false;
  }

  function toggleDay(items) {
    const all = items.every((a) => selection.has(a.id));
    for (const a of items) all ? selection.delete(a.id) : selection.add(a.id);
  }
</script>

<div class="timeline" bind:this={root}>
  <div class="content"><div class="inner" bind:clientWidth={width}>
    {#if title}
      <div class="page-head"><h1>{title}</h1><span class="muted small">{count(total)} 個項目</span></div>
    {/if}

    {#if ready && !buckets.length}
      <div class="empty">
        {#if emptyText}
          <h2>{title || "沒有項目"}</h2><p>{emptyText}</p>
        {:else}
          <h2>歡迎使用 Lumitake Library</h2>
          <p>加入電腦或外接 SSD 上的照片資料夾，就會自動掃描並依時間排列。<br />原始檔案留在原位，不會被複製。</p>
          <p><a class="btn" href="/settings" use:link>加入照片資料夾</a></p>
        {/if}
      </div>
    {/if}

    {#each buckets as b (b.month)}
      <section
        data-month={b.month}
        class="month"
        style:min-height={b.assets ? null : `${estimateHeight(b.count, width, rowTarget) + 56}px`}
      >
        <h2 class="month-title">{monthLabel(b.month)}</h2>
        {#if b.assets}
          <div class="days">
          {#each days(b.assets) as d (d.day)}
            {@const allSel = d.items.every((a) => selection.has(a.id))}
            <div class="day" style:width={dayWidth(d.items)}>
              <div class="day-head">
                <button class="day-check" class:on={allSel || selection.size} onclick={() => toggleDay(d.items)} aria-label="選取這一天">
                  <Icon path={allSel ? mdiCheckCircle : mdiCheckboxBlankCircleOutline} size={20} />
                </button>
                <span>{dayLabel(d.items[0].at)}</span>
              </div>
              <Grid assets={d.items} list={flat.out} offset={(flat.bases[b.month] || 0) + d.offset} target={rowTarget} layoutWidth={width} />
            </div>
          {/each}
          </div>
        {/if}
      </section>
    {/each}
  </div></div>

  {#if buckets.length > 1}
    <!-- svelte-ignore a11y_no_static_element_interactions -->
    <div
      class="scrubber"
      class:dragging
      bind:this={scrubEl}
      bind:clientHeight={scrubHeight}
      onpointerdown={scrubDown}
      onpointermove={scrubMove}
      onpointerup={scrubUp}
      onpointercancel={scrubUp}
      onpointerleave={() => (scrubHover = null)}
    >
      {#each years as y (y.year)}
        {#if !y.hidden}<span class="year" style:top="{y.top * 100}%">{y.year}</span>{/if}
        <span class="dot" style:top="{y.top * 100}%"></span>
      {/each}
      {#if scrubActive >= 0 && marks[scrubActive]}
        <span class="indicator" style:top="{marks[scrubActive].top * 100}%"></span>
      {/if}
      {#if scrubHover && marks[scrubHover.i]}
        <span class="hover-label" style:top="{scrubHover.y}px">{monthLabel(marks[scrubHover.i].month)}</span>
      {:else if dragging && marks[scrubActive]}
        <span class="hover-label" style:top="{marks[scrubActive].top * scrubHeight}px">{monthLabel(marks[scrubActive].month)}</span>
      {/if}
    </div>
  {/if}
</div>

<style>
  .timeline { display: flex; min-height: 100%; }
  .content { flex: 1; min-width: 0; padding: 0 12px 100px 24px; }
  .month-title { font-size: 20px; font-weight: 600; margin: 22px 0 4px; }
  .days { display: flex; flex-wrap: wrap; column-gap: 12px; }
  @media (max-width: 639px) { .days { column-gap: 2px; } }
  .day { margin-bottom: 12px; min-width: 0; }
  .day-head span { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .day-head { display: flex; align-items: center; gap: 4px; height: 40px; font-size: 14px; font-weight: 500; }
  .day-check {
    border: 0; background: none; padding: 0; width: 0; overflow: hidden; color: var(--muted); cursor: pointer;
    transition: width .15s; display: flex;
  }
  .day:hover .day-check, .day-check.on { width: 24px; }
  .day-check.on { color: var(--primary); }

  .scrubber {
    position: sticky; top: 0; height: calc(100vh - var(--topbar)); height: calc(100dvh - var(--topbar));
    width: 64px; flex-shrink: 0; cursor: row-resize; user-select: none; touch-action: none;
    padding: 12px 0;
  }
  .year {
    position: absolute; right: 14px; transform: translateY(-50%); font-size: 11px; color: var(--muted);
    pointer-events: none; margin-top: 12px;
  }
  .dot {
    position: absolute; right: 6px; width: 4px; height: 4px; border-radius: 50%; background: var(--line);
    margin-top: 12px; pointer-events: none;
  }
  .indicator {
    position: absolute; right: 0; width: 22px; height: 2px; background: var(--primary); margin-top: 12px;
    transition: top .12s; pointer-events: none;
  }
  .hover-label {
    position: absolute; right: 58px; transform: translateY(-50%); background: var(--panel); color: var(--text);
    box-shadow: var(--shadow); border-radius: 8px; padding: 4px 10px; font-size: 13px; white-space: nowrap;
    pointer-events: none; z-index: 5;
  }
  @media (max-width: 760px) {
    .content { padding: 0 4px 100px; }
    .month-title { font-size: 17px; margin: 16px 6px 2px; }
    .day-head { padding: 0 6px; height: 34px; font-size: 13px; }
    .scrubber { width: 26px; position: fixed; right: 0; top: var(--topbar); bottom: 64px; height: auto; z-index: 10; }
    .year, .dot { display: none; }
    .scrubber.dragging .year { display: block; }
    .indicator { width: 6px; height: 36px; border-radius: 3px; right: 3px; transform: translateY(-50%); opacity: .6; }
    .hover-label { right: 30px; }
  }
</style>
