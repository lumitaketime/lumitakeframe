<script>
  import Loading from "../components/Loading.svelte";
  import { onMount, tick, untrack } from "svelte";
  import Grid from "../components/Grid.svelte";
  import Icon from "../components/Icon.svelte";
  import Memories from "../components/Memories.svelte";
  import Scrubber from "../components/Scrubber.svelte";
  import DatePill from "../components/DatePill.svelte";
  import { filterParams, filterActive, clearFilter, useFilter } from "../lib/filter.svelte.js";
  import { api } from "../lib/api.js";
  import { app, selection } from "../lib/state.svelte.js";
  import { link } from "../lib/router.svelte.js";
  import { dayLabel, fullDayLabel, monthLabel, count } from "../lib/format.js";
  import { estimateHeight, naturalWidth, squareCols } from "../lib/layout.js";
  import { mdiCheckCircle, mdiCheckboxBlankCircleOutline } from "../lib/icons.js";
  import { slide } from "svelte/transition";

  let { scope = {}, title = "", emptyText = "" } = $props();

  let buckets = $state([]);
  let width = $state(0);
  let ready = $state(false);
  let root;
  let scroller;
  let observer;
  let scrubActive = $state(-1);
  let dragging = $state(false);

  const fullScope = $derived({ ...scope, ...filterParams() });
  const fkey = $derived(JSON.stringify(filterParams()));
  let lastKey = null;
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

  // 正方形（手機一律、桌機可在設定選）：幾張照片的日期並排但仍對齊欄位；依比例：等高列，小群組並排
  const square = $derived(width < 640 || app.server?.ui?.grid_style === "square");
  const cols = $derived(squareCols(width, rowTarget));
  function dayWidth(items) {
    if (!width) return "100%";
    if (square) {
      if (items.length >= cols) return "100%";
      const gap = width < 640 ? 2 : 4;
      const sq = (width - gap * (cols - 1)) / cols;
      return `${items.length * sq + (items.length - 1) * gap}px`;
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
    const list = await api("/api/timeline/buckets", { params: fullScope });
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
      b.assets = await api("/api/timeline/bucket", { params: { ...fullScope, month: b.month } });
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
    const k = fkey;
    untrack(() => {
      if (lastKey !== null && lastKey !== k) buckets = []; // 換了篩選條件：重新載入
      lastKey = k;
      loadBuckets().catch(() => (ready = true));
    });
  });

  // ---- 右側時間捲軸 ----
  const marks = $derived.by(() => {
    let acc = 0;
    return buckets.map((b) => {
      const top = total ? acc / total : 0;
      acc += b.count;
      return { label: monthLabel(b.month), year: b.month.slice(0, 4), top, size: total ? b.count / total : 0, count: b.count };
    });
  });

  function jump(i) {
    scrubActive = i;
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

  function toggleDay(items) {
    const all = items.every((a) => selection.has(a.id));
    for (const a of items) all ? selection.delete(a.id) : selection.add(a.id);
  }
  // 篩選按鈕在頂欄搜尋框旁邊
  onMount(() => useFilter(scope.type !== "video"));
</script>

<div class="timeline" bind:this={root}>
  <div class="content"><div class="inner" bind:clientWidth={width}>
    {#if !title && !filterActive()}<Memories />{/if}
    {#if title}
      <div class="tl-head titled"><div class="tl-title"><h1>{title}</h1><span class="muted small">{count(total)} 個項目</span></div></div>
    {/if}

    {#if !ready}<Loading kind="grid" />{/if}
    {#if ready && !buckets.length}
      <div class="empty">
        {#if filterActive()}
          <h2>沒有符合篩選條件的項目</h2><p><button class="btn ghost" onclick={clearFilter}>清除篩選</button></p>
        {:else if emptyText}
          <h2>{title || "沒有項目"}</h2><p>{emptyText}</p>
        {:else}
          <h2>歡迎使用 Lumitake Library</h2>
          <p>加入電腦或外接 SSD 上的照片資料夾，就會自動掃描並依時間排列。<br />原始檔案留在原位，不會被複製。</p>
          <p><a class="btn" href="/settings/library" use:link>加入照片資料夾</a></p>
        {/if}
      </div>
    {/if}

    {#each buckets as b (b.month)}
      <section
        data-month={b.month}
        class="month"
        style:min-height={b.assets ? null : `${estimateHeight(b.count, width, rowTarget, 4, square) + 56}px`}
      >
        <h2 class="month-title">{monthLabel(b.month)}</h2>
        {#if b.assets}
          <div class="days">
          {#each days(b.assets) as d (d.day)}
            {@const allSel = d.items.every((a) => selection.has(a.id))}
            <div class="day" style:width={dayWidth(d.items)} data-label={fullDayLabel(d.items[0].at)}>
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
        {:else}
          <Loading kind="grid" count={Math.min(b.count, 18)} delay={0} />
        {/if}
      </section>
    {/each}
  </div></div>

  {#if buckets.length > 1}
    <Scrubber {marks} active={scrubActive} onjump={jump} bind:dragging />
  {/if}
  <DatePill />
</div>

<style>
  .tl-head { display: flex; align-items: center; gap: 4px; margin: -4px 0 0; min-height: 40px; }
  .tl-head.titled { min-height: 64px; margin: 0; }
  .tl-title { display: flex; align-items: baseline; gap: 12px; min-width: 0; }
  .tl-title h1 { font-size: 28px; line-height: 36px; font-weight: 400; margin: 0; }
  .spacer { flex: 1; }
  .timeline { display: flex; min-height: 100%; }
  .content { flex: 1; min-width: 0; padding: 0 12px 100px 24px; }
  .month-title { font-size: 20px; font-weight: 500; margin: 22px 0 4px; }
  .days { display: flex; flex-wrap: wrap; column-gap: 12px; }
  @media (max-width: 639px) { .days { column-gap: 2px; } }
  .day { margin-bottom: 12px; min-width: 0; }
  .day-head span { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .day-head { display: flex; align-items: center; gap: 4px; height: 40px; font-size: 14px; font-weight: 500; }
  .day-check {
    border: 0; background: none; padding: 0; width: 0; overflow: hidden; color: var(--on-surface-variant); cursor: pointer;
    transition: width .15s; display: flex;
  }
  .day:hover .day-check, .day-check.on { width: 24px; }
  .day-check.on { color: var(--primary); }

  @media (max-width: 760px) {
    .content { padding: 0 4px 100px; }
    .month-title { font-size: 17px; margin: 16px 6px 2px; }
    .day-head { padding: 0 6px; height: 34px; font-size: 13px; }
  }
</style>
