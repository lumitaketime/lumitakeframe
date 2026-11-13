<script>
  import { slider } from "../lib/slider.js";
  import Loading from "../components/Loading.svelte";
  import { tick } from "svelte";
  import StatusCards from "../components/StatusCards.svelte";
  import Wordmark from "../components/Wordmark.svelte";
  import SectionTitle from "../components/SectionTitle.svelte";
  import { ABOUT, THIRD_PARTY } from "../lib/about.js";
  import BackButton from "../components/BackButton.svelte";
  import { onMount } from "svelte";
  import Icon from "../components/Icon.svelte";
  import JobList from "../components/JobList.svelte";
  import StoragePanel from "../components/StoragePanel.svelte";
  import { api } from "../lib/api.js";
  import { app, refresh, showDialog, toast } from "../lib/state.svelte.js";
  import { link } from "../lib/router.svelte.js";
  import { confirm, copyText } from "../lib/actions.js";
  import { bytes, count } from "../lib/format.js";
  import {
    mdiHarddisk, mdiRefresh, mdiPencilOutline, mdiDeleteOutline, mdiPlus, mdiCreation, mdiCheck, mdiDownload,
    mdiCellphone, mdiStop, mdiThemeLightDark, mdiServerNetwork, mdiAlertCircleOutline, mdiFaceRecognition,
    mdiImageSearchOutline, mdiStar, mdiTuneVariant, mdiArrowLeft, mdiViewDashboardOutline, mdiDatabaseOutline, mdiToolboxOutline, filled,
  } from "../lib/icons.js";


  let { section = "" } = $props();
  let winWidth = $state(1200);
  // 6 個分類；每類裡面是原本的幾個區塊（舊網址 /settings/faces 這類仍然有效，會捲到那個區塊）
  const SECTIONS = [
    { id: "library", label: "圖庫", sub: "資料夾、外觀與選單", icon: mdiHarddisk, members: ["library", "look", "features"] },
    { id: "ai", label: "AI 分析", sub: "模型、時機、提示詞", icon: mdiCreation, members: ["ai"] },
    { id: "recog", label: "辨識", sub: "人臉", icon: mdiFaceRecognition, members: ["faces"] },
    { id: "search", label: "搜尋", sub: "同義詞、圖像搜尋", icon: mdiImageSearchOutline, members: ["search"] },
    { id: "organize", label: "整理與疊放", sub: "判定標準、星等、疊放", icon: mdiStar, members: ["rating", "tools"] },
    { id: "system", label: "系統", sub: "手機、儲存空間、進階", icon: mdiTuneVariant, members: ["phone", "storage", "advanced"] },
  ];
  // 桌機沒有指定分類時顯示第一個；手機先顯示分類清單
  const groupOf = (id) => SECTIONS.find((c) => c.id === id || c.members.includes(id))?.id;
  const current = $derived(section === "about" ? "about" : groupOf(section) || (winWidth > 760 ? "library" : ""));
  // 從舊網址或其他頁面連進來（例如 /settings/faces）：捲到那個區塊
  $effect(() => {
    const target = section;
    if (!target || SECTIONS.some((c) => c.id === target) || target === "about") return;
    // 等換頁動畫與內容載入後再捲過去
    tick().then(() => setTimeout(() => document.getElementById(`sec-${target}`)?.scrollIntoView({ block: "start" }), 350));
  });

  const FEATURES = [
    { href: "/explore", label: "探索", hint: "依地點、物品、場景瀏覽" },
    { href: "/favorites", label: "我的最愛", hint: "按愛心收藏的作品" },
    { href: "/videos", label: "影片", hint: "只看影片" },
    { href: "/people", label: "人物", hint: "人臉辨識；關掉時也會停止在背景偵測人臉" },
    { href: "/keywords", label: "關鍵字", hint: "常拍內容的關鍵字雲" },
    { href: "/tools", label: "整理工具", hint: "截圖與文件、大檔案、重複照片" },
  ];
  const hiddenSet = $derived(new Set((settings?.nav_hidden || "").split(",").filter(Boolean)));

  async function setFeature(href, on) {
    const next = new Set(hiddenSet);
    on ? next.delete(href) : next.add(href);
    const body = { nav_hidden: [...next].join(",") };
    if (href === "/people" && !on) body.face_enabled = 0;
    settings = await api("/api/settings", { body });
    refresh();
  }

  async function pullAndUse(name) {
    settings = await api("/api/settings", { body: { vision_model: name } });
    await job("pull", { model: name });
    models = await api("/api/models");
    toast(settings?.auto_analyze ? `開始下載 ${name}，完成後會自動開始分析` : `開始下載 ${name}，完成後就可以開始分析`);
  }

  let roots = $state([]);
  let faceModels = $state([]);
  let ollamaUrl = $state("");
  let ollamaTest = $state("");
  let prompt = $state("");
  let textModel = $state("");
  let embedCustom = $state("");
  let clipRepo = $state("");
  let faceCustom = $state({ url: "", det: "", rec: "" });
  let clipModels = $state([]);
  let models = $state(null);
  let settings = $state(null);
  let lan = $state(null);
  let newPath = $state("");
  let newName = $state("");
  let customModel = $state("");
  let password = $state("");
  let restarting = $state(false);
  let aiTest = $state(null);
  let aiTesting = $state(false);

  const s = $derived(app.server);
  const jobs = $derived(s?.jobs);
  const local = $derived(!!s?.local);
  // 下載中的模型（可以同時下載好幾個）：{ 模型名稱: 工作 }
  const downloads = $derived(Object.fromEntries((jobs?.active || []).filter((j) => j.lane === "download").map((j) => [j.model, j])));
  const dlText = (name) => {
    const j = downloads[name];
    if (!j) return null;
    return j.total ? `下載中 ${Math.round((j.done / j.total) * 100)}%` : "下載中…";
  };
  const aiRunning = $derived((jobs?.active || []).some((j) => j.kind === "analyze"));
  const vision = $derived(models?.recommended.filter((m) => m.kind === "vision") || []);
  const embeds = $derived(models?.recommended.filter((m) => m.kind === "embed") || []);
  const otherInstalled = $derived(
    models?.installed.filter((m) => !models.recommended.some((r) => sameModel(r.name, m.name))) || [],
  );

  function sameModel(a, b) {
    const n = (x) => (x.includes(":") ? x : `${x}:latest`);
    return !!a && !!b && n(a) === n(b);
  }

  async function loadAll() {
    [roots, settings, lan] = await Promise.all([api("/api/roots"), api("/api/settings"), api("/api/lan")]);
    ollamaUrl = settings.ollama_url;
    prompt = settings.analysis_prompt || "";
    textModel = settings.text_model || "";
    clipRepo = settings.clip_custom_repo || "";
    faceCustom = { url: settings.face_custom_url, det: settings.face_custom_det, rec: settings.face_custom_rec };
    models = await api("/api/models");
    loadExtra();
  }

  function loadExtra() {
    api("/api/faces/models").then((m) => (faceModels = m));
    loadSched();
    api("/api/clip/models").then((m) => (clipModels = m));
  }

  onMount(() => {
    loadAll();
  });

  $effect(() => {
    app.refreshKey;
    api("/api/roots").then((r) => (roots = r));
    api("/api/models").then((m) => (models = m)).catch(() => {});
    loadExtra();
  });


  async function useFaceModel(name) {
    if (settings.face_model !== name && s?.stats.faces) {
      const ok = await confirm("切換人臉模型？", "不同模型的臉部特徵不相容，會清除目前的人臉與人物資料（包含名稱），之後重新偵測。", { ok: "切換", danger: true });
      if (!ok) return;
    }
    settings = await api("/api/settings", { body: { face_model: name } });
    loadExtra();
    refresh();
  }

  // ---- 分析時機 ----
  let schedStatus = $state(null);
  const sched = $derived.by(() => {
    const st = schedStatus;
    return {
      mode: st?.mode || "always", days: settings?.schedule_days || "1234567",
      start: settings?.schedule_start || "22:00", end: settings?.schedule_end || "07:00",
      ac: !!settings?.schedule_ac, idle: Number(settings?.schedule_idle || 0), battery: Number(settings?.schedule_battery || 0),
    };
  });
  function loadSched() {
    api("/api/analysis/schedule").then((d) => (schedStatus = d)).catch(() => {});
  }
  async function saveSched(values) {
    settings = await api("/api/settings", { body: values });
    loadSched();
  }
  async function setMode(mode) {
    const extra = {};
    // 從舊版的「只在夜間／接電源」切換過來時，把原本的時段帶進新排程
    if (mode === "schedule" && ["ac", "night", "ac_night"].includes(settings.analyze_schedule) && schedStatus) {
      Object.assign(extra, { schedule_start: schedStatus.start, schedule_end: schedStatus.end, schedule_ac: schedStatus.ac ? 1 : 0 });
    }
    await saveSched({ analyze_schedule: mode, ...extra });
    toast(mode === "ask" ? "掃描到新照片時會先問你要不要分析" : mode === "schedule" ? "已改成依排程分析" : "分析不限時段，隨時都可以進行");
  }
  function toggleDay(d) {
    const set = new Set(sched.days.split(""));
    set.has(String(d)) ? set.delete(String(d)) : set.add(String(d));
    if (!set.size) {
      toast("至少要選一天");
      return;
    }
    saveSched({ schedule_days: [...set].sort().join("") });
  }

  async function clearFaces() {
    const ok = await confirm("刪除所有人臉資料？", "會刪除所有偵測到的臉、臉部特徵與人物名稱。照片本身不受影響，之後可以重新偵測。", { ok: "全部刪除", danger: true });
    if (!ok) return;
    await api("/api/faces/clear", { body: {} });
    toast("人臉資料已刪除");
    refresh();
  }

  async function deleteExtraModel(kind, name) {
    if (!(await confirm(`刪除 ${name}？`, "只刪除模型檔案以釋放空間，已建立的資料保留。", { ok: "刪除", danger: true }))) return;
    await api(`/api/${kind}/models/delete`, { body: { name } });
    loadExtra();
  }

  // ---- 資料夾 ----
  async function pick() {
    try {
      const { path } = await api("/api/pick-folder", { body: {} });
      if (path) newPath = path;
    } catch (e) {
      toast(e.message, "error");
    }
  }

  async function addRoot() {
    try {
      const r = await api("/api/roots", { body: { path: newPath.trim(), name: newName.trim() || undefined } });
      toast(`已加入「${r.name}」，開始掃描…`);
      newPath = newName = "";
      roots = await api("/api/roots");
      refresh();
    } catch (e) {
      toast(e.message, "error", 6000);
    }
  }

  async function relocate(r) {
    let path = null;
    if (local && s?.platform === "darwin") {
      path = (await api("/api/pick-folder", { body: {} })).path;
    } else {
      path = await showDialog("prompt", { title: `「${r.name}」的新位置`, value: r.path, ok: "更新" });
    }
    if (!path) return;
    try {
      await api(`/api/roots/${r.id}`, { body: { path } });
      toast("已更新位置並重新掃描，分析結果都會保留");
      roots = await api("/api/roots");
      refresh();
    } catch (e) {
      toast(e.message, "error");
    }
  }

  async function removeRoot(r) {
    const ok = await confirm(
      `從圖庫移除「${r.name}」？`,
      "會一起清除這個資料夾的縮圖、AI 分析結果與人臉資料，釋放空間。硬碟上的照片完全不受影響，之後重新加入需要重新分析。",
      { ok: "移除並清除資料", danger: true },
    );
    if (!ok) return;
    try {
      const res = await api(`/api/roots/${r.id}`, { method: "DELETE" });
      toast(`已移除「${r.name}」${res.freed ? `，釋放約 ${bytes(res.freed)}` : ""}`);
    } catch (e) {
      toast(e.message, "error");
    }
    roots = await api("/api/roots");
    refresh();
  }

  // ---- 工作 ----
  async function job(kind, extra = {}) {
    try {
      await api("/api/jobs", { body: { kind, ...extra } });
      refresh();
    } catch (e) {
      toast(e.message, "error");
    }
  }

  // ---- 模型 ----
  async function useModel(kind, name) {
    settings = await api("/api/settings", { body: { [kind === "vision" ? "vision_model" : "embed_model"]: name } });
    models = await api("/api/models");
    toast(name ? `已切換為 ${name}` : "已關閉語意搜尋");
    refresh();
  }

  async function pull(name) {
    await job("pull", { model: name });
    toast(`開始下載 ${name}，完成後即可使用`);
  }

  async function deleteModel(name) {
    if (!(await confirm(`刪除模型 ${name}？`, "會從 Ollama 移除以釋放空間，已完成的分析結果不受影響。", { ok: "刪除", danger: true }))) return;
    try {
      await api("/api/models/delete", { body: { name } });
      models = await api("/api/models");
    } catch (e) {
      toast(e.message, "error");
    }
  }

  async function testOllama() {
    ollamaTest = "測試中…";
    const r = await api("/api/ollama/test", { body: { url: ollamaUrl } });
    ollamaTest = r.ok ? `✓ 已連線，有 ${r.count} 個模型` : `✗ ${r.error}`;
  }

  async function saveMany(values, message = "已儲存") {
    settings = await api("/api/settings", { body: values });
    toast(message);
    loadExtra();
    models = await api("/api/models").catch(() => models);
  }

  async function saveSetting(key, value) {
    settings = await api("/api/settings", { body: { [key]: value } });
    toast("已儲存");
  }

  async function testAnalyze() {
    aiTesting = true;
    aiTest = null;
    try {
      aiTest = await api("/api/ai/test", { body: {} });
    } catch (e) {
      aiTest = { ok: false, error: e.message };
    } finally {
      aiTesting = false;
    }
  }

  // ---- 手機連線 ----
  async function savePassword() {
    try {
      await api("/api/lan", { body: { password } });
      password = "";
      lan = await api("/api/lan");
      toast("密碼已設定");
    } catch (e) {
      toast(e.message, "error");
    }
  }

  async function setLan(enabled) {
    try {
      await api("/api/lan", { body: { enabled } });
      lan = await api("/api/lan");
    } catch (e) {
      toast(e.message, "error");
    }
  }

  async function restart() {
    restarting = true;
    await api("/api/restart", { body: {} }).catch(() => {});
    for (let i = 0; i < 40; i++) {
      await new Promise((r) => setTimeout(r, 750));
      try {
        await fetch("/api/auth/status");
        location.reload();
        return;
      } catch {
        /* 還在重新啟動 */
      }
    }
    restarting = false;
    toast("重新啟動逾時，請手動重新開啟程式", "error");
  }
</script>

<svelte:window bind:innerWidth={winWidth} />

<div class="page settings" class:has-section={!!section}>
  <aside class="cats" aria-label="設定分類">
    <div class="cats-head"><BackButton to="/" label="離開設定" /><h1>設定</h1></div>
    {#each SECTIONS as c (c.id)}
      <a href={`/settings/${c.id}`} use:link class:on={current === c.id}><Icon path={current === c.id ? filled(c.icon) : c.icon} size={20} /><span class="cl"><span>{c.label}</span><span class="csub">{c.sub}</span></span></a>
    {/each}
    <a class="ver" class:on={current === "about"} href="/settings/about" use:link title="關於 Re'memor">Re'memor {app.server?.version || ""}</a>
  </aside>
  <div class="pane">
    <a class="back" href="/settings" use:link><Icon path={mdiArrowLeft} size={20} />設定</a>
    {#if current !== "about"}<StatusCards />{/if}
    {#if current === "about"}
    <!-- 關於 -->
    <section class="card about">
      <div class="about-head">
        <img src="/icon.png" alt="" width="56" height="56" />
        <div>
          <h2 class="plain"><Wordmark size={28} /></h2>
          <span class="muted small">{ABOUT.tagline} · 版本 {app.server?.version || ""}</span>
        </div>
      </div>
      <p class="small">© {ABOUT.year} {ABOUT.author}</p>
      <div class="row wrap contact">
        <span class="small">聯絡：<span class="sel">{ABOUT.email}</span></span>
        <button class="btn text small" onclick={() => copyText(ABOUT.email)}>複製</button>
      </div>
      <h3>使用條款</h3>
      <p class="small">本軟體以{ABOUT.license.name}授權。</p>
      <ul class="small terms">{#each ABOUT.license.summary as line (line)}<li>{line}</li>{/each}</ul>
      <p class="small"><a href={ABOUT.license.url} target="_blank" rel="noopener">閱讀完整授權條款</a></p>
      <details class="more">
        <summary>第三方元件與資料</summary>
        <p class="muted tiny">以下元件與資料各自依原本的授權使用，不受上方條款影響。</p>
        <ul class="tp">{#each THIRD_PARTY as [name, lic] (name)}<li><span>{name}</span><span class="muted">{lic}</span></li>{/each}</ul>
      </details>
    </section>
    {/if}
    {#if current === "library"}
    <div class="anchor" id="sec-library"></div>
    <!-- 圖庫資料夾 -->
    <section class="card">
      <SectionTitle icon={mdiHarddisk} title="圖庫資料夾">加入電腦或外接 SSD 上的資料夾。檔案留在原位，不會被複製；之後新增的照片按「重新掃描」或重新開啟程式就會出現。</SectionTitle>
      {#each roots as r (r.id)}
        <div class="root">
          <span class="dot" class:off={!r.online}></span>
          <div class="grow">
            <b>{r.name}</b> <span class="muted small">{count(r.count)} 個項目{r.online ? "" : " · 未連接"}</span>
            <div class="muted tiny path">{r.path}</div>
            {#if r.last_scan}<div class="muted tiny">上次掃描：{r.last_scan.slice(0, 16).replace("T", " ")}</div>{/if}
          </div>
          <button class="icon-btn" title="重新掃描" onclick={() => job("scan", { roots: [r.name] })}><Icon path={mdiRefresh} /></button>
          <button class="icon-btn" title="變更位置（硬碟換了名稱或位置時）" onclick={() => relocate(r)}><Icon path={mdiPencilOutline} /></button>
          <button class="icon-btn" title="從圖庫移除" onclick={() => removeRoot(r)}><Icon path={mdiDeleteOutline} /></button>
        </div>
      {/each}
      <div class="add">
        <div class="row">
          <input class="input" bind:value={newPath} placeholder={s?.platform === "darwin" ? "/Users/你/Pictures 或 /Volumes/SSD名稱/作品" : "資料夾完整路徑"} />
          {#if local && s?.platform === "darwin"}<button class="btn ghost" onclick={pick}>選擇資料夾…</button>{/if}
        </div>
        <div class="row">
          <input class="input" bind:value={newName} placeholder="顯示名稱（選填），例如：作品集 SSD" />
          <button class="btn" disabled={!newPath.trim()} onclick={addRoot}><Icon path={mdiPlus} size={18} />加入並掃描</button>
        </div>
        <p class="muted tiny">練習建議：先加入「圖片」資料夾（/Users/你的名稱/Pictures）。蘋果「照片」App 的資料庫會自動略過。</p>
      </div>
    </section>
    {/if}
    {#if current === "ai"}
    <div class="anchor" id="sec-ai"></div>
    <!-- 工作 -->
    <section class="card">
      <h2><Icon path={mdiCreation} />AI 分析</h2>
      {#if s}
        <div class="stats">
          <a href="/" use:link><b>{count(s.stats.photos)}</b><span>照片</span></a>
          <a href="/videos" use:link><b>{count(s.stats.videos)}</b><span>影片</span></a>
          <a href="/search?q=is:analyzed" use:link><b>{count(s.stats.analyzed)}</b><span>已分析</span></a>
          <a href="/search?q=is:pending" use:link><b>{count(s.stats.pending)}</b><span>待分析</span></a>
          <a href="/search?q=is:failed" use:link class:bad={s.stats.failed}><b>{count(s.stats.failed)}</b><span>失敗</span></a>
          <a href="/search?q=is:missing" use:link><b>{count(s.stats.missing)}</b><span>遺失</span></a>
        </div>
      {/if}
      <JobList />
      {#if jobs?.last && !jobs.active?.length}
        <p class="small" class:danger-text={jobs.last.error}>上次「{jobs.last.label}」：{jobs.last.message}</p>
      {/if}
      {#if s?.ai}
        {#if s.ai.ready}
          <p class="small ok-text"><Icon path={mdiCheck} size={16} />AI 已就緒：{s.ai.model}{settings?.auto_analyze ? "，掃描後會自動分析新照片" : ""}</p>
        {:else}
          <div class="warn">
            <Icon path={mdiAlertCircleOutline} />
            <div><b>AI 分析還不能開始</b><p class="small">{s.ai.message}</p></div>
          </div>
        {/if}
      {/if}
      <div class="row wrap">
        <button class="btn" onclick={() => job("analyze")} disabled={!s?.ai?.ready || aiRunning}>開始 AI 分析{s?.stats.pending ? `（${count(s.stats.pending)} 個）` : ""}</button>
        <button class="btn ghost" onclick={testAnalyze} disabled={aiTesting || !s?.ai?.ollama}>{aiTesting ? "測試中…（第一次載入模型可能要一分鐘）" : "用一張照片測試"}</button>
      </div>
      {#if aiTest}
        <div class="test-result" class:bad={!aiTest.ok}>
          {#if aiTest.ok}
            <b>✓ 成功</b>：{aiTest.name}，模型 {aiTest.model} 花了 {aiTest.seconds} 秒
            <p class="small">{aiTest.result.description}</p>
            <p class="tiny muted">{aiTest.result.tags.join("、")}</p>
          {:else}
            <b>✗ 失敗</b>{#if aiTest.name}：{aiTest.name}（{aiTest.seconds} 秒）{/if}
            <p class="small mono">{aiTest.error}</p>
            <p class="tiny muted">把這段文字截圖給開發者，就能知道原因。</p>
          {/if}
        </div>
      {/if}
      {#if settings}
        <label class="toggle"><input type="checkbox" checked={!!settings.auto_analyze} onchange={(e) => saveSetting("auto_analyze", e.currentTarget.checked ? 1 : 0)} />掃描到新照片後自動 AI 分析</label>
      <div class="sched">
        <span class="label">什麼時候分析</span>
        <div class="seg3" role="radiogroup" aria-label="分析時機" use:slider>
          {#each [["always", "隨時", "不限時段"], ["schedule", "依排程", "指定星期、時段與條件"], ["ask", "每次先問我", "掃描到新照片時先詢問"]] as [v, label, hint] (v)}
            <button role="radio" aria-checked={sched.mode === v} class:on={sched.mode === v} onclick={() => setMode(v)}>
              <b>{label}</b><span>{hint}</span>
            </button>
          {/each}
        </div>
        {#if sched.mode === "schedule"}
          <div class="sched-body">
            <div class="srow">
              <span class="slabel">星期</span>
              <div class="days">
                {#each [1, 2, 3, 4, 5, 6, 7] as d (d)}
                  <button class="day" class:on={sched.days.includes(String(d))} onclick={() => toggleDay(d)} aria-pressed={sched.days.includes(String(d))}>{"一二三四五六日"[d - 1]}</button>
                {/each}
                <span class="presets">
                  <button class="btn text small" onclick={() => saveSched({ schedule_days: "1234567" })}>每天</button>
                  <button class="btn text small" onclick={() => saveSched({ schedule_days: "12345" })}>平日</button>
                  <button class="btn text small" onclick={() => saveSched({ schedule_days: "67" })}>週末</button>
                </span>
              </div>
            </div>
            <div class="srow">
              <span class="slabel">時段</span>
              <div class="times">
                <label class="toggle inline"><input type="checkbox" checked={sched.start === sched.end} onchange={(e) => saveSched(e.currentTarget.checked ? { schedule_start: "00:00", schedule_end: "00:00" } : { schedule_start: "22:00", schedule_end: "07:00" })} />全天</label>
                {#if sched.start !== sched.end}
                  <input class="input time" type="time" value={sched.start} onchange={(e) => saveSched({ schedule_start: e.currentTarget.value })} aria-label="開始時間" />
                  <span>到</span>
                  <input class="input time" type="time" value={sched.end} onchange={(e) => saveSched({ schedule_end: e.currentTarget.value })} aria-label="結束時間" />
                  <span class="muted tiny">{sched.end < sched.start ? "（跨過午夜，到隔天）" : ""}</span>
                {/if}
              </div>
            </div>
            <div class="srow">
              <span class="slabel">條件</span>
              <div class="conds">
                <label class="toggle"><input type="checkbox" checked={sched.ac} onchange={(e) => saveSched({ schedule_ac: e.currentTarget.checked ? 1 : 0 })} />只在接上電源時</label>
                <div class="cond">
                  <label class="toggle"><input type="checkbox" checked={sched.idle > 0} onchange={(e) => saveSched({ schedule_idle: e.currentTarget.checked ? 10 : 0 })} />電腦沒人使用時才分析</label>
                  {#if sched.idle > 0}
                    <select class="input mini" value={String(sched.idle)} onchange={(e) => saveSched({ schedule_idle: Number(e.currentTarget.value) })} aria-label="閒置幾分鐘">
                      {#each [5, 10, 15, 30, 60] as m (m)}<option value={String(m)}>閒置 {m} 分鐘以上</option>{/each}
                    </select>
                  {/if}
                </div>
                <div class="cond">
                  <label class="toggle"><input type="checkbox" checked={sched.battery > 0} onchange={(e) => saveSched({ schedule_battery: e.currentTarget.checked ? 50 : 0 })} />用電池時，電量夠才分析</label>
                  {#if sched.battery > 0}
                    <select class="input mini" value={String(sched.battery)} onchange={(e) => saveSched({ schedule_battery: Number(e.currentTarget.value) })} aria-label="電量下限">
                      {#each [20, 30, 50, 70, 90] as p (p)}<option value={String(p)}>電量 {p}% 以上</option>{/each}
                    </select>
                  {/if}
                </div>
              </div>
            </div>
          </div>
        {/if}
        {#if schedStatus}
          <p class="sched-sum">
            <b>{schedStatus.summary}</b>
            {#if schedStatus.mode === "schedule"}<span class="now" class:ok={schedStatus.ok}>現在：{schedStatus.ok ? "可以分析" : schedStatus.reason}</span>{/if}
          </p>
        {/if}
      </div>
      <p class="muted tiny">不符合排程時，分析會自動暫停，時間到或條件符合後接著做；有人開始用電腦時也會暫停。</p>
      {:else}<Loading kind="rows" count={2} />{/if}
      <div class="row wrap">
        <button class="btn ghost" onclick={() => job("index")}>掃描並分析全部</button>
        <button class="btn ghost" onclick={() => job("scan")}>只掃描</button>
        {#if s?.stats.failed}<button class="btn ghost" onclick={() => job("analyze", { retry_failed: true })}>重試失敗的 {s.stats.failed} 個</button>{/if}
      </div>
      <p class="muted tiny">AI 分析可隨時停止，下次會從未完成的項目繼續。照片很多時，可以先用「速度優先」的模型掃一輪；也可以在資料夾或相簿頁只分析特定作品。</p>
    </section>

    <!-- 模型 -->
    <section class="card">
      <h2><Icon path={mdiCreation} />模型</h2>
      {#if !models}
        <Loading kind="rows" count={3} />
      {:else if !models.ollama_ok}
        <div class="warn">
          <Icon path={mdiAlertCircleOutline} />
          <div>
            <b>沒有連上 Ollama</b>
            <p class="small">AI 分析需要免費的 Ollama 在這台 Mac 上執行模型。照著引導做，大約 3 分鐘。</p>
            <div class="row"><a class="btn small" href="/welcome?step=ollama" use:link>打開安裝引導</a></div>
            <p class="tiny muted">{models.error}</p>
          </div>
        </div>
      {:else}
        <p class="muted small">使用中的視覺模型：<b class="primary">{models.active.vision}</b>。模型在這台 Mac 上執行，照片不會上傳。</p>
      {/if}
      {#if models?.picks}
        {#if models.machine?.ram_gb}<p class="small muted">這台電腦：{models.machine.chip} · {models.machine.ram_gb} GB 記憶體，建議：</p>{/if}
        <div class="picks">
          {#each [["best", "品質優先", "描述比較細，速度普通"], ["fast", "速度優先", "比較快，適合照片很多時先掃一輪"]].filter(([k]) => k === "best" || models.picks.fast !== models.picks.best) as [key, title, hint] (key)}
            {@const name = models.picks[key]}
            {@const info = vision.find((v) => v.name === name)}
            {@const using = sameModel(models.active.vision, name)}
            <div class="pick" class:active={using}>
              <span class="tiny muted">{title}</span>
              <b>{name}</b>
              <span class="tiny muted">{info ? `約 ${info.size_gb} GB · ` : ""}{hint}</span>
              {#if using}
                <span class="using"><Icon path={mdiCheck} size={18} />使用中{info && !info.installed ? "（下載中或尚未下載）" : ""}</span>
                {#if info && !info.installed}<button class="btn small soft" disabled={!models.ollama_ok || !!downloads[name]} onclick={() => pull(name)}>{dlText(name) || "下載"}</button>{/if}
              {:else if info?.installed}
                <button class="btn small" onclick={() => useModel("vision", name)}>使用</button>
              {:else}
                <button class="btn small soft" disabled={!models.ollama_ok || !!downloads[name]} onclick={() => pullAndUse(name)}><Icon path={mdiDownload} size={16} />{dlText(name) || "下載並使用"}</button>
              {/if}
            </div>
          {/each}
        </div>
      {/if}
      {#if settings}
        <div class="detail-pick">
          <span class="small"><b>分析詳細程度</b></span>
          <div class="seg" use:slider>
            <button class:on={settings.analysis_detail !== "fast"} onclick={() => saveSetting("analysis_detail", "standard")}>標準</button>
            <button class:on={settings.analysis_detail === "fast"} onclick={() => saveSetting("analysis_detail", "fast")}>快速</button>
          </div>
          <span class="tiny muted">{settings.analysis_detail === "fast" ? "描述 1–2 句、8–12 個關鍵字，每張約快一倍" : "描述 2–4 句、10–25 個關鍵字（中英對照）"}</span>
        </div>
      {:else}<Loading kind="rows" count={2} />{/if}
      {#if models}
        <details class="more">
        <summary>所有視覺模型（含 Gemma 4、Qwen3-VL 各種大小）</summary>
        <p class="small muted">灰色的模型對這台電腦太大。</p>
        <div class="models">
          {#each vision as m (m.name)}
            {@const active = sameModel(models.active.vision, m.name)}
            <div class="model" class:active class:too-big={m.fit === "too_big" && !m.installed}>
              <div class="mhead"><b>{m.name}</b>{#if m.badge}<span class="badge">{m.badge}</span>{/if}</div>
              <div class="tiny muted">{m.family} · 約 {m.size_gb} GB · {m.speed_text}{m.fit === "tight" ? " · 記憶體吃緊" : m.fit === "too_big" ? ` · 建議 ${m.min_ram}GB 以上記憶體` : ""}</div>
              <p class="small">{m.note}</p>
              <div class="row">
                {#if active}
                  <span class="using"><Icon path={mdiCheck} size={18} />使用中</span>
                {:else if m.installed}
                  <button class="btn small" onclick={() => useModel("vision", m.name)}>使用</button>
                {/if}
                {#if !m.installed}
                  <button class="btn small soft" disabled={!models.ollama_ok || !!downloads[m.name]} onclick={() => pull(m.name)}>
                    <Icon path={mdiDownload} size={16} />{dlText(m.name) || "下載"}
                  </button>
                {:else if !active}
                  <button class="icon-btn" title="刪除模型" onclick={() => deleteModel(m.name)}><Icon path={mdiDeleteOutline} size={20} /></button>
                {/if}
              </div>
            </div>
          {/each}
        </div>
        {#if otherInstalled.length}
          <p class="small">其他已安裝的模型：
            {#each otherInstalled as m (m.name)}
              <button class="chip" class:on={sameModel(models.active.vision, m.name)} onclick={() => useModel("vision", m.name)}>{m.name} · {bytes(m.size)}</button>
            {/each}
          </p>
        {/if}
        <div class="row">
          <input class="input" bind:value={customModel} placeholder="其他 Ollama 視覺模型名稱，例如 qwen2.5vl:32b" />
          <button class="btn ghost" disabled={!customModel.trim() || !models.ollama_ok} onclick={() => pull(customModel.trim())}>下載</button>
          <button class="btn ghost" disabled={!customModel.trim()} onclick={() => useModel("vision", customModel.trim())}>使用</button>
        </div>
        </details>

        <details class="more">
        <summary>語意搜尋（選用的向量模型）</summary>
        <p class="muted small">讓「沙灘」也能找到描述寫「海邊」的照片，中英文互查。</p>
        <div class="models">
          {#each embeds as m (m.name)}
            {@const active = sameModel(models.active.embed, m.name)}
            <div class="model" class:active>
              <div class="mhead"><b>{m.name}</b>{#if m.badge}<span class="badge">{m.badge}</span>{/if}</div>
              <div class="tiny muted">約 {m.size_gb} GB</div>
              <p class="small">{m.note}</p>
              <div class="row">
                {#if active}
                  <span class="using"><Icon path={mdiCheck} size={18} />使用中</span>
                  <button class="btn small ghost" onclick={() => useModel("embed", "")}>關閉</button>
                {:else if m.installed}
                  <button class="btn small" onclick={async () => { await useModel("embed", m.name); job("embed"); }}>使用</button>
                {:else}
                  <button class="btn small soft" disabled={!models.ollama_ok || !!downloads[m.name]} onclick={() => pull(m.name)}>
                    <Icon path={mdiDownload} size={16} />{dlText(m.name) || "下載"}
                  </button>
                {/if}
              </div>
            </div>
          {/each}
        </div>

        </details>
        {#if settings}
          <details class="more">
          <summary>分析選項（語言、尺寸、自動掃描）</summary>
          <div class="row wrap">
            <label class="field">描述語言
              <select class="input" value={settings.language} onchange={(e) => saveSetting("language", e.currentTarget.value)}>
                <option value="zh-TW">繁體中文（附英文關鍵字）</option>
                <option value="en">English</option>
              </select>
            </label>
            <label class="field">送進模型的尺寸
              <select class="input" value={String(settings.analyze_max_side)} onchange={(e) => saveSetting("analyze_max_side", Number(e.currentTarget.value))}>
                <option value="768">768（較快）</option>
                <option value="1024">1024（建議）</option>
                <option value="1344">1344（細節多、較慢）</option>
              </select>
            </label>
            <label class="field">開啟時自動掃描
              <select class="input" value={String(settings.scan_on_start)} onchange={(e) => saveSetting("scan_on_start", Number(e.currentTarget.value))}>
                <option value="1">是</option>
                <option value="0">否</option>
              </select>
            </label>
          </div>
          </details>
        {:else}<Loading kind="rows" count={2} />{/if}
      {:else}<Loading kind="rows" count={2} />{/if}
    </section>
    {/if}
    {#if current === "recog"}
    <div class="anchor" id="sec-faces"></div>
    <!-- 人臉辨識 -->
    <section class="card" id="faces">
      <SectionTitle icon={mdiFaceRecognition} title="人臉辨識">自動找出照片中的人臉，把同一個人整理在一起，命名後可直接搜尋名字。全部在這台 Mac 上運算，臉部特徵只存在本機。</SectionTitle>
      {#if settings}
        <label class="toggle">
          <input type="checkbox" checked={!!settings.face_enabled}
            onchange={async (e) => { settings = await api("/api/settings", { body: { face_enabled: e.currentTarget.checked ? 1 : 0 } }); }} />
          掃描新照片時自動偵測人臉
        </label>
        <div class="models">
          {#each faceModels as m (m.name)}
            {@const active = settings.face_model === m.name}
            <div class="model" class:active>
              <div class="mhead"><b>{m.label}</b></div>
              {#if m.download_mb}<div class="tiny muted">下載約 {m.download_mb} MB · 安裝後 {m.disk_mb} MB</div>{/if}
              <p class="small">{m.note}</p>
              <div class="row">
                {#if !m.installed}
                  <button class="btn small soft" disabled={!!downloads[m.name] || (m.custom && !m.url)} onclick={() => job("face_model", { model: m.name })}>
                    <Icon path={mdiDownload} size={16} />{dlText(m.name) || "下載"}
                  </button>
                {/if}
                {#if active}
                  <span class="using"><Icon path={mdiCheck} size={18} />使用中</span>
                {:else if m.installed}
                  <button class="btn small" onclick={() => useFaceModel(m.name)}>使用</button>
                {/if}
                {#if m.installed && !active}
                  <button class="icon-btn" title="刪除模型" onclick={() => deleteExtraModel("faces", m.name)}><Icon path={mdiDeleteOutline} size={20} /></button>
                {/if}
              </div>
            </div>
          {/each}
        </div>
        <div class="row wrap">
          <label class="field">辨識嚴格度
            <select class="input" value={String(settings.face_similarity)}
              onchange={(e) => saveSetting("face_similarity", Number(e.currentTarget.value))}>
              <option value="42">寬鬆（容易合在一起）</option>
              <option value="50">標準（建議）</option>
              <option value="58">嚴格（容易分成多人）</option>
            </select>
          </label>
          <label class="field">出現幾次才建立人物
            <select class="input" value={String(settings.face_min_faces)}
              onchange={(e) => saveSetting("face_min_faces", Number(e.currentTarget.value))}>
              {#each [2, 3, 5, 10] as n (n)}<option value={String(n)}>{n} 次</option>{/each}
            </select>
          </label>
        </div>
        {#if s}
          <JobList kinds={["faces", "cluster", "face_model"]} compact />
        <p class="small">已找到 {count(s.stats.faces)} 張臉、{count(s.stats.people)} 位人物；尚未偵測 {count(s.stats.faces_pending)} 張照片。</p>
        {/if}
        <div class="row wrap">
          <button class="btn" disabled={!faceModels.find((m) => m.active)?.installed} onclick={() => job("faces")}>偵測人臉</button>
          <button class="btn ghost" onclick={() => job("cluster")}>重新分群</button>
          <button class="btn ghost danger-text" onclick={clearFaces}>刪除所有人臉資料</button>
        </div>
        <p class="muted tiny">「重新分群」會保留已命名的人物與你手動更正的結果。InsightFace 預訓練模型授權僅限非商業用途。</p>
      {:else}<Loading kind="rows" count={2} />{/if}
    </section>
    {/if}
    {#if current === "search"}
    <div class="anchor" id="sec-search"></div>
    <!-- 智慧搜尋 -->
    <section class="card" id="search">
      <h2><Icon path={mdiImageSearchOutline} />智慧搜尋（跨語言）</h2>
      {#if settings}
        <label class="toggle">
          <input type="checkbox" checked={!!settings.query_rewrite}
            onchange={async (e) => { settings = await api("/api/settings", { body: { query_rewrite: e.currentTarget.checked ? 1 : 0 } }); }} />
          用 AI 翻譯並擴充搜尋詞
        </label>
        <p class="muted small">輸入「貓」也會找 cat、kitten、貓咪；輸入 beach 也會找海邊、沙灘。使用目前的視覺模型（{settings.vision_model}），每個新查詢約 1–3 秒，重複查詢會立即回應。</p>

        <h3>圖像搜尋（多語言 CLIP）</h3>
        <p class="muted small">直接用文字比對畫面內容，不需要等 AI 描述跑完；建立索引很快（十萬張約半小時）。</p>
        <label class="toggle">
          <input type="checkbox" checked={!!settings.clip_enabled}
            onchange={async (e) => {
              settings = await api("/api/settings", { body: { clip_enabled: e.currentTarget.checked ? 1 : 0 } });
              if (settings.clip_enabled && clipModels.find((m) => m.active)?.installed) job("clip");
            }} />
          搜尋時比對畫面內容，掃描新照片時自動建立索引
        </label>
        <div class="models">
          {#each clipModels as m (m.name)}
            {@const active = settings.clip_model === m.name}
            <div class="model" class:active>
              <div class="mhead"><b>{m.label}</b></div>
              <p class="small">{m.note}</p>
              <div class="row">
                {#if !m.installed}
                  <button class="btn small soft" disabled={!!downloads[m.name] || (m.custom && !m.repo)} onclick={() => job("clip_model", { model: m.name })}>
                    <Icon path={mdiDownload} size={16} />{dlText(m.name) || "下載"}
                  </button>
                {/if}
                {#if active}
                  <span class="using"><Icon path={mdiCheck} size={18} />使用中</span>
                {:else if m.installed}
                  <button class="btn small" onclick={async () => { settings = await api("/api/settings", { body: { clip_model: m.name } }); loadExtra(); job("clip"); }}>使用</button>
                {/if}
                {#if m.installed && !active}
                  <button class="icon-btn" title="刪除模型" onclick={() => deleteExtraModel("clip", m.name)}><Icon path={mdiDeleteOutline} size={20} /></button>
                {/if}
              </div>
            </div>
          {/each}
        </div>
        <JobList kinds={["clip", "clip_model"]} compact />
      {#if s}<p class="small">已建立圖像索引：{count(s.stats.clip_done)} / {count(s.stats.images)}</p>{/if}
        <div class="row wrap">
          <button class="btn ghost" disabled={!clipModels.find((m) => m.active)?.installed} onclick={() => job("clip")}>建立圖像索引</button>
        </div>
        <p class="muted tiny">模型從 Hugging Face 下載（Immich 專案提供的 ONNX 版本），檔案約數百 MB 到 1 GB 以上。</p>
      {:else}<Loading kind="rows" count={2} />{/if}
    </section>
    {/if}
    {#if current === "organize"}
    <div class="anchor" id="sec-rating"></div>
    <!-- 星等與疊放 -->
    <section class="card" id="rating">
      <h2><Icon path={mdiStar} />星等與疊放</h2>
      {#if settings}
        <p class="muted small">星等、顏色標籤與拒絕只存在圖庫裡，不會改動硬碟上的檔案。
          檢視照片時可用快捷鍵：0–5 星等、6–9 顏色、X 拒絕、U 取消拒絕。</p>
        <label class="toggle">
          <input type="checkbox" checked={!!settings.viewer_rating_bar}
            onchange={async (e) => { settings = await api("/api/settings", { body: { viewer_rating_bar: e.currentTarget.checked ? 1 : 0 } }); refresh(); }} />
          檢視照片時，在下方顯示星等與顏色標籤列（關閉後快捷鍵仍可使用）
        </label>
        <label class="toggle">
          <input type="checkbox" checked={!!settings.stack_enabled}
            onchange={async (e) => { settings = await api("/api/settings", { body: { stack_enabled: e.currentTarget.checked ? 1 : 0 } }); job("stacks"); }} />
          自動疊放 RAW＋JPEG 與連拍
        </label>
        <div class="row wrap">
          <label class="field">連拍判定間隔
            <select class="input" value={String(settings.burst_seconds)}
              onchange={async (e) => { await saveSetting("burst_seconds", Number(e.currentTarget.value)); job("stacks"); }}>
              <option value="1">1 秒內（較嚴格）</option>
              <option value="2">2 秒內</option>
              <option value="3">3 秒內（較寬鬆）</option>
            </select>
          </label>
        </div>
        <p class="muted tiny">連續 3 張以上、同一台相機才算連拍。手動解除或調整過的疊放不會被重新計算覆蓋。</p>
      {:else}<Loading kind="rows" count={2} />{/if}
    </section>
    {/if}
    {#if current === "library"}
    <div class="anchor" id="sec-features"></div>
    <section class="card">
      <SectionTitle icon={mdiViewDashboardOutline} title="功能與選單">關掉的功能會從左側選單消失。照片、資料夾、相簿和設定一定會顯示。</SectionTitle>
      <div class="feature-list">
        {#each FEATURES as f (f.href)}
          <label class="feature">
            <span><b>{f.label}</b><span class="tiny muted">{f.hint}</span></span>
            <input type="checkbox" class="switch" checked={!hiddenSet.has(f.href)} onchange={(e) => setFeature(f.href, e.currentTarget.checked)} />
          </label>
        {/each}
      </div>
      <p class="muted tiny">左側選單的分組（圖庫、整理、分類…）可以點組名收合。</p>
    </section>
    {/if}
    {#if current === "system"}
    <div class="anchor" id="sec-phone"></div>
    <!-- 手機 -->
    <section class="card">
      <h2><Icon path={mdiCellphone} />手機與平板（同一個 Wi-Fi）</h2>
      {#if lan}
        {#if !lan.local}
          <p class="muted small">你正透過區網連線。連線設定只能在 Mac 本機修改。</p>
        {:else}
          <p class="muted small">開啟後，同一個 Wi-Fi 下的 iPhone／iPad 用瀏覽器開啟下方網址，輸入密碼即可瀏覽。Mac 需要保持開機、不睡眠，外接 SSD 需接上。</p>
          <div class="row wrap">
            <input class="input pw" type="password" bind:value={password} placeholder={lan.has_password ? "變更密碼（至少 6 個字元）" : "設定連線密碼（至少 6 個字元）"} />
            <button class="btn ghost" disabled={password.length < 6} onclick={savePassword}>{lan.has_password ? "變更密碼" : "設定密碼"}</button>
          </div>
          <label class="toggle">
            <input type="checkbox" checked={lan.enabled} disabled={!lan.has_password} onchange={(e) => setLan(e.currentTarget.checked)} />
            允許手機與平板連線{lan.has_password ? "" : "（請先設定密碼）"}
          </label>
          {#if lan.needs_restart}
            <div class="warn">
              <Icon path={mdiServerNetwork} />
              <div><b>需要重新啟動服務才會生效</b>
                <p class="small">macOS 第一次可能詢問是否允許 Python 接受連入連線，請選「允許」。</p>
                <button class="btn small" disabled={restarting} onclick={restart}>{restarting ? "重新啟動中…" : "立即重新啟動"}</button>
              </div>
            </div>
          {/if}
        {/if}
        {#if lan.active && lan.urls.length}
          <div class="qr-row">
            {#if lan.qr}<div class="qr">{@html lan.qr}</div>{/if}
            <div>
              <p class="small">用 iPhone 相機掃描 QR code，或在瀏覽器輸入：</p>
              {#each lan.urls as u (u)}<p><code>{u}</code></p>{/each}
              <p class="tiny muted">在 Safari 按「分享」→「加入主畫面」，就能像 App 一樣全螢幕使用。</p>
            </div>
          </div>
        {/if}
      {:else}<Loading kind="rows" count={2} />{/if}
    </section>
    {/if}
    {#if current === "organize"}
    <div class="anchor" id="sec-tools"></div>
      <section class="card">
        <SectionTitle icon={mdiToolboxOutline} title="整理工具的判定標準">每個整理工具的判斷方式都在這裡調整，全部在這台 Mac 上計算，不用 AI。調整後，「整理工具」的清單會立刻更新。</SectionTitle>
        {#if settings}
          <h3 class="tool-h">重複照片</h3>
          <div class="row wrap">
            <label class="field">相似度判定
              <select class="input" value={String(settings.dup_threshold)} onchange={(e) => saveSetting("dup_threshold", Number(e.currentTarget.value))}>
                <option value="3">嚴格（只找幾乎一模一樣的）</option>
                <option value="6">標準（建議）</option>
                <option value="10">寬鬆（連拍、構圖相近也算）</option>
              </select>
            </label>
          </div>
          <p class="muted tiny">改了之後到「整理工具 → 重複照片」按「重新比對」套用。</p>
          <h3 class="tool-h">截圖與文件</h3>
          <label class="toggle"><input type="checkbox" checked={!!settings.screen_png_rule}
            onchange={(e) => saveSetting("screen_png_rule", e.currentTarget.checked ? 1 : 0)} />沒有相機資訊的 PNG 也算截圖</label>
          <p class="muted tiny">另外一定會列入：檔名含「螢幕截圖、Screenshot」的，以及 AI 判斷是截圖、文件、收據的照片。</p>
          <h3 class="tool-h">大檔案</h3>
          <div class="row wrap">
            <label class="field">列出幾個
              <select class="input" value={String(settings.large_files_limit)} onchange={(e) => saveSetting("large_files_limit", Number(e.currentTarget.value))}>
                {#each [100, 200, 500, 1000] as n (n)}<option value={String(n)}>最大的 {n} 個</option>{/each}
              </select>
            </label>
          </div>
        {:else}<Loading kind="rows" count={2} />{/if}
      </section>
    {/if}
    {#if current === "system"}
    <div class="anchor" id="sec-storage"></div>
      <StoragePanel />
    {/if}
    {#if current === "library"}
    <div class="anchor" id="sec-look"></div>
    <!-- 外觀與系統 -->
    <section class="card">
      <h2><Icon path={mdiThemeLightDark} />外觀</h2>
      <h3>照片呈現方式</h3>
      {#if settings}
        <div class="styles">
          {#each [["aspect", "依照片比例", "完整顯示構圖，橫幅、直幅照片都不裁切（像 Google 相簿）"], ["square", "正方形", "每張裁成正方形，排列整齊，一次看到比較多張"]] as [v, label, hint] (v)}
            <button class="style" class:on={settings.grid_style === v} onclick={async () => { await saveSetting("grid_style", v); refresh(); }}>
              <span class="preview {v}"><i></i><i></i><i></i><i></i><i></i></span>
              <b>{label}</b><span class="tiny muted">{hint}</span>
            </button>
          {/each}
        </div>
        <p class="tiny muted">手機螢幕較窄，一律用正方形顯示。</p>
      {:else}<Loading kind="rows" count={2} />{/if}
      <h3>系統</h3>
      {#if s}
        <ul class="sys small">
          <li>exiftool（完整 EXIF、RAW 預覽）：{s.tools.exiftool ? "✓" : "未安裝 → brew install exiftool"}</li>
          <li>ffmpeg（影片縮圖與分析）：{s.tools.ffmpeg ? "✓" : "未安裝 → brew install ffmpeg"}</li>
          <li>HEIC 支援：{s.tools.heif ? "✓" : "未安裝 pillow-heif"}</li>
          {#if s.home}<li>圖庫資料（資料庫與縮圖）：<code>{s.home}</code></li>{/if}
          <li class="muted">Re'memor {s.version}</li>
        </ul>
      {/if}
      <div class="row wrap"><a class="btn ghost small" href="/welcome" use:link>重新執行設定引導</a></div>
    </section>
    {/if}
    {#if current === "system"}
    <div class="anchor" id="sec-advanced"></div>
    <!-- 自訂模型 -->
    <section class="card" id="custom-models">
      <SectionTitle icon={mdiTuneVariant} title="進階：自訂模型與提示詞">推薦清單之外，任何模型都可以自己指定。改了模型或提示詞之後，可到資料夾或相簿按「AI 分析」重新分析。一般使用不需要改這裡。</SectionTitle>
      {#if settings && models}
        <h3>Ollama 位址</h3>
        <div class="row">
          <input class="input" bind:value={ollamaUrl} placeholder="http://127.0.0.1:11434" />
          <button class="btn ghost" onclick={testOllama}>測試</button>
          <button class="btn" disabled={ollamaUrl === settings.ollama_url} onclick={() => saveMany({ ollama_url: ollamaUrl.trim() }, "已更新 Ollama 位址")}>儲存</button>
        </div>
        {#if ollamaTest}<p class="small">{ollamaTest}</p>{/if}
        <p class="muted tiny">可以指向區網內另一台有更強顯示卡的電腦，例如 http://192.168.1.30:11434（那台的 Ollama 需設定 OLLAMA_HOST=0.0.0.0）。照片會透過區網傳過去分析。</p>

        <h3>視覺模型（描述照片）</h3>
        <div class="row">
          <select class="input" value={settings.vision_model} onchange={(e) => useModel("vision", e.currentTarget.value)}>
            {#if !models.installed.some((m) => sameModel(m.name, settings.vision_model))}<option value={settings.vision_model}>{settings.vision_model}（{models.ollama_ok ? "未下載" : "Ollama 未連線"}）</option>{/if}
            {#each models.installed as m (m.name)}<option value={m.name}>{m.name}{m.parameter_size ? ` · ${m.parameter_size}` : ""} · {bytes(m.size)}</option>{/each}
          </select>
        </div>
        <p class="muted tiny">清單是 Ollama 已下載的所有模型；要用沒下載的模型，到「AI 分析 → 所有視覺模型」最下面輸入名稱並下載。請選支援圖片輸入的模型（例如 gemma4、qwen3-vl、qwen2.5vl、minicpm-v）。</p>

        <h3>搜尋翻譯用的文字模型</h3>
        <div class="row">
          <select class="input" bind:value={textModel}>
            <option value="">與視覺模型相同（{settings.vision_model}）</option>
            {#each models.installed as m (m.name)}<option value={m.name}>{m.name}</option>{/each}
          </select>
          <button class="btn" disabled={textModel === (settings.text_model || "")} onclick={() => saveMany({ text_model: textModel }, "已更新搜尋翻譯模型")}>儲存</button>
        </div>
        <p class="muted tiny">智慧搜尋把查詢翻成中英文同義詞、以及「翻譯成中文」時使用。用小一點的純文字模型（例如 qwen2.5:3b）搜尋會更快。</p>

        <h3>語意搜尋向量模型</h3>
        <div class="row">
          <select class="input" value={settings.embed_model} onchange={async (e) => { await useModel("embed", e.currentTarget.value); if (e.currentTarget.value) job("embed"); }}>
            <option value="">不使用</option>
            {#if settings.embed_model && !models.installed.some((m) => sameModel(m.name, settings.embed_model))}<option value={settings.embed_model}>{settings.embed_model}（{models.ollama_ok ? "未下載" : "Ollama 未連線"}）</option>{/if}
            {#each models.installed as m (m.name)}<option value={m.name}>{m.name}</option>{/each}
          </select>
        </div>
        <div class="row">
          <input class="input" bind:value={embedCustom} placeholder="其他向量模型名稱，例如 nomic-embed-text" />
          <button class="btn ghost" disabled={!embedCustom.trim()} onclick={() => pull(embedCustom.trim())}>下載</button>
          <button class="btn ghost" disabled={!embedCustom.trim()} onclick={async () => { await useModel("embed", embedCustom.trim()); job("embed"); }}>使用</button>
        </div>

        <h3>AI 描述提示詞</h3>
        <textarea class="input prompt" rows="9" bind:value={prompt} placeholder={settings.default_prompt}></textarea>
        <div class="row">
          <button class="btn" disabled={prompt === (settings.analysis_prompt || "")} onclick={() => saveMany({ analysis_prompt: prompt }, "已更新提示詞")}>儲存</button>
          <button class="btn ghost" onclick={() => (prompt = settings.default_prompt)}>從內建提示詞開始改</button>
          <button class="btn ghost" disabled={!settings.analysis_prompt} onclick={() => { prompt = ""; saveMany({ analysis_prompt: "" }, "已恢復內建提示詞"); }}>恢復內建</button>
        </div>
        <p class="muted tiny">空白時使用內建提示詞（灰字）。自訂時請保留要求輸出 description、tags、objects、scene、text_in_image 的說明；程式會自動附上檔案路徑與拍攝日期作為參考。</p>

        <h3>自訂圖像搜尋模型（CLIP）</h3>
        <div class="row">
          <input class="input" bind:value={clipRepo} placeholder="Hugging Face 儲存庫，例如 immich-app/ViT-B-16-SigLIP2__webli" />
          <button class="btn ghost" disabled={!clipRepo.trim() || clipRepo === settings.clip_custom_repo} onclick={() => saveMany({ clip_custom_repo: clipRepo.trim() }, "已儲存，請到「智慧搜尋」區下載「自訂模型」")}>儲存</button>
        </div>
        <p class="muted tiny">需為 Immich 格式（含 visual/model.onnx 與 textual/model.onnx）。Immich 的模型清單：huggingface.co/immich-app。</p>

        <h3>自訂人臉模型（InsightFace 格式）</h3>
        <div class="row wrap">
          <input class="input" bind:value={faceCustom.url} placeholder="模型 zip 網址" />
          <input class="input short" bind:value={faceCustom.det} placeholder="偵測檔名，例如 det_10g.onnx" />
          <input class="input short" bind:value={faceCustom.rec} placeholder="特徵檔名，例如 w600k_r50.onnx" />
          <button class="btn ghost" disabled={!faceCustom.url || !faceCustom.det || !faceCustom.rec}
            onclick={() => saveMany({ face_custom_url: faceCustom.url.trim(), face_custom_det: faceCustom.det.trim(), face_custom_rec: faceCustom.rec.trim() }, "已儲存，請到「人臉辨識」區下載「自訂模型」")}>儲存</button>
        </div>
      {/if}
    </section>
    {/if}
  </div>
</div>

<style>
  .settings { max-width: 1120px; display: grid; grid-template-columns: 220px minmax(0, 1fr); gap: 28px; align-items: start; }
  .cats { position: sticky; top: 16px; display: flex; flex-direction: column; gap: 2px; }
  .cats-head { display: flex; align-items: center; gap: 4px; margin: 0 12px 14px 8px; }
  .cats h1 { font-size: var(--text-title-1); margin: 0; font-weight: 400; }
  .cats a {
    display: flex; align-items: center; gap: 12px; padding: 9px 14px; border-radius: var(--corner-full); text-decoration: none;
    color: var(--on-surface); font-size: var(--text-title-3);
  }
  .cats a:hover { background: var(--surface-container); }
  .cats a { position: relative; isolation: isolate; }
  .cats a.on { color: var(--on-secondary-container); font-weight: 500; background: none; }
  /* M3：選取的膠囊在新項目上由中間展開 */
  .cats a.on:not(.ver)::after {
    content: ""; position: absolute; inset: 0; border-radius: inherit; background: var(--secondary-container); z-index: -1;
    animation: cat-pill var(--spring-expressive-fast-spatial-duration) var(--spring-expressive-fast-spatial);
  }
  @keyframes cat-pill { from { transform: scaleX(0.3); opacity: 0.4; } }
  .cl { display: flex; flex-direction: column; min-width: 0; }
  .tool-h { font-size: var(--text-body); font-weight: 500; margin: 20px 0 8px; }
  .csub { display: none; font-size: var(--text-callout); font-weight: 400; color: var(--on-surface-variant); }
  .anchor { scroll-margin-top: 16px; }
  .cats a.ver { margin-top: 12px; padding: 6px 14px; font-size: var(--text-callout); color: var(--on-surface-variant); font-weight: 400; background: none; }
  .cats a.ver:hover { color: var(--on-surface); background: none; text-decoration: underline; }
  .about-head { display: flex; align-items: center; gap: 14px; margin-bottom: 12px; }
  .about-head h2.plain { margin: 0; font-size: var(--text-title-1); font-weight: 400; }
  .about h3 { font-size: var(--text-body); font-weight: 500; margin: 18px 0 4px; }
  .about .sel { user-select: text; font-weight: 500; }
  .about .terms { margin: 4px 0 8px; padding-left: 20px; display: flex; flex-direction: column; gap: 2px; color: var(--on-surface-variant); }
  .about .tp { list-style: none; margin: 6px 0 0; padding: 0; display: flex; flex-direction: column; font-size: var(--text-body); }
  .about .tp li { display: flex; justify-content: space-between; gap: 12px; padding: 6px 0; border-bottom: 1px solid var(--outline-variant); flex-wrap: wrap; }
  .back { display: none; }
  .pane { min-width: 0; }
  details.more { margin-top: 14px; border-top: 1px solid var(--outline-variant); padding-top: 10px; }
  details.more summary { cursor: pointer; font-weight: 500; font-size: var(--text-body); color: var(--on-surface-variant); padding: 4px 0; }
  details.more[open] summary { color: var(--on-surface); margin-bottom: 8px; }
  .detail-pick { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; margin: 10px 0 4px; }
  .detail-pick .seg { display: inline-flex; border: 1px solid var(--outline-variant); border-radius: var(--corner-full); overflow: hidden; }
  .detail-pick .seg button { border: 0; background: none; color: var(--on-surface-variant); padding: 4px 16px; font-size: var(--text-body); cursor: pointer; }
  .detail-pick .seg button + button { border-left: 1px solid var(--outline-variant); }
  .detail-pick .seg button.on { background: var(--secondary-container); color: var(--primary); font-weight: 500; }
  .picks { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 10px; margin: 8px 0; }
  .pick { background: var(--surface); border: 2px solid transparent; border-radius: var(--corner-medium); padding: 12px 14px; display: flex; flex-direction: column; gap: 4px; align-items: flex-start; }
  .pick.active { border-color: var(--primary); }
  .pick b { font-size: var(--text-title-3); }
  .feature-list { display: flex; flex-direction: column; background: var(--surface); border-radius: var(--corner-medium); margin: 12px 0; }
  .feature { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 12px 14px; cursor: pointer; }
  .feature + .feature { border-top: 1px solid var(--outline-variant); }
  .feature > span { display: flex; flex-direction: column; }
  /* 開關一律用全站的 M3 Switch（app.css） */
  .styles { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 10px; }
  .style { background: var(--surface); border: 2px solid transparent; border-radius: var(--corner-medium); padding: 12px; display: flex; flex-direction: column; gap: 4px; align-items: flex-start; text-align: left; cursor: pointer; color: var(--on-surface); }
  .style.on { border-color: var(--primary); }
  .preview { display: flex; gap: 3px; height: 34px; width: 100%; margin-bottom: 6px; }
  .preview i { background: var(--secondary-container); border-radius: var(--radius-xs); }
  .preview.aspect i:nth-child(1) { flex: 1.5; } .preview.aspect i:nth-child(2) { flex: .7; } .preview.aspect i:nth-child(3) { flex: 1.5; }
  .preview.aspect i:nth-child(4) { flex: 1; } .preview.aspect i:nth-child(5) { flex: .7; }
  .preview.square i { width: 34px; flex: none; }
  @media (max-width: 760px) {
    .settings { grid-template-columns: 1fr; gap: 8px; }
    .settings.has-section .cats { display: none; }
    .settings:not(.has-section) .pane { display: none; }
    .cats { position: static; }
    .cats a { padding: 12px 14px; border-radius: var(--corner-medium); }
    .csub { display: block; }
    .back { display: inline-flex; align-items: center; gap: 6px; text-decoration: none; color: var(--on-surface-variant); margin: 0 0 10px; }
  }
  .sched { display: flex; flex-direction: column; gap: 10px; margin: 14px 0 6px; }
  .sched .label { font-size: var(--text-body); font-weight: 500; }
  .seg3 { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; }
  .seg3 button { display: flex; flex-direction: column; gap: 2px; text-align: left; padding: 10px 14px; border-radius: var(--corner-medium); border: 1px solid var(--outline-variant); background: none; color: var(--on-surface); cursor: pointer; }
  .seg3 button b { font-weight: 500; font-size: var(--text-body); }
  .seg3 button span { font-size: var(--text-callout); color: var(--on-surface-variant); }
  .seg3 button.on { border: 2px solid var(--primary); padding: 9px 13px; background: color-mix(in srgb, var(--primary) 8%, transparent); }
  .sched-body { display: flex; flex-direction: column; gap: 14px; padding: 14px 16px; border-radius: var(--corner-medium); background: var(--surface-container); }
  .srow { display: grid; grid-template-columns: 56px minmax(0, 1fr); gap: 12px; align-items: start; }
  .slabel { font-size: var(--text-body); color: var(--on-surface-variant); padding-top: 8px; }
  .days { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; }
  .day { width: 40px; height: 40px; border-radius: 50%; border: 1px solid var(--outline); background: none; color: var(--on-surface); font-size: var(--text-body); cursor: pointer; }
  .day.on { background: var(--secondary-container); color: var(--on-secondary-container); border-color: transparent; font-weight: 500; }
  .presets { display: inline-flex; margin-left: 4px; }
  .times { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; }
  .time { width: auto; min-width: 120px; }
  .toggle.inline { flex-direction: row; gap: 8px; }
  .conds { display: flex; flex-direction: column; gap: 10px; }
  .cond { display: flex; flex-direction: column; gap: 6px; }
  .input.mini { width: auto; align-self: flex-start; }
  .sched-sum { display: flex; flex-wrap: wrap; gap: 4px 12px; margin: 2px 0 0; font-size: var(--text-body); }
  .sched-sum b { font-weight: 500; }
  .now { color: var(--on-surface-variant); }
  .now.ok { color: var(--primary); }
  @media (max-width: 600px) { .seg3 { grid-template-columns: 1fr; } .srow { grid-template-columns: 1fr; gap: 4px; } .slabel { padding-top: 0; } }
  .card { background: var(--surface-container-low); border-radius: var(--corner-large); padding: 20px 24px; margin-bottom: 16px; }
  h2 { display: flex; align-items: center; gap: 12px; font-size: var(--text-title-1); line-height: 28px; font-weight: 400; margin: 0 0 8px; }
  h3 { font-size: var(--text-body); margin: 20px 0 10px; }
  .root { display: flex; align-items: center; gap: 8px; padding: 10px 0; border-bottom: 1px solid var(--outline-variant); }
  .dot { width: 10px; height: 10px; border-radius: 50%; background: var(--system-green); flex-shrink: 0; }
  .dot.off { background: var(--error); }
  .grow { flex: 1; min-width: 0; }
  .path { word-break: break-all; font-family: var(--font-mono); }
  .add { margin-top: 14px; display: flex; flex-direction: column; gap: 8px; }
  .row { display: flex; gap: 8px; align-items: center; }
  .row.wrap { flex-wrap: wrap; margin-top: 10px; }
  .stats { display: grid; grid-template-columns: repeat(6, 1fr); gap: 8px; margin: 12px 0; }
  .stats a { background: var(--surface); border-radius: var(--corner-medium); padding: 10px; display: flex; flex-direction: column; align-items: center; text-decoration: none; color: var(--on-surface); border: 2px solid transparent; }
  .stats a:hover { border-color: var(--secondary-container); }
  .stats a.bad b { color: var(--error); }
  .stats b { font-size: var(--text-title-1); font-weight: 400; }
  .stats span { font-size: var(--text-callout); color: var(--on-surface-variant); }
  .job { display: flex; gap: 12px; align-items: flex-start; background: var(--surface); padding: 12px; border-radius: var(--corner-medium); }
  .msg { word-break: break-all; }
  .models { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 10px; }
  .model { background: var(--surface); border-radius: var(--corner-medium); padding: 12px; border: 2px solid transparent; display: flex; flex-direction: column; }
  .model.active { border-color: var(--primary); }
  .model.too-big { opacity: .55; }
  .machine { background: var(--surface); border-radius: var(--corner-medium); padding: 10px 12px; }
  .ok-text { color: var(--primary); display: flex; align-items: center; gap: 6px; }
  .test-result { background: var(--surface); border-radius: var(--corner-medium); padding: 12px; margin: 10px 0; border-left: 4px solid var(--primary); }
  .test-result.bad { border-left-color: var(--error); }
  .test-result p { margin: 6px 0 0; }
  .mono { font-family: var(--font-mono); word-break: break-all; white-space: pre-wrap; }
  .model p { margin: 6px 0 10px; flex: 1; }
  .mhead { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
  .badge { background: var(--secondary-container); color: var(--primary); font-size: var(--text-sub); padding: 1px 8px; border-radius: var(--corner-full); font-weight: 500; }
  .using { display: inline-flex; align-items: center; gap: 4px; color: var(--primary); font-weight: 500; font-size: var(--text-body); }
  .primary { color: var(--primary); }
  .warn { display: flex; gap: 12px; background: var(--surface); border-radius: var(--corner-medium); padding: 12px; margin: 10px 0; color: var(--error); }
  .warn > div { color: var(--on-surface); }
  .warn p { margin: 4px 0; }
  .field { display: flex; flex-direction: column; gap: 4px; font-size: var(--text-body); color: var(--on-surface-variant); min-width: 200px; flex: 1; }
  .toggle { display: flex; flex-direction: row-reverse; align-items: center; justify-content: space-between; gap: 16px; margin: 12px 0; font-size: var(--text-title-3); line-height: 24px; cursor: pointer; }
  .pw { max-width: 320px; }
  .qr-row { display: flex; gap: 20px; align-items: center; flex-wrap: wrap; margin-top: 12px; }
  .qr { width: 170px; height: 170px; background: var(--media-fg); border-radius: var(--corner-medium); padding: 6px; }
  .qr :global(svg) { width: 100%; height: 100%; }
  .prompt { font-family: var(--font-mono); font-size: var(--text-callout); resize: vertical; margin-bottom: 8px; }
  .short { max-width: 260px; }
  code { background: var(--surface); padding: 2px 8px; border-radius: var(--corner-small); font-size: var(--text-body); word-break: break-all; }
  .sys { margin: 14px 0 0; padding-left: 18px; display: flex; flex-direction: column; gap: 4px; }
  @media (max-width: 760px) {
    .stats { grid-template-columns: repeat(3, 1fr); }
    .row:not(.wrap) { flex-wrap: wrap; }
  }
</style>
