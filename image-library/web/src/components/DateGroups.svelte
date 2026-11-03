<script>
  /**
   * 資料夾與相簿的照片：依日／月／年分組或不分組，可改排序。
   * 每個資料夾或相簿各自記住選擇（存在這台裝置的瀏覽器）。
   */
  import { onMount } from "svelte";
  import Grid from "./Grid.svelte";
  import Scrubber from "./Scrubber.svelte";
  import DatePill from "./DatePill.svelte";
  import { fullDayLabel, monthLabel, count } from "../lib/format.js";

  let { assets = [], storeKey = "", defaultGroup = "month" } = $props();

  const GROUPS = [["day", "日"], ["month", "月"], ["year", "年"], ["none", "不分組"]];
  // svelte-ignore state_referenced_locally
  let group = $state(read("group") || defaultGroup);
  let order = $state(read("order") || "desc");
  let root;
  let scroller;
  let active = $state(0);
  let dragging = $state(false);

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

  const sorted = $derived.by(() => {
    const list = [...assets];
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
    return group === "day" ? a.at.slice(0, 10) : group === "month" ? a.at.slice(0, 7) : a.at.slice(0, 4);
  }
  function labelOf(key, sample) {
    if (!key) return "日期不明";
    if (group === "day") return fullDayLabel(sample.at);
    if (group === "month") return monthLabel(key);
    return `${key}年`;
  }

  const groups = $derived.by(() => {
    if (group === "none") return [{ key: "all", label: "", items: sorted, offset: 0 }];
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
  const showScrubber = $derived(group !== "none" && groups.length > 3 && sorted.length > 60);

  function jump(i) {
    active = i;
    const el = root?.querySelectorAll("[data-group]")[i];
    if (el && scroller) scroller.scrollTop = el.offsetTop - 8;
  }

  onMount(() => {
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
    return () => scroller?.removeEventListener("scroll", onScroll);
  });
</script>

<div class="dg" bind:this={root}>
  <div class="body">
    <div class="tools">
      <div class="seg" role="group" aria-label="分組方式">
        {#each GROUPS as [v, label] (v)}
          <button class:on={group === v} onclick={() => setGroup(v)}>{label}</button>
        {/each}
      </div>
      <div class="seg" role="group" aria-label="排序">
        <button class:on={order === "desc"} onclick={() => setOrder("desc")}>新 → 舊</button>
        <button class:on={order === "asc"} onclick={() => setOrder("asc")}>舊 → 新</button>
      </div>
    </div>
    {#each groups as g (g.key)}
      <section data-group={g.key} data-label={g.label || null}>
        {#if g.label}<h2 class="title">{g.label}<span>{count(g.items.length)} 張</span></h2>{/if}
        <Grid assets={g.items} list={sorted} offset={g.offset} />
      </section>
    {/each}
  </div>
  {#if showScrubber}
    <Scrubber {marks} {active} onjump={jump} bind:dragging />
  {/if}
  {#if group !== "none"}<DatePill />{/if}
</div>

<style>
  .dg { display: flex; gap: 8px; }
  .body { flex: 1; min-width: 0; }
  .tools { display: flex; gap: 10px; flex-wrap: wrap; margin: 4px 0 8px; }
  .seg { display: inline-flex; border: 1px solid var(--line); border-radius: 999px; overflow: hidden; }
  .seg button { border: 0; background: none; color: var(--muted); padding: 5px 14px; font-size: 13px; cursor: pointer; }
  .seg button + button { border-left: 1px solid var(--line); }
  .seg button.on { background: var(--primary-soft); color: var(--primary); font-weight: 600; }
  .title { font-size: 17px; font-weight: 600; margin: 18px 0 8px; display: flex; align-items: baseline; gap: 10px; }
  .title span { font-size: 12px; font-weight: 400; color: var(--muted); }
</style>
