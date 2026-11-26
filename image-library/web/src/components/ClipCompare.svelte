<script>
  /**
   * 比較圖像搜尋模型（目前使用的 vs EmbeddingGemma 2）：
   * 1. 用最近的照片替新模型試建索引（和正式索引分開），同時量兩個模型每張要多久
   * 2. 輸入或點選一句搜尋，兩邊在同一批照片裡各找出最像的 12 張，並排比較
   *    盲測：兩欄只標 A／B、左右隨機，選完哪邊比較好才揭曉，結果累計在這台裝置上
   * 3. 決定換：試用的結果直接沿用，其他照片在背景補建
   */
  import Icon from "./Icon.svelte";
  import JobList from "./JobList.svelte";
  import Loading from "./Loading.svelte";
  import { api, thumbUrl } from "../lib/api.js";
  import { app, toast, refresh, openViewer } from "../lib/state.svelte.js";
  import { count } from "../lib/format.js";
  import { mdiMagnify, mdiCheck } from "../lib/icons.js";

  let { models = [], onchange } = $props();
  const CANDIDATE = "embeddinggemma-2";
  const candidate = $derived(models.find((m) => m.name === CANDIDATE));
  const usingCandidate = $derived(!!candidate?.active);

  let status = $state(null);
  let size = $state(1000);
  let q = $state("");
  let result = $state(null);
  let searching = $state(false);
  let flipped = $state(false); // true：A 是新模型
  let voted = $state(null); // 這一句選了什麼（選完才揭曉）
  let tally = $state(readTally());

  const PRESETS = ["海邊", "夕陽", "夜景", "下雪", "雨天", "森林", "山", "花", "天空和雲", "城市街道", "小孩", "背影", "合照", "人像",
    "狗", "貓", "食物", "咖啡", "室內", "窗邊的光", "紅色衣服", "黑白照片", "車", "腳踏車", "建築", "橋", "河流", "婚禮", "生日蛋糕", "書"];

  function readTally() {
    try {
      return JSON.parse(localStorage.getItem("clip-compare") || "null") || { candidate: 0, current: 0, tie: 0, done: [] };
    } catch {
      return { candidate: 0, current: 0, tie: 0, done: [] };
    }
  }
  function saveTally() {
    try {
      localStorage.setItem("clip-compare", JSON.stringify(tally));
    } catch {
      /* 只影響這次 */
    }
  }

  $effect(() => {
    app.refreshKey;
    api("/api/clip/trial").then((s) => (status = s)).catch(() => {});
  });

  const trialRunning = $derived((app.server?.jobs?.active || []).some((j) => j.kind === "clip_trial"));
  const ready = $derived(status?.candidate === CANDIDATE && status.count > 0 && candidate?.installed);

  function dur(sec) {
    if (sec == null) return "—";
    if (sec < 90) return `${Math.max(1, Math.round(sec))} 秒`;
    if (sec < 5400) return `${Math.round(sec / 60)} 分鐘`;
    const h = sec / 3600;
    return h < 48 ? `${h.toFixed(h < 10 ? 1 : 0)} 小時` : `${(h / 24).toFixed(1)} 天`;
  }

  async function startTrial() {
    try {
      await api("/api/jobs", { body: { kind: "clip_trial", model: CANDIDATE, count: size } });
      toast(`開始用最近 ${count(size)} 張照片試建索引，完成後就能比較`);
      refresh();
    } catch (e) {
      toast(e.message, "error");
    }
  }

  async function search(text = q) {
    text = text.trim();
    if (!text) return;
    q = text;
    searching = true;
    voted = null;
    try {
      result = await api("/api/clip/compare", { params: { q: text } });
      flipped = Math.random() < 0.5;
    } catch (e) {
      toast(e.message, "error");
    } finally {
      searching = false;
    }
  }

  // A／B 兩欄：哪一欄是哪個模型，選完才揭曉
  const columns = $derived(result ? (flipped
    ? [{ key: "candidate", hits: result.candidate_hits }, { key: "current", hits: result.current_hits }]
    : [{ key: "current", hits: result.current_hits }, { key: "candidate", hits: result.candidate_hits }]) : []);
  const label = (key) => (key === "candidate" ? "EmbeddingGemma 2" : status?.current_label || "目前的模型");

  function vote(which) {
    if (voted || !result) return;
    voted = which;
    const already = tally.done.includes(result.query);
    if (!already) {
      tally[which] += 1;
      tally.done = [...tally.done, result.query].slice(-200);
      saveTally();
    }
  }
  function resetTally() {
    tally = { candidate: 0, current: 0, tie: 0, done: [] };
    saveTally();
  }

  async function adopt() {
    try {
      const r = await api("/api/clip/trial/adopt", { body: {} });
      toast(`已改用 EmbeddingGemma 2：沿用 ${count(r.kept)} 張試用結果，其他照片在背景建立索引`);
      onchange?.();
      refresh();
    } catch (e) {
      toast(e.message, "error");
    }
  }
  async function clearTrial() {
    await api("/api/clip/trial/clear", { body: {} });
    result = null;
    toast("已清除試用索引");
    refresh();
  }
</script>

{#if candidate && !usingCandidate}
  <div class="cmp">
    <h3>比較：EmbeddingGemma 2</h3>
    <p class="muted small">Google 2026 年的新模型，比較懂中文描述，但建立索引比較慢。先用你自己的照片試試，看搜尋結果和速度再決定要不要換。試用不會影響現在的搜尋。</p>

    <ol class="steps">
      <li class:done={candidate.installed}>
        <b>下載模型</b>（約 {candidate.size_mb || 540} MB）
        {#if candidate.installed}<span class="ok"><Icon path={mdiCheck} size={16} />已下載</span>{:else}<span class="muted small">— 在上面的模型清單按「下載」</span>{/if}
      </li>
      <li class:done={ready}>
        <b>試建索引</b>
        <div class="row wrap">
          <select bind:value={size} aria-label="試用幾張" disabled={trialRunning}>
            {#each [300, 1000, 3000] as n (n)}<option value={n}>最近 {count(n)} 張</option>{/each}
          </select>
          <button class="btn small" disabled={!candidate.installed || trialRunning} onclick={startTrial}>{ready ? "重新試建" : "開始試建"}</button>
          {#if ready}<button class="btn text small" onclick={clearTrial}>清除試用</button>{/if}
        </div>
        <JobList kinds={["clip_trial"]} compact />
        {#if ready}
          <div class="speed">
            <span>已試建 <b>{count(status.count)}</b> 張</span>
            <span>每張：EmbeddingGemma 2 <b>{status.candidate_ms ? (status.candidate_ms / 1000).toFixed(2) : "—"} 秒</b> · 目前 <b>{status.current_ms ? (status.current_ms / 1000).toFixed(2) : "—"} 秒</b></span>
            <span>整個圖庫（{count(status.photos)} 張）建立索引約需：EmbeddingGemma 2 <b>{dur(status.candidate_total_s)}</b> · 目前 <b>{dur(status.current_total_s)}</b></span>
          </div>
        {/if}
      </li>
      <li class:done={tally.candidate + tally.current + tally.tie > 0}>
        <b>比較搜尋結果</b>（盲測：A、B 兩欄隨機排列，選完才揭曉是哪個模型）
        {#if ready}
          <form class="qrow" onsubmit={(e) => { e.preventDefault(); search(); }}>
            <input class="input" bind:value={q} placeholder="輸入想找的畫面，例如：窗邊看書的女生" aria-label="比較用的搜尋" />
            <button class="btn" disabled={!q.trim() || searching}><Icon path={mdiMagnify} size={18} />比較</button>
          </form>
          <div class="chips presets">
            {#each PRESETS as p (p)}
              <button class="chip" class:on={tally.done.includes(p)} onclick={() => search(p)}>{p}</button>
            {/each}
          </div>
          {#if searching && !result}<Loading kind="grid" count={8} />{/if}
          {#if result}
            <div class="cols">
              {#each columns as col, ci (col.key)}
                <div class="col" class:win={voted === col.key}>
                  <div class="col-head">
                    <b>{ci === 0 ? "A" : "B"}</b>
                    {#if voted}<span class="reveal">{label(col.key)}</span>{/if}
                  </div>
                  {#if col.hits.length}
                    <div class="hits">
                      {#each col.hits as h, i (h.id)}
                        <button class="hit" onclick={() => openViewer(col.hits, i)} title={h.name}><img src={thumbUrl(h)} alt="" loading="lazy" /></button>
                      {/each}
                    </div>
                  {:else}
                    <p class="muted small">{col.key === "current" ? "目前的模型還沒有這些照片的索引，請先按「建立圖像索引」。" : "沒有結果"}</p>
                  {/if}
                </div>
              {/each}
            </div>
            <div class="vote" role="group" aria-label="哪一邊比較好">
              {#if !voted}
                <span class="muted small">「{result.query}」哪一邊找得比較好？</span>
                <button class="btn small soft" onclick={() => vote(columns[0].key)}>A 比較好</button>
                <button class="btn small ghost" onclick={() => vote("tie")}>差不多</button>
                <button class="btn small soft" onclick={() => vote(columns[1].key)}>B 比較好</button>
              {:else}
                <span class="small">{voted === "tie" ? "差不多" : `${label(voted)} 比較好`}；A 是 {label(columns[0].key)}，B 是 {label(columns[1].key)}</span>
              {/if}
            </div>
          {/if}
          {#if tally.candidate + tally.current + tally.tie}
            <p class="tally small">
              目前結果：EmbeddingGemma 2 <b>{tally.candidate}</b> 次比較好 · 目前的模型 <b>{tally.current}</b> 次 · 差不多 <b>{tally.tie}</b> 次
              <button class="btn text small" onclick={resetTally}>重新計算</button>
            </p>
          {/if}
        {:else}
          <span class="muted small">— 試建索引完成後就能比較</span>
        {/if}
      </li>
      <li>
        <b>決定</b>
        <div class="row wrap">
          <button class="btn small" disabled={!ready} onclick={adopt}>改用 EmbeddingGemma 2</button>
          <span class="muted small">試用過的照片直接沿用，其他照片在背景補建；之後也可以在上面的清單換回來。</span>
        </div>
      </li>
    </ol>
  </div>
{/if}

<style>
  .cmp { margin-top: 20px; padding: 16px 20px; border-radius: var(--corner-large); background: var(--surface-container); }
  .cmp h3 { margin: 0 0 4px; }
  .steps { margin: 12px 0 0; padding-left: 20px; display: flex; flex-direction: column; gap: 14px; }
  .steps li { font-size: 14px; }
  .steps li.done::marker { color: var(--primary); }
  .row { display: flex; align-items: center; gap: 8px; margin-top: 6px; }
  .ok { display: inline-flex; align-items: center; gap: 4px; color: var(--primary); margin-left: 6px; font-size: 14px; }
  .speed { display: flex; flex-direction: column; gap: 2px; margin-top: 8px; font-size: 14px; color: var(--on-surface-variant); }
  .speed b { color: var(--on-surface); font-weight: 500; }
  .qrow { display: flex; gap: 8px; margin: 8px 0; }
  .qrow .input { flex: 1; }
  .presets { margin-bottom: 12px; }
  .cols { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
  .col { border-radius: var(--corner-medium); padding: 8px; background: var(--surface-container-low); outline: 2px solid transparent; }
  .col.win { outline-color: var(--primary); }
  .col-head { display: flex; align-items: baseline; gap: 8px; margin-bottom: 6px; }
  .col-head b { font-size: 16px; }
  .reveal { font-size: 12px; color: var(--primary); }
  .hits { display: grid; grid-template-columns: repeat(4, 1fr); gap: 4px; }
  .hit { padding: 0; border: 0; aspect-ratio: 1; border-radius: var(--corner-small); overflow: hidden; cursor: pointer; background: var(--surface-container-highest); }
  .hit img { width: 100%; height: 100%; object-fit: cover; display: block; }
  .vote { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-top: 10px; }
  .tally { margin-top: 8px; }
  .tally b { font-weight: 500; }
  @media (max-width: 640px) { .cols { grid-template-columns: 1fr; } .hits { grid-template-columns: repeat(3, 1fr); } }
</style>
