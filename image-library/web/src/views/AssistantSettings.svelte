<script>
  /**
   * 設定 → AI 助理：
   * 1. 在哪裡執行：這台電腦（Ollama，預設，離線）、Claude、Gemini、OpenAI，或其他 OpenAI 相容的服務。
   *    這台電腦：顯示偵測到的晶片與記憶體，依記憶體推薦模型；太大的模型標出來，下載前再提醒。
   *    雲端服務：切換前一定先跳出確認（核心原則二：資料不出家門，例外要本人明確同意）。金鑰只存在這台電腦，介面不會再顯示。
   * 2. 助理可以做什麼：四個權限等級；雲端服務可不可以看到文件內容另外一個開關。
   * 3. 助理做過的動作（最近 7 天；每筆一行，點開看細節）：可以復原。分類的設定在「設定 → 分類」。
   */
  import { Alert, Button, List, ListRow, PopUpButton, RadioGroup, TextField, Toggle } from "../ui/index.js";
  import { loadModels, testAssistant, saveSettings } from "../data/settings.js";
  import { downloadModel, loadActions, loadProviderModels } from "../data/assistant.js";
  import ActionCard from "./ActionCard.svelte";
  import OllamaSetup from "./OllamaSetup.svelte";
  import { t, i18n } from "../i18n/index.svelte.js";
  import { app, toast, refresh } from "../lib/state.svelte.js";

  let { settings, set } = $props();

  // Claude 的模型：和引擎 lumilib/llm.py 的 CLAUDE_MODELS 一致
  const CLAUDE = [
    { id: "claude-opus-5-5", name: "Claude Opus 5.5", price: [4, 20], note: "best" },
    { id: "claude-sonnet-5-5", name: "Claude Sonnet 5.5", price: [2, 10], note: "balanced" },
    { id: "claude-haiku-5-5", name: "Claude Haiku 5.5", price: [0.1, 0.5], note: "cheap" },
  ];
  const CLOUD = ["claude", "gemini", "openai"];
  const SERVICE = { claude: "Claude", gemini: "Gemini", openai: "OpenAI" };
  const KEY = { claude: "assistant_claude_key", gemini: "assistant_gemini_key", openai: "assistant_openai_key", custom: "assistant_api_key" };
  const MODEL = { claude: "assistant_claude_model", gemini: "assistant_gemini_model", openai: "assistant_openai_model", custom: "assistant_api_model" };

  let models = $state(null);
  let actions = $state([]);
  $effect(() => {
    app.refreshKey;
    loadModels().then((d) => (models = d)).catch(() => {});
    loadActions(20).then((d) => (actions = d)).catch(() => {});
  });

  const isLocal = (u) => /^https?:\/\/(127\.0\.0\.1|localhost|\[::1\])(:|\/|$)/i.test(u) || /^https?:\/\/[^/]+\.local(:|\/|$)/i.test(u);
  const host = (u) => { try { return new URL(u).host; } catch { return u; } };
  // 舊版的「openai」其實是任何相容的網址：沒存 OpenAI 金鑰的話當成「其他相容服務」（和引擎的 provider_of 一樣）
  const provider = $derived.by(() => {
    const p = settings?.assistant_provider || "ollama";
    if (p === "openai" && !settings?.assistant_openai_key_set && settings?.assistant_api_url) return "custom";
    return ["ollama", "claude", "gemini", "openai", "custom"].includes(p) ? p : "ollama";
  });
  const remote = $derived(CLOUD.includes(provider) || (provider === "custom" && !!settings?.assistant_api_url && !isLocal(settings.assistant_api_url)));
  const serviceName = $derived(SERVICE[provider] || host(settings?.assistant_api_url || ""));

  // ---- 這台電腦 ----
  const machine = $derived(models?.machine || null);
  const pick = $derived(models?.assistant_pick || settings?.assistant_model_effective || "gemma4:e4b");
  const installed = $derived((models?.installed || []).filter((m) => !/embed|nomic|bge|minilm/i.test(m.name)).map((m) => m.name));
  const recommended = $derived((models?.recommended || []).filter((m) => m.kind === "vision"));
  const chosen = $derived(settings?.assistant_model || ""); // 空白＝自動
  const current = $derived(chosen || pick);
  const badge = (m) => (m.name === pick ? t("set.ai.badge.best") : m.fit === "too_big" ? t("set.ai.badge.slow") : m.fit === "tight" ? t("set.ai.badge.tight") : "");
  const options = $derived.by(() => {
    const out = [{ value: "", label: `${t("set.ai.auto", { model: pick })} · ${t("set.ai.badge.best")}` }];
    const seen = new Set();
    const sorted = [...recommended].sort((a, b) => (a.family === "Gemma 4" ? 0 : 1) - (b.family === "Gemma 4" ? 0 : 1));
    for (const m of sorted) {
      seen.add(m.name);
      out.push({ value: m.name, label: [m.name, `${m.size_gb} GB`, badge(m), m.installed ? t("set.ai.installed") : ""].filter(Boolean).join(" · ") });
    }
    for (const n of installed) if (!seen.has(n)) out.push({ value: n, label: `${n} · ${t("set.ai.installed")}` });
    if (chosen && !out.some((o) => o.value === chosen)) out.push({ value: chosen, label: chosen });
    return out;
  });
  const info = $derived(recommended.find((m) => m.name === current));
  const fitText = $derived.by(() => {
    if (!chosen) return t("set.ai.fit.auto");
    if (!info || !machine?.ram_gb) return "";
    return t(`set.ai.fit.${info.fit}`, { ram: machine.ram_gb, need: info.min_ram, pick });
  });
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

  // ---- 其他服務 ----
  let url = $state("");
  let model = $state("");
  let key = $state("");
  let list = $state([]); // 從服務取得的模型
  let listing = $state(false);
  $effect(() => {
    provider;
    url = settings?.assistant_api_url || "";
    model = (MODEL[provider] && settings?.[MODEL[provider]]) || (provider === "claude" ? CLAUDE[0].id : "");
    key = "";
    list = [];
  });
  const keySet = $derived(!!(KEY[provider] && settings?.[`${KEY[provider]}_set`]));
  let confirmRemote = $state(null); // 要存的設定，等本人確認
  let testing = $state(false);
  let result = $state(null);

  function chooseProvider(v) {
    const values = { assistant_provider: v };
    const cloud = CLOUD.includes(v) || (v === "custom" && settings?.assistant_api_url && !isLocal(settings.assistant_api_url));
    if (cloud) confirmRemote = { values, name: SERVICE[v] || host(settings.assistant_api_url) };
    else apply(values);
  }
  function save() {
    const values = { assistant_provider: provider, [MODEL[provider]]: model.trim() };
    if (provider === "custom") values.assistant_api_url = url.trim();
    if (key.trim()) values[KEY[provider]] = key.trim();
    if (provider === "custom" && values.assistant_api_url && !isLocal(values.assistant_api_url) && values.assistant_api_url !== settings.assistant_api_url) {
      confirmRemote = { values, name: host(values.assistant_api_url) };
      return;
    }
    apply(values);
  }
  async function apply(values) {
    confirmRemote = null;
    try {
      Object.assign(settings, await saveSettings(values)); // 服務、網址、模型、金鑰一起存
      key = "";
      result = null;
      toast(t("set.ai.saved"));
      refresh();
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
  async function fetchList() {
    if (key.trim()) await apply({ [KEY[provider]]: key.trim() }); // 先存好金鑰（不顯示），再向服務要清單
    listing = true;
    try {
      const r = await loadProviderModels(provider);
      if (!r.ok) throw new Error(r.error);
      list = r.models;
      toast(t("set.ai.modelsFound", { n: r.models.length }));
    } catch (e) {
      toast(e.message, "error");
    } finally {
      listing = false;
    }
  }
  const claudeInfo = $derived(CLAUDE.find((m) => m.id === model));
  const EXAMPLES = [
    { label: "LM Studio", url: "http://127.0.0.1:1234/v1" },
    { label: "Ollama", url: "http://127.0.0.1:11434/v1" },
  ];
  const canSave = $derived(provider === "custom" ? !!url.trim() && !!model.trim() : !!model.trim() && (keySet || !!key.trim()));
  const configured = $derived(provider === "custom" ? !!settings?.assistant_api_url : keySet);

  // ---- 權限 ----
  const level = $derived(Number(settings?.assistant_permission) || 2);
  let confirmLevel = $state(false);
  let confirmContent = $state(false);
  function chooseLevel(v) {
    if (Number(v) === 4 && level < 4) confirmLevel = true;
    else set("assistant_permission", Number(v));
  }
  function chooseContent(on) {
    if (on) confirmContent = true;
    else set("assistant_cloud_content", 0);
  }
  const PROVIDERS = $derived([
    { value: "ollama", label: t("set.ai.p.ollama") },
    { value: "claude", label: t("set.ai.p.claude") },
    { value: "gemini", label: t("set.ai.p.gemini") },
    { value: "openai", label: t("set.ai.p.openai") },
    { value: "custom", label: t("set.ai.p.custom") },
  ]);
</script>

{#if settings}
  <List header={t("set.ai.where")} footer={provider === "ollama" ? t("set.ai.ollamaHint") : t(`set.ai.hint.${provider}`)}>
    <ListRow title={t("set.ai.machine")} icon="house"
      detail={machine ? (machine.ram_gb ? t("set.ai.machineInfo", { chip: machine.chip || "", ram: machine.ram_gb }) : t("set.ai.machineUnknown")) : ""} />
    <div class="pad">
      <RadioGroup value={provider} onchange={chooseProvider} options={PROVIDERS} />
    </div>
  </List>

  {#if provider === "ollama"}
    <OllamaSetup header="Ollama" onready={() => loadModels().then((d) => (models = d)).catch(() => {})} />
    <List header={t("set.ai.model")} footer={info?.note || ""}>
      <ListRow title={t("set.ai.model")} subtitle={fitText}>
        {#snippet trailing()}<PopUpButton value={chosen} onchange={(v) => set("assistant_model", v)} {options} menuWidth={380} />{/snippet}
      </ListRow>
      {#if models && !models.ollama_ok}
        <ListRow title={t("oll.needFirst")} />
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
        {#if provider === "custom"}
          <TextField label={t("set.ai.url")} bind:value={url} placeholder="http://127.0.0.1:1234/v1" />
          <div class="examples mac-callout">
            {#each EXAMPLES as ex (ex.url)}
              <button type="button" onclick={() => (url = ex.url)}>{ex.label}<span>{t("set.ai.local")}</span></button>
            {/each}
          </div>
        {/if}
        <TextField label={t("set.ai.key")} bind:value={key} secure
          placeholder={keySet ? t("set.ai.keySet") : provider === "custom" ? t("set.ai.keyOptional") : t("set.ai.keyRequired")} />
        {#if provider === "claude"}
          <div class="row">
            <span class="mac-body">{t("set.ai.claudeModel")}</span>
            <PopUpButton value={model} onchange={(v) => (model = v)} menuWidth={340}
              options={CLAUDE.map((m) => ({ value: m.id, label: `${m.name} · ${t(`set.ai.claude.${m.note}`)}` }))} />
          </div>
          {#if claudeInfo}<p class="mac-caption-1 sub">{t("set.ai.price", { in: claudeInfo.price[0], out: claudeInfo.price[1] })}</p>{/if}
        {:else}
          <TextField label={t("set.ai.modelName")} bind:value={model} placeholder={provider === "custom" ? "gemma-4-e4b" : ""} />
          <div class="row">
            <Button size="small" variant="bordered" loading={listing} disabled={provider === "custom" ? !url.trim() : !(keySet || key.trim())}
              onclick={fetchList}>{t("set.ai.fetchModels")}</Button>
            {#if list.length}
              <PopUpButton value={list.includes(model) ? model : ""} onchange={(v) => (model = v)} menuWidth={320}
                options={[{ value: "", label: t("set.ai.modelPick") }, ...list.map((m) => ({ value: m, label: m }))]} />
            {/if}
          </div>
        {/if}
      </div>
      {#if remote || (provider === "custom" && url && !isLocal(url))}
        <p class="warn mac-callout">{t("set.ai.remoteWarn", { host: serviceName || host(url) })}</p>
      {/if}
      <div class="pad acts">
        <Button variant="borderedProminent" disabled={!canSave} onclick={save}>{t("set.ai.save")}</Button>
        <Button variant="bordered" loading={testing} disabled={!configured} onclick={test}>{t("set.ai.test")}</Button>
        {#if keySet}
          <Button variant="borderless" onclick={() => apply({ [KEY[provider]]: "", [`clear_${KEY[provider]}`]: true })}>{t("set.ai.clearKey")}</Button>
        {/if}
      </div>
      {#if result}
        <p class="mac-callout result" class:bad={!result.ok}>{result.ok ? t("set.ai.testOk", { reply: result.reply }) : result.error}</p>
      {/if}
    </List>
  {/if}

  <List header={t("set.ai.perm")} footer={t(`set.ai.perm.${level}.hint`) + (i18n.locale.startsWith("zh") ? "" : " ") + t("set.ai.permFooter")}>
    <div class="pad">
      <RadioGroup value={String(level)} onchange={chooseLevel}
        options={[1, 2, 3, 4].map((n) => ({ value: String(n), label: t(`set.ai.perm.${n}`) }))} />
    </div>
    {#if remote && level >= 2}
      <ListRow title={t("set.ai.cloudContent", { service: serviceName })} subtitle={t("set.ai.cloudContentHint")}>
        {#snippet trailing()}<Toggle checked={!!settings.assistant_cloud_content} onchange={chooseContent}
          aria-label={t("set.ai.cloudContent", { service: serviceName })} />{/snippet}
      </ListRow>
    {/if}
  </List>

  <List header={t("set.ai.history")} footer={t("set.ai.historyRecent") + (actions.length ? " " + t("set.ai.historyFooter") : "")}>
    {#if actions.length}
      <div class="pad history">
        {#each actions as _, k (actions[k].id)}
          <ActionCard bind:action={actions[k]} compact />
        {/each}
      </div>
    {:else}
      <ListRow title={t("set.ai.historyEmpty")} />
    {/if}
  </List>
{/if}

{#if confirmPull}
  <div class="backdrop">
    <Alert title={t("ai.setup.confirmTitle", { model: current })}
      message={t("set.ai.pullMessage", { size: info ? `${info.size_gb} GB` : "" }) + (info?.fit === "too_big" ? `\n\n${t("set.ai.pullBig")}` : "")} actions={[
      { label: t("ai.setup.download"), role: "default", onPress: pullModel },
      { label: t("common.cancel"), role: "cancel", onPress: () => (confirmPull = false) },
    ]} />
  </div>
{/if}
{#if confirmRemote}
  <div class="backdrop">
    <Alert title={t("set.ai.remoteTitle", { host: confirmRemote.name })} message={t("set.ai.remoteMessage")} actions={[
        { label: t("set.ai.remoteOk"), role: "default", onPress: () => apply(confirmRemote.values) },
        { label: t("common.cancel"), role: "cancel", onPress: () => (confirmRemote = null) },
      ]} />
  </div>
{/if}
{#if confirmLevel}
  <div class="backdrop">
    <Alert title={t("set.ai.perm4Title")} message={t("set.ai.perm4Message")} actions={[
        { label: t("set.ai.allow"), role: "default", onPress: () => { confirmLevel = false; set("assistant_permission", 4); } },
        { label: t("common.cancel"), role: "cancel", onPress: () => (confirmLevel = false) },
      ]} />
  </div>
{/if}
{#if confirmContent}
  <div class="backdrop">
    <Alert title={t("set.ai.cloudContentTitle", { service: serviceName })} message={t("set.ai.cloudContentMessage", { service: serviceName })} actions={[
        { label: t("set.ai.allow"), role: "default", onPress: () => { confirmContent = false; set("assistant_cloud_content", 1); } },
        { label: t("common.cancel"), role: "cancel", onPress: () => (confirmContent = false) },
      ]} />
  </div>
{/if}

<style>
  .pad { padding: var(--space-2) var(--space-3); }
  .fields { display: flex; flex-direction: column; gap: var(--space-3); }
  .row { display: flex; align-items: center; gap: var(--space-2); flex-wrap: wrap; }
  .sub { margin: calc(-1 * var(--space-2)) 0 0; color: var(--label-secondary); }
  .examples { display: flex; flex-wrap: wrap; gap: var(--space-2); margin-top: calc(-1 * var(--space-2)); }
  .examples button { display: inline-flex; gap: var(--space-1); padding: 2px var(--space-2); border: 0; border-radius: var(--radius-capsule);
    background: var(--fill-tertiary); color: var(--label-primary); font: inherit; cursor: pointer; }
  .examples span { color: var(--label-secondary); }
  .acts { display: flex; flex-wrap: wrap; gap: var(--space-2); }
  .warn { margin: 0 var(--space-3) var(--space-2); padding: var(--space-2) var(--space-3); border-radius: var(--radius-sm);
    background: color-mix(in srgb, var(--system-orange) 14%, transparent); color: var(--label-primary); }
  .result { margin: 0 var(--space-3) var(--space-3); color: var(--system-green); }
  .result.bad { color: var(--system-red); }
  .history { display: flex; flex-direction: column; gap: var(--space-2); }
  .backdrop { position: fixed; inset: 0; z-index: 320; display: flex; align-items: center; justify-content: center; background: var(--media-scrim-light); }
</style>
