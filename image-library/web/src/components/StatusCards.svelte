<script>
  /**
   * 設定頁最上面的狀態卡：AI、辨識、儲存空間，以及未連接的資料夾。
   * 有問題的卡片換成提醒底色，附一鍵修正或前往設定。
   */
  import Icon from "./Icon.svelte";
  import { api } from "../lib/api.js";
  import { app, refresh, toast } from "../lib/state.svelte.js";
  import { navigate } from "../lib/router.svelte.js";
  import { bytes, count } from "../lib/format.js";
  import { mdiCreation, mdiFaceRecognition, mdiDatabaseOutline, mdiHarddisk, mdiAlertOutline } from "../lib/icons.js";

  let storage = $state(null);
  let pets = $state(null);
  let cleaning = $state(false);

  $effect(() => {
    app.refreshKey;
    api("/api/storage").then((d) => (storage = d)).catch(() => {});
    api("/api/pets").then((d) => (pets = d)).catch(() => {});
  });

  const s = $derived(app.server);
  const ai = $derived(s?.ai);
  const total = $derived(storage ? storage.database.bytes + storage.thumbs.bytes + storage.face_thumbs.bytes
    + storage.models.reduce((n, m) => n + (m.bytes || 0), 0) : 0);
  const reclaim = $derived(storage?.orphans?.bytes || 0);
  const offline = $derived((s?.roots || []).filter((r) => !r.online));
  const aiBusy = $derived((s?.jobs?.active || []).some((j) => j.kind === "analyze"));

  async function startPets() {
    try {
      await api("/api/settings", { body: { pet_enabled: 1 } });
      await api("/api/jobs", { body: { kind: pets.installed ? "pets" : "pet_model", model: pets.model || "standard" } });
      toast(pets.installed ? "開始辨識寵物" : "開始下載寵物辨識模型，完成後會自動辨識");
      refresh();
    } catch (e) {
      toast(e.message, "error");
    }
  }

  async function clean() {
    cleaning = true;
    try {
      const res = await api("/api/storage/clean", { body: {} });
      toast(`已清理 ${count(res.files)} 個檔案，釋放約 ${bytes(res.freed)}`);
      refresh();
    } catch (e) {
      toast(e.message, "error");
    } finally {
      cleaning = false;
    }
  }
</script>

{#if s}
  <div class="cards" role="list" aria-label="狀態">
    <div class="st" class:warn={!ai?.ready} role="listitem">
      <span class="ic"><Icon path={ai?.ready ? mdiCreation : mdiAlertOutline} size={20} /></span>
      <div class="txt">
        <b>{ai?.ready ? (aiBusy ? "AI 分析中" : "AI 已就緒") : "AI 還不能用"}</b>
        <span>{ai?.ready ? `${ai.model} · 待分析 ${count(s.stats.pending)} 張` : ai?.message || ""}</span>
      </div>
      {#if !ai?.ready}<button class="btn text small" onclick={() => navigate("/settings/ai")}>設定 AI</button>{/if}
    </div>

    <div class="st" class:warn={pets && !pets.installed} role="listitem">
      <span class="ic"><Icon path={mdiFaceRecognition} size={20} /></span>
      <div class="txt">
        <b>{count(s.stats.people || 0)} 位人物{pets?.pets?.length ? ` · ${count(pets.pets.length)} 隻寵物` : ""}</b>
        <span>{pets && !pets.installed ? "寵物辨識模型還沒下載（約 124 MB）" : s.stats.faces_pending ? `${count(s.stats.faces_pending)} 張還沒找人臉` : "人臉與寵物都已整理"}</span>
      </div>
      {#if pets && !pets.installed}<button class="btn text small" onclick={startPets}>下載並開始</button>{/if}
    </div>

    <div class="st" role="listitem">
      <span class="ic"><Icon path={mdiDatabaseOutline} size={20} /></span>
      <div class="txt">
        <b>{storage ? bytes(total) || "0 KB" : "…"}</b>
        <span>{reclaim >= 1048576 ? `可以清理 ${bytes(reclaim)}` : "快取不需要清理"}</span>
      </div>
      {#if reclaim >= 1048576}<button class="btn text small" onclick={clean} disabled={cleaning}>{cleaning ? "清理中…" : "清理"}</button>{/if}
    </div>

    {#if offline.length}
      <div class="st warn" role="listitem">
        <span class="ic"><Icon path={mdiHarddisk} size={20} /></span>
        <div class="txt">
          <b>{offline.length} 個資料夾未連接</b>
          <span>{offline.map((r) => r.name).join("、")}：接上硬碟後按重新掃描</span>
        </div>
        <button class="btn text small" onclick={() => navigate("/settings/library")}>查看</button>
      </div>
    {/if}
  </div>
{/if}

<style>
  .cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 8px; margin-bottom: 16px; }
  .st {
    display: grid; grid-template-columns: 36px minmax(0, 1fr); column-gap: 12px; row-gap: 2px; align-items: center;
    padding: 12px 14px; border-radius: var(--corner-large); background: var(--surface-container-low); min-width: 0;
  }
  .st.warn { background: var(--secondary-container); color: var(--on-secondary-container); }
  .ic { width: 36px; height: 36px; border-radius: 50%; display: flex; align-items: center; justify-content: center; flex-shrink: 0;
    background: var(--surface-container-highest); color: var(--on-surface-variant); }
  .st.warn .ic { background: color-mix(in srgb, var(--on-secondary-container) 12%, transparent); color: inherit; }
  .txt { flex: 1; min-width: 0; display: flex; flex-direction: column; }
  .txt b { font-weight: 500; font-size: 15px; line-height: 20px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .txt span { font-size: 12px; line-height: 16px; color: var(--on-surface-variant); overflow: hidden; text-overflow: ellipsis; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; }
  .st.warn .txt span { color: inherit; opacity: .85; }
  .btn.text { grid-column: 2; justify-self: start; margin-left: -12px; color: inherit; font-weight: 500; }
  .st:not(.warn) .btn.text { color: var(--primary); }
</style>
