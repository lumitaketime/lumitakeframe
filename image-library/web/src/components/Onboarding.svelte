<script>
  /**
   * 首次使用（手冊「首次使用」）：四個畫面，每一步都可以略過。
   * 1. 歡迎與承諾（只讀不寫硬碟、永不自動刪除、資料不出家門）→「開始使用」
   * 2. 目錄放在哪裡（預設這台 Mac，可以選常接的 SSD）→「繼續」
   * 3. 自動整理：要不要自動分類、要不要讓 AI 在夜間處理（本人決定；略過的話之後第一次有檔案時再問）→「繼續」
   * 4. 接上第一顆硬碟並加入目錄（不會自動掃描，要按「加入目錄」）→「完成」
   * 之後可以在「設定 → 關於」重新執行。
   */
  import { fsName } from "../lib/names.js";
  import { Button, Icon, ProgressIndicator } from "../ui/index.js";
  import Wordmark from "./Wordmark.svelte";
  import CatalogLocation from "../views/CatalogLocation.svelte";
  import ClassifyChoices from "../views/ClassifyChoices.svelte";
  import { classifyConsent } from "../data/category.svelte.js";
  import { loadDrivesDetail, addRoot, pickFolder } from "../data/drives.js";
  import { loadCatalog } from "../data/catalog.svelte.js";
  import { saveSetting } from "../data/settings.js";
  import { t, formatBytes } from "../i18n/index.svelte.js";
  import { app, toast, refresh } from "../lib/state.svelte.js";
  import { navigate } from "../lib/router.svelte.js";

  const STEPS = ["welcome", "catalog", "organize", "drive"];
  let organize = $state({ rules_auto: true, ai_auto: true, read_text: true });
  let step = $state(0);
  let detail = $state(null);
  let busy = $state("");
  const local = $derived(!!app.server?.local);

  // 第三步：每 3 秒看一次有沒有新接上的硬碟
  function loadDrives() {
    loadDrivesDetail().then((d) => (detail = d)).catch(() => {});
  }
  $effect(() => {
    if (step !== 3) return;
    loadDrives();
    const timer = setInterval(loadDrives, 3000);
    return () => clearInterval(timer);
  });

  async function add(v) {
    busy = v.path;
    try {
      await addRoot(v.path, v.name);
      toast(t("drives.added", { name: v.name }));
      await loadCatalog();
      loadDrives();
      refresh();
    } catch (e) {
      toast(e.message, "error");
    } finally {
      busy = "";
    }
  }
  async function addFolder() {
    busy = "pick";
    try {
      const path = await pickFolder();
      if (path) {
        await addRoot(path);
        toast(t("drives.addedFolder"));
        await loadCatalog();
        loadDrives();
        refresh();
      }
    } catch (e) {
      toast(e.message, "error");
    } finally {
      busy = "";
    }
  }

  async function finish() {
    try {
      await saveSetting("onboarded", 1);
    } catch {
      /* 下次再問也沒關係 */
    }
    if (app.server?.ui) app.server.ui.onboarded = 1;
    navigate(detail?.drives?.length ? "/drives" : "/folders", { replace: true });
  }
  // 「自動整理」按「繼續」才記下本人的選擇；按「略過」就之後再問
  async function next() {
    if (STEPS[step] === "organize") classifyConsent(organize).catch(() => {});
    if (step < STEPS.length - 1) step += 1;
    else finish();
  }
  const skip = () => (step < STEPS.length - 1 ? (step += 1) : finish());
  const PRIMARY = ["onb.start", "onb.continue", "onb.continue", "onb.done"];
  const PROMISES = [
    { icon: "external-drive-fill", key: "readOnly" },
    { icon: "trash", key: "noDelete" },
    { icon: "house", key: "local" },
  ];
</script>

<div class="scrim" role="presentation">
  <div class="panel" role="dialog" aria-modal="true" aria-labelledby="onb-title">
    <div class="dots" aria-label={t("onb.progress", { n: step + 1, total: STEPS.length })}>
      {#each STEPS as s, i (s)}<span class:on={i === step} class:done={i < step}></span>{/each}
    </div>

    <div class="body">
      {#if step === 0}
        <div class="hero">
          <img src="/icon.png" alt="" width="72" height="72" />
          <Wordmark size={34} />
        </div>
        <h1 id="onb-title" class="mac-title-2">{t("onb.welcome.title")}</h1>
        <p class="lead mac-body">{t("onb.welcome.lead")}</p>
        <ul class="promises">
          {#each PROMISES as p (p.key)}
            <li>
              <span class="pi"><Icon name={p.icon} size={16} weight="medium" /></span>
              <span><b class="mac-headline">{t(`onb.promise.${p.key}`)}</b><span class="mac-callout sub">{t(`onb.promise.${p.key}.hint`)}</span></span>
            </li>
          {/each}
        </ul>
      {:else if step === 1}
        <h1 id="onb-title" class="mac-title-2">{t("onb.catalog.title")}</h1>
        <p class="lead mac-body">{t("onb.catalog.lead")}</p>
        <CatalogLocation header={t("onb.catalog.header")} />
      {:else if step === 2}
        <h1 id="onb-title" class="mac-title-2">{t("onb.organize.title")}</h1>
        <p class="lead mac-body">{t("onb.organize.lead")}</p>
        <ClassifyChoices bind:value={organize} />
        <p class="mac-callout sub">{t("cat.consent.promise")}</p>
      {:else}
        <h1 id="onb-title" class="mac-title-2">{t("onb.drive.title")}</h1>
        <p class="lead mac-body">{t("onb.drive.lead")}</p>
        {#if !detail}
          <div class="wait"><ProgressIndicator kind="spinner" size="small" label={t("view.loading")} /></div>
        {:else}
          <ul class="drives">
            {#each detail.new as v (v.path)}
              <li>
                <span class="pi"><Icon name="external-drive-fill" size={16} weight="medium" /></span>
                <span class="grow"><b class="mac-headline">{v.name}</b><span class="mac-callout sub">{[fsName(v.fs_label, t), v.capacity ? formatBytes(v.capacity) : "", v.read_only ? t("drive.readOnly") : ""].filter(Boolean).join(" · ")}</span></span>
                <Button size="small" variant="borderedProminent" loading={busy === v.path} disabled={!!busy || !local} onclick={() => add(v)}>{t("drives.add")}</Button>
              </li>
            {/each}
            {#each detail.drives as d (d.key)}
              <li class="added">
                <span class="pi ok"><Icon name="checkmark" size={14} weight="bold" /></span>
                <span class="grow"><b class="mac-headline">{d.name}</b><span class="mac-callout sub">{t("onb.drive.added")}</span></span>
              </li>
            {/each}
            {#if !detail.new.length && !detail.drives.length}
              <li class="empty mac-callout"><ProgressIndicator kind="spinner" size="small" label={t("onb.drive.waiting")} />{t("onb.drive.waiting")}</li>
            {/if}
          </ul>
          {#if local}
            <Button variant="borderless" icon="folder" disabled={!!busy} onclick={addFolder}>{t("onb.drive.folder")}</Button>
          {:else}
            <p class="mac-callout sub">{t("drives.addOnMac")}</p>
          {/if}
        {/if}
      {/if}
    </div>

    <footer>
      {#if step > 0}<Button variant="bordered" onclick={() => (step -= 1)}>{t("common.back")}</Button>{/if}
      <span class="grow"></span>
      <Button variant="borderless" onclick={step === 0 ? finish : skip}>{t(step === 0 ? "onb.skipAll" : "onb.skip")}</Button>
      <Button variant="borderedProminent" onclick={next}>{t(PRIMARY[step])}</Button>
    </footer>
  </div>
</div>

<style>
  .scrim { position: fixed; inset: 0; z-index: 300; display: flex; align-items: center; justify-content: center; padding: var(--space-4);
    background: var(--media-scrim-light); }
  .panel { box-sizing: border-box; width: min(560px, 100%); max-height: calc(100vh - var(--space-8)); display: flex; flex-direction: column;
    border-radius: var(--radius-xl); background: var(--window-bg); box-shadow: var(--shadow-window); overflow: hidden; }
  .dots { display: flex; justify-content: center; gap: var(--space-2); padding: var(--space-4) 0 0; }
  .dots span { width: var(--space-2); height: var(--space-2); border-radius: var(--radius-capsule); background: var(--fill-secondary); transition: width var(--dur-fast) var(--ease-out), background var(--dur-fast); }
  .dots span.on { width: var(--space-5); background: var(--accent); }
  .dots span.done { background: var(--accent); opacity: .5; }
  .body { flex: 1; min-height: 0; overflow-y: auto; padding: var(--space-4) var(--space-6) var(--space-2); display: flex; flex-direction: column; gap: var(--space-3); }
  .hero { display: flex; flex-direction: column; align-items: center; gap: var(--space-3); padding: var(--space-2) 0; }
  .hero img { border-radius: var(--radius-lg); }
  h1 { margin: 0; text-align: center; color: var(--label-primary); }
  .lead { margin: 0; text-align: center; color: var(--label-secondary); }
  .promises, .drives { list-style: none; margin: var(--space-2) 0 0; padding: 0; display: flex; flex-direction: column; gap: var(--space-2); }
  .promises li, .drives li { display: flex; align-items: center; gap: var(--space-3); padding: var(--space-3); border-radius: var(--radius-md); background: var(--fill-quaternary); }
  .promises li > span:last-child, .drives .grow { display: flex; flex-direction: column; min-width: 0; }
  .grow { flex: 1; min-width: 0; }
  .pi { flex: none; display: inline-flex; align-items: center; justify-content: center; width: 32px; height: 32px; border-radius: var(--radius-sm);
    background: var(--accent); color: var(--on-accent); }
  .pi.ok { background: var(--system-green); }
  .sub { color: var(--label-secondary); }
  .drives .empty { justify-content: center; color: var(--label-secondary); }
  .wait { display: flex; justify-content: center; padding: var(--space-6); }
  footer { display: flex; align-items: center; gap: var(--space-2); padding: var(--space-3) var(--space-5) var(--space-4); border-top: 1px solid var(--separator); }
  @media (prefers-reduced-motion: reduce) { .dots span { transition: none; } }
</style>
