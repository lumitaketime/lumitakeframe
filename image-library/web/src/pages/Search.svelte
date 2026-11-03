<script>
  import BackButton from "../components/BackButton.svelte";
  import Grid from "../components/Grid.svelte";
  import { api } from "../lib/api.js";
  import { route, navigate } from "../lib/router.svelte.js";
  import { app, showDialog, toast } from "../lib/state.svelte.js";

  let result = $state(null);
  let loading = $state(false);
  let semantic = $state(false);
  let more = $state(false);
  const q = $derived(route.query.q || "");
  const canSemantic = $derived(!!app.server?.models?.embed);
  const failedView = $derived(q.split(/\s+/).includes("is:failed"));
  let reasons = $state([]);

  $effect(() => {
    app.refreshKey;
    if (failedView) api("/api/analysis/errors").then((r) => (reasons = r)).catch(() => {});
  });

  async function retryFailed() {
    await api("/api/jobs", { body: { kind: "analyze", retry_failed: true } });
    toast("已開始重新分析失敗的照片");
  }

  const QUICK = [
    ["rating:3", "★3 以上"], ["rating:5", "★5"], ["is:rejected", "已拒絕"], ["label:red", "紅標"], ["label:green", "綠標"],
    ["type:photo", "照片"], ["type:video", "影片"], ["type:raw", "RAW"], ["is:favorite", "我的最愛"],
    ["is:pending", "待分析"], ["is:failed", "分析失敗"], ["is:missing", "遺失檔案"],
  ];

  // 先秀結果，再補強：關鍵字（含人名、寵物名）立刻顯示；智慧搜尋（同義詞、畫面比對、語意）在背景跑完再補進來
  let seq = 0;
  let enhancing = $state(false);
  let added = $state(0);
  let smartWarning = $state("");

  async function run(append = false) {
    if (!q) {
      result = null;
      return;
    }
    if (append) {
      loading = true;
      try {
        const data = await api("/api/search", { params: { q, limit: 300, offset: result.results.length, semantic: semantic ? 1 : 0 } });
        const known = new Set(result.results.map((r) => r.id));
        result = { ...result, results: [...result.results, ...data.results.filter((r) => !known.has(r.id))] };
        more = result.results.length < result.total;
      } finally {
        loading = false;
      }
      return;
    }
    const mine = ++seq;
    loading = true;
    added = 0;
    smartWarning = "";
    try {
      const quick = await api("/api/search", { params: { q, limit: 300, smart: 0 } });
      if (mine !== seq) return;
      result = quick;
      more = quick.results.length < quick.total;
    } finally {
      if (mine === seq) loading = false;
    }
    if (!result?.query?.terms?.length) return; // 只有篩選條件時不需要智慧搜尋
    enhancing = true;
    try {
      const full = await api("/api/search", { params: { q, limit: 300, semantic: semantic ? 1 : 0, smart: 1 } });
      if (mine !== seq) return;
      const known = new Set(result.results.map((r) => r.id));
      const extra = full.results.filter((r) => !known.has(r.id));
      added = extra.length;
      smartWarning = full.warning || "";
      result = { ...full, results: [...result.results, ...extra], total: Math.max(full.total, result.total) };
      more = result.results.length < result.total;
    } catch {
      /* 智慧搜尋失敗時保留關鍵字結果 */
    } finally {
      if (mine === seq) enhancing = false;
    }
  }

  $effect(() => {
    q;
    semantic;
    app.refreshKey;
    run();
  });

  async function saveSmart() {
    const name = await showDialog("prompt", { title: "存成智慧相簿", value: q, placeholder: "相簿名稱", ok: "儲存" });
    if (!name) return;
    const res = await api("/api/smart-albums", { body: { name, query: q } });
    toast("已建立智慧相簿，符合條件的新照片會自動加入");
    navigate(`/albums/smart/${res.id}`);
  }

  function toggle(token) {
    const parts = q.split(/\s+/).filter(Boolean);
    const next = parts.includes(token) ? parts.filter((p) => p !== token) : [...parts, token];
    navigate(`/search?q=${encodeURIComponent(next.join(" "))}`, { replace: true });
  }
</script>

<div class="page">
  <div class="page-head">
    <BackButton to="/" />
    <h1>{q ? `「${q}」` : "搜尋"}</h1>
    {#if result}<span class="muted small">{result.total.toLocaleString()} 個結果</span>{/if}
    {#if q}<button class="btn small ghost" onclick={saveSmart}>存成智慧相簿</button>{/if}
    {#if canSemantic}
      <label class="sem"><input type="checkbox" bind:checked={semantic} /> 語意搜尋</label>
    {/if}
  </div>
  <div class="chips quick">
    {#each QUICK as [token, label] (token)}
      <button class="chip" class:on={q.split(/\s+/).includes(token)} onclick={() => toggle(token)}>{label}</button>
    {/each}
  </div>
  {#if enhancing}
    <div class="status-pill" role="status"><span class="ring"></span>正在尋找相近結果…</div>
  {:else if added}
    <div class="status-pill done" role="status">已加入 {added.toLocaleString()} 個相近結果</div>
  {/if}
  {#if smartWarning && !enhancing}<p class="muted small">{smartWarning}</p>{/if}
  {#if failedView && reasons.length}
    <div class="reasons">
      <b>失敗原因</b>
      <ul>
        {#each reasons as r (r.reason)}<li><span class="n">{r.count.toLocaleString()} 張</span><span class="why">{r.reason}</span></li>{/each}
      </ul>
      <div class="row"><button class="btn small" onclick={retryFailed}>重新分析失敗的照片</button>
        <span class="tiny muted">點照片後按 ⓘ 可以看單張的錯誤。</span></div>
    </div>
  {/if}
  {#if result?.expanded?.length || result?.modes?.includes("image")}
    <p class="muted small smart">
      {#if result.expanded?.length}也搜尋了：{result.expanded.slice(0, 12).join("、")}{/if}
      {#if result.modes?.includes("image")}{result.expanded?.length ? "　·　" : ""}含畫面內容比對{/if}
    </p>
  {/if}

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
          <tr><td><code>person:媽媽</code></td><td>人物（人臉辨識後命名）</td></tr>
          <tr><td><code>place:恆春</code>　或直接輸入 <code>京都</code></td><td>地點（依 GPS 自動換算，不需連網）</td></tr>
          <tr><td><code>rating:4</code>　<code>label:紅</code>　<code>is:rejected</code></td><td>星等（以上）、顏色標籤、被拒絕（與 Lightroom 同步）</td></tr>
          <tr><td><code>is:favorite</code>　<code>is:pending</code>　<code>is:missing</code></td><td>狀態</td></tr>
        </tbody>
      </table>
    </div>
  {:else if result && !result.results.length && !loading}
    <div class="empty"><h2>找不到符合的項目</h2><p>試試其他關鍵字，或在設定開啟「圖像搜尋」，用畫面內容找照片。</p></div>
  {:else if result}
    <Grid assets={result.results} />
    {#if more}<p class="center"><button class="btn ghost" disabled={loading} onclick={() => run(true)}>載入更多</button></p>{/if}
  {/if}
  {#if loading && !result}<p class="muted"><span class="spinner"></span></p>{/if}
</div>

<style>
  .reasons { background: var(--bg-2); border-radius: 16px; padding: 12px 16px; margin: 6px 0 14px; }
  .reasons ul { list-style: none; padding: 0; margin: 8px 0; display: flex; flex-direction: column; gap: 6px; }
  .reasons li { display: flex; gap: 12px; font-size: 13px; }
  .reasons .n { flex-shrink: 0; width: 72px; font-weight: 600; color: var(--danger); font-variant-numeric: tabular-nums; }
  .reasons .why { word-break: break-all; color: var(--muted); }
  .reasons .row { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
  .quick { margin-bottom: 14px; }
  .status-pill {
    display: inline-flex; align-items: center; gap: 12px; height: 48px; padding: 0 24px 0 16px; margin: 0 0 12px;
    border-radius: var(--corner-full); background: var(--secondary-container); color: var(--on-secondary-container); font-size: 15px;
    animation: m3-enter var(--duration-medium2) var(--easing-emphasized-decelerate);
  }
  .status-pill.done { padding-left: 24px; }
  .ring { width: 22px; height: 22px; border-radius: 50%; border: 3px solid color-mix(in srgb, var(--primary) 25%, transparent); border-top-color: var(--primary); animation: spin .9s linear infinite; }
  @keyframes spin { to { transform: rotate(360deg); } }
  .smart { margin: -6px 0 12px; }
  .sem { display: flex; align-items: center; gap: 6px; font-size: 14px; }
  .help table { border-collapse: collapse; width: 100%; max-width: 760px; font-size: 14px; }
  .help td { padding: 8px 10px; border-bottom: 1px solid var(--line); vertical-align: top; }
  .help td:first-child { white-space: nowrap; }
  code { background: var(--bg-2); padding: 2px 6px; border-radius: 6px; font-size: 13px; }
  .center { text-align: center; margin: 20px; }
  @media (max-width: 760px) { .help td:first-child { white-space: normal; } }
</style>
