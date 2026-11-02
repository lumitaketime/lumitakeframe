<script>
  import Grid from "../components/Grid.svelte";
  import { api } from "../lib/api.js";
  import { route, navigate } from "../lib/router.svelte.js";
  import { app } from "../lib/state.svelte.js";

  let result = $state(null);
  let loading = $state(false);
  let semantic = $state(false);
  let more = $state(false);
  const q = $derived(route.query.q || "");
  const canSemantic = $derived(!!app.server?.models?.embed);

  const QUICK = [
    ["type:photo", "照片"], ["type:video", "影片"], ["type:raw", "RAW"], ["is:favorite", "我的最愛"],
    ["is:pending", "待分析"], ["is:failed", "分析失敗"], ["is:missing", "遺失檔案"],
  ];

  async function run(append = false) {
    if (!q) {
      result = null;
      return;
    }
    loading = true;
    try {
      const offset = append ? result.results.length : 0;
      const data = await api("/api/search", { params: { q, limit: 300, offset, semantic: semantic ? 1 : 0 } });
      result = append ? { ...data, results: [...result.results, ...data.results] } : data;
      more = result.results.length < result.total;
    } finally {
      loading = false;
    }
  }

  $effect(() => {
    q;
    semantic;
    app.refreshKey;
    run();
  });

  function toggle(token) {
    const parts = q.split(/\s+/).filter(Boolean);
    const next = parts.includes(token) ? parts.filter((p) => p !== token) : [...parts, token];
    navigate(`/search?q=${encodeURIComponent(next.join(" "))}`, { replace: true });
  }
</script>

<div class="page">
  <div class="page-head">
    <h1>{q ? `「${q}」` : "搜尋"}</h1>
    {#if result}<span class="muted small">{result.total.toLocaleString()} 個結果{result.mode === "hybrid" ? "（含語意相近）" : ""}</span>{/if}
    {#if canSemantic}
      <label class="sem"><input type="checkbox" bind:checked={semantic} /> 語意搜尋</label>
    {/if}
  </div>
  <div class="chips quick">
    {#each QUICK as [token, label] (token)}
      <button class="chip" class:on={q.split(/\s+/).includes(token)} onclick={() => toggle(token)}>{label}</button>
    {/each}
  </div>
  {#if result?.warning}<p class="danger-text small">{result.warning}</p>{/if}

  {#if !q}
    <div class="help">
      <h2 class="section-title">搜尋技巧</h2>
      <table>
        <tbody>
          <tr><td><code>貓 沙發</code></td><td>同時包含兩個關鍵字（描述、關鍵字、圖中文字、檔名、資料夾）</td></tr>
          <tr><td><code>"日落 海邊"</code></td><td>完整片語</td></tr>
          <tr><td><code>-狗</code></td><td>排除</td></tr>
          <tr><td><code>tag:作品集</code></td><td>只找關鍵字（AI、Lightroom 關鍵字、手動標籤）</td></tr>
          <tr><td><code>folder:婚禮</code></td><td>資料夾路徑</td></tr>
          <tr><td><code>camera:x-t5</code>　<code>lens:56mm</code></td><td>相機、鏡頭</td></tr>
          <tr><td><code>year:2024</code>　<code>after:2024-05-01</code>　<code>before:2024-06-01</code></td><td>拍攝日期</td></tr>
          <tr><td><code>type:video</code>　<code>type:raw</code>　<code>ext:heic</code></td><td>檔案類型</td></tr>
          <tr><td><code>is:favorite</code>　<code>is:pending</code>　<code>is:missing</code></td><td>狀態</td></tr>
        </tbody>
      </table>
    </div>
  {:else if result && !result.results.length && !loading}
    <div class="empty"><h2>找不到符合的項目</h2><p>試試其他關鍵字，或在設定開啟語意搜尋。</p></div>
  {:else if result}
    <Grid assets={result.results} />
    {#if more}<p class="center"><button class="btn ghost" disabled={loading} onclick={() => run(true)}>載入更多</button></p>{/if}
  {/if}
  {#if loading && !result}<p class="muted"><span class="spinner"></span></p>{/if}
</div>

<style>
  .quick { margin-bottom: 14px; }
  .sem { display: flex; align-items: center; gap: 6px; font-size: 14px; }
  .help table { border-collapse: collapse; width: 100%; max-width: 760px; font-size: 14px; }
  .help td { padding: 8px 10px; border-bottom: 1px solid var(--line); vertical-align: top; }
  .help td:first-child { white-space: nowrap; }
  code { background: var(--bg-2); padding: 2px 6px; border-radius: 6px; font-size: 13px; }
  .center { text-align: center; margin: 20px; }
  @media (max-width: 760px) { .help td:first-child { white-space: normal; } }
</style>
