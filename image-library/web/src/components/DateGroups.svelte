<script>
  /**
   * 資料夾與相簿的照片：依日／月／年分組或不分組，可改排序。
   * 每個資料夾或相簿各自記住選擇（存在這台裝置的瀏覽器）。
   */
  import { onMount } from "svelte";
  import Grid from "./Grid.svelte";
  import Scrubber from "./Scrubber.svelte";
  import DatePill from "./DatePill.svelte";
  import Slideshow from "./Slideshow.svelte";
  import Icon from "./Icon.svelte";
  import Menu from "./Menu.svelte";
  import BackButton from "./BackButton.svelte";
  import { slide } from "svelte/transition";
  import { link } from "../lib/router.svelte.js";
  import { mdiPlayBoxMultipleOutline, mdiSort, mdiChevronRight } from "../lib/icons.js";
  import { fullDayLabel, monthLabel, count } from "../lib/format.js";
  import { matches, filterActive, clearFilter, useFilter } from "../lib/filter.svelte.js";

  /**
   * 頁首：返回鍵、上一層路徑、標題、副標（張數與日期範圍），右側是篩選、檢視、播放與「更多」選單。
   * above：放在頁首和照片之間的內容（例如子資料夾）。
   */
  let { assets = [], storeKey = "", defaultGroup = "month", title = "", subtitle = null, back = null, crumbs = [], menu = [], above = null, titleExtra = null } = $props();


  const GROUPS = [["day", "依日期"], ["month", "依月份"], ["year", "依年份"], ["none", "不分組"]];
  // svelte-ignore state_referenced_locally
  let group = $state(read("group") || defaultGroup);
  let order = $state(read("order") || "desc");
  let root;
  let scroller;
  let active = $state(0);
  let dragging = $state(false);
  let showing = $state(false);

  function read(k) {
    try {
      return storeKey ? localStorage.getItem(`dg:${storeKey}:${k}`) : null;
    } catch {
      return null;
    }
  }
  function save(k, v) {
    try {
      if (storeKey) localStorage.setItem(`dg:${storeKey}:${k}`, v);
    } catch {
      /* 無法儲存時只影響這次 */
    }
  }
  function setGroup(v) {
    group = v;
    save("group", v);
  }
  function setOrder(v) {
    order = v;
    save("order", v);
  }

  // 依檔名排序用自然順序：IMG_2 排在 IMG_10 前面
  const collator = new Intl.Collator(undefined, { numeric: true, sensitivity: "base" });
  const byName = $derived(order === "name" || order === "name-desc");
  // 依檔名排序時不分組（日期分組對檔名排序沒有意義）
  const effGroup = $derived(byName ? "none" : group);

  const sorted = $derived.by(() => {
    const list = assets.filter(matches);
    if (byName) {
      const dir = order === "name" ? 1 : -1;
      return list.sort((a, b) => dir * (collator.compare(a.name || "", b.name || "") || a.id - b.id));
    }
    list.sort((a, b) => {
      const x = a.at || "";
      const y = b.at || "";
      if (!x !== !y) return x ? -1 : 1; // 沒有日期的放最後
      return order === "asc" ? x.localeCompare(y) || a.id - b.id : y.localeCompare(x) || b.id - a.id;
    });
    return list;
  });

  function keyOf(a) {
    if (!a.at) return "";
    return effGroup === "day" ? a.at.slice(0, 10) : effGroup === "month" ? a.at.slice(0, 7) : a.at.slice(0, 4);
  }
  function labelOf(key, sample) {
    if (!key) return "日期不明";
    if (effGroup === "day") return fullDayLabel(sample.at);
    if (effGroup === "month") return monthLabel(key);
    return `${key}年`;
  }

  const groups = $derived.by(() => {
    if (effGroup === "none") return [{ key: "all", label: "", items: sorted, offset: 0 }];
    const out = [];
    let cur = null;
    sorted.forEach((a, i) => {
      const k = keyOf(a);
      if (!cur || cur.key !== k) {
        cur = { key: k, label: labelOf(k, a), items: [], offset: i };
        out.push(cur);
      }
      cur.items.push(a);
    });
    return out;
  });

  const marks = $derived.by(() => {
    const total = sorted.length || 1;
    return groups.map((g) => ({
      label: g.label, year: (g.items[0]?.at || "").slice(0, 4) || "?", top: g.offset / total,
      size: g.items.length / total, count: g.items.length,
    }));
  });
  const showScrubber = $derived(effGroup !== "none" && groups.length > 3 && sorted.length > 60);

  const viewItems = $derived([
    { section: "分組" },
    ...GROUPS.map(([v, label]) => ({ label, checked: effGroup === v, disabled: byName && v !== "none", run: () => setGroup(v) })),
    { section: "排序" },
    { label: "新的在前", checked: order === "desc", run: () => setOrder("desc") },
    { label: "舊的在前", checked: order === "asc", run: () => setOrder("asc") },
    { label: "檔名 A → Z", checked: order === "name", run: () => setOrder("name") },
    { label: "檔名 Z → A", checked: order === "name-desc", run: () => setOrder("name-desc") },
  ]);

  // 副標：張數與拍攝日期範圍
  const autoSubtitle = $derived.by(() => {
    if (!assets.length) return "";
    const dates = assets.map((a) => a.at).filter(Boolean).sort();
    const fmt = (iso) => monthLabel(iso.slice(0, 7));
    let range = "";
    if (dates.length) {
      const a = fmt(dates[0]);
      const b = fmt(dates[dates.length - 1]);
      range = a === b ? a : `${a} – ${b}`;
    }
    const n = filterActive() ? `${count(sorted.length)} / ${count(assets.length)} 個項目` : `${count(assets.length)} 個項目`;
    return range ? `${n} · ${range}` : n;
  });

  function jump(i) {
    active = i;
    const el = root?.querySelectorAll("[data-group]")[i];
    if (el && scroller) scroller.scrollTop = el.offsetTop - 8;
  }

  onMount(() => {
    const releaseFilter = useFilter(true);
    scroller = root.closest("main");
    const onScroll = () => {
      if (dragging || !root) return;
      const top = scroller.scrollTop + 80;
      const els = root.querySelectorAll("[data-group]");
      let idx = 0;
      for (let i = 0; i < els.length; i++) {
        if (els[i].offsetTop <= top) idx = i;
        else break;
      }
      active = idx;
    };
    scroller?.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      releaseFilter();
      scroller?.removeEventListener("scroll", onScroll);
    };
  });
</script>

<div class="dg" bind:this={root}>
  <div class="body">
    <div class="dg-head" class:bare={!title && !crumbs.length}>
      {#if back}<BackButton to={back} />{/if}
      {#if title || titleExtra || crumbs.length}
        <div class="titles">
          {#if crumbs.length}
            <nav class="crumbs" aria-label="位置">
              {#each crumbs as c, i (i)}
                {#if i}<Icon path={mdiChevronRight} size={14} />{/if}<a href={c.href} use:link>{c.label}</a>
              {/each}
            </nav>
          {/if}
          <div class="title-row">{#if title}<h1>{title}</h1>{/if}{@render titleExtra?.()}</div>
          {#if subtitle ?? autoSubtitle}<span class="sub">{subtitle ?? autoSubtitle}</span>{/if}
        </div>
      {/if}
      <span class="spacer"></span>
      {#if assets.length}
        <Menu icon={mdiSort} label="分組與排序" items={viewItems} />
        <button class="icon-btn ctl" onclick={() => (showing = true)} disabled={!sorted.length} aria-label="播放幻燈片" title="播放幻燈片"><Icon path={mdiPlayBoxMultipleOutline} /></button>
      {/if}
      {#if menu.length}<Menu items={menu} />{/if}
    </div>
    {@render above?.()}
    {#if !sorted.length && filterActive()}
      <div class="empty"><h2>沒有符合篩選條件的項目</h2><p><button class="btn ghost" onclick={clearFilter}>清除篩選</button></p></div>
    {/if}
    {#each groups.filter((g) => g.items.length) as g (g.key)}
      <section data-group={g.key} data-label={g.label || null}>
        {#if g.label}<h2 class="title">{g.label}<span>{count(g.items.length)} 張</span></h2>{/if}
        <Grid assets={g.items} list={sorted} offset={g.offset} />
      </section>
    {/each}
  </div>
  {#if showScrubber}
    <Scrubber {marks} {active} onjump={jump} bind:dragging />
  {/if}
  {#if effGroup !== "none"}<DatePill />{/if}
  {#if showing}<Slideshow items={sorted} onclose={() => (showing = false)} />{/if}
</div>

<style>
  .dg { display: flex; gap: 8px; }
  .body { flex: 1; min-width: 0; }
  .dg-head { display: flex; align-items: center; gap: 4px; min-height: 64px; padding: 8px 0; }
  .dg-head.bare { min-height: 0; padding: 0 0 4px; }
  .titles { display: flex; flex-direction: column; min-width: 0; margin-left: 4px; }
  .crumbs { display: flex; align-items: center; flex-wrap: wrap; gap: 2px; font-size: 14px; line-height: 18px; color: var(--on-surface-variant); }
  .crumbs a { color: inherit; text-decoration: none; border-radius: var(--corner-extra-small); padding: 0 2px; }
  .crumbs a:hover { color: var(--primary); text-decoration: underline; }
  .title-row { display: flex; align-items: center; gap: 4px; min-width: 0; }
  .title-row h1 { font-size: 28px; line-height: 36px; font-weight: 400; margin: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; min-width: 0; }
  .sub { font-size: 14px; line-height: 20px; color: var(--on-surface-variant); }
  .spacer { flex: 1; }
  .ctl { color: var(--on-surface-variant); position: relative; }
  .title { font-size: 16px; line-height: 24px; font-weight: 500; margin: 20px 0 8px; display: flex; align-items: baseline; gap: 10px; }
  .title span { font-size: 12px; font-weight: 400; color: var(--on-surface-variant); }
  @media (max-width: 600px) { .title-row h1 { font-size: 22px; line-height: 28px; } }
</style>
