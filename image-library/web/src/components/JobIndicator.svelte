<script>
  import Icon from "./Icon.svelte";
  import { app, refresh, toast } from "../lib/state.svelte.js";
  import { navigate } from "../lib/router.svelte.js";
  import { api } from "../lib/api.js";
  import { mdiCreation, mdiAlertCircleOutline } from "../lib/icons.js";

  const jobs = $derived(app.server?.jobs);
  const cur = $derived(jobs?.current);
  const pct = $derived(cur?.total ? Math.round((cur.done / cur.total) * 100) : null);
  const ai = $derived(app.server?.ai);

  async function start() {
    try {
      await api("/api/jobs", { body: { kind: "analyze" } });
      toast("開始 AI 分析，可以在設定頁隨時停止");
      refresh();
    } catch (e) {
      toast(e.message, "error");
    }
  }
</script>

{#if cur}
  <button class="job" onclick={() => navigate("/settings#jobs")} title={cur.message}>
    <span class="spinner"></span>
    <span class="txt"><b>{cur.label}</b>{pct !== null ? ` ${pct}%` : ""}{jobs.queued.length ? `（另有 ${jobs.queued.length} 項）` : ""}</span>
    {#if pct !== null}<span class="bar" style:width="{pct}%"></span>{/if}
  </button>
{:else if app.server && app.server.stats.pending > 0 && ai && !ai.ready}
  <button class="job warn" onclick={() => navigate("/settings#jobs")} title={ai.message}>
    <Icon path={mdiAlertCircleOutline} size={18} /><span class="txt">AI 未就緒 · {app.server.stats.pending} 待分析</span>
  </button>
{:else if app.server && app.server.stats.pending > 0}
  <button class="job idle" onclick={start} title="按一下開始用 {ai?.model || 'AI'} 分析">
    <Icon path={mdiCreation} size={18} /><span class="txt">開始分析 {app.server.stats.pending} 張</span>
  </button>
{/if}

<style>
  .job {
    position: relative; overflow: hidden; display: flex; align-items: center; gap: 8px; border: 0; cursor: pointer;
    background: var(--primary-soft); color: var(--primary); border-radius: 999px; padding: 6px 14px; font-size: 13px;
    max-width: 260px;
  }
  .job.idle { background: var(--bg-2); color: var(--muted); }
  .job.idle:hover { color: var(--primary); }
  .job.warn { background: var(--bg-2); color: var(--danger); }
  .txt { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .bar { position: absolute; left: 0; bottom: 0; height: 3px; background: var(--primary); transition: width .4s; }
  @media (max-width: 760px) { .txt { display: none; } .job { padding: 8px; } }
</style>
