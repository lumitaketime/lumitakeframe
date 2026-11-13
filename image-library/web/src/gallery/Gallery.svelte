<script>
  /**
   * 基礎元件展示頁：只在開發時使用，用來檢查四個主題、鍵盤焦點與兩種語言。
   * 這裡的「主題」切換只是為了檢查；App 本身一律跟隨系統，不提供外觀開關。
   */
  import {
    Alert, Button, Checkbox, Glass, Icon, List, ListRow, Menu, Popover, PopUpButton, ProgressIndicator, PullDownButton, RadioGroup,
    SearchField, SegmentedControl, Sheet, Sidebar, Slider, Stepper, TextField, Toggle, Toolbar, iconNames,
  } from "../ui/index.js";
  import Wordmark from "../components/Wordmark.svelte";
  import { t, i18n, setLocale, LOCALES, formatBytes, formatDate, formatNumber } from "../i18n/index.svelte.js";

  const params = new URLSearchParams(location.search);
  let theme = $state(params.get("theme") || "system");
  if (params.get("lang")) setLocale(params.get("lang"));
  $effect(() => {
    if (theme === "system") delete document.documentElement.dataset.theme;
    else document.documentElement.dataset.theme = theme;
  });

  let view = $state("list");
  let auto = $state(false);
  let compare = $state(true);
  let hidden = $state(true);
  let when = $state("night");
  let thumb = $state(128);
  let parallel = $state(2);
  let name = $state("");
  let query = $state("");
  let sort = $state("size");
  let nav = $state("all");
  let loading = $state(false);

  const TYPE_STYLES = ["mac-large-title-em", "mac-title-1", "mac-title-2", "mac-title-3", "mac-headline", "mac-body", "mac-callout", "mac-subheadline", "mac-caption-1"];
  const KINDS = ["video", "photo", "document", "audio", "archive", "other", "folder", "duplicate"];
  const SWATCHES = ["accent", "destructive", "label-primary", "label-secondary", "label-tertiary", "window-bg", "control-bg", "separator", "selection-muted"];
</script>

<main class="wrap">
  <header class="head">
    <div>
      <Wordmark size={30} />
      <h1 class="mac-large-title-em">{t("gallery.title")}</h1>
      <p class="mac-body intro">{t("gallery.intro")} {t("gallery.focusHint")}</p>
    </div>
    <div class="switches">
      <PopUpButton label={t("gallery.theme")} bind:value={theme} width={170}
        options={["system", "light", "dark", "light-hc", "dark-hc"].map((v) => ({ value: v, label: t(`gallery.theme.${v}`) }))} />
      <PopUpButton label={t("gallery.language")} value={i18n.locale} onchange={setLocale} width={120} options={LOCALES.map((l) => ({ value: l.id, label: l.label }))} />
    </div>
  </header>

  <section>
    <h2 class="mac-title-2">{t("gallery.buttons")}</h2>
    <div class="row">
      <Button variant="borderedProminent">{t("gallery.addToCatalog")}</Button>
      <Button>{t("gallery.scan")}</Button>
      <Button role="destructive">{t("gallery.moveToTrash")}</Button>
      <Button variant="borderless">{t("gallery.learnMore")}</Button>
      <Button disabled>{t("gallery.scan")}</Button>
      <Button {loading} loadingLabel={t("gallery.scanning")} onclick={() => { loading = true; setTimeout(() => (loading = false), 2000); }}>{t("gallery.scan")}</Button>
      <Button size="small">{t("gallery.scan")}</Button>
      <Button size="large" variant="borderedProminent">{t("gallery.addToCatalog")}</Button>
      <Button icon="share" iconOnly aria-label={t("gallery.share")} />
      <Button icon="ellipsis" iconOnly aria-label={t("gallery.more")} />
    </div>
  </section>

  <section>
    <h2 class="mac-title-2">{t("gallery.controls")}</h2>
    <div class="grid">
      <div class="col">
        <Toggle label={t("gallery.autoAnalyze")} bind:checked={auto} />
        <Toggle label={t("gallery.compareContent")} bind:checked={compare} />
        <Checkbox label={t("gallery.skipHidden")} bind:checked={hidden} />
        <Checkbox label={t("gallery.someDrives")} checked="mixed" />
        <RadioGroup label={t("gallery.when")} bind:value={when} options={[{ value: "always", label: t("gallery.when.always") }, { value: "night", label: t("gallery.when.night") }]} />
      </div>
      <div class="col">
        <SegmentedControl ariaLabel={t("gallery.view")} bind:value={view} segments={[
          { value: "icons", icon: "grid", ariaLabel: t("gallery.view.icons") }, { value: "list", icon: "list", ariaLabel: t("gallery.view.list") },
          { value: "columns", icon: "columns", ariaLabel: t("gallery.view.columns") }, { value: "tree", icon: "tree", ariaLabel: t("gallery.view.tree") },
          { value: "map", icon: "treemap", ariaLabel: t("gallery.view.map") }]} />
        <SegmentedControl ariaLabel={t("gallery.sort")} bind:value={sort} segments={["name", "size", "date"].map((v) => ({ value: v, label: t(`gallery.sort.${v}`) }))} />
        <Slider label={t("gallery.thumbSize")} bind:value={thumb} min={64} max={256} minIcon="photo" maxIcon="photo" valueLabel={(v) => `${v}`} />
        <Stepper label={t("gallery.parallel")} bind:value={parallel} min={1} max={4} />
      </div>
    </div>
  </section>

  <section>
    <h2 class="mac-title-2">{t("gallery.fields")}</h2>
    <div class="grid">
      <div class="col">
        <TextField label={t("gallery.catalogLocation")} value="~/.rememor" hint={t("gallery.catalogHint")} leadingIcon="folder" width={300} />
        <TextField label={t("gallery.driveName")} bind:value={name} error={name ? "" : t("gallery.nameError")} width={300} />
      </div>
      <div class="col">
        <SearchField placeholder={t("gallery.searchPlaceholder")} bind:value={query} width={300} />
        <SearchField placeholder={t("gallery.searchPlaceholder")} tokens={[t("gallery.videos"), "2019"]} onremovetoken={() => {}} width={300} />
      </div>
    </div>
  </section>

  <section>
    <h2 class="mac-title-2">{t("gallery.progress")}</h2>
    <div class="row">
      <div class="bar"><ProgressIndicator value={0.62} label={t("gallery.scanning")} /></div>
      <div class="bar"><ProgressIndicator label={t("gallery.scanning")} /></div>
      <ProgressIndicator kind="circular" value={0.62} />
      <ProgressIndicator kind="spinner" />
    </div>
  </section>

  <section>
    <h2 class="mac-title-2">{t("gallery.menus")}</h2>
    <div class="row top">
      <PopUpButton label={t("gallery.sort")} bind:value={sort} options={["name", "size", "date"].map((v) => ({ value: v, label: t(`gallery.sort.${v}`) }))} />
      <PullDownButton label={t("gallery.actions")} items={[{ label: t("gallery.reveal") }, { label: t("gallery.copyPath") }, { separator: true }, { label: t("gallery.markDelete"), destructive: true }]} />
      <Menu width={230} items={[
        { label: t("gallery.reveal"), icon: "folder", shortcut: "⌘R" }, { label: t("gallery.copyPath"), icon: "share", shortcut: "⌥⌘C" },
        { label: t("gallery.showCopies"), icon: "duplicate" }, { separator: true },
        { label: t("gallery.markDelete"), icon: "trash", destructive: true }, { label: t("gallery.getInfo"), icon: "info", shortcut: "⌘I", disabled: true }]} />
    </div>
  </section>

  <section>
    <h2 class="mac-title-2">{t("gallery.list")}</h2>
    <div class="grid">
      <List header={t("gallery.drives")} footer={t("gallery.catalogHint")}>
        <ListRow title={t("gallery.driveA")} subtitle={`ExFAT・${formatBytes(2.4e12)}`} icon="external-drive" iconTint="blue" accessory="disclosure" onclick={() => {}} />
        <ListRow title={t("gallery.driveB")} subtitle={t("gallery.readOnly")} detail={t("gallery.offline")} icon="external-drive" iconTint="gray-1" accessory="disclosure" onclick={() => {}} />
        <ListRow title={t("gallery.autoAnalyze")}>{#snippet trailing()}<Toggle bind:checked={auto} aria-label={t("gallery.autoAnalyze")} />{/snippet}</ListRow>
      </List>
      <List appearance="plain" alternating>
        <ListRow title="自然科報告.docx" detail={formatBytes(1.04e6)} icon="document" iconTint="blue" onclick={() => {}} />
        <ListRow title="畢業旅行.mov" detail={formatBytes(3.2e9)} icon="video" iconTint="indigo" selected onclick={() => {}} />
        <ListRow title="備份.zip" detail={formatBytes(15e6)} icon="archive" iconTint="brown" onclick={() => {}} />
        <ListRow title="IMG_0042.jpg" detail={formatDate(new Date(2026, 10, 10))} icon="photo" iconTint="teal" disabled />
      </List>
    </div>
  </section>

  <section>
    <h2 class="mac-title-2">{t("gallery.glass")}</h2>
    <div class="stage">
      <div class="stage-content" aria-hidden="true">
        {#each ["indigo", "mint", "blue", "pink", "brown", "orange", "yellow", "teal", "indigo", "mint", "blue", "pink"] as c, i (i)}<span style:background="var(--system-{c})"></span>{/each}
      </div>
      <div class="stage-side">
        <Sidebar bind:value={nav} width={210} sections={[
          { title: t("gallery.library"), items: [
            { value: "all", label: t("gallery.allFiles"), icon: "folder", badge: formatNumber(128432) }, { value: "photos", label: t("gallery.photos"), icon: "photo" },
            { value: "dup", label: t("gallery.duplicates"), icon: "duplicate", badge: 36 }, { value: "del", label: t("gallery.pending"), icon: "trash" }] },
          { title: t("gallery.kinds"), items: [
            { value: "video", label: t("gallery.videos"), icon: "video" }, { value: "doc", label: t("gallery.documents"), icon: "document" }, { value: "music", label: t("gallery.music"), icon: "music-note" }] },
          { title: t("gallery.drives"), items: [
            { value: "a", label: t("gallery.driveA"), icon: "external-drive" },
            { value: "b", label: t("gallery.driveB"), icon: "external-drive", muted: true, trailing: t("gallery.offline") }] }]} />
      </div>
      <div class="stage-bar">
        <Toolbar title={t("gallery.allFiles")} subtitle={t("format.items", { count: formatNumber(128432) })}
          leading={[[{ icon: "chevron-left", label: t("common.back") }, { icon: "chevron-right", label: t("common.forward"), disabled: true }]]}
          trailing={[[{ icon: "share", label: t("gallery.share") }, { icon: "info", label: t("gallery.getInfo") }], [{ icon: "plus", label: t("gallery.addToCatalog"), prominent: true }]]}>
          {#snippet centerExtra()}
            <Glass shape="capsule" class="seg-glass"><SegmentedControl size="small" ariaLabel={t("gallery.view")} bind:value={view} segments={[
              { value: "icons", icon: "grid", ariaLabel: t("gallery.view.icons") }, { value: "list", icon: "list", ariaLabel: t("gallery.view.list") }, { value: "columns", icon: "columns", ariaLabel: t("gallery.view.columns") }]} /></Glass>
          {/snippet}
          {#snippet trailingExtra()}<SearchField glass placeholder={t("common.search")} width={160} />{/snippet}
        </Toolbar>
      </div>
    </div>
  </section>

  <section>
    <h2 class="mac-title-2">{t("gallery.dialogs")}</h2>
    <div class="row top dialogs">
      <Alert title={t("gallery.alertTitle")} message={t("gallery.alertMessage")}
        actions={[{ label: t("common.cancel"), role: "cancel" }, { label: t("gallery.moveToTrash"), role: "destructive" }]} />
      <Sheet title={t("gallery.sheetTitle")} doneLabel={t("gallery.add")}><p class="mac-body">{t("gallery.sheetBody")}</p></Sheet>
      <Popover title={t("gallery.popoverTitle")} width={240}><p class="mac-callout pop">{t("gallery.popoverBody")}</p><ProgressIndicator value={0.6} label={t("gallery.popoverTitle")} /></Popover>
    </div>
  </section>

  <section>
    <h2 class="mac-title-2">{t("gallery.type")}</h2>
    <div class="grid">
      <div class="col tight">{#each TYPE_STYLES as s (s)}<div class={s}>{t("gallery.sample")} <span class="mac-caption-1 dim">{s}</span></div>{/each}</div>
      <div class="col">
        <div class="swatches">{#each SWATCHES as s (s)}<span class="sw"><i style:background="var(--{s})"></i><span class="mac-caption-1">{s}</span></span>{/each}</div>
        <div class="swatches">{#each KINDS as k (k)}<span class="sw"><i style:background="var(--kind-{k})"></i><span class="mac-caption-1">kind-{k}</span></span>{/each}</div>
        <div class="icons">{#each iconNames as n (n)}<span title={n}><Icon name={n} size={18} /></span>{/each}</div>
      </div>
    </div>
  </section>
</main>

<style>
  :global(body) { overflow: auto; }
  .wrap { max-width: 1040px; margin: 0 auto; padding: var(--space-6) var(--space-5) var(--space-10); display: flex; flex-direction: column; gap: var(--space-8); }
  .head { display: flex; justify-content: space-between; align-items: flex-start; gap: var(--space-5); flex-wrap: wrap; }
  .head h1 { margin: var(--space-3) 0 var(--space-1); }
  .intro { margin: 0; color: var(--label-secondary); max-width: 60ch; }
  .switches { display: flex; flex-direction: column; gap: var(--space-2); align-items: flex-end; }
  section { background: var(--control-bg); border-radius: var(--radius-lg); padding: var(--space-5); box-shadow: inset 0 0 0 1px var(--separator); }
  h2 { margin: 0 0 var(--space-4); font-weight: 700; }
  .row { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-3); }
  .row.top { align-items: flex-start; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: var(--space-6); align-items: start; }
  .col { display: flex; flex-direction: column; gap: var(--space-3); align-items: flex-start; min-width: 0; }
  .col.tight { gap: var(--space-2); }
  .bar { width: 200px; }
  .dim { color: var(--label-secondary); }
  .pop { margin: 0 0 var(--space-2); color: var(--label-glass-secondary); }
  .dialogs { gap: var(--space-6); }
  .dialogs :global(.lg-sheet) { width: 320px; }
  .stage { position: relative; height: 380px; border-radius: var(--radius-lg); overflow: hidden; background: var(--window-bg); }
  .stage-content { position: absolute; inset: 0; display: grid; grid-template-columns: repeat(4, 1fr); gap: var(--space-1); padding: var(--space-1); opacity: .85; }
  .stage-content span { border-radius: var(--radius-sm); }
  .stage-side { position: absolute; top: var(--space-2); left: var(--space-2); bottom: var(--space-2); display: flex; }
  .stage-bar { position: absolute; top: 0; left: 226px; right: 0; }
  .stage :global(.seg-glass) { display: inline-flex; padding: 2px; }
  .stage :global(.seg-glass .lg-seg) { background: transparent; box-shadow: none; }
  .swatches { display: flex; flex-wrap: wrap; gap: var(--space-3); }
  .sw { display: inline-flex; flex-direction: column; align-items: center; gap: var(--space-1); width: 84px; text-align: center; color: var(--label-secondary); }
  .sw i { width: 44px; height: 28px; border-radius: var(--radius-sm); box-shadow: inset 0 0 0 1px var(--separator); }
  .icons { display: flex; flex-wrap: wrap; gap: var(--space-2); color: var(--label-primary); }
  .icons span { display: inline-flex; align-items: center; justify-content: center; width: var(--target-mac); height: var(--target-mac); border-radius: var(--radius-sm); background: var(--fill-quaternary); }
</style>
