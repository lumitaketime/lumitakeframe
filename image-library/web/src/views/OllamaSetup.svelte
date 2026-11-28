<script>
  /**
   * Ollama 的狀態與「一鍵」處理，放在 AI 相關設定的最上面：
   * - 還沒安裝：「下載並安裝 Ollama」（先跳確認，說明會從 Ollama 官網下載；只在 Mac 上、在這台電腦打開時）
   * - 安裝中：進度
   * - 裝了但沒開：「打開 Ollama」（終端機／Homebrew 裝的也認得，會在背景啟動）
   * - 執行中：版本，旁邊有「更新 Ollama」（新模型需要新版時用）
   * 用 List 包起來；header／footer 由外面決定要不要顯示。
   */
  import { Alert, Button, List, ListRow, ProgressIndicator } from "../ui/index.js";
  import { loadOllamaStatus, installOllama, startOllama } from "../data/ollama.js";
  import { t } from "../i18n/index.svelte.js";
  import { app, toast, refresh } from "../lib/state.svelte.js";

  let { header = "", footer = "", showRunning = true, onready = () => {} } = $props();

  let st = $state(null);
  let confirm = $state(""); // "install" | "update"
  let opening = $state(false);
  let failed = $state("");

  async function load() {
    try {
      const was = st?.running;
      st = await loadOllamaStatus();
      if (st.running && !was) onready();
    } catch {
      /* 稍後再試 */
    }
  }
  $effect(() => {
    app.refreshKey;
    load();
  });
  // 還沒在執行時每 4 秒看一次（使用者可能自己去打開了）
  $effect(() => {
    if (st?.running) return;
    const timer = setInterval(load, 4000);
    return () => clearInterval(timer);
  });

  const job = $derived((app.server?.jobs?.active || []).find((j) => j.kind === "ollama_install") || null);
  const local = $derived(app.server?.local !== false);
  const canInstall = $derived(!!st?.can_install && local);
  // 安裝工作結束：重新檢查；失敗的話把原因留在畫面上
  let wasRunning = false;
  $effect(() => {
    const now = !!job;
    if (wasRunning && !now) {
      const last = app.server?.jobs?.last;
      failed = last?.kind === "ollama_install" && last.error ? last.error : "";
      if (!failed) toast(last?.message || t("oll.done"));
      load();
      refresh();
    }
    wasRunning = now;
  });

  async function install() {
    confirm = "";
    failed = "";
    try {
      await installOllama();
      refresh();
    } catch (e) {
      toast(e.message, "error");
    }
  }
  async function open() {
    opening = true;
    try {
      await startOllama();
      toast(t("oll.opening"));
      setTimeout(load, 2500);
    } catch (e) {
      toast(e.message, "error");
    } finally {
      setTimeout(() => (opening = false), 3000);
    }
  }
  const pct = $derived(job?.total ? job.done / job.total : undefined);
  const version = $derived(st?.running_version || st?.version || "");
</script>

{#if st && (showRunning || !st.running || job || failed)}
  <List {header} {footer}>
    {#if job}
      <ListRow title={t("oll.installing")} subtitle={job.message} icon="arrow-down" iconTint="blue" />
      <div class="pad"><ProgressIndicator value={pct} label={t("oll.installing")} /></div>
    {:else if st.running}
      <ListRow title={t("oll.running")} subtitle={version ? t("oll.version", { v: version }) : ""} icon="checkmark" iconTint="green">
        {#snippet trailing()}
          {#if canInstall && st.app}<Button size="small" variant="bordered" onclick={() => (confirm = "update")}>{t("oll.update")}</Button>{/if}
        {/snippet}
      </ListRow>
      {#if st.brew}<ListRow title={t("oll.brewTitle")} subtitle={t("oll.brewHint")} />{/if}
    {:else if st.installed}
      <ListRow title={t("ai.setup.ollamaOff")} subtitle={st.app ? t("oll.offHint") : t("oll.offHintCli")} icon="exclamation-triangle" iconTint="orange">
        {#snippet trailing()}<Button size="small" variant="borderedProminent" loading={opening} onclick={open}>{t("ai.setup.openOllama")}</Button>{/snippet}
      </ListRow>
    {:else}
      <ListRow title={t("ai.setup.noOllama")} subtitle={canInstall ? t("oll.installHint") : t("oll.manualHint")} icon="exclamation-triangle" iconTint="orange">
        {#snippet trailing()}
          {#if canInstall}<Button size="small" variant="borderedProminent" icon="arrow-down" onclick={() => (confirm = "install")}>{t("oll.install")}</Button>
          {:else}<a class="link mac-callout" href="https://ollama.com/download" target="_blank" rel="noopener">{t("oll.downloadPage")}</a>{/if}
        {/snippet}
      </ListRow>
    {/if}
    {#if failed}
      <p class="err mac-callout" role="alert">{failed}</p>
    {/if}
  </List>
{/if}

{#if confirm}
  <Alert title={t(confirm === "update" ? "oll.confirmUpdate" : "oll.confirmInstall")}
    message={t(confirm === "update" ? "oll.confirmUpdateMessage" : "oll.confirmInstallMessage")} actions={[
      { label: t(confirm === "update" ? "oll.updateShort" : "oll.installShort"), role: "default", onPress: install },
      { label: t("common.cancel"), role: "cancel", onPress: () => (confirm = "") },
    ]} />
{/if}

<style>
  .pad { padding: 0 var(--space-4) var(--space-3); }
  .err { margin: 0; padding: var(--space-2) var(--space-4) var(--space-3); color: var(--destructive); white-space: pre-line; }
  .link { color: var(--accent); text-decoration: none; white-space: nowrap; }
  .link:hover { text-decoration: underline; }
</style>
