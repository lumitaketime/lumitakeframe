<script>
  /**
   * 設定：左邊分類、右邊內容（手冊「設定」）。一般、目錄、掃描、文字與搜尋是檔案目錄的設定；
   * 照片、連線與系統沿用照片圖庫原有的設定（PhotoSettings）。
   * 改了就生效，不需要按「儲存」。所有設定與資料都在這台電腦上，不上傳。
   */
  import { Alert, Button, Checkbox, Icon, List, ListRow, PopUpButton, ProgressIndicator, RadioGroup, SegmentedControl, Toggle } from "../ui/index.js";
  import PhotoSettings from "./PhotoSettings.svelte";
  import CatalogLocation from "../views/CatalogLocation.svelte";
  import AssistantSettings from "../views/AssistantSettings.svelte";
  import SemanticSettings from "../views/SemanticSettings.svelte";
  import { loadSettings, saveSetting, loadStorage, resetText } from "../data/settings.js";
  import { loadTextStatus, startExtract, startOcr, stopJob } from "../data/find.svelte.js";
  import { setFrame } from "../shell/frame.svelte.js";
  import { t, i18n, LOCALES, setLocale, formatNumber, formatBytes, formatDuration } from "../i18n/index.svelte.js";
  import { app, toast, refresh } from "../lib/state.svelte.js";
  import { route, navigate } from "../lib/router.svelte.js";

  let { section = "" } = $props();

  const CATS = [
    { id: "general", icon: "gear", tint: "gray-1" },
    { id: "catalog", icon: "external-drive-fill", tint: "blue" },
    { id: "scan", icon: "clock", tint: "orange" },
    { id: "text", icon: "magnifyingglass", tint: "indigo" },
    { id: "assistant", icon: "sparkles", tint: "purple" },
    { id: "photos", icon: "photo", tint: "pink" },
    { id: "system", icon: "slider-horizontal", tint: "gray-1" },
  ];
  // 舊網址（照片圖庫的設定分類）對到新的分類與子分類
  const OLD = { ai: ["photos", "ai"], recog: ["photos", "recog"], faces: ["photos", "recog"], search: ["photos", "search"], organize: ["photos", "organize"],
    rating: ["photos", "organize"], tools: ["photos", "organize"], library: ["photos", "library"], look: ["photos", "library"], features: ["photos", "library"],
    phone: ["system", ""], storage: ["system", ""], advanced: ["system", ""], about: ["about", ""] };
  const sub = $derived(route.path.split("/").filter(Boolean)[2] || "");
  const mapped = $derived(OLD[section] || null);
  const current = $derived(mapped ? mapped[0] : CATS.some((c) => c.id === section) ? section : "");
  const photoTab = $derived((mapped && mapped[0] === "photos" ? mapped[1] : sub) || "ai");
  let width = $state(1200);
  const narrow = $derived(width < 640);
  const shown = $derived(current || (narrow ? "" : "general")); // 窄視窗先顯示分類清單

  $effect(() => {
    setFrame({ crumbs: [], status: "", location: null, info: null });
  });

  // ---- 設定值 ----
  let settings = $state(null);
  let error = $state("");
  function load() {
    loadSettings().then((d) => { settings = d; error = ""; }).catch((e) => (error = e.message));
  }
  $effect(() => {
    load();
  });
  async function set(key, value) {
    const before = settings?.[key];
    if (settings) settings[key] = value;
    try {
      await saveSetting(key, value);
    } catch (e) {
      if (settings) settings[key] = before;
      toast(e.message, "error");
    }
  }

  // ---- 目錄與文字索引的狀態 ----
  let storage = $state(null);
  let text = $state(null);
  $effect(() => {
    app.refreshKey;
    if (shown === "catalog") loadStorage().then((d) => (storage = d)).catch(() => {});
    if (shown === "catalog" || shown === "text") loadTextStatus().then((d) => (text = d)).catch(() => {});
  });
  const textJob = $derived(app.server?.jobs?.active?.find((j) => j.kind === "extract" || j.kind === "ocr") || null);
  $effect(() => {
    if (!textJob) return;
    const timer = setInterval(() => loadTextStatus().then((d) => (text = d)).catch(() => {}), 5000);
    return () => clearInterval(timer);
  });
  async function start(kind) {
    try {
      await (kind === "ocr" ? startOcr() : startExtract(kind === "retry"));
      toast(kind === "ocr" ? t("find.ocrStarted") : t("find.extractStarted"));
      refresh();
    } catch (e) {
      toast(e.message, "error");
    }
  }
  async function stop() {
    try {
      await stopJob(textJob?.id);
      refresh();
    } catch (e) {
      toast(e.message, "error");
    }
  }
  let confirmReset = $state(false);
  async function doReset() {
    confirmReset = false;
    try {
      const { cleared } = await resetText();
      toast(t("set.text.resetDone", { count: formatNumber(cleared) }));
      refresh();
    } catch (e) {
      toast(e.message, "error");
    }
  }

  // ---- 文字辨識的語言（Apple Vision 的語言代碼） ----
  const OCR_LANGS = ["zh-Hant", "zh-Hans", "en-US", "ja-JP", "ko-KR"];
  const langs = $derived(new Set((settings?.ocr_languages || "").split(",").filter(Boolean)));
  function toggleLang(code, on) {
    const next = OCR_LANGS.filter((c) => (c === code ? on : langs.has(c)));
    if (!next.length) return toast(t("set.ocr.needOne"));
    set("ocr_languages", next.join(","));
  }

  const local = $derived(!!app.server?.local);
  const isMac = $derived(app.server?.platform === "darwin");
  const go = (id) => navigate(`/settings/${id}`);
  const FORMATS = ["pdf", "office", "text", "ebook", "mac", "archive"];
</script>

<div class="settings" bind:clientWidth={width} class:narrow>
  {#if !narrow || !shown}
    <nav class="cats" aria-label={t("set.categories")}>
      <List appearance="plain">
        {#each CATS as c (c.id)}
          <ListRow title={t(`set.cat.${c.id}`)} icon={c.icon} iconTint={c.tint} selected={shown === c.id} onclick={() => go(c.id)} accessory={narrow ? "disclosure" : "none"} />
        {/each}
        <ListRow title={t("set.cat.about")} icon="info" iconTint="gray-1" selected={shown === "about"} onclick={() => go("about")} accessory={narrow ? "disclosure" : "none"} />
      </List>
    </nav>
  {/if}

  {#if shown}
  <div class="pane" class:wide={shown === "photos" || shown === "system" || shown === "about"}>
    {#if narrow}<div class="back"><Button variant="borderless" icon="chevron-left" onclick={() => navigate("/settings")}>{t("nav.settings")}</Button></div>{/if}
    <h1 class="mac-title-1">{t(`set.cat.${shown}`)}</h1>
    {#if error}
      <p class="err mac-body" role="alert">{error} <Button size="small" variant="bordered" onclick={load}>{t("view.retry")}</Button></p>
    {/if}

    {#if shown === "general"}
      <List header={t("set.general.ui")}>
        <ListRow title={t("set.general.language")} subtitle={t("set.general.languageHint")}>
          {#snippet trailing()}<PopUpButton value={i18n.locale} onchange={setLocale} options={LOCALES.map((l) => ({ value: l.id, label: l.label }))} />{/snippet}
        </ListRow>
        <ListRow title={t("set.general.appearance")} detail={t("set.general.appearanceSystem")} />
        <ListRow title={t("set.general.onboarding")} subtitle={t("set.general.onboardingHint")}>
          {#snippet trailing()}<Button size="small" variant="bordered" onclick={() => navigate("/welcome")}>{t("set.general.onboardingOpen")}</Button>{/snippet}
        </ListRow>
        <ListRow title={t("set.general.version")} subtitle={t("set.general.versionHint")} detail={`${app.server?.version || ""}（${app.server?.build || "—"}）`} />
      </List>
      {#if settings}
        <List header={t("set.general.start")} footer={t("set.general.startHint")}>
          <ListRow title={t("set.general.startPage")}>
            {#snippet trailing()}<PopUpButton value={settings.start_page || "folders"} onchange={(v) => set("start_page", v)}
              options={["folders", "drives", "find", "photos"].map((v) => ({ value: v, label: t(`set.start.${v}`) }))} />{/snippet}
          </ListRow>
        </List>
        <List header={t("settings.open.title")} footer={t("settings.open.hint")}>
          <div class="pad">
            <RadioGroup value={settings.open_action || ""} onchange={(v) => set("open_action", v)} options={[
              { value: "", label: t("settings.open.ask") },
              { value: "open", label: t("open.optOpen") },
              { value: "reveal", label: t("open.optReveal") },
            ]} />
          </div>
        </List>
      {/if}

    {:else if shown === "catalog"}
      <CatalogLocation showSize={false} />
      <List header={t("set.catalog.size")} footer={t("set.catalog.sizeHint")}>
        {#if storage}
          <ListRow title={t("set.catalog.db")} subtitle={t("set.catalog.dbHint")} detail={formatBytes(storage.database.bytes)} />
          <ListRow title={t("set.catalog.textIndex")} detail={text ? formatBytes(text.bytes) || "0 KB" : "…"} />
          <ListRow title={t("set.catalog.thumbs")} subtitle={t("set.catalog.thumbsHint", { count: formatNumber(storage.thumbs.files + storage.face_thumbs.files) })}
            detail={formatBytes(storage.thumbs.bytes + storage.face_thumbs.bytes) || "0 KB"} />
        {:else}
          <div class="pad"><ProgressIndicator kind="spinner" size="small" label={t("view.loading")} /></div>
        {/if}
      </List>
      <List header={t("set.catalog.skip")} footer={t("set.catalog.skipHint")}>
        <ListRow title={t("set.catalog.skipHidden")} />
        <ListRow title={t("set.catalog.skipSystem")} subtitle="$RECYCLE.BIN · System Volume Information · .Trashes · .Spotlight-V100 · node_modules" />
        <ListRow title={t("set.catalog.skipLibrary")} subtitle={t("set.catalog.skipLibraryHint")} />
        <ListRow title={t("set.catalog.skipNoindex")} subtitle={t("set.catalog.skipNoindexHint")} />
      </List>
      <List>
        <ListRow title={t("set.catalog.drives")} subtitle={t("set.catalog.drivesHint")} icon="external-drive-fill" accessory="disclosure" onclick={() => navigate("/drives")} />
      </List>

    {:else if shown === "scan"}
      <List header={t("set.scan.promise")}>
        <ListRow title={t("set.scan.readOnly")} subtitle={t("set.scan.readOnlyHint")} icon="checkmark" iconTint="green" />
        <ListRow title={t("set.scan.resume")} subtitle={t("set.scan.resumeHint")} icon="checkmark" iconTint="green" />
      </List>
      {#if settings}
        <List header={t("set.scan.when")}>
          <ListRow title={t("set.scan.onStart")} subtitle={t("set.scan.onStartHint")}>
            {#snippet trailing()}<Toggle checked={!!settings.scan_on_start} aria-label={t("set.scan.onStart")} onchange={(v) => set("scan_on_start", v ? 1 : 0)} />{/snippet}
          </ListRow>
          <ListRow title={t("set.scan.autoText")} subtitle={t("set.scan.autoTextHint")}>
            {#snippet trailing()}<Toggle checked={!!settings.auto_extract} aria-label={t("set.scan.autoText")} onchange={(v) => set("auto_extract", v ? 1 : 0)} />{/snippet}
          </ListRow>
          {#if isMac}
            <ListRow title={t("set.scan.awake")} subtitle={t("set.scan.awakeHint")}>
              {#snippet trailing()}<Toggle checked={!!settings.keep_awake} aria-label={t("set.scan.awake")} onchange={(v) => set("keep_awake", v ? 1 : 0)} />{/snippet}
            </ListRow>
          {/if}
        </List>
      {/if}
      <List header={t("set.scan.manual")} footer={t("set.scan.manualHint")}>
        <ListRow title={t("nav.duplicates")} subtitle={t("set.scan.compare")} icon="duplicate" accessory="disclosure" onclick={() => navigate("/duplicates")} />
        <ListRow title={t("nav.scanProgress")} subtitle={t("set.scan.log")} icon="clock" accessory="disclosure" onclick={() => navigate("/activity")} />
      </List>

    {:else if shown === "text"}
      <List header={t("set.text.status")}>
        {#if !text}
          <div class="pad"><ProgressIndicator kind="spinner" size="small" label={t("view.loading")} /></div>
        {:else}
          {#if textJob}
            <ListRow title={t(textJob.kind === "ocr" ? "find.ocring" : "find.extracting")}
              subtitle={(textJob.total ? t("find.progress", { done: formatNumber(textJob.done), total: formatNumber(textJob.total) }) : t("dupes.waiting")) + (textJob.eta ? ` · ${t("dupes.remaining", { time: formatDuration(textJob.eta) })}` : "")}>
              {#snippet trailing()}<span class="job"><ProgressIndicator kind="circular" size="small" value={textJob.total ? textJob.done / textJob.total : undefined} label={t("find.extracting")} /><Button size="small" variant="bordered" onclick={stop}>{t("drives.stop")}</Button></span>{/snippet}
            </ListRow>
          {/if}
          <ListRow title={t("set.text.done")} detail={formatNumber(text.extract.done)} />
          <ListRow title={t("set.text.todo")} subtitle={text.extract.offline.files ? t("find.offline", { count: formatNumber(text.extract.offline.files) }) : ""} detail={formatNumber(text.extract.todo.files)}>
            {#snippet trailing()}{#if !textJob && text.extract.todo.files}<Button size="small" variant="borderedProminent" onclick={() => start("extract")}>{t("find.extract")}</Button>{/if}{/snippet}
          </ListRow>
          {#if text.extract.failed}
            <ListRow title={t("set.text.failed")} subtitle={t("set.text.failedHint")} detail={formatNumber(text.extract.failed)}>
              {#snippet trailing()}{#if !textJob && text.extract.errors}<Button size="small" variant="bordered" onclick={() => start("retry")}>{t("set.text.retry")}</Button>{/if}{/snippet}
            </ListRow>
          {/if}
          {#if text.extract.cloud}<ListRow title={t("set.text.cloud")} subtitle={t("set.text.cloudHint")} detail={formatNumber(text.extract.cloud)} />{/if}
          <ListRow title={t("set.text.indexSize")} detail={formatBytes(text.bytes) || "0 KB"} />
        {/if}
      </List>

      <SemanticSettings {settings} {set} />

      <List header={t("set.text.formats")} footer={t("set.text.formatsLater")}>
        {#each FORMATS as f (f)}
          <ListRow title={t(`set.fmt.${f}`)} subtitle={t(`set.fmt.${f}.ext`)} detail={f === "mac" && !isMac ? t("set.fmt.macOnly") : ""} />
        {/each}
      </List>

      {#if settings}
        <List header={t("set.ocr.title")} footer={text?.ocr.available === false ? t("set.ocr.unavailable") : t("find.ocrHint")}>
          <div class="pad">
            <RadioGroup value={settings.ocr_scope || "scans"} onchange={(v) => set("ocr_scope", v)} options={[
              { value: "scans", label: t("set.ocr.scans") },
              { value: "all", label: t("set.ocr.all") },
              { value: "off", label: t("set.ocr.off") },
            ]} />
          </div>
          {#if settings.ocr_scope !== "off"}
            <ListRow title={t("set.ocr.languages")} subtitle={t("set.ocr.languagesHint")} />
            <div class="pad langs">
              {#each OCR_LANGS as code (code)}
                <Checkbox label={t(`set.ocr.lang.${code}`)} checked={langs.has(code)} onchange={(v) => toggleLang(code, v)} />
              {/each}
            </div>
            {#if text?.ocr.available}
              <ListRow title={t("set.ocr.todo")} detail={formatNumber(text.ocr.todo)}>
                {#snippet trailing()}{#if !textJob && text.ocr.todo}<Button size="small" variant="bordered" onclick={() => start("ocr")}>{t("find.ocr")}</Button>{/if}{/snippet}
              </ListRow>
            {/if}
          {/if}
        </List>
      {/if}

      <List header={t("set.text.reset")} footer={t("set.text.resetHint")}>
        <ListRow title={t("set.text.resetAll")}>
          {#snippet trailing()}<Button size="small" variant="bordered" disabled={!!textJob} onclick={() => (confirmReset = true)}>{t("set.text.resetButton")}</Button>{/snippet}
        </ListRow>
      </List>

    {:else if shown === "assistant"}
      <AssistantSettings {settings} {set} />

    {:else if shown === "photos"}
      <p class="lead mac-body">{t("set.photos.lead")}</p>
      <SegmentedControl value={photoTab} onchange={(v) => navigate(`/settings/photos/${v}`, { replace: true })} ariaLabel={t("set.cat.photos")}
        segments={["ai", "recog", "search", "organize", "library"].map((v) => ({ value: v, label: t(`set.photos.${v}`) }))} />
      <div class="legacy"><PhotoSettings embedded section={photoTab} /></div>

    {:else if shown === "system"}
      <div class="legacy"><PhotoSettings embedded section="system" /></div>

    {:else if shown === "about"}
      <div class="legacy"><PhotoSettings embedded section="about" /></div>
    {/if}
  </div>
  {/if}
</div>

{#if confirmReset}
  <div class="backdrop">
    <Alert title={t("set.text.resetTitle")} message={t("set.text.resetMessage")} actions={[
      { label: t("set.text.resetButton"), role: "default", onPress: doReset },
      { label: t("common.cancel"), role: "cancel", onPress: () => (confirmReset = false) },
    ]} />
  </div>
{/if}

<style>
  .settings { display: grid; grid-template-columns: 220px minmax(0, 1fr); gap: var(--space-6); align-items: start; padding: var(--space-5) var(--space-6) var(--space-8); }
  .settings.narrow { grid-template-columns: minmax(0, 1fr); padding: var(--space-4); }
  .cats { position: sticky; top: var(--space-4); }
  .pane { min-width: 0; max-width: 680px; display: flex; flex-direction: column; gap: var(--space-5); }
  .pane.wide { max-width: 980px; }
  h1 { margin: 0; color: var(--label-primary); }
  .pad { padding: var(--space-2) var(--space-3); }
  .langs { display: flex; flex-wrap: wrap; gap: var(--space-2) var(--space-5); }
  .job { display: inline-flex; align-items: center; gap: var(--space-2); }
  .lead { margin: 0; color: var(--label-secondary); }
  .err { margin: 0; color: var(--system-red); display: flex; align-items: center; gap: var(--space-2); }
  .legacy { min-width: 0; }
  .back { display: flex; margin-left: calc(-1 * var(--space-3)); }
  .backdrop { position: fixed; inset: 0; z-index: 320; display: flex; align-items: center; justify-content: center; background: var(--media-scrim-light); }
</style>
