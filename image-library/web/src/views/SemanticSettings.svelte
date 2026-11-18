<script>
  /**
   * 設定 → 文字與搜尋 → 用意思找文件（跨語言、同義詞）。
   * 打開後在這台電腦上用向量模型（預設 bge-m3）替文件建立索引；模型沒下載的話，先問本人要不要下載（唯一會連網的時候）。
   * 關掉只是不再用意思找，已建立的索引留著（再打開不用重做）。
   */
  import { Alert, Button, List, ListRow, Toggle } from "../ui/index.js";
  import { api } from "../lib/api.js";
  import { t, formatNumber } from "../i18n/index.svelte.js";
  import { app, toast, refresh } from "../lib/state.svelte.js";

  let { settings, set } = $props();

  let st = $state(null);
  $effect(() => {
    app.refreshKey;
    api("/api/semantic/status", { quiet: true }).then((d) => (st = d)).catch(() => {});
  });
  const jobs = $derived(app.server?.jobs?.active || []);
  const job = $derived(jobs.find((j) => j.kind === "embed_docs") || null);
  const pull = $derived(st ? jobs.find((j) => j.kind === "pull" && j.model?.startsWith(st.model)) || null : null);
  const on = $derived(!!settings?.doc_semantic);
  let confirmPull = $state(false);

  async function startJob() {
    try {
      await api("/api/jobs", { body: { kind: "embed_docs" } });
      refresh();
    } catch (e) {
      toast(e.message, "error");
    }
  }
  async function toggle(v) {
    await set("doc_semantic", v ? 1 : 0);
    if (!v || !st) return;
    if (!st.model_ready) confirmPull = true;
    else if (st.todo && !job) startJob();
  }
  async function download() {
    confirmPull = false;
    try {
      await api("/api/jobs", { body: { kind: "pull", model: st.model } });
      toast(t("ai.downloading", { model: st.model }));
      refresh();
    } catch (e) {
      toast(e.message, "error");
    }
  }
  const pct = (j) => (j?.total ? `${Math.round((j.done / j.total) * 100)}%` : "");
</script>

{#if settings}
  <List header={t("set.sem.title")} footer={t("set.sem.footer")}>
    <ListRow title={t("set.sem.toggle")} subtitle={t("set.sem.hint")}>
      {#snippet trailing()}<Toggle checked={on} onchange={toggle} aria-label={t("set.sem.toggle")} />{/snippet}
    </ListRow>
    {#if on && st}
      {#if !st.ollama}
        <ListRow title={t("ai.setup.ollamaOff")} subtitle={t("set.sem.ollamaHint")} />
      {:else if pull}
        <ListRow title={t("ai.setup.downloading", { model: st.model })} detail={pct(pull)} />
      {:else if !st.model_ready}
        <ListRow title={t("set.sem.noModel", { model: st.model })}>
          {#snippet trailing()}<Button size="small" variant="borderedProminent" icon="arrow-down" onclick={() => (confirmPull = true)}>{t("ai.setup.download")}</Button>{/snippet}
        </ListRow>
      {:else if job}
        <ListRow title={t("set.sem.building")} subtitle={job.message || ""} detail={job.total ? `${formatNumber(job.done)} / ${formatNumber(job.total)}` : ""} />
      {:else}
        <ListRow title={t("set.sem.progress", { done: formatNumber(st.done), todo: formatNumber(st.todo) })} subtitle={t("set.sem.model", { model: st.model })}>
          {#snippet trailing()}{#if st.todo}<Button size="small" variant="bordered" onclick={startJob}>{t("set.sem.build")}</Button>{/if}{/snippet}
        </ListRow>
      {/if}
    {/if}
  </List>
{/if}

{#if confirmPull && st}
  <div class="backdrop">
    <Alert title={t("ai.setup.confirmTitle", { model: st.model })} message={t("set.sem.pullMessage", { size: st.size_gb ? `${st.size_gb} GB` : "" })} actions={[
      { label: t("ai.setup.download"), role: "default", onPress: download },
      { label: t("common.cancel"), role: "cancel", onPress: () => (confirmPull = false) },
    ]} />
  </div>
{/if}

<style>
  .backdrop { position: fixed; inset: 0; z-index: 320; display: flex; align-items: center; justify-content: center; background: var(--media-scrim-light); }
</style>
