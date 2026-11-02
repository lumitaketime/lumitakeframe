<script>
  import Icon from "./Icon.svelte";
  import { app } from "../lib/state.svelte.js";
  import { navigate } from "../lib/router.svelte.js";
  import { mdiCreation } from "../lib/icons.js";

  const jobs = $derived(app.server?.jobs);
  const cur = $derived(jobs?.current);
  const pct = $derived(cur?.total ? Math.round((cur.done / cur.total) * 100) : null);
</script>

{#if cur}
  <button class="job" onclick={() => navigate("/settings#jobs")} title={cur.message}>
    <span class="spinner"></span>
    <span class="txt"><b>{cur.label}</b>{pct !== null ? ` ${pct}%` : ""}{jobs.queued.length ? `（另有 ${jobs.queued.length} 項）` : ""}</span>
    {#if pct !== null}<span class="bar" style:width="{pct}%"></span>{/if}
  </button>
{:else if app.server && app.server.stats.pending > 0}
  <button class="job idle" onclick={() => navigate("/settings#jobs")} title="尚未 AI 分析的項目">
    <Icon path={mdiCreation} size={18} /><span class="txt">{app.server.stats.pending} 待分析</span>
  </button>
{/if}

<style>
  .job {
    position: relative; overflow: hidden; display: flex; align-items: center; gap: 8px; border: 0; cursor: pointer;
    background: var(--primary-soft); color: var(--primary); border-radius: 999px; padding: 6px 14px; font-size: 13px;
    max-width: 260px;
  }
  .job.idle { background: var(--bg-2); color: var(--muted); }
  .txt { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .bar { position: absolute; left: 0; bottom: 0; height: 3px; background: var(--primary); transition: width .4s; }
  @media (max-width: 760px) { .txt { display: none; } .job { padding: 8px; } }
</style>
