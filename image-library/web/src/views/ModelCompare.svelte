<script>
  /**
   * 實測比較：挑兩個已下載的模型，用幾張你自己的照片各跑一次，並排看速度與寫出來的結果，再決定用哪個分析照片。
   * 只讀照片、不寫進圖庫（現有的分析結果不會被換掉）；全部在這台電腦上執行。
   * 還沒有可以比較的模型時，提供下載 Qwen 3.8 27B（先跳確認，說明大小與會連到 Ollama 網站）。
   */
  import { Alert, Button, List, ListRow, PopUpButton, ProgressIndicator } from "../ui/index.js";
  import { loadModels, saveSetting } from "../data/settings.js";
  import { downloadModel } from "../data/assistant.js";
  import { loadCompare, startCompare } from "../data/ollama.js";
  import { thumbUrl } from "../lib/api.js";
  import { t, formatNumber } from "../i18n/index.svelte.js";
  import { app, toast, refresh } from "../lib/state.svelte.js";

  const SUGGEST = "qwen3.8:27b";
  let models = $state(null);
  let result = $state(null);
  let a = $state("");
  let b = $state("");
  let n = $state("8");
  let starting = $state(false);
  let confirmPull = $state(false);
  let showAll = $state(false);

  async function load() {
    try {
      models = await loadModels();
      result = await loadCompare();
    } catch {
      /* Ollama 沒開時 OllamaSetup 會說明 */
    }
  }
  $effect(() => {
    app.refreshKey;
    load();
  });

  const norm = (x) => (x && !x.includes(":") ? `${x}:latest` : x);
  const vision = $derived((models?.installed || []).filter((m) => !/embed|nomic|bge|minilm|clip/i.test(m.name)).map((m) => m.name));
  // 預設：目前分析照片用的模型 vs. Qwen 3.8（有下載的話），否則第二個已下載的模型
  $effect(() => {
    if (!models || a) return;
    const active = vision.find((x) => norm(x) === norm(models.active?.vision)) || vision[0] || "";
    a = active;
    b = vision.find((x) => x !== active && norm(x) === norm(SUGGEST)) || vision.find((x) => x !== active) || "";
  });
  const suggestInfo = $derived((models?.recommended || []).find((m) => m.name === SUGGEST));
  const hasSuggest = $derived(vision.some((x) => norm(x) === norm(SUGGEST)));
  const job = $derived((app.server?.jobs?.active || []).find((j) => j.kind === "model_compare") || null);
  const queued = $derived((app.server?.jobs?.queued || []).some((j) => j.kind === "model_compare"));
  const pull = $derived((app.server?.jobs?.active || []).find((j) => j.kind === "pull" && j.model === SUGGEST) || null);
  let wasBusy = false;
  $effect(() => {
    const busy = !!job || queued || !!pull;
    if (wasBusy && !busy) load();
    wasBusy = busy;
  });

  async function start() {
    starting = true;
    try {
      await startCompare([a, b], Number(n));
      result = null;
      refresh();
    } catch (e) {
      toast(e.message, "error", 6000);
    } finally {
      starting = false;
    }
  }
  async function pullSuggest() {
    confirmPull = false;
    try {
      await downloadModel(SUGGEST);
      toast(t("ai.downloading", { model: SUGGEST }));
      refresh();
    } catch (e) {
      toast(e.message, "error");
    }
  }
  async function use(name) {
    try {
      await saveSetting("vision_model", name);
      models = { ...models, active: { ...models.active, vision: name } };
      toast(t("cmp.using", { model: name }));
      refresh();
    } catch (e) {
      toast(e.message, "error");
    }
  }
  const opts = $derived(vision.map((x) => ({ value: x, label: x })));
  const secs = (v) => (v == null ? "—" : t("cmp.secs", { n: formatNumber(v) }));
  const fastest = $derived(result ? Math.min(...result.models.filter((m) => m.median_seconds != null).map((m) => m.median_seconds)) : null);
  const items = $derived(result ? (showAll ? result.items : result.items.slice(0, 4)) : []);
</script>

{#if models?.ollama_ok}
  <List header={t("cmp.title")} footer={t("cmp.footer")}>
    {#if vision.length < 2}
      <ListRow title={t("cmp.needTwo")} subtitle={suggestInfo && !hasSuggest ? t("cmp.suggest", { model: SUGGEST, size: `${suggestInfo.size_gb} GB` }) : ""}>
        {#snippet trailing()}
          {#if pull}<span class="mac-callout sub">{pull.total ? `${Math.round((pull.done / pull.total) * 100)}%` : "…"}</span>
          {:else if suggestInfo && !hasSuggest}<Button size="small" variant="bordered" icon="arrow-down" onclick={() => (confirmPull = true)}>{t("cmp.download", { model: SUGGEST })}</Button>{/if}
        {/snippet}
      </ListRow>
    {:else}
      <ListRow title={t("cmp.modelA")}>{#snippet trailing()}<PopUpButton value={a} onchange={(v) => (a = v)} options={opts} menuWidth={280} disabled={!!job} />{/snippet}</ListRow>
      <ListRow title={t("cmp.modelB")}>{#snippet trailing()}<PopUpButton value={b} onchange={(v) => (b = v)} options={opts} menuWidth={280} disabled={!!job} />{/snippet}</ListRow>
      <ListRow title={t("cmp.photos")}>
        {#snippet trailing()}<PopUpButton value={n} onchange={(v) => (n = v)} disabled={!!job}
          options={["4", "8", "12", "20"].map((v) => ({ value: v, label: t("cmp.photosN", { n: v }) }))} />{/snippet}
      </ListRow>
      {#if job || queued}
        <ListRow title={t("cmp.running")} subtitle={job?.message || t("cmp.queued")} />
        <div class="pad"><ProgressIndicator value={job?.total ? job.done / job.total : undefined} label={t("cmp.running")} /></div>
      {:else}
        <div class="pad acts">
          <Button variant="borderedProminent" loading={starting} disabled={!a || !b || a === b} onclick={start}>{t("cmp.start")}</Button>
          {#if !hasSuggest && suggestInfo}
            {#if pull}<span class="mac-callout sub">{t("ai.setup.downloading", { model: SUGGEST })} {pull.total ? `${Math.round((pull.done / pull.total) * 100)}%` : ""}</span>
            {:else}<Button variant="bordered" icon="arrow-down" onclick={() => (confirmPull = true)}>{t("cmp.download", { model: SUGGEST })}</Button>{/if}
          {/if}
        </div>
      {/if}
    {/if}
  </List>

  {#if result && !job}
    <section class="result" aria-label={t("cmp.resultTitle")}>
      <h3 class="mac-headline">{t("cmp.resultTitle")}<span class="mac-caption-1 sub">{new Date(result.at).toLocaleString()}</span></h3>
      <div class="cols" style:--n={result.models.length}>
        {#each result.models as m (m.model)}
          {@const using = norm(m.model) === norm(models.active?.vision)}
          <div class="col">
            <b class="mac-body name">{m.model}</b>
            <span class="big mac-title-1" class:win={m.median_seconds != null && m.median_seconds === fastest}>{secs(m.median_seconds)}</span>
            <span class="mac-caption-1 sub">{t("cmp.perPhoto")}</span>
            <ul class="mac-callout facts">
              <li>{t("cmp.first", { s: secs(m.first_seconds) })}</li>
              <li>{t("cmp.ok", { ok: m.ok, n: m.count })}</li>
              <li>{t("cmp.tags", { n: m.tags_avg })}</li>
              <li>{t("cmp.text", { n: m.text_found })}</li>
            </ul>
            {#if using}<span class="mac-callout using">{t("cmp.inUse")}</span>
            {:else}<Button size="small" variant="bordered" disabled={!m.ok} onclick={() => use(m.model)}>{t("cmp.use")}</Button>{/if}
          </div>
        {/each}
      </div>
      {#if result.stopped}<p class="mac-callout sub">{t("cmp.stopped")}</p>{/if}

      <h4 class="mac-subheadline sub">{t("cmp.samples")}</h4>
      {#each items as it (it.id)}
        <div class="item">
          <img src={thumbUrl({ id: it.id })} alt="" loading="lazy" />
          <div class="outs" style:--n={result.models.length}>
            {#each result.models as m (m.model)}
              {@const r = it.results[m.model]}
              <div class="out mac-callout">
                <span class="mac-caption-1 sub">{m.model} · {r ? secs(r.seconds) : "—"}</span>
                {#if !r}<span class="sub">—</span>
                {:else if r.error}<span class="bad">{r.error}</span>
                {:else}
                  <span>{r.description}</span>
                  {#if r.tags?.length}<span class="sub tags mac-caption-1">{r.tags.slice(0, 12).join("、")}</span>{/if}
                  {#if r.ocr_text}<span class="sub">{t("cmp.ocr")}{r.ocr_text.slice(0, 80)}</span>{/if}
                {/if}
              </div>
            {/each}
          </div>
        </div>
      {/each}
      {#if result.items.length > 4}
        <Button size="small" variant="borderless" onclick={() => (showAll = !showAll)}>{showAll ? t("cmp.less") : t("cmp.more", { n: result.items.length })}</Button>
      {/if}
    </section>
  {/if}
{/if}

{#if confirmPull && suggestInfo}
  <Alert title={t("ai.setup.confirmTitle", { model: SUGGEST })} message={t("set.ai.pullMessage", { size: `${suggestInfo.size_gb} GB` }) + `\n\n${t("cmp.pullNote")}`} actions={[
    { label: t("ai.setup.download"), role: "default", onPress: pullSuggest },
    { label: t("common.cancel"), role: "cancel", onPress: () => (confirmPull = false) },
  ]} />
{/if}

<style>
  .pad { padding: var(--space-2) var(--space-4) var(--space-3); }
  .acts { display: flex; gap: var(--space-2); align-items: center; flex-wrap: wrap; }
  .sub { color: var(--label-secondary); }
  .bad { color: var(--destructive); }
  .result { display: flex; flex-direction: column; gap: var(--space-3); margin-top: var(--space-3); color: var(--label-primary); }
  .result h3 { margin: 0; display: flex; align-items: baseline; gap: var(--space-2); flex-wrap: wrap; }
  .result h4 { margin: var(--space-2) 0 0; }
  .cols { display: grid; grid-template-columns: repeat(var(--n), minmax(0, 1fr)); gap: var(--space-3); }
  .col { display: flex; flex-direction: column; align-items: flex-start; gap: var(--space-1); padding: var(--space-3) var(--space-4);
    border-radius: var(--radius-lg); background: var(--fill-quaternary); min-width: 0; }
  .name { overflow-wrap: anywhere; }
  .big { font-weight: 600; font-feature-settings: "tnum"; }
  .big.win { color: var(--system-green); }
  .facts { list-style: none; margin: var(--space-1) 0; padding: 0; color: var(--label-secondary); display: flex; flex-direction: column; gap: 2px; }
  .using { color: var(--system-green); }
  .item { display: grid; grid-template-columns: 96px minmax(0, 1fr); gap: var(--space-3); align-items: start; }
  .item img { width: 96px; height: 96px; object-fit: cover; border-radius: var(--radius-md); background: var(--fill-tertiary); }
  .outs { display: grid; grid-template-columns: repeat(var(--n), minmax(0, 1fr)); gap: var(--space-3); }
  .out { display: flex; flex-direction: column; gap: var(--space-1); min-width: 0; overflow-wrap: anywhere; }
  @media (max-width: 640px) {
    .cols, .outs { grid-template-columns: minmax(0, 1fr); }
    .item { grid-template-columns: 64px minmax(0, 1fr); }
    .item img { width: 64px; height: 64px; }
  }
</style>
