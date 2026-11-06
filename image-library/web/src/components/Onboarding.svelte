<script>
  /**
   * 第一次開啟的設定引導：加入資料夾 → 安裝 Ollama → 下載模型 → 完成。
   * 每一步都可以略過，之後可在「設定 → 外觀與系統」重新執行。
   */
  import { onMount } from "svelte";
  import Icon from "./Icon.svelte";
  import { api } from "../lib/api.js";
  import { app, refresh, toast } from "../lib/state.svelte.js";
  import { navigate } from "../lib/router.svelte.js";
  import { count } from "../lib/format.js";
  import { mdiCheck, mdiClose, mdiHarddisk, mdiContentCopy, mdiDownload, mdiCreation, mdiImageMultipleOutline } from "../lib/icons.js";

  let { startStep = "" } = $props();

  const STEPS = ["welcome", "folder", "ollama", "model", "done"];
  // svelte-ignore state_referenced_locally
  let step = $state(STEPS.includes(startStep) ? startStep : "welcome");
  let ai = $state(null);
  let models = $state(null);
  let newPath = $state("");
  let adding = $state(false);
  let starting = $state(false);
  let timer;

  const s = $derived(app.server);
  const roots = $derived(s?.roots || []);
  const isMac = $derived(s?.platform === "darwin");
  const pullJob = $derived((s?.jobs?.active || []).find((j) => j.kind === "pull" && j.model === models?.active?.vision) || null);
  const pullQueued = $derived((s?.jobs?.queued || []).some((j) => j.kind === "pull"));
  const index = $derived(STEPS.indexOf(step));

  async function checkAi() {
    try {
      ai = await api("/api/ai/status");
      if (ai.ollama && (!models || !models.ollama_ok)) models = await api("/api/models");
    } catch {
      /* 稍後再試 */
    }
  }

  onMount(() => {
    checkAi();
    api("/api/models").then((m) => (models = m)).catch(() => {});
    timer = setInterval(() => {
      if (step === "ollama" || step === "model") checkAi();
    }, 3000);
    return () => clearInterval(timer);
  });

  // 模型下載完成後更新清單
  let wasPulling = false;
  $effect(() => {
    const now = !!pullJob || pullQueued;
    if (wasPulling && !now) {
      checkAi();
      api("/api/models").then((m) => (models = m)).catch(() => {});
    }
    wasPulling = now;
  });

  function go(name) {
    step = name;
    if (name === "ollama" || name === "model") checkAi();
  }
  const next = () => go(STEPS[Math.min(index + 1, STEPS.length - 1)]);
  const back = () => go(STEPS[Math.max(index - 1, 0)]);

  async function pick() {
    try {
      const { path } = await api("/api/pick-folder", { body: {} });
      if (path) newPath = path;
    } catch (e) {
      toast(e.message, "error");
    }
  }

  async function addRoot() {
    adding = true;
    try {
      const r = await api("/api/roots", { body: { path: newPath.trim() } });
      toast(`已加入「${r.name}」，開始掃描`);
      newPath = "";
      refresh();
    } catch (e) {
      toast(e.message, "error", 6000);
    } finally {
      adding = false;
    }
  }

  async function startOllama() {
    starting = true;
    try {
      await api("/api/ollama/start", { body: {} });
      toast("正在打開 Ollama…");
      setTimeout(checkAi, 2500);
    } catch (e) {
      toast(e.message, "error");
    } finally {
      setTimeout(() => (starting = false), 3000);
    }
  }

  async function copy(text) {
    try {
      await navigator.clipboard.writeText(text);
      toast("已複製");
    } catch {
      toast("無法複製，請手動選取文字", "error");
    }
  }

  async function choose(name) {
    const info = models?.recommended.find((m) => m.name === name);
    await api("/api/settings", { body: { vision_model: name } });
    if (info && !info.installed) {
      await api("/api/jobs", { body: { kind: "pull", model: name } });
      toast(`開始下載 ${name}`);
    }
    models = await api("/api/models");
    checkAi();
    refresh();
  }

  async function finish() {
    await api("/api/settings", { body: { onboarded: 1 } }).catch(() => {});
    if (app.server?.ui) app.server.ui.onboarded = 1;
    // 模型已準備好、又有待分析的照片：直接開始
    if (ai?.ready && s?.stats.pending && !(s?.jobs?.active || []).some((j) => j.kind === "analyze")) {
      await api("/api/jobs", { body: { kind: "analyze" } }).catch(() => {});
    }
    refresh();
    navigate("/");
  }

  const picks = $derived(models?.picks ? [
    { key: "best", title: "品質優先", hint: "描述比較細，速度普通" },
    { key: "fast", title: "速度優先", hint: "比較快，照片很多時先掃一輪" },
  ].map((p) => ({ ...p, model: models.recommended.find((m) => m.name === models.picks[p.key]) }))
    .filter((p, i, arr) => p.model && arr.findIndex((q) => q.model?.name === p.model.name) === i) : []);
  const chosen = $derived(models?.active?.vision);
  const chosenInfo = $derived(models?.recommended.find((m) => m.name === chosen) || models?.installed.find((m) => m.name === chosen));
  const pct = $derived(pullJob?.total ? Math.round((pullJob.done / pullJob.total) * 100) : null);
</script>

<div class="overlay" role="dialog" aria-modal="true" aria-label="設定引導">
  <div class="card">
    <header>
      <div class="dots" aria-hidden="true">
        {#each STEPS as st, i (st)}<span class:on={i <= index}></span>{/each}
      </div>
      <button class="icon-btn" onclick={finish} title="略過引導" aria-label="略過引導"><Icon path={mdiClose} /></button>
    </header>

    {#if step === "welcome"}
      <div class="hero"><img src="/icon.svg" alt="" width="64" height="64" /></div>
      <h1>歡迎使用 Lumitake Library</h1>
      <p class="lead">把電腦或外接 SSD 上的作品整理成像 Google 相簿一樣好找的圖庫。照片留在原本的位置，AI 在這台 Mac 上分析，不會上傳到任何地方。</p>
      <ol class="plan">
        <li><b>加入照片資料夾</b><span>選擇作品所在的資料夾或 SSD</span></li>
        <li><b>安裝 Ollama</b><span>免費的 AI 執行程式，約 3 分鐘</span></li>
        <li><b>下載 AI 模型</b><span>依你的 Mac 推薦，約 3–10 GB</span></li>
      </ol>
      <div class="actions"><span></span><button class="btn" onclick={next}>開始設定</button></div>

    {:else if step === "folder"}
      <h2><Icon path={mdiHarddisk} />加入照片資料夾</h2>
      <p class="lead">選擇作品所在的資料夾，例如「圖片」或外接 SSD 上的作品集。之後可以再加入更多。</p>
      {#if roots.length}
        <ul class="roots">
          {#each roots as r (r.id)}
            <li><Icon path={mdiCheck} size={18} /><b>{r.name}</b><span class="muted small">{count(r.count)} 個項目</span></li>
          {/each}
        </ul>
      {/if}
      <div class="row">
        <input class="input" bind:value={newPath} placeholder={isMac ? "/Users/你的名稱/Pictures 或 /Volumes/SSD名稱/作品" : "資料夾完整路徑"} />
        {#if s?.local && isMac}<button class="btn ghost" onclick={pick}>選擇資料夾…</button>{/if}
      </div>
      <div class="row"><button class="btn" disabled={!newPath.trim() || adding} onclick={addRoot}>{adding ? "加入中…" : roots.length ? "再加入一個" : "加入並開始掃描"}</button></div>
      <p class="tiny muted">掃描只讀取檔案資訊與產生縮圖，不會修改或搬動你的照片。</p>
      <div class="actions">
        <button class="btn ghost" onclick={back}>上一步</button>
        <button class="btn" onclick={next}>{roots.length ? "下一步" : "先略過"}</button>
      </div>

    {:else if step === "ollama"}
      <h2><Icon path={mdiCreation} />安裝 Ollama</h2>
      {#if ai?.ollama}
        <div class="ok"><Icon path={mdiCheck} /><div><b>Ollama 已經在執行</b><p class="small">這一步完成了。</p></div></div>
      {:else if ai?.installed}
        <p class="lead">Ollama 已經安裝，但還沒有打開。</p>
        <div class="row"><button class="btn" disabled={starting} onclick={startOllama}>{starting ? "打開中…" : "打開 Ollama"}</button></div>
        <p class="small muted">或到「應用程式」資料夾雙擊 Ollama。打開後，螢幕上方選單列會出現小羊駝圖示，這裡會自動偵測。</p>
      {:else}
        <p class="lead">Ollama 是免費的程式，負責在你的 Mac 上執行 AI 模型。照著下面做，這個畫面會自動偵測安裝結果。</p>
        <ol class="howto">
          <li>
            <b>下載 Ollama</b>
            <a class="btn small" href="https://ollama.com/download" target="_blank" rel="noopener"><Icon path={mdiDownload} size={16} />打開下載頁</a>
            <span class="small muted">在網頁上按「Download for macOS」。</span>
          </li>
          <li><b>安裝</b><span class="small muted">打開「下載項目」裡的 Ollama 檔案，把 Ollama 圖示拖進「應用程式」資料夾。</span></li>
          <li><b>打開 Ollama</b><span class="small muted">到「應用程式」雙擊 Ollama。如果問「確定要打開嗎？」，按「打開」。看到螢幕上方選單列出現小羊駝圖示就完成了，不需要登入或設定。</span></li>
          <li><b>回到這裡</b><span class="small muted">每 3 秒自動偵測一次，偵測到會顯示「已經在執行」。</span></li>
        </ol>
        <details class="alt">
          <summary>會用終端機？也可以用 Homebrew 安裝</summary>
          {#each ["brew install ollama", "brew services start ollama"] as cmd (cmd)}
            <div class="cmd"><code>{cmd}</code><button class="icon-btn" title="複製" onclick={() => copy(cmd)}><Icon path={mdiContentCopy} size={18} /></button></div>
          {/each}
        </details>
      {/if}
      <p class="tiny muted status"><span class="spinner small-spin"></span>{ai?.ollama ? "已連線" : "正在偵測 Ollama…"}</p>
      <div class="actions">
        <button class="btn ghost" onclick={back}>上一步</button>
        <button class="btn" class:ghost={!ai?.ollama} onclick={next}>{ai?.ollama ? "下一步" : "先略過"}</button>
      </div>

    {:else if step === "model"}
      <h2><Icon path={mdiImageMultipleOutline} />下載 AI 模型</h2>
      {#if !ai?.ollama}
        <p class="lead">要先完成 Ollama 安裝才能下載模型。</p>
        <div class="row"><button class="btn ghost" onclick={() => go("ollama")}>回到安裝 Ollama</button></div>
      {:else}
        <p class="lead">模型負責「看」照片並寫下描述和關鍵字。依你的 Mac{models?.machine?.ram_gb ? `（${models.machine.chip}，${models.machine.ram_gb} GB 記憶體）` : ""}推薦：</p>
        <div class="picks">
          {#each picks as p (p.key)}
            {@const using = chosen === p.model.name}
            <button class="pick" class:on={using} onclick={() => choose(p.model.name)} disabled={!!pullJob && !using}>
              <span class="tiny muted">{p.title}</span>
              <b>{p.model.name}</b>
              <span class="tiny muted">{p.model.family} · 約 {p.model.size_gb} GB · {p.hint}</span>
              <span class="state">{p.model.installed ? (using ? "✓ 使用中" : "已下載，按一下使用") : using ? "下載中…" : "按一下下載並使用"}</span>
            </button>
          {/each}
        </div>
        {#if pullJob}
          <div class="progress">
            <div class="small">{pullJob.message}</div>
            {#if pct !== null}<progress max="100" value={pct}></progress>{/if}
            <p class="tiny muted">下載時可以繼續使用電腦；關掉這個視窗也會在背景繼續。</p>
          </div>
        {:else if ai?.ready}
          <div class="ok"><Icon path={mdiCheck} /><div><b>{ai.model} 已就緒</b><p class="small">掃描到的照片會自動開始分析。</p></div></div>
        {/if}
        <p class="tiny muted">之後可在「設定 → AI 分析」換成其他模型，包含 Gemma 4、Qwen3-VL 的各種大小。</p>
      {/if}
      <div class="actions">
        <button class="btn ghost" onclick={back}>上一步</button>
        <button class="btn" class:ghost={!ai?.ready && !pullJob} onclick={next}>{ai?.ready || pullJob ? "下一步" : "先略過"}</button>
      </div>

    {:else}
      <h2><Icon path={mdiCheck} />設定完成</h2>
      <ul class="summary">
        <li class:done={roots.length}><Icon path={roots.length ? mdiCheck : mdiClose} size={18} />照片資料夾：{roots.length ? `${roots.length} 個` : "尚未加入（設定 → 圖庫資料夾）"}</li>
        <li class:done={ai?.ollama}><Icon path={ai?.ollama ? mdiCheck : mdiClose} size={18} />Ollama：{ai?.ollama ? "執行中" : "尚未安裝（設定 → AI 分析）"}</li>
        <li class:done={ai?.ready || pullJob}><Icon path={ai?.ready || pullJob ? mdiCheck : mdiClose} size={18} />AI 模型：{ai?.ready ? `${ai.model} 已就緒` : pullJob ? `${chosen} 下載中` : "尚未下載"}</li>
      </ul>
      <p class="small">AI 分析在背景進行，右上角會顯示進度，可以隨時停止。每張約數秒，照片很多時會花上幾個小時，可以讓 Mac 開著慢慢跑。</p>
      <p class="small muted">還可以在設定裡打開：人臉辨識、手機與平板連線、Lightroom 同步、照片呈現方式（依比例或正方形）。</p>
      {#if chosenInfo && !ai?.ready && !pullJob}<p class="small muted">已選擇 {chosen}，下載完成後就會開始分析。</p>{/if}
      <div class="actions">
        <button class="btn ghost" onclick={back}>上一步</button>
        <button class="btn" onclick={finish}>開始使用</button>
      </div>
    {/if}
  </div>
</div>

<style>
  .overlay {
    position: fixed; inset: 0; z-index: 60; background: rgba(15, 17, 24, .55); display: flex; align-items: center;
    justify-content: center; padding: max(16px, env(safe-area-inset-top)) 16px max(16px, env(safe-area-inset-bottom));
    overflow-y: auto;
  }
  .card {
    background: var(--surface); color: var(--on-surface); border-radius: var(--corner-extra-large); width: min(640px, 100%); padding: 22px 28px 24px;
    margin: auto;
  }
  header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
  .dots { display: flex; gap: 6px; }
  .dots span { width: 26px; height: 4px; border-radius: 2px; background: var(--outline-variant); }
  .dots span.on { background: var(--primary); }
  .hero { display: flex; justify-content: center; margin: 8px 0 4px; }
  h1 { font-size: 24px; text-align: center; margin: 8px 0; text-wrap: balance; }
  h2 { display: flex; align-items: center; gap: 10px; font-size: 22px; margin: 6px 0 10px; }
  .lead { color: var(--on-surface-variant); line-height: 1.6; margin: 0 0 14px; }
  .plan, .howto { margin: 0 0 8px; padding-left: 22px; display: flex; flex-direction: column; gap: 12px; }
  .plan li, .howto li { padding-left: 4px; }
  .plan li b, .howto li b { display: block; margin-bottom: 2px; }
  .plan li span { color: var(--on-surface-variant); font-size: 14px; }
  .howto li { display: flex; flex-direction: column; align-items: flex-start; gap: 6px; }
  .howto li::marker { font-weight: 700; color: var(--primary); }
  .row { display: flex; gap: 8px; margin: 8px 0; flex-wrap: wrap; }
  .row .input { flex: 1; min-width: 200px; }
  .roots { list-style: none; padding: 0; margin: 0 0 8px; display: flex; flex-direction: column; gap: 6px; }
  .roots li { display: flex; align-items: center; gap: 8px; color: var(--primary); }
  .roots li b { color: var(--on-surface); }
  .ok { display: flex; gap: 12px; align-items: flex-start; background: var(--secondary-container); color: var(--primary); border-radius: var(--corner-medium); padding: 12px 14px; margin: 10px 0; }
  .ok b { color: var(--on-surface); }
  .ok p { margin: 2px 0 0; color: var(--on-surface-variant); }
  .alt { margin-top: 12px; }
  .alt summary { cursor: pointer; color: var(--on-surface-variant); font-size: 14px; }
  .cmd { display: flex; align-items: center; gap: 8px; margin-top: 8px; }
  .cmd code { flex: 1; background: var(--surface-container); padding: 8px 12px; border-radius: var(--corner-small); font-size: 14px; }
  .status { display: flex; align-items: center; gap: 8px; margin-top: 14px; }
  .small-spin { width: 12px; height: 12px; }
  .picks { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 10px; margin: 6px 0 12px; }
  .pick {
    display: flex; flex-direction: column; align-items: flex-start; gap: 4px; text-align: left; cursor: pointer;
    background: var(--surface-container); border: 2px solid transparent; border-radius: var(--corner-large); padding: 14px; color: var(--on-surface);
  }
  .pick.on { border-color: var(--primary); }
  .pick b { font-size: 16px; }
  .pick .state { margin-top: 6px; font-size: 14px; font-weight: 500; color: var(--primary); }
  .pick:disabled { opacity: .5; cursor: default; }
  .progress { background: var(--surface-container); border-radius: var(--corner-medium); padding: 12px 14px; margin-bottom: 10px; }
  progress { width: 100%; height: 6px; accent-color: var(--primary); }
  .summary { list-style: none; padding: 0; margin: 0 0 12px; display: flex; flex-direction: column; gap: 8px; }
  .summary li { display: flex; align-items: center; gap: 8px; color: var(--on-surface-variant); }
  .summary li.done { color: var(--on-surface); }
  .summary li.done :global(svg) { color: var(--primary); }
  .actions { display: flex; justify-content: space-between; align-items: center; gap: 8px; margin-top: 20px; }
  @media (max-width: 520px) { .card { padding: 18px 18px 20px; border-radius: var(--corner-large); } }
</style>
