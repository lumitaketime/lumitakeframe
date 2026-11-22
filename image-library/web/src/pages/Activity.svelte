<script>
  /**
   * 掃描進度：每個工作一列（階段、進度條、已處理與總數、預估剩餘時間），可以停止；
   * 硬碟被拔掉顯示「已中斷，接上後可繼續」，不當成錯誤。紀錄存在資料庫裡，關掉 App 再開仍然在。
   */
  import { Button, Icon, ProgressIndicator } from "../ui/index.js";
  import { loadActivity, stopJob, resumeJob, pauseJob } from "../data/activity.js";
  import { setFrame } from "../shell/frame.svelte.js";
  import { t, formatNumber, formatBytes, formatDuration, formatDateTime } from "../i18n/index.svelte.js";
  import { app, toast, refresh } from "../lib/state.svelte.js";

  let data = $state(null);
  let error = $state("");
  let busy = $state(0);

  async function load() {
    try {
      data = await loadActivity();
      error = "";
    } catch (e) {
      error = e.message;
    }
  }
  // 有工作在跑時每 2 秒更新一次；沒有時跟著伺服器狀態更新
  $effect(() => {
    app.server?.jobs;
    app.refreshKey;
    load();
  });
  $effect(() => {
    if (!data?.active.length) return;
    const timer = setInterval(load, 2000);
    return () => clearInterval(timer);
  });
  $effect(() => {
    setFrame({ crumbs: [], location: null, info: null, status: data?.active.length ? t("activity.running", { count: formatNumber(data.active.length + data.queued.length) }) : "" });
  });
  async function act(id, fn) {
    busy = id;
    try {
      await fn();
      refresh();
      await load();
    } catch (e) {
      toast(e.message, "error");
    } finally {
      busy = 0;
    }
  }
  const STAGE = { scan: "activity.stage.scan", index: "activity.stage.scan", compare: "activity.stage.compare", analyze: "activity.stage.analyze" };
  const stageOnly = (kind, label) => (STAGE[kind] ? t(STAGE[kind]) : label);
  // 好幾顆硬碟同時掃：每列寫上是哪一顆
  const stage = (kind, label, target) => (target ? t("activity.onDrive", { stage: stageOnly(kind, label), drive: target }) : stageOnly(kind, label));
  const PAUSABLE = new Set(["scan", "index", "compare", "extract", "ocr", "embed_docs", "photos"]);
  const amount = (j) => (!j.total ? ((j.kind === "scan" || j.kind === "index") ? t("activity.firstScan") : "")
    : j.unit === "folders" ? t("activity.folders", { done: formatNumber(j.done), total: formatNumber(j.total) })
    : j.unit === "bytes" || j.kind === "compare"
    ? t("activity.amount", { done: formatBytes(j.done) || "0 KB", total: formatBytes(j.total) })
    : t("activity.amount", { done: formatNumber(j.done), total: formatNumber(j.total) }));
  const STATE_ICON = { done: "checkmark", stopped: "minus", interrupted: "exclamation-triangle", error: "exclamation-triangle", replaced: "minus", paused: "pause" };
  const idle = $derived(!data?.active.length && !data?.queued.length && !data?.paused?.length);
</script>

<div class="activity">
  {#if error}
    <div class="state" role="alert"><h2 class="mac-title-3">{t("view.error")}</h2><p class="mac-body">{error}</p><Button onclick={load}>{t("view.retry")}</Button></div>
  {:else if !data}
    <div class="state"><ProgressIndicator kind="spinner" label={t("view.loading")} /></div>
  {:else}
    <h2 class="mac-headline section">{t("activity.now")}</h2>
    {#if idle}
      <p class="mac-body sub idle">{t("activity.idle")}</p>
    {:else}
      <ul class="jobs" aria-live="polite">
        {#each data.active as j (j.id)}
          <li class="job">
            <div class="head">
              <ProgressIndicator kind="circular" size="small" value={j.total ? j.done / j.total : undefined} label={stage(j.kind, j.label, j.target)} />
              <div class="titles">
                <b class="mac-body">{stage(j.kind, j.label, j.target)}</b>
                <p class="mac-callout sub">{[amount(j), j.eta ? t("activity.eta", { time: formatDuration(j.eta) }) : ""].filter(Boolean).join(" · ") || t("activity.working")}</p>
              </div>
              {#if PAUSABLE.has(j.kind)}<Button variant="bordered" disabled={!!busy} onclick={() => act(j.id, () => pauseJob(j.id))}>{t("activity.pause")}</Button>{/if}
              <Button variant="bordered" loading={busy === j.id} disabled={!!busy} onclick={() => act(j.id, () => stopJob(j.id))}>{t("drives.stop")}</Button>
            </div>
            {#if j.total}<ProgressIndicator value={j.done / j.total} label={stage(j.kind, j.label, j.target)} />{/if}
            {#if j.message}<p class="mac-callout sub msg" title={j.message}>{j.message}</p>{/if}
          </li>
        {/each}
        {#each data.queued as j (j.id)}
          <li class="job">
            <div class="head">
              <Icon name="clock" size={16} weight="medium" class="wait" />
              <div class="titles"><b class="mac-body">{stage(j.kind, j.label, j.target)}</b><p class="mac-callout sub">{j.kind === "scan" ? t("activity.queuedScan", { n: data.scan_parallel }) : t("activity.queued")}</p></div>
              <Button variant="borderless" disabled={!!busy} onclick={() => act(j.id, () => stopJob(j.id))}>{t("common.cancel")}</Button>
            </div>
          </li>
        {/each}
        <!-- 暫停中：停在原來的位置，按「繼續」從這裡接著做（關掉 App 再開也一樣） -->
        {#each data.paused || [] as h (h.id)}
          <li class="job">
            <div class="head">
              <Icon name="pause" size={16} weight="medium" class="wait" />
              <div class="titles"><b class="mac-body">{stage(h.kind, h.label, h.target)} <span class="tag mac-callout">{t("activity.state.paused")}</span></b>
                <p class="mac-callout sub">{t("activity.pausedHint")}</p></div>
              <Button variant="borderedProminent" loading={busy === -h.id} disabled={!!busy} onclick={() => act(-h.id, () => resumeJob(h.id))}>{t("activity.resume")}</Button>
            </div>
          </li>
        {/each}
      </ul>
      <p class="mac-callout sub hint">{t("activity.stopHint")}</p>
    {/if}

    <h2 class="mac-headline section">{t("activity.history")}</h2>
    {#if !data.history.length}
      <p class="mac-body sub idle">{t("activity.noHistory")}</p>
    {:else}
      <ul class="jobs">
        {#each data.history as h (h.id)}
          <li class="job past">
            <div class="head">
              <Icon name={STATE_ICON[h.state] || "clock"} size={15} weight="bold" class="st-{h.state}" />
              <div class="titles">
                <b class="mac-body">{stage(h.kind, h.label, h.target)} <span class="tag mac-callout" class:warn={h.state === "error"}>{t(`activity.state.${h.state}`)}</span></b>
                <p class="mac-callout sub">{h.finished_at ? formatDateTime(new Date(h.finished_at)) : ""}</p>
              </div>
              {#if h.resumable}<Button variant="bordered" loading={busy === -h.id} disabled={!!busy} onclick={() => act(-h.id, () => resumeJob(h.id))}>{t("activity.resume")}</Button>{/if}
            </div>
            {#if h.message}<p class="mac-callout sub msg wrap">{h.message}</p>{/if}
          </li>
        {/each}
      </ul>
    {/if}
  {/if}
</div>

<style>
  .activity { padding: var(--space-4) var(--space-6) var(--space-8); max-width: 900px; color: var(--label-primary); }
  h2, p { margin: 0; }
  .section { margin: var(--space-5) 0 var(--space-3); color: var(--label-secondary); }
  .section:first-child { margin-top: 0; }
  .sub { color: var(--label-secondary); }
  .idle { padding: var(--space-3) 0; }
  .hint { margin-top: var(--space-2); }
  .jobs { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: var(--space-2); }
  .job { display: flex; flex-direction: column; gap: var(--space-2); padding: var(--space-3) var(--space-4); border-radius: var(--radius-md); background: var(--fill-quaternary);
    box-shadow: inset 0 0 0 1px var(--separator); }
  .head { display: flex; align-items: center; gap: var(--space-3); }
  .titles { flex: 1; min-width: 0; }
  .msg { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .msg.wrap { white-space: normal; overflow-wrap: anywhere; }
  .tag { margin-left: var(--space-2); padding: 0 var(--space-2); border-radius: var(--radius-capsule); box-shadow: inset 0 0 0 1px var(--separator); color: var(--label-secondary); font-weight: 400; }
  .tag.warn { color: var(--destructive); }
  .job :global(.wait), .job :global(.st-stopped), .job :global(.st-interrupted) { color: var(--label-secondary); flex: none; }
  .job :global(.st-done) { color: var(--accent); flex: none; }
  .job :global(.st-error) { color: var(--destructive); flex: none; }
  .state { display: flex; flex-direction: column; align-items: center; gap: var(--space-3); padding: var(--space-10) var(--space-6); text-align: center; color: var(--label-secondary); }
  .state h2 { color: var(--label-primary); }
</style>
