<script>
  /**
   * 設定 → AI 助理：選擇助理用的模型。
   * 這台電腦（Ollama，預設）：從已下載的模型或推薦清單選一個，沒下載的可以按「下載」（會先確認）。
   * 其他服務（OpenAI 相容的 API）：本機的 LM Studio 等資料不會離開這台電腦；雲端服務會把問題、檔名與文件片段送出去，
   * 切換前一定先跳出確認（核心原則二：資料不出家門，例外要本人明確同意）。API 金鑰只存在這台電腦，介面不會再顯示。
   */
  import { Alert, Button, List, ListRow, PopUpButton, RadioGroup, TextField } from "../ui/index.js";
  import { loadModels, testAssistant, saveSettings } from "../data/settings.js";
  import { downloadModel } from "../data/assistant.js";
  import { t, formatBytes } from "../i18n/index.svelte.js";
  import { app, toast, refresh } from "../lib/state.svelte.js";

  let { settings, set } = $props();

  let models = $state(null);
  $effect(() => {
    app.refreshKey;
    loadModels().then((d) => (models = d)).catch(() => {});
  });
  const provider = $derived(settings?.assistant_provider === "openai" ? "openai" : "ollama");
  const installed = $derived((models?.installed || []).filter((m) => !/embed|nomic|bge|minilm/i.test(m.name)).map((m) => m.name));
  const recommended = $derived((models?.recommended || []).filter((m) => m.kind === "vision"));
  const current = $derived(settings?.assistant_model || "gemma4:e4b");
  const options = $derived.by(() => {
    const seen = new Set();
    const out = [];
    for (const m of recommended) {
      seen.add(m.name);
      out.push({ value: m.name, label: `${m.name} · ${m.size_gb} GB${m.installed ? ` · ${t("set.ai.installed")}` : ""}` });
    }
    for (const n of installed) if (!seen.has(n)) out.push({ value: n, label: `${n} · ${t("set.ai.installed")}` });
    if (!out.some((o) => o.value === current)) out.unshift({ value: current, label: current });
    return out;
  });
  const info = $derived(recommended.find((m) => m.name === current));
  const ready = $derived(installed.includes(current) || !!info?.installed);
  const pull = $derived(app.server?.jobs?.active?.find((j) => j.kind === "pull" && j.model === current) || null);
  let confirmPull = $state(false);
  async function pullModel() {
    confirmPull = false;
    try {
      await downloadModel(current);
      toast(t("ai.downloading", { model: current }));
      refresh();
    } catch (e) {
      toast(e.message, "error");
    }
  }

  // ---- OpenAI 相容的 API ----
  let url = $state("");
  let model = $state("");
  let key = $state("");
  $effect(() => {
    url = settings?.assistant_api_url || "";
    model = settings?.assistant_api_model || "";
  });
  const isLocal = (u) => /^https?:\/\/(127\.0\.0\.1|localhost|\[::1\])(:|\/|$)/i.test(u) || /^https?:\/\/[^/]+\.local(:|\/|$)/i.test(u);
  const host = (u) => { try { return new URL(u).host; } catch { return u; } };
  let confirmRemote = $state(null); // 要存的設定，等本人確認
  let testing = $state(false);
  let result = $state(null);
  function chooseProvider(v) {
    if (v === "openai" && settings?.assistant_api_url && !isLocal(settings.assistant_api_url)) {
      confirmRemote = { assistant_provider: "openai" };
      return;
    }
    apply({ assistant_provider: v });
  }
  function saveApi() {
    const values = { assistant_provider: "openai", assistant_api_url: url.trim(), assistant_api_model: model.trim() };
    if (key.trim()) values.assistant_api_key = key.trim();
    if (values.assistant_api_url && !isLocal(values.assistant_api_url)) {
      confirmRemote = values;
      return;
    }
    apply(values);
  }
  async function apply(values) {
    confirmRemote = null;
    try {
      Object.assign(settings, await saveSettings(values)); // 網址、模型、金鑰一起存
      key = "";
      result = null;
      toast(t("set.ai.saved"));
    } catch (e) {
      toast(e.message, "error");
    }
  }
  async function test() {
    testing = true;
    result = null;
    try {
      result = await testAssistant();
    } catch (e) {
      result = { ok: false, error: e.message };
    } finally {
      testing = false;
    }
  }
  const EXAMPLES = [
    { label: "LM Studio", url: "http://127.0.0.1:1234/v1", local: true },
    { label: "Ollama", url: "http://127.0.0.1:11434/v1", local: true },
    { label: "OpenAI", url: "https://api.openai.com/v1", local: false },
  ];
</script>

{#if settings}
  <List header={t("set.ai.where")} footer={provider === "ollama" ? t("set.ai.ollamaHint") : t("set.ai.apiHint")}>
    <div class="pad">
      <RadioGroup value={provider} onchange={chooseProvider} options={[
        { value: "ollama", label: t("set.ai.ollama") },
        { value: "openai", label: t("set.ai.api") },
      ]} />
    </div>
  </List>

  {#if provider === "ollama"}
    <List header={t("set.ai.model")} footer={info?.note || ""}>
      <ListRow title={t("set.ai.model")} subtitle={info ? t("set.ai.ram", { ram: info.min_ram }) : ""}>
        {#snippet trailing()}<PopUpButton value={current} onchange={(v) => set("assistant_model", v)} {options} menuWidth={320} />{/snippet}
      </ListRow>
      {#if models && !models.ollama_ok}
        <ListRow title={t("ai.setup.ollamaOff")} subtitle={t("ai.setup.ollamaHint")} />
      {:else if pull}
        <ListRow title={t("ai.setup.downloading", { model: current })} detail={pull.total ? `${Math.round((pull.done / pull.total) * 100)}%` : ""} />
      {:else if models && !ready}
        <ListRow title={t("ai.setup.noModel", { model: current })}>
          {#snippet trailing()}<Button size="small" variant="borderedProminent" icon="arrow-down" onclick={() => (confirmPull = true)}>{t("ai.setup.download")}</Button>{/snippet}
        </ListRow>
      {:else if models}
        <ListRow title={t("set.ai.ready")} icon="checkmark" iconTint="green" />
      {/if}
    </List>
  {:else}
    <List header={t("set.ai.apiSettings")} footer={t("set.ai.keyHint")}>
      <div class="pad fields">
        <TextField label={t("set.ai.url")} bind:value={url} placeholder="http://127.0.0.1:1234/v1" />
        <div class="examples mac-callout">
          {#each EXAMPLES as ex (ex.url)}
            <button type="button" onclick={() => (url = ex.url)}>{ex.label}<span>{ex.local ? t("set.ai.local") : t("set.ai.cloud")}</span></button>
          {/each}
        </div>
        <TextField label={t("set.ai.modelName")} bind:value={model} placeholder="gemma-4-e4b / gpt-4.1-mini" />
        <TextField label={t("set.ai.key")} bind:value={key} secure
          placeholder={settings.assistant_api_key_set ? t("set.ai.keySet") : t("set.ai.keyOptional")} />
      </div>
      {#if url && !isLocal(url)}
        <p class="warn mac-callout">{t("set.ai.remoteWarn", { host: host(url) })}</p>
      {/if}
      <div class="pad acts">
        <Button variant="borderedProminent" disabled={!url.trim() || !model.trim()} onclick={saveApi}>{t("set.ai.save")}</Button>
        <Button variant="bordered" loading={testing} disabled={!settings.assistant_api_url} onclick={test}>{t("set.ai.test")}</Button>
        {#if settings.assistant_api_key_set}
          <Button variant="borderless" onclick={() => apply({ assistant_api_key: "", clear_api_key: true })}>{t("set.ai.clearKey")}</Button>
        {/if}
      </div>
      {#if result}
        <p class="mac-callout result" class:bad={!result.ok}>{result.ok ? t("set.ai.testOk", { reply: result.reply }) : result.error}</p>
      {/if}
    </List>
  {/if}
{/if}

{#if confirmPull}
  <div class="backdrop">
    <Alert title={t("ai.setup.confirmTitle", { model: current })} message={t("set.ai.pullMessage", { size: info ? `${info.size_gb} GB` : "" })} actions={[
      { label: t("ai.setup.download"), role: "default", onPress: pullModel },
      { label: t("common.cancel"), role: "cancel", onPress: () => (confirmPull = false) },
    ]} />
  </div>
{/if}
{#if confirmRemote}
  <div class="backdrop">
    <Alert title={t("set.ai.remoteTitle", { host: host(confirmRemote.assistant_api_url || settings.assistant_api_url) })}
      message={t("set.ai.remoteMessage")} actions={[
        { label: t("set.ai.remoteOk"), role: "default", onPress: () => apply(confirmRemote) },
        { label: t("common.cancel"), role: "cancel", onPress: () => (confirmRemote = null) },
      ]} />
  </div>
{/if}

<style>
  .pad { padding: var(--space-2) var(--space-3); }
  .fields { display: flex; flex-direction: column; gap: var(--space-3); }
  .examples { display: flex; flex-wrap: wrap; gap: var(--space-2); margin-top: calc(-1 * var(--space-2)); }
  .examples button { display: inline-flex; gap: var(--space-1); padding: 2px var(--space-2); border: 0; border-radius: var(--radius-capsule);
    background: var(--fill-tertiary); color: var(--label-primary); font: inherit; cursor: pointer; }
  .examples span { color: var(--label-secondary); }
  .acts { display: flex; flex-wrap: wrap; gap: var(--space-2); }
  .warn { margin: 0 var(--space-3) var(--space-2); padding: var(--space-2) var(--space-3); border-radius: var(--radius-sm);
    background: color-mix(in srgb, var(--system-orange) 14%, transparent); color: var(--label-primary); }
  .result { margin: 0 var(--space-3) var(--space-3); color: var(--system-green); }
  .result.bad { color: var(--system-red); }
  .backdrop { position: fixed; inset: 0; z-index: 320; display: flex; align-items: center; justify-content: center; background: var(--media-scrim-light); }
</style>
