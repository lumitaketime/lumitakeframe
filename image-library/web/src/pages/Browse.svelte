<script>
  import { untrack } from "svelte";
  /**
   * 瀏覽頁：「所有檔案」、每顆硬碟的資料夾、跨硬碟的類型，共用同一頁，用工具列切換檢視。
   * scope：{type: "roots"}｜{type: "folder", root, path}｜{type: "kind", kind}
   * 這一頁只組合檢視元件與資料；資料都從資料層來，硬碟沒接上也能看。
   */
  import { Alert, Button, ProgressIndicator, SegmentedControl } from "../ui/index.js";
  import ItemList from "../views/ItemList.svelte";
  import ItemGrid from "../views/ItemGrid.svelte";
  import ItemTree from "../views/ItemTree.svelte";
  import ItemGraph from "../views/ItemGraph.svelte";
  import { createGraph } from "../data/graph.svelte.js";
  import ItemColumns from "../views/ItemColumns.svelte";
  import ItemUsage from "../views/ItemUsage.svelte";
  import { buildTree } from "../views/usage.js";
  import { createTreeSource } from "../data/tree.svelte.js";
  import ContextMenu from "../views/ContextMenu.svelte";
  import QuickLook from "../views/QuickLook.svelte";
  import { createSelection } from "../views/selection.svelte.js";
  import { prefs, viewFor, toggleColumn, COLUMNS, setTreeStyle } from "../views/prefs.svelte.js";
  import { createItemSource, createStaticSource, loadGroups } from "../data/items.svelte.js";
  import { buildSections } from "../views/sections.js";
  import { catalog, driveOfRoot } from "../data/catalog.svelte.js";
  import { loadLocation, openItem, saveOpenAction, setLabel, pinFolder, pinLink, fileHref, DRAG_FOLDER, DRAG_LINK, loadUsageTree, loadKinds } from "../data/browse.js";
  import { loadCatalog } from "../data/catalog.svelte.js";
  import { setFrame, frame, toggleInfo } from "../shell/frame.svelte.js";
  import { t, formatNumber, formatBytes, formatDate } from "../i18n/index.svelte.js";
  import { app, toast, openViewer, refresh } from "../lib/state.svelte.js";
  import { navigate, route } from "../lib/router.svelte.js";
  import { api } from "../lib/api.js";

  let { scope } = $props();

  const place = $derived(scope.type === "folder" ? `folder:${scope.root}:${scope.path}` : scope.type === "kind" ? `kind:${scope.kind}`
    : scope.type === "label" ? `label:${scope.label}` : "roots");
  const view = $derived(viewFor(place));
  const sel = createSelection();
  // 網址帶 select＝某個名稱（例如從 Spotlight、助理打開）：選好那一項並捲到它
  let selected = "";
  $effect(() => {
    const name = route.query.select;
    if (scope.type !== "folder" || !name) return;
    const key = `${scope.root}:${scope.path}:${name}`;
    if (selected === key) return;
    selected = key;
    api("/api/items/position", { params: { root: scope.root, path: scope.path, name, sort: prefs.sort, desc: prefs.desc ? "true" : undefined,
      group: grouping || undefined }, quiet: true })
      .then((d) => { if (d.index != null) sel.click(d.index); }).catch(() => {});
  });

  // 「所有檔案」最上層：每個資料夾來源一項（硬碟沒接上也列出）
  const rootItems = $derived(catalog.drives.flatMap((d) => d.roots.map((r) => ({
    type: "folder", id: `root:${r.id}`, name: r.name, kind: "folder", icon: r.online ? "drive" : "drive-offline", size: r.bytes, files: r.files,
    root_id: r.id, path: "", kindLabel: t("info.kind.drive"), note: r.online ? "" : t("drive.offline"),
  }))));
  let rev = $state(0); // 在標籤頁改了標籤：重新讀取，讓不再屬於這個標籤的項目消失
  // 引擎看的範圍；分組只用在圖像與列表，其他檢視不分組
  const engineScope = $derived(scope.type === "kind" ? { kind: scope.kind } : scope.type === "label" ? (rev, { label: scope.label })
    : scope.type === "folder" ? { root: scope.root, path: scope.path } : null);
  const grouping = $derived(engineScope && prefs.group !== "none" && (view === "icons" || view === "list") ? prefs.group : "");
  const source = $derived(
    scope.type === "roots" ? createStaticSource(rootItems)
      : createItemSource(engineScope, prefs.sort, prefs.desc, grouping));
  // 分組只用在圖像與列表；載入每組的數量，畫出每一段的標題
  let groupData = $state(null);
  $effect(() => {
    groupData = null;
    if (!grouping) return;
    const want = { scope: engineScope, group: grouping };
    app.refreshKey;
    rev;
    loadGroups(want.scope, want.group).then((d) => {
      if (grouping === want.group && engineScope === want.scope) groupData = d;
    }).catch(() => {});
  });
  const sections = $derived(grouping && groupData ? buildSections(groupData, grouping, t) : null);
  // 樹狀檢視：把展開的資料夾攤平成一條清單；佔比檢視：兩層的大小統計。兩者的介面和一般來源相同
  const treeSource = $derived(scope.type === "folder" && view === "tree" && prefs.treeStyle === "list" ? createTreeSource(scope.root, scope.path, prefs.sort, prefs.desc) : null);
  const graph = $derived(scope.type === "folder" && view === "tree" && prefs.treeStyle === "graph" ? createGraph(scope.root, scope.path, t, formatNumber) : null);
  let usage = $state(null);
  let usageError = $state("");
  $effect(() => {
    usage = null;
    usageError = "";
    if (scope.type !== "folder" || view !== "treemap") return;
    const { root, path } = scope;
    app.refreshKey;
    // 依畫面大小決定拆多細：小到不到幾個像素的才合併成「其他」
    const px = Math.max(400_000, (window.innerWidth || 1400) * (window.innerHeight || 900) * 0.8);
    loadUsageTree(root, path, { px }).then((d) => {
      if (scope.type === "folder" && scope.root === root && scope.path === path) usage = d;
    }).catch((e) => (usageError = e.message));
  });
  const chart = $derived(usage ? buildTree(usage, scope.root, t, formatNumber) : { units: [], kids: [], top: [] });
  const usageSource = $derived(createStaticSource(chart.units));
  /** 目前這個檢視在用的來源：選取、開啟、右鍵選單、快速預覽都透過它 */
  const active = $derived(graph ? graph : view === "tree" && treeSource ? treeSource : view === "treemap" && scope.type === "folder" ? usageSource : source);
  $effect(() => {
    const now = active;
    untrack(() => {
      source.start();
      if (now !== source) now.start(); // 連線圖、清單式樹狀圖各自從第一層開始讀
      sel.clear();
    });
  });
  const total = $derived(view === "treemap" && scope.type === "folder" && !usage ? null : active.state.total);

  // 超過 300 毫秒還沒讀到才顯示「載入中」，避免一閃而過
  let slow = $state(false);
  $effect(() => {
    slow = false;
    if (total !== null) return;
    const timer = setTimeout(() => (slow = true), 300);
    return () => clearTimeout(timer);
  });

  // 目前位置（路徑列、狀態列、資訊欄）
  let loc = $state(null);
  let locError = $state("");
  $effect(() => {
    loc = null;
    locError = "";
    if (scope.type !== "folder") return;
    const { root, path } = scope;
    loadLocation(root, path).then((d) => {
      if (scope.type === "folder" && scope.root === root && scope.path === path) loc = d;
    }).catch((e) => (locError = e.message));
  });

  const rootPath = (rootId) => app.server?.roots?.find((r) => r.id === rootId)?.path || "";
  const absPath = (item) => [rootPath(item.root_id), item.path].filter(Boolean).join("/");
  const driveName = (item) => driveOfRoot(item.root_id)?.name || "";
  const hrefOf = (rootId, path) => `/folders/${rootId}${path ? `?path=${encodeURIComponent(path)}` : ""}`;

  const picked = $derived(sel.size === 1 ? active.get(sel.indexes()[0]) : null);
  // 資訊欄打開時才讀「各類型佔多少」（要統計整個子樹，不需要時不算）
  let kinds = $state(null);
  $effect(() => {
    kinds = null;
    if (scope.type !== "folder" || !frame.info) return;
    const { root, path } = scope;
    app.refreshKey;
    loadKinds(root, path).then((d) => {
      if (scope.type === "folder" && scope.root === root && scope.path === path) kinds = d;
    }).catch(() => {});
  });
  $effect(() => {
    const drive = scope.type === "folder" ? driveOfRoot(scope.root) : null;
    const online = loc ? loc.root.online : drive?.online;
    const count = total === null ? "" : t("view.count", { count: formatNumber(total) });
    const status = [count, sel.size ? t("view.selected", { count: formatNumber(sel.size) }) : "",
      loc && !sel.size ? formatBytes(loc.bytes) : ""].filter(Boolean).join(" · ");
    let info = null;
    if (picked) {
      info = {
        title: picked.name,
        kind: picked.kindLabel || (picked.type === "folder" ? t("info.kind.folder") : t(`kind.${picked.kind}`)),
        rows: [
          [t("info.where"), absPath(picked)],
          [t("info.size"), picked.size ? formatBytes(picked.size) : ""],
          [t("info.files"), picked.type === "folder" && picked.files != null ? formatNumber(picked.files) : ""],
          [t("info.modified"), picked.mtime ? formatDate(picked.mtime) : ""],
          [t("info.drive"), driveName(picked)],
        ],
      };
    } else if (loc) {
      info = {
        title: loc.name,
        kind: loc.path ? t("info.kind.folder") : t("info.kind.drive"),
        rows: [
          [t("info.where"), loc.abs_path],
          [t("info.files"), formatNumber(loc.files)],
          [t("info.size"), formatBytes(loc.bytes)],
          [t("info.drive"), loc.drive?.name || loc.root.name],
          [t("info.format"), loc.drive?.fs_label],
          [t("info.capacity"), loc.drive?.capacity ? formatBytes(loc.drive.capacity) : ""],
          [t("info.status"), (loc.root.online ? t("drive.online") : t("drive.offline")) + (loc.root.scan_state === "partial" ? ` · ${t("drive.incomplete")}` : "")],
          [t("info.lastScan"), loc.root.last_scan ? formatDate(new Date(loc.root.last_scan)) : t("drive.neverScanned")],
        ],
        kinds: kinds || [],
      };
    }
    const driveLabel = loc?.drive?.name;
    const sameName = !driveLabel || driveLabel === loc?.root.name;
    setFrame({
      browse: place,
      crumbs: !loc ? [] : [
        { label: t("nav.allFiles"), href: "/folders" },
        ...(sameName ? [] : [{ label: driveLabel, href: hrefOf(scope.root, ""), icon: online ? "external-drive-fill" : "external-drive" }]),
        { label: loc.root.name, href: hrefOf(scope.root, ""), icon: sameName ? (online ? "external-drive-fill" : "external-drive") : "folder" },
        ...loc.crumbs.map((c) => ({ label: c.name, href: hrefOf(scope.root, c.path) })),
      ],
      status,
      location: scope.type === "folder" && (loc || drive) ? { name: driveLabel || drive?.name || loc?.root.name, online } : null,
      info,
    });
  });

  // ---- 開啟 ----
  let asking = $state(null); // 第一次按兩下檔案：先問要「打開」還是「在 Finder 中顯示」
  async function run(item, action) {
    try {
      await openItem(item, action);
    } catch (e) {
      toast(e.message, "error");
    }
  }
  function open(i) {
    const item = active.get(i);
    if (!item) return;
    if (item.type === "folder") return navigate(hrefOf(item.root_id, item.path));
    if (item.type === "group") { // 佔比圖上「直接放在某個資料夾裡的檔案」或「其他」：進入那個資料夾
      if (scope.type === "folder" && item.path !== scope.path) navigate(hrefOf(item.root_id, item.path));
      return;
    }
    if (item.image_id) return openViewer([{ id: item.image_id, type: item.kind === "video" ? "video" : "photo", name: item.name }], 0);
    if (!app.server?.local) return toast(t("open.localOnly"));
    const action = app.server?.ui?.open_action;
    if (action === "open" || action === "reveal") run(item, action);
    else asking = item;
  }
  // 「其他」清單裡的一項：資料夾就進去，檔案就照「按兩下」的設定開啟
  function openAny(it) {
    if (it.type === "folder") return navigate(hrefOf(it.root_id, it.path));
    if (!app.server?.local) return toast(t("open.localOnly"));
    const action = app.server?.ui?.open_action;
    if (action === "open" || action === "reveal") run(it, action);
    else asking = it;
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
  // ---- 快速預覽（空白鍵）：跟著目前選到的項目 ----
  let quick = $state(false);
  const quickItem = $derived(quick && sel.focus >= 0 ? active.get(sel.focus) : null);
  const rootOnline = (rootId) => !!catalog.drives.some((d) => d.roots.some((r) => r.id === rootId && r.online));
  function preview(i) {
    if (active.get(i)) quick = true;
  }
  $effect(() => {
    place; // 換位置就關掉
    quick = false;
  });

  // ---- 右鍵選單 ----
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
  // ---- 標籤與喜好項目 ----
  const LABELS = ["red", "yellow", "green", "blue", "purple"];
  const chosen = () => sel.indexes().map((i) => active.peek(i)).filter(Boolean);
  async function label(items, value) {
    try {
      await setLabel(items, value);
      for (const it of items) it.label = value;
      active.touch();
      loadCatalog();
      if (scope.type === "label") rev++;
    } catch (e) {
      toast(e.message, "error");
    }
  }
  const isPinned = (item) => !!app.server?.favorites?.some((f) => f.kind === "folder" && f.root_id === item.root_id && f.path === item.path);
  async function pin(item, on) {
    try {
      await pinFolder(item.root_id, item.path, on);
      toast(on ? t("fav.added", { name: item.name }) : t("fav.removed", { name: item.name }));
      refresh();
    } catch (e) {
      toast(e.message, "error");
    }
  }
  // 拖到側邊欄的「喜好項目」就釘選：資料夾記在資料夾偏好；檔案記成「打開所在資料夾並選好它」的捷徑
  const FILE_ICONS = { photo: "photo", raw: "photo", video: "video", audio: "music-note", document: "document", archive: "archive" };
  const fileLink = (item) => ({ kind: "file", href: fileHref(item), name: item.name, icon: FILE_ICONS[item.kind] || "file" });
  function dragItem(e, item) {
    if (item?.type === "folder") e.dataTransfer.setData(DRAG_FOLDER, JSON.stringify({ root_id: item.root_id, path: item.path, name: item.name }));
    else if (item?.type === "file") e.dataTransfer.setData(DRAG_LINK, JSON.stringify(fileLink(item)));
    else return;
    e.dataTransfer.effectAllowed = "copyMove";
  }
  const isFilePinned = (item) => (app.server?.favorites || []).some((f) => f.kind === "file" && f.href === fileHref(item));
  async function pinFile(item, on) {
    try {
      await pinLink(fileLink(item), on);
      toast(on ? t("fav.added", { name: item.name }) : t("fav.removed", { name: item.name }));
      refresh();
    } catch (e) {
      toast(e.message, "error");
    }
  }

  function itemMenu(e, i) {
    const item = active.get(i);
    if (!item) return;
    if (item.type === "group") {
      menu = { x: e.clientX, y: e.clientY, items: [{ label: t("menu.open"), disabled: item.path === scope.path, onSelect: () => open(i) }] };
      return;
    }
    const local = !!app.server?.local;
    const items = chosen().filter((it) => typeof it.id === "number");
    const targets = items.length ? items : typeof item.id === "number" ? [item] : [];
    const pinned = item.type === "folder" && isPinned(item);
    menu = { x: e.clientX, y: e.clientY, items: [
      { label: t("menu.open"), onSelect: () => open(i) },
      { label: t("menu.quickLook"), shortcut: t("key.space"), onSelect: () => preview(i) },
      { label: t("menu.reveal"), disabled: !local, onSelect: () => run(item, "reveal") },
      { separator: true },
      { label: t("menu.copyPath"), onSelect: () => copyPath(item) },
      { label: t("menu.info"), shortcut: "⌘I", onSelect: () => { if (!frame.info) toggleInfo(); } },
      ...(item.type === "folder" ? [{ separator: true }, { label: pinned ? t("fav.remove") : t("fav.add"), onSelect: () => pin(item, !pinned) }] : []),
      ...(item.type === "file" ? [{ separator: true }, isFilePinned(item)
        ? { label: t("fav.remove"), onSelect: () => pinFile(item, false) }
        : { label: t("fav.add"), onSelect: () => pinFile(item, true) }] : []),
      ...(targets.length ? [
        { separator: true }, { header: t("nav.labels") },
        ...LABELS.map((key) => ({ label: t(`label.${key}`), checked: targets.every((it) => it.label === key), onSelect: () => label(targets, key) })),
        { label: t("label.none"), checked: false, disabled: !targets.some((it) => it.label), onSelect: () => label(targets, null) },
      ] : []),
    ] };
  }
  function headerMenu(e) {
    menu = { x: e.clientX, y: e.clientY, items: [
      { header: t("view.columns") },
      ...COLUMNS.filter((c) => c !== "name" && (c !== "drive" || scope.type !== "folder"))
        .map((c) => ({ label: t(`view.col.${c}`), checked: !prefs.hidden.includes(c), onSelect: () => toggleColumn(c) })),
    ] };
  }
</script>

<div class="browse">
  {#if source.state.error || locError || usageError}
    <div class="state" role="alert">
      <h2 class="mac-title-3">{t("view.error")}</h2>
      <p class="mac-body">{source.state.error || locError || usageError}</p>
      <Button variant="bordered" onclick={() => source.retry()}>{t("view.retry")}</Button>
    </div>
  {:else if total === null}
    {#if slow}<div class="state"><ProgressIndicator kind="spinner" label={t("view.loading")} /><p class="mac-body">{t("view.loading")}</p></div>{/if}
  {:else if total === 0}
    <div class="state">
      {#if scope.type === "roots"}
        <h2 class="mac-title-3">{t("drive.noDrives")}</h2>
        <Button variant="borderedProminent" onclick={() => navigate("/drives")}>{t("nav.addDrive")}</Button>
      {:else if scope.type === "label"}
        <h2 class="mac-title-3">{t("view.empty.label", { label: t(`label.${scope.label}`) })}</h2>
        <p class="mac-body">{t("view.empty.labelHint")}</p>
      {:else if scope.type === "kind"}
        <h2 class="mac-title-3">{t("view.empty.kind", { kind: t(`kind.${scope.kind}`) })}</h2>
        <p class="mac-body">{t("view.empty.kindHint")}</p>
      {:else}
        <h2 class="mac-title-3">{t("view.empty.folder")}</h2>
      {/if}
    </div>
  {:else if view === "treemap" && scope.type === "folder"}
    <ItemUsage {usage} tree={chart} {sel} onopen={open} onpreview={preview} oncontext={itemMenu} onopenitem={openAny} />
  {:else if view === "tree" && scope.type === "folder"}
    <div class="treebar mac-callout">
      <span class="sub">{prefs.treeStyle === "graph" ? t("tree.graphHint") : ""}</span>
      <SegmentedControl size="small" value={prefs.treeStyle} onchange={setTreeStyle} ariaLabel={t("tree.style")}
        segments={[{ value: "graph", label: t("tree.graph") }, { value: "list", label: t("tree.list") }]} />
    </div>
    {#if graph}
      <ItemGraph {graph} {sel} onopen={open} onpreview={preview} oncontext={itemMenu} />
    {:else if treeSource}
    <ItemTree source={treeSource} {sel} totalBytes={loc?.bytes || 0} onopen={open} onpreview={preview} oncontext={itemMenu} ondragitem={dragItem} />
    {/if}
  {:else if view === "columns" && scope.type === "folder"}
    <ItemColumns root={scope.root} path={scope.path} {source} {sel} onnavigate={(p) => navigate(hrefOf(scope.root, p))}
      onopen={open} onpreview={preview} oncontext={itemMenu} ondragitem={dragItem} />
  {:else if view === "icons"}
    <ItemGrid {source} {sel} sections={grouping ? sections : null} onopen={open} onpreview={preview} oncontext={itemMenu} ondragitem={dragItem} />
  {:else}
    <ItemList {source} {sel} sections={grouping ? sections : null} totalBytes={scope.type === "folder" ? loc?.bytes || 0 : 0} showDrive={scope.type === "kind" || scope.type === "label"} ondragitem={dragItem} {driveName} onopen={open} onpreview={preview} oncontext={itemMenu} onheadercontext={headerMenu} />
  {/if}
</div>

{#if quickItem}
  <QuickLook item={quickItem} online={rootOnline(quickItem.root_id)} driveName={driveName(quickItem)} canOpen={!!app.server?.local}
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

<style>
  .browse { height: 100%; min-height: 0; display: flex; flex-direction: column; }
  .treebar { flex: none; display: flex; align-items: center; justify-content: space-between; gap: var(--space-3); padding: var(--space-2) var(--space-4);
    border-bottom: 1px solid var(--separator); color: var(--label-secondary); }
  .state { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: var(--space-3); padding: var(--space-8);
    text-align: center; color: var(--label-secondary); }
  .state h2 { margin: 0; color: var(--label-primary); }
  .state p { margin: 0; max-width: 420px; }
  .backdrop { position: fixed; inset: 0; z-index: 320; display: flex; align-items: center; justify-content: center; background: var(--media-scrim-light); }
</style>
