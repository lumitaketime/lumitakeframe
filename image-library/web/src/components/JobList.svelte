<script>
  import { eta } from "../lib/format.js";
  /** 進行中與排隊中的背景工作，每項都有進度條與停止按鈕。 */
  import Icon from "./Icon.svelte";
  import { api } from "../lib/api.js";
  import { app, refresh } from "../lib/state.svelte.js";
  import { mdiStop, mdiClose } from "../lib/icons.js";

  let { kinds = null, compact = false } = $props();

  const jobs = $derived(app.server?.jobs);
  const match = (j) => !kinds || kinds.includes(j.kind);
  const active = $derived((jobs?.active || []).filter(match));
  const queued = $derived((jobs?.queued || []).filter(match));
  const LANE = { ai: "AI", main: "整理", download: "下載" };

  async function stop(id) {
    await api("/api/jobs/stop", { body: { id } }).catch(() => {});
    refresh();
  }
  const pct = (j) => (j.total ? Math.min(100, Math.round((j.done / j.total) * 100)) : null);
</script>

{#if active.length || queued.length}
  <div class="jobs" class:compact>
    {#each active as j (j.id)}
      {@const p = pct(j)}
      <div class="job" class:paused={j.paused}>
        <span class="lane">{LANE[j.lane] || ""}</span>
        <div class="grow">
          <div class="head"><b>{j.label}{j.model ? `：${j.model}` : ""}</b>{#if p !== null}<span class="pct">{p}%{#if eta(j.eta)} · 剩 {eta(j.eta)}{/if}</span>{/if}</div>
          <div class="bar" class:indeterminate={p === null}><span style:width="{p ?? 30}%"></span></div>
          <div class="msg tiny muted">{j.message}</div>
        </div>
        <button class="icon-btn" title="停止" aria-label="停止 {j.label}" onclick={() => stop(j.id)}><Icon path={mdiStop} size={20} /></button>
      </div>
    {/each}
    {#each queued as j (j.id)}
      <div class="job queued">
        <span class="lane">{LANE[j.lane] || ""}</span>
        <div class="grow"><b>{j.label}</b><div class="msg tiny muted">排隊中</div></div>
        <button class="icon-btn" title="取消" aria-label="取消 {j.label}" onclick={() => stop(j.id)}><Icon path={mdiClose} size={20} /></button>
      </div>
    {/each}
  </div>
{/if}

<style>
  .jobs { display: flex; flex-direction: column; gap: 8px; margin: 10px 0; }
  .job { display: flex; gap: 10px; align-items: center; background: var(--surface); border-radius: var(--corner-medium); padding: 10px 12px; }
  .compact .job { padding: 8px 10px; }
  .job.queued { opacity: .7; }
  .grow { flex: 1; min-width: 0; }
  .head { display: flex; justify-content: space-between; gap: 8px; font-size: 14px; }
  .head b { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .pct { font-variant-numeric: tabular-nums; color: var(--primary); font-weight: 500; font-size: 13px; }
  .lane { font-size: 11px; color: var(--primary); background: var(--secondary-container); border-radius: var(--corner-full); padding: 2px 8px; flex-shrink: 0; }
  .bar { height: 6px; border-radius: 3px; background: var(--outline-variant); overflow: hidden; margin: 6px 0 4px; }
  .bar span { display: block; height: 100%; background: var(--primary); transition: width .4s; border-radius: 3px; }
  .paused .bar span { background: var(--on-surface-variant); }
  .bar.indeterminate span { animation: slide 1.4s ease-in-out infinite; }
  @keyframes slide { 0% { transform: translateX(-100%); } 100% { transform: translateX(340%); } }
  @media (prefers-reduced-motion: reduce) { .bar.indeterminate span { animation: none; } }
  .msg { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
</style>
