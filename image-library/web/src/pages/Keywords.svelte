<script>
  import Loading from "../components/Loading.svelte";
  import ExploreTabs from "../components/ExploreTabs.svelte";
  import { api } from "../lib/api.js";
  import { navigate } from "../lib/router.svelte.js";
  import { app } from "../lib/state.svelte.js";

  let data = $state(null);
  let source = $state("all");
  let year = $state("");
  let view = $state("cloud");

  $effect(() => {
    app.refreshKey;
    api("/api/keywords", { params: { source, year, limit: 300 } }).then((d) => (data = d));
  });

  const list = $derived(data?.keywords || []);
  const max = $derived(Math.max(1, ...list.map((k) => k.count)));
  const min = $derived(Math.min(...list.map((k) => k.count), max));
  // 字級依出現次數（取對數，避免最常見的詞把其他擠得太小）
  function size(n) {
    if (max === min) return 20;
    return 13 + (38 * (Math.log(n) - Math.log(min))) / (Math.log(max) - Math.log(min));
  }
  // 雲的排列：大的放中間，像文字雲
  const cloud = $derived.by(() => {
    const sorted = [...list].slice(0, 160);
    const out = [];
    sorted.forEach((k, i) => (i % 2 ? out.push(k) : out.unshift(k)));
    return out;
  });
  const go = (t) => navigate(`/search?q=${encodeURIComponent(`tag:${/\s/.test(t) ? `"${t}"` : t}`)}`);
</script>

<div class="page">
  <div class="page-head">
    <h1>探索</h1>
    <select class="input year" bind:value={year} aria-label="年份">
      <option value="">全部年份</option>
      {#each data?.years || [] as y (y)}<option value={y}>{y}</option>{/each}
    </select>
  </div>
  <ExploreTabs />
  <div class="chips bar">
    <div class="chips">
      <button class="chip" class:on={source === "all"} onclick={() => (source = "all")}>全部</button>
      <button class="chip" class:on={source === "mine"} onclick={() => (source = "mine")}>我的與 Lightroom</button>
      <button class="chip" class:on={source === "ai"} onclick={() => (source = "ai")}>AI 關鍵字</button>
    </div>
    <span class="spacer"></span>
    <div class="chips">
      <button class="chip" class:on={view === "cloud"} onclick={() => (view = "cloud")}>文字雲</button>
      <button class="chip" class:on={view === "list"} onclick={() => (view = "list")}>排行</button>
    </div>
  </div>

  {#if !data}
    <Loading kind="spinner" label="正在整理關鍵字…" />
  {:else if !list.length}
    <div class="empty"><h2>還沒有關鍵字</h2><p>AI 分析後、或在照片加上關鍵字（含 Lightroom 匯入的）後，這裡會依出現次數整理你最常拍的內容。</p></div>
  {:else if view === "cloud"}
    <div class="cloud">
      {#each cloud as k (k.tag)}
        <button class="word" class:mine={k.kind === "mine"} style:font-size="{size(k.count)}px"
          style:opacity={0.55 + (0.45 * size(k.count)) / 51} title="{k.tag}：{k.count} 張" onclick={() => go(k.tag)}>
          #{k.tag}
        </button>
      {/each}
    </div>
    <p class="muted tiny">字越大代表出現在越多照片；藍色是你自己或 Lightroom 加的關鍵字。點任何一個看照片。</p>
  {:else}
    <ol class="rank">
      {#each list as k, i (k.tag)}
        <li>
          <span class="no">{i + 1}</span>
          <button class="tag" class:mine={k.kind === "mine"} onclick={() => go(k.tag)}>#{k.tag}</button>
          <span class="count">{k.count.toLocaleString()} 張</span>
        </li>
      {/each}
    </ol>
  {/if}
</div>

<style>
  .year { width: auto; }
  .bar { margin-bottom: 16px; align-items: center; }
  .spacer { flex: 1; }
  .cloud {
    display: flex; flex-wrap: wrap; justify-content: center; align-items: center; gap: 6px 14px;
    padding: 28px 16px; background: var(--surface-container); border-radius: var(--corner-large-increased); line-height: 1.2;
  }
  .word { border: 0; background: none; color: var(--on-surface); cursor: pointer; font-weight: 500; padding: 2px 4px; border-radius: var(--corner-small); }
  .word.mine { color: var(--primary); }
  .word:hover { background: var(--surface-container-highest); opacity: 1 !important; }
  .rank { list-style: none; padding: 0; margin: 0; max-width: 640px; }
  .rank li { display: flex; align-items: center; gap: 12px; padding: 8px 4px; border-bottom: 1px solid var(--outline-variant); }
  .no { width: 32px; text-align: right; color: var(--on-surface-variant); font-variant-numeric: tabular-nums; }
  .tag { border: 0; background: none; color: var(--on-surface); cursor: pointer; font-size: 15px; font-weight: 500; padding: 0; flex: 1; text-align: left; }
  .tag.mine { color: var(--primary); }
  .count { color: var(--on-surface-variant); font-size: 13px; }
</style>
