<script>
  /**
   * 搜尋結果：檔名、資料夾路徑、文件內容、文字辨識、照片描述合在同一份清單。
   * 上方一列篩選標籤（範圍、類型、年份、大小、所在硬碟），是 type:／year:／root: 語法的圖形介面；
   * 可以把目前的搜尋儲存為智慧資料夾。文件文字與文字辨識由使用者按下才開始讀取（只讀取，不修改硬碟）。
   */
  import { untrack } from "svelte";
  import { Alert, Button, Icon, ProgressIndicator, PullDownButton, SegmentedControl } from "../ui/index.js";
  import ResultList from "../views/ResultList.svelte";
  import ContextMenu from "../views/ContextMenu.svelte";
  import QuickLook from "../views/QuickLook.svelte";
  import { createSelection } from "../views/selection.svelte.js";
  import { createFindSource, engineParams, findParams, findHref, loadTextStatus, startExtract, startOcr, stopJob, saveSmartFolder } from "../data/find.svelte.js";
  import { catalog, driveOfRoot, loadCatalog } from "../data/catalog.svelte.js";
  import { openItem, saveOpenAction } from "../data/browse.js";
  import { setFrame, frame, toggleInfo } from "../shell/frame.svelte.js";
  import { t, formatNumber, formatBytes, formatDate, formatDuration } from "../i18n/index.svelte.js";
  import { app, toast, openViewer, refresh } from "../lib/state.svelte.js";
  import { route, navigate } from "../lib/router.svelte.js";

  const KINDS = ["document", "photo", "video", "audio", "archive", "other"];
  const SIZES = ["huge", "large", "medium", "small", "tiny"];
  const thisYear = new Date().getFullYear();
  const YEARS = Array.from({ length: thisYear - 1989 }, (_, i) => thisYear - i);

  // 網址就是搜尋條件：上一頁、智慧資料夾、重新整理都能還原
  const params = $derived(findParams(route.query));
  const engine = $derived(engineParams(route.query));
  const key = $derived(JSON.stringify(engine));
  const hasQuery = $derived(Object.keys(engine).length > 0);
  const source = $derived((key, createFindSource(engine)));
  const sel = createSelection();
  $effect(() => {
    const s = source;
    untrack(() => {
      if (hasQuery) s.start();
      sel.clear();
    });
  });
  const total = $derived(hasQuery ? source.state.total : 0);

  /** 改一個篩選條件（空值＝拿掉）；同一次搜尋只換網址，不新增上一頁的紀錄 */
  function setParam(k, v) {
    const next = { ...params, [k]: v ?? "" };
    navigate(findHref(next, route.query.smart || null), { replace: true });
  }

  // ---- 範圍：從資料夾開始搜尋時，可以切換「這個資料夾」與「所有硬碟」 ----
  const scopeName = $derived.by(() => {
    if (!params.root) return "";
    if (params.path) return params.path.split("/").pop();
    return driveOfRoot(Number(params.root))?.roots.find((r) => r.id === Number(params.root))?.name || t("find.scopeHere");
  });
  const scopeSegments = $derived([{ value: "here", label: scopeName }, { value: "all", label: t("find.scopeAll") }]);

  // ---- 篩選標籤 ----
  const kindItems = $derived([
    { label: t("find.any"), checked: !params.kind, onSelect: () => setParam("kind", "") },
    { separator: true },
    ...KINDS.map((k) => ({ label: t(`kind.${k}`), checked: params.kind === k, onSelect: () => setParam("kind", k) })),
  ]);
  const yearItems = $derived([
    { label: t("find.any"), checked: !params.year, onSelect: () => setParam("year", "") },
    { separator: true },
    ...YEARS.map((y) => ({ label: String(y), checked: params.year === String(y), onSelect: () => setParam("year", String(y)) })),
  ]);
  const sizeItems = $derived([
    { label: t("find.any"), checked: !params.size, onSelect: () => setParam("size", "") },
    { separator: true },
    ...SIZES.map((s) => ({ label: t(`find.size.${s}`), checked: params.size === s, onSelect: () => setParam("size", s) })),
  ]);
  const driveList = $derived(catalog.drives.filter((d) => d.drive_id != null));
  const driveItems = $derived([
    { label: t("find.any"), checked: !params.drive, onSelect: () => setParam("drive", "") },
    { separator: true },
    ...driveList.map((d) => ({ label: d.name, checked: params.drive === String(d.drive_id), onSelect: () => setParam("drive", String(d.drive_id)) })),
  ]);
  const chipLabel = (name, value) => (value ? t("find.chipValue", { name, value }) : name);
  const driveLabel = $derived(driveList.find((d) => String(d.drive_id) === params.drive)?.name || "");
  const filtered = $derived(!!(params.kind || params.year || params.size || params.drive));
  function clearFilters() {
    const next = { ...params, kind: "", year: "", size: "", drive: "" };
    navigate(findHref(next, route.query.smart || null), { replace: true });
  }

  // ---- 文件文字與文字辨識：使用者按下才開始 ----
  let text = $state(null);
  let starting = $state(false);
  const textJob = $derived(app.server?.jobs?.active?.find((j) => j.kind === "extract" || j.kind === "ocr") || null);
  const textQueued = $derived(app.server?.jobs?.queued?.find((j) => j.kind === "extract" || j.kind === "ocr") || null);
  function loadText() {
    loadTextStatus().then((d) => (text = d)).catch(() => {});
  }
  $effect(() => {
    app.refreshKey;
    loadText();
  });
  // 讀取期間每 10 秒更新還剩多少；讀完時重新搜尋（結果可能變多）
  $effect(() => {
    if (!textJob) return;
    const timer = setInterval(loadText, 10000);
    return () => {
      clearInterval(timer);
      loadText();
      untrack(() => { if (hasQuery) source.reload(); });
    };
  });
  async function start(kind) {
    starting = true;
    try {
      await (kind === "ocr" ? startOcr() : startExtract());
      toast(kind === "ocr" ? t("find.ocrStarted") : t("find.extractStarted"));
      refresh();
    } catch (e) {
      toast(e.message, "error");
    } finally {
      starting = false;
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
  const extractTodo = $derived(text?.extract.todo.files || 0);
  const ocrTodo = $derived(text?.ocr.available ? text.ocr.todo : 0);
  const offlineTodo = $derived((text?.extract.offline.files || 0) + (text?.ocr.available ? text.ocr.offline : 0));

  // ---- 狀態列、資訊欄 ----
  const picked = $derived(sel.size === 1 ? source.peek(sel.indexes()[0]) : null);
  const rootPath = (rootId) => app.server?.roots?.find((r) => r.id === rootId)?.path || "";
  const absPath = (item) => [rootPath(item.root_id), item.path].filter(Boolean).join("/");
  $effect(() => {
    const count = !hasQuery || total === null ? "" : source.state.more ? t("find.countMore", { count: formatNumber(total) }) : t("find.count", { count: formatNumber(total) });
    setFrame({
      crumbs: [], location: null,
      status: [count, sel.size ? t("view.selected", { count: formatNumber(sel.size) }) : ""].filter(Boolean).join(" · "),
      info: picked ? { title: picked.name, kind: t(`kind.${picked.kind}`), rows: [
        [t("info.where"), absPath(picked)],
        [t("info.size"), picked.size ? formatBytes(picked.size) : ""],
        [t("info.modified"), picked.mtime ? formatDate(picked.mtime) : ""],
        [t("info.drive"), picked.drive],
        [t("find.matchIn"), t(`find.match.${picked.match}`)],
      ] } : null,
    });
  });

  // ---- 開啟、快速預覽、右鍵選單（和資料夾頁相同的規則） ----
  const rootOnline = (rootId) => !!catalog.drives.some((d) => d.roots.some((r) => r.id === rootId && r.online));
  const folderHref = (item) => `/folders/${item.root_id}${item.folder ? `?path=${encodeURIComponent(item.folder)}` : ""}`;
  let asking = $state(null);
  async function run(item, action) {
    try {
      await openItem(item, action);
    } catch (e) {
      toast(e.message, "error");
    }
  }
  function open(i) {
    const item = source.get(i);
    if (!item) return;
    if (item.image_id) return openViewer([{ id: item.image_id, type: item.kind === "video" ? "video" : "photo", name: item.name }], 0);
    if (!app.server?.local) return toast(t("open.localOnly"));
    if (!rootOnline(item.root_id)) return toast(t("find.connect", { drive: item.drive }));
    const action = app.server?.ui?.open_action;
    if (action === "open" || action === "reveal") run(item, action);
    else asking = item;
  }
  async function choose(action) {
    const item = asking;
    asking = null;
    try {
      await saveOpenAction(action);
    } catch (e) {
      toast(e.message, "error");
    }
    run(item, action);
  }
  let quick = $state(false);
  const quickItem = $derived(quick && sel.focus >= 0 ? source.get(sel.focus) : null);
  function preview(i) {
    if (source.get(i)) quick = true;
  }
  let menu = $state(null);
  async function copyPath(item) {
    const path = absPath(item);
    try {
      await navigator.clipboard.writeText(path);
      toast(t("menu.copied"));
    } catch {
      toast(path);
    }
  }
  function itemMenu(e, i) {
    const item = source.get(i);
    if (!item) return;
    const online = rootOnline(item.root_id);
    const local = !!app.server?.local;
    menu = { x: e.clientX, y: e.clientY, items: [
      { label: t("menu.open"), disabled: !item.image_id && (!local || !online), onSelect: () => open(i) },
      { label: t("menu.quickLook"), shortcut: t("key.space"), onSelect: () => preview(i) },
      { label: t("find.showInFolder"), onSelect: () => navigate(folderHref(item)) },
      { label: t("menu.reveal"), disabled: !local || !online, onSelect: () => run(item, "reveal") },
      { separator: true },
      { label: t("menu.copyPath"), onSelect: () => copyPath(item) },
      { label: t("menu.info"), shortcut: "⌘I", onSelect: () => { if (!frame.info) toggleInfo(); } },
    ] };
  }

  // ---- 儲存為智慧資料夾 ----
  let saving = $state(null); // { name, error }
  function askSave() {
    saving = { name: engine.q || t("find.untitled"), error: "" };
  }
  async function save() {
    const name = saving.name.trim();
    if (!name) {
      saving.error = t("find.nameNeeded");
      return;
    }
    try {
      const { id } = await saveSmartFolder(name, engine);
      saving = null;
      toast(t("find.saved", { name }));
      await loadCatalog();
      navigate(findHref(params, id), { replace: true });
    } catch (e) {
      saving.error = e.message;
    }
  }
  const smart = $derived(route.query.smart ? catalog.smart.find((s) => String(s.id) === route.query.smart) : null);

  // 打字中（200 毫秒延遲＋查詢）超過 300 毫秒才顯示載入中
  let slow = $state(false);
  $effect(() => {
    slow = false;
    if (!hasQuery || total !== null) return;
    const timer = setTimeout(() => (slow = true), 300);
    return () => clearTimeout(timer);
  });
  const EXAMPLES = ["find.ex.words", "find.ex.phrase", "find.ex.type", "find.ex.year", "find.ex.root"];
</script>

<div class="findpage">
  <div class="bar mac-callout">
    {#if smart}<span class="smart"><Icon name="magnifyingglass" size={12} weight="semibold" />{smart.name}</span>{/if}
    <span class="lead">{t("find.in")}</span>
    {#if params.root}
      <SegmentedControl size="small" segments={scopeSegments} value={params.all ? "all" : "here"} ariaLabel={t("find.scope")}
        onchange={(v) => setParam("all", v === "all" ? "1" : "")} />
    {:else}
      <span class="scope">{t("find.scopeAll")}</span>
    {/if}
    <span class="sep" aria-hidden="true"></span>
    <PullDownButton size="small" label={chipLabel(t("find.kind"), params.kind ? t(`kind.${params.kind}`) : "")} items={kindItems} menuWidth={180}
      class={params.kind ? "fchip on" : "fchip"} />
    <PullDownButton size="small" label={chipLabel(t("find.year"), params.year || "")} items={yearItems} menuWidth={140} class={params.year ? "fchip on" : "fchip"} />
    <PullDownButton size="small" label={chipLabel(t("find.size"), params.size ? t(`find.size.${params.size}`) : "")} items={sizeItems} menuWidth={200}
      class={params.size ? "fchip on" : "fchip"} />
    {#if driveList.length > 1}
      <PullDownButton size="small" label={chipLabel(t("find.drive"), driveLabel)} items={driveItems} menuWidth={220} class={params.drive ? "fchip on" : "fchip"} />
    {/if}
    {#if filtered}<Button size="small" variant="borderless" onclick={clearFilters}>{t("find.clearFilters")}</Button>{/if}
    <span class="grow"></span>
    {#if !smart}<Button size="small" variant="bordered" icon="plus" disabled={!hasQuery} onclick={askSave}>{t("find.save")}</Button>{/if}
  </div>

  {#if textJob || textQueued}
    <section class="text mac-callout" aria-live="polite">
      <ProgressIndicator kind="circular" size="small" value={textJob?.total ? textJob.done / textJob.total : undefined} label={t(textJob?.kind === "ocr" || textQueued?.kind === "ocr" ? "find.ocring" : "find.extracting")} />
      <div class="grow">
        <b>{t(textJob?.kind === "ocr" || (!textJob && textQueued?.kind === "ocr") ? "find.ocring" : "find.extracting")}</b>
        <span class="sub">{textJob?.total ? t("find.progress", { done: formatNumber(textJob.done), total: formatNumber(textJob.total) }) : t("dupes.waiting")}{textJob?.eta ? ` · ${t("dupes.remaining", { time: formatDuration(textJob.eta) })}` : ""}</span>
      </div>
      <Button size="small" variant="bordered" disabled={!textJob} onclick={stop}>{t("drives.stop")}</Button>
    </section>
  {:else if extractTodo}
    <section class="text mac-callout">
      <Icon name="document" size={16} />
      <div class="grow">
        <b>{t("find.extractTodo", { count: formatNumber(extractTodo) })}</b>
        <span class="sub">{t("find.extractHint")}</span>
      </div>
      <Button size="small" variant="borderedProminent" disabled={starting} onclick={() => start("extract")}>{t("find.extract")}</Button>
    </section>
  {:else if ocrTodo}
    <section class="text mac-callout">
      <Icon name="photo" size={16} />
      <div class="grow">
        <b>{t("find.ocrTodo", { count: formatNumber(ocrTodo) })}</b>
        <span class="sub">{t("find.ocrHint")}</span>
      </div>
      <Button size="small" variant="bordered" disabled={starting} onclick={() => start("ocr")}>{t("find.ocr")}</Button>
    </section>
  {/if}
  {#if offlineTodo && !textJob && (extractTodo || ocrTodo)}
    <p class="offline mac-callout">{t("find.offline", { count: formatNumber(offlineTodo) })}</p>
  {/if}

  <div class="content">
    {#if !hasQuery}
      <div class="state">
        <Icon name="magnifyingglass" size={32} />
        <h2 class="mac-title-3">{t("find.emptyTitle")}</h2>
        <p class="mac-body">{t("find.emptyHint")}</p>
        <ul class="examples mac-callout">
          {#each EXAMPLES as ex (ex)}<li><code>{t(`${ex}.code`)}</code><span>{t(ex)}</span></li>{/each}
        </ul>
      </div>
    {:else if source.state.error}
      <div class="state" role="alert">
        <h2 class="mac-title-3">{t("view.error")}</h2>
        <p class="mac-body">{source.state.error}</p>
        <Button variant="bordered" onclick={() => source.retry()}>{t("view.retry")}</Button>
      </div>
    {:else if total === null}
      {#if slow}<div class="state"><ProgressIndicator kind="spinner" label={t("view.loading")} /></div>{/if}
    {:else if total === 0}
      <div class="state">
        <h2 class="mac-title-3">{engine.q ? t("find.none", { q: engine.q }) : t("find.noneFiltered")}</h2>
        {#if params.root && !params.all}
          <p class="mac-body">{t("find.tryAll")}</p>
          <Button variant="bordered" onclick={() => setParam("all", "1")}>{t("find.searchAll")}</Button>
        {:else if filtered}
          <p class="mac-body">{t("find.tryFewer")}</p>
          <Button variant="bordered" onclick={clearFilters}>{t("find.clearFilters")}</Button>
        {/if}
        {#if extractTodo}<p class="mac-body">{t("find.maybeUnread", { count: formatNumber(extractTodo) })}</p>{/if}
      </div>
    {:else}
      <ResultList {source} {sel} onopen={open} onpreview={preview} oncontext={itemMenu} />
    {/if}
  </div>
</div>

{#if quickItem}
  <QuickLook item={quickItem} online={rootOnline(quickItem.root_id)} driveName={quickItem.drive} canOpen={!!app.server?.local}
    onclose={() => (quick = false)} onmove={(d) => sel.moveTo(sel.focus + d, total ?? 0)}
    onopen={() => { const i = sel.focus; quick = false; open(i); }} onreveal={() => run(quickItem, "reveal")} />
{/if}
{#if menu}<ContextMenu x={menu.x} y={menu.y} items={menu.items} onclose={() => (menu = null)} />{/if}
{#if asking}
  <div class="backdrop">
    <Alert title={t("open.askTitle")} message={t("open.askMessage")} actions={[
      { label: t("open.optOpen"), role: "default", onPress: () => choose("open") },
      { label: t("open.optReveal"), onPress: () => choose("reveal") },
      { label: t("common.cancel"), role: "cancel", onPress: () => (asking = null) },
    ]} />
  </div>
{/if}
{#if saving}
  <div class="backdrop">
    <Alert title={t("find.saveTitle")} message={t("find.saveMessage")}
      textField={{ placeholder: t("find.namePlaceholder"), value: saving.name, onchange: (v) => { saving.name = v; saving.error = ""; }, error: saving.error }}
      actions={[
        { label: t("find.save"), role: "default", onPress: save },
        { label: t("common.cancel"), role: "cancel", onPress: () => (saving = null) },
      ]} />
  </div>
{/if}

<style>
  .findpage { height: 100%; min-height: 0; display: flex; flex-direction: column; }
  .bar { flex: none; display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-2); padding: var(--space-2) var(--space-4);
    border-bottom: 1px solid var(--separator); color: var(--label-secondary); }
  .lead { color: var(--label-secondary); }
  .scope { color: var(--label-primary); font-weight: 600; }
  .smart { display: inline-flex; align-items: center; gap: var(--space-1); margin-right: var(--space-2); color: var(--label-primary); font-weight: 600; }
  .sep { width: 1px; height: var(--space-4); background: var(--separator); margin: 0 var(--space-1); }
  .grow { flex: 1; min-width: 0; }
  .bar :global(.fchip.on .lg-btn) { color: var(--accent); box-shadow: inset 0 0 0 1px var(--accent); }
  .text { flex: none; display: flex; align-items: center; gap: var(--space-3); margin: var(--space-3) var(--space-4) 0; padding: var(--space-2) var(--space-3);
    border-radius: var(--radius-md); background: var(--fill-tertiary); color: var(--label-primary); }
  .text .grow { display: flex; flex-direction: column; }
  .sub { color: var(--label-secondary); }
  .offline { flex: none; margin: var(--space-1) var(--space-4) 0; color: var(--label-secondary); }
  .content { flex: 1; min-height: 0; display: flex; flex-direction: column; padding-top: var(--space-2); }
  .state { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: var(--space-3); padding: var(--space-8);
    text-align: center; color: var(--label-secondary); }
  .state h2 { margin: 0; color: var(--label-primary); }
  .state p { margin: 0; max-width: 460px; }
  .examples { margin: 0; padding: 0; list-style: none; display: grid; grid-template-columns: auto 1fr; gap: var(--space-2) var(--space-3); text-align: left; }
  .examples li { display: contents; }
  .examples code { justify-self: start; padding: 0 var(--space-1); border-radius: var(--radius-xs); background: var(--fill-tertiary); color: var(--label-primary); font-family: var(--font-mono); }
  .backdrop { position: fixed; inset: 0; z-index: 320; display: flex; align-items: center; justify-content: center; background: var(--media-scrim-light); }
</style>
