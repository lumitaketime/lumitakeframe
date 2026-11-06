<script>
  /**
   * 設定頁最上面的狀態卡：AI 分析、辨識、圖庫，以及未連接的資料夾。
   * 整張卡可以點，會跳到對應的設定；有進度的顯示進度條；需要處理的換成提醒底色並附一鍵處理。
   */
  import Icon from "./Icon.svelte";
  import { api } from "../lib/api.js";
  import { app, refresh, toast } from "../lib/state.svelte.js";
  import { navigate } from "../lib/router.svelte.js";
  import { count, eta } from "../lib/format.js";
  import { mdiCreation, mdiFaceRecognition, mdiImageMultipleOutline, mdiHarddisk, mdiAlertOutline } from "../lib/icons.js";

  let pets = $state(null);

  $effect(() => {
    app.refreshKey;
    api("/api/pets").then((d) => (pets = d)).catch(() => {});
  });

  const s = $derived(app.server);
  const st = $derived(s?.stats || {});
  const ai = $derived(s?.ai);
  const active = $derived(s?.jobs?.active || []);
  const jobOf = (...kinds) => active.find((j) => kinds.includes(j.kind));
  const pct = (done, total) => (total > 0 ? Math.min(100, Math.round((done / total) * 100)) : null);

  // AI：正在分析就顯示這次工作的進度，否則顯示整個圖庫分析了多少
  const aiJob = $derived(jobOf("analyze", "index"));
  const aiPct = $derived(aiJob?.total ? pct(aiJob.done, aiJob.total) : pct(st.analyzed || 0, (st.analyzed || 0) + (st.pending || 0)));
  // 辨識：人臉找過的照片比例；正在跑人臉或寵物時顯示那個工作的進度
  const recogJob = $derived(jobOf("faces", "pets", "pet_model", "cluster", "pet_cluster"));
  const facePct = $derived(recogJob?.total ? pct(recogJob.done, recogJob.total) : pct((st.photos || 0) - (st.faces_pending || 0), st.photos || 0));
  // 圖庫：掃描中才有進度
  const scanJob = $derived(jobOf("scan"));
  const offline = $derived((s?.roots || []).filter((r) => !r.online));

  function go(href) {
    navigate(href);
  }
  function key(e, href) {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      go(href);
    }
  }

  async function startPets(e) {
    e.stopPropagation();
    try {
      await api("/api/settings", { body: { pet_enabled: 1 } });
      await api("/api/jobs", { body: { kind: pets.installed ? "pets" : "pet_model", model: pets.model || "standard" } });
      toast(pets.installed ? "開始辨識寵物" : "開始下載寵物辨識模型，完成後會自動辨識");
      refresh();
    } catch (err) {
      toast(err.message, "error");
    }
  }
</script>

{#if s}
  <div class="cards" role="list" aria-label="狀態">
    <div class="st m3-state" class:warn={!ai?.ready} role="link" tabindex="0" onclick={() => go("/settings/ai")} onkeydown={(e) => key(e, "/settings/ai")}>
      <span class="ic"><Icon path={ai?.ready ? mdiCreation : mdiAlertOutline} size={20} /></span>
      <div class="txt">
        <b>{ai?.ready ? (aiJob ? "AI 分析中" : "AI 已就緒") : "AI 還不能用"}</b>
        <span>{ai?.ready ? (aiJob?.total ? `${count(aiJob.done)} / ${count(aiJob.total)}${eta(aiJob.eta) ? ` · 剩 ${eta(aiJob.eta)}` : ` · ${ai.model}`}` : `已分析 ${count(st.analyzed || 0)} 張 · 待分析 ${count(st.pending || 0)}`) : ai?.message || ""}</span>
      </div>
      {#if ai?.ready && aiPct !== null}
        <div class="bar" class:live={!!aiJob} role="progressbar" aria-valuenow={aiPct} aria-valuemin="0" aria-valuemax="100" aria-label="AI 分析進度"><span style:width="{aiPct}%"></span></div>
        <span class="pct">{aiPct}%</span>
      {/if}
    </div>

    <div class="st m3-state" class:warn={pets && !pets.installed} role="link" tabindex="0" onclick={() => go("/settings/recog")} onkeydown={(e) => key(e, "/settings/recog")}>
      <span class="ic"><Icon path={mdiFaceRecognition} size={20} /></span>
      <div class="txt">
        <b>{count(st.people || 0)} 位人物{pets?.pets?.length ? ` · ${count(pets.pets.length)} 隻寵物` : ""}</b>
        <span>{recogJob ? `${recogJob.label}${eta(recogJob.eta) ? `（剩 ${eta(recogJob.eta)}）` : ""}：${recogJob.message || ""}` : pets && !pets.installed ? "寵物辨識模型還沒下載（約 124 MB）" : st.faces_pending ? `${count(st.faces_pending)} 張還沒找人臉` : "人臉與寵物都已整理"}</span>
      </div>
      {#if facePct !== null}
        <div class="bar" class:live={!!recogJob} role="progressbar" aria-valuenow={facePct} aria-valuemin="0" aria-valuemax="100" aria-label="辨識進度"><span style:width="{facePct}%"></span></div>
        <span class="pct">{facePct}%</span>
      {/if}
      {#if pets && !pets.installed && !recogJob}<button class="btn text small act" onclick={startPets}>下載寵物模型</button>{/if}
    </div>

    <div class="st m3-state" role="link" tabindex="0" onclick={() => go("/settings/library")} onkeydown={(e) => key(e, "/settings/library")}>
      <span class="ic"><Icon path={mdiImageMultipleOutline} size={20} /></span>
      <div class="txt">
        <b>{count(st.photos || 0)} 張照片 · {count(st.videos || 0)} 部影片</b>
        <span>{scanJob ? `${eta(scanJob.eta) ? `剩 ${eta(scanJob.eta)} · ` : ""}${scanJob.message || "掃描中…"}` : `${count(st.roots || 0)} 個資料夾來源${st.missing ? ` · ${count(st.missing)} 個檔案遺失` : ""}`}</span>
      </div>
      {#if scanJob}
        <div class="bar live" class:indeterminate={!scanJob.total} role="progressbar" aria-label="掃描進度"><span style:width="{scanJob.total ? pct(scanJob.done, scanJob.total) : 40}%"></span></div>
        {#if scanJob.total}<span class="pct">{pct(scanJob.done, scanJob.total)}%</span>{/if}
      {/if}
    </div>

    {#if offline.length}
      <div class="st m3-state warn" role="link" tabindex="0" onclick={() => go("/settings/library")} onkeydown={(e) => key(e, "/settings/library")}>
        <span class="ic"><Icon path={mdiHarddisk} size={20} /></span>
        <div class="txt">
          <b>{offline.length} 個資料夾未連接</b>
          <span>{offline.map((r) => r.name).join("、")}：接上硬碟後按重新掃描</span>
        </div>
      </div>
    {/if}
  </div>
{/if}

<style>
  .cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 8px; margin-bottom: 16px; }
  .st {
    position: relative; display: grid; grid-template-columns: 36px minmax(0, 1fr) auto; column-gap: 12px; row-gap: 8px; align-items: center;
    padding: 12px 14px; border-radius: var(--corner-large); background: var(--surface-container-low); min-width: 0; cursor: pointer; overflow: hidden;
    transition: border-radius var(--spring-expressive-fast-spatial-duration) var(--spring-expressive-fast-spatial);
  }
  .st:hover { border-radius: var(--corner-extra-large); }
  .st:active { transform: scale(.985); }
  .st:focus-visible { outline: 2px solid var(--primary); outline-offset: 2px; }
  .st.warn { background: var(--secondary-container); color: var(--on-secondary-container); }
  .ic { width: 36px; height: 36px; border-radius: 50%; display: flex; align-items: center; justify-content: center; flex-shrink: 0;
    background: var(--surface-container-highest); color: var(--on-surface-variant); }
  .st.warn .ic { background: color-mix(in srgb, var(--on-secondary-container) 12%, transparent); color: inherit; }
  .txt { grid-column: 2 / 4; min-width: 0; display: flex; flex-direction: column; }
  /* 窄的時候換行（最多兩行），不要把數字截掉 */
  .txt b, .txt span { overflow: hidden; display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; word-break: keep-all; overflow-wrap: anywhere; }
  .txt b { font-weight: 500; font-size: 16px; line-height: 20px; }
  .txt span { font-size: 12px; line-height: 16px; color: var(--on-surface-variant); }
  .st.warn .txt span { color: inherit; opacity: .85; }
  /* M3 線性進度條 */
  .bar { grid-column: 1 / 3; height: 4px; border-radius: 2px; background: var(--surface-container-highest); overflow: hidden; position: relative; }
  .bar span { display: block; height: 100%; border-radius: 2px; background: var(--primary); transition: width .6s cubic-bezier(.2, 0, 0, 1); }
  .bar.indeterminate span { position: absolute; animation: indet 1.4s cubic-bezier(.4, 0, .2, 1) infinite; }
  @keyframes indet { from { left: -40%; } to { left: 100%; } }
  .pct { font-size: 12px; color: var(--on-surface-variant); font-variant-numeric: tabular-nums; justify-self: end; }
  .act { grid-column: 2 / 4; justify-self: start; margin-left: -12px; color: inherit; font-weight: 500; }
  @media (prefers-reduced-motion: reduce) { .bar span { transition: none; } .bar.indeterminate span { animation: none; left: 0; } }
</style>
