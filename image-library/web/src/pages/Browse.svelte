<script>
  /**
   * 瀏覽頁：「所有檔案」、每顆硬碟的資料夾、跨硬碟的類型，共用同一頁，用工具列切換檢視。
   * scope：{type: "roots"}｜{type: "folder", root, path}｜{type: "kind", kind}
   * 這一頁只組合檢視元件與資料；資料都從資料層來，硬碟沒接上也能看。
   */
  import { Alert, Button, ProgressIndicator } from "../ui/index.js";
  import ItemList from "../views/ItemList.svelte";
  import ItemGrid from "../views/ItemGrid.svelte";
  import ContextMenu from "../views/ContextMenu.svelte";
  import { createSelection } from "../views/selection.svelte.js";
  import { prefs, viewFor, toggleColumn, COLUMNS } from "../views/prefs.svelte.js";
  import { createItemSource, createStaticSource } from "../data/items.svelte.js";
  import { catalog, driveOfRoot } from "../data/catalog.svelte.js";
  import { loadLocation, openItem, saveOpenAction } from "../data/browse.js";
  import { setFrame, frame, toggleInfo } from "../shell/frame.svelte.js";
  import { t, formatNumber, formatBytes, formatDate } from "../i18n/index.svelte.js";
  import { app, toast, openViewer } from "../lib/state.svelte.js";
  import { navigate } from "../lib/router.svelte.js";

  let { scope } = $props();

  const place = $derived(scope.type === "folder" ? `folder:${scope.root}:${scope.path}` : scope.type === "kind" ? `kind:${scope.kind}` : "roots");
  const view = $derived(viewFor(place));
  const sel = createSelection();

  // 「所有檔案」最上層：每個資料夾來源一項（硬碟沒接上也列出）
  const rootItems = $derived(catalog.drives.flatMap((d) => d.roots.map((r) => ({
    type: "folder", id: `root:${r.id}`, name: r.name, kind: "folder", icon: r.online ? "drive" : "drive-offline", size: r.bytes, files: r.files,
    root_id: r.id, path: "", kindLabel: t("info.kind.drive"), note: r.online ? "" : t("drive.offline"),
  }))));
  const source = $derived(
    scope.type === "roots" ? createStaticSource(rootItems)
      : scope.type === "kind" ? createItemSource({ kind: scope.kind }, prefs.sort, prefs.desc)
        : createItemSource({ root: scope.root, path: scope.path }, prefs.sort, prefs.desc));
  $effect(() => {
    source.start();
    sel.clear();
  });
  const total = $derived(source.state.total);

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

  const picked = $derived(sel.size === 1 ? source.get(sel.indexes()[0]) : null);
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
    const item = source.get(i);
    if (!item) return;
    if (item.type === "folder") return navigate(hrefOf(item.root_id, item.path));
    if (item.image_id) return openViewer([{ id: item.image_id, type: item.kind === "video" ? "video" : "photo", name: item.name }], 0);
    if (!app.server?.local) return toast(t("open.localOnly"));
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
  function preview(i) {
    const item = source.get(i);
    if (item?.image_id) openViewer([{ id: item.image_id, type: item.kind === "video" ? "video" : "photo", name: item.name }], 0);
    else if (item && !frame.info) toggleInfo(); // 其他檔案：先顯示資訊欄（完整的快速預覽在之後的步驟）
  }

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
  function itemMenu(e, i) {
    const item = source.get(i);
    if (!item) return;
    const local = !!app.server?.local;
    menu = { x: e.clientX, y: e.clientY, items: [
      { label: t("menu.open"), onSelect: () => open(i) },
      { label: t("menu.reveal"), disabled: !local, onSelect: () => run(item, "reveal") },
      { separator: true },
      { label: t("menu.copyPath"), onSelect: () => copyPath(item) },
      { label: t("menu.info"), shortcut: "⌘I", onSelect: () => { if (!frame.info) toggleInfo(); } },
    ] };
  }
  function headerMenu(e) {
    menu = { x: e.clientX, y: e.clientY, items: [
      { header: t("view.columns") },
      ...COLUMNS.filter((c) => c !== "name" && (c !== "drive" || scope.type === "kind"))
        .map((c) => ({ label: t(`view.col.${c}`), checked: !prefs.hidden.includes(c), onSelect: () => toggleColumn(c) })),
    ] };
  }
</script>

<div class="browse">
  {#if source.state.error || locError}
    <div class="state" role="alert">
      <h2 class="mac-title-3">{t("view.error")}</h2>
      <p class="mac-body">{source.state.error || locError}</p>
      <Button variant="bordered" onclick={() => source.retry()}>{t("view.retry")}</Button>
    </div>
  {:else if total === null}
    {#if slow}<div class="state"><ProgressIndicator kind="spinner" label={t("view.loading")} /><p class="mac-body">{t("view.loading")}</p></div>{/if}
  {:else if total === 0}
    <div class="state">
      {#if scope.type === "roots"}
        <h2 class="mac-title-3">{t("drive.noDrives")}</h2>
        <Button variant="borderedProminent" onclick={() => navigate("/settings/library")}>{t("nav.addDrive")}</Button>
      {:else if scope.type === "kind"}
        <h2 class="mac-title-3">{t("view.empty.kind", { kind: t(`kind.${scope.kind}`) })}</h2>
        <p class="mac-body">{t("view.empty.kindHint")}</p>
      {:else}
        <h2 class="mac-title-3">{t("view.empty.folder")}</h2>
      {/if}
    </div>
  {:else if view === "icons"}
    <ItemGrid {source} {sel} onopen={open} onpreview={preview} oncontext={itemMenu} />
  {:else}
    <ItemList {source} {sel} showDrive={scope.type === "kind"} {driveName} onopen={open} onpreview={preview} oncontext={itemMenu} onheadercontext={headerMenu} />
  {/if}
</div>

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
  .state { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: var(--space-3); padding: var(--space-8);
    text-align: center; color: var(--label-secondary); }
  .state h2 { margin: 0; color: var(--label-primary); }
  .state p { margin: 0; max-width: 420px; }
  .backdrop { position: fixed; inset: 0; z-index: 320; display: flex; align-items: center; justify-content: center; background: var(--media-scrim-light); }
</style>
