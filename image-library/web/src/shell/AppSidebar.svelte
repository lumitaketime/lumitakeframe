<script>
  /**
   * App 的側邊欄（像 Finder）：最上面是「喜好項目」，下面是資料庫、類型、硬碟（不論是否接上都列出）、智慧資料夾、標籤；
   * 底部固定「掃描進度」與「設定」。
   * - 喜好項目：把資料夾、檔案，或側邊欄的其他項目拖進來就釘選；在裡面拖曳排順序；按右鍵移除。只記在目錄裡，不動硬碟上的檔案。
   * - 每一組都可以收起來（不一定每一組都會用到）；收起來的記在這台電腦的瀏覽器裡，下次打開還是一樣。
   */
  import { Sidebar } from "../ui/index.js";
  import Wordmark from "../components/Wordmark.svelte";
  import { t, formatBytes, formatDate, formatNumber } from "../i18n/index.svelte.js";
  import { app } from "../lib/state.svelte.js";
  import { route, navigate } from "../lib/router.svelte.js";
  import { catalog, loadCatalog } from "../data/catalog.svelte.js";
  import { frame } from "./frame.svelte.js";
  import ContextMenu from "../views/ContextMenu.svelte";
  import { pinFolder, pinLink, orderFavorites, DRAG_FOLDER, DRAG_LINK, DRAG_FAV } from "../data/browse.js";
  import { findHref, deleteSmartFolder } from "../data/find.svelte.js";
  import { categoryName, CATEGORY_ICONS } from "../data/category.svelte.js";
  import { toast, refresh } from "../lib/state.svelte.js";

  let { width = 240 } = $props();

  // 照片圖庫沿用的頁面，都算在「照片」底下
  const PHOTO_PAGES = new Set(["", "welcome", "favorites", "videos", "albums", "explore", "people", "keywords", "tools", "similar"]);
  const page = $derived(route.path.split("/").filter(Boolean)[0] || "");
  const rootId = $derived(page === "folders" ? Number(route.path.split("/")[2]) || null : null);
  const hereKey = $derived(route.path + (route.query.path ? `?path=${encodeURIComponent(route.query.path)}` : ""));

  // ---- 收起來的組（只是這台電腦上的顯示習慣，存不了也沒關係） ----
  const COLLAPSED_KEY = "rememor.sidebar.collapsed";
  function loadCollapsed() {
    try {
      return JSON.parse(localStorage.getItem(COLLAPSED_KEY) || "{}") || {};
    } catch {
      return {};
    }
  }
  let collapsed = $state(loadCollapsed());
  function toggleSection(id) {
    collapsed = { ...collapsed, [id]: !collapsed[id] };
    try {
      localStorage.setItem(COLLAPSED_KEY, JSON.stringify(collapsed));
    } catch {
      /* 私密視窗等存不了：這次打開時照樣有效 */
    }
  }

  function driveItem(d) {
    const percent = d.progress != null ? Math.round(d.progress * 100) : null;
    // 三種狀態都有文字或圖形，不只靠顏色：已連線＝實心圖示；未連線＝空心圖示＋「未連線」；掃描中＝進度環＋百分比
    const trailing = d.scanning ? (percent != null ? `${percent}%` : t("drive.scanning")) : d.online ? "" : t("drive.offline");
    const sub = d.last_scan
      ? t("drive.lastScan", { date: formatDate(new Date(d.last_scan)) }) + (d.complete ? "" : ` · ${t("drive.incomplete")}`)
      : t("drive.neverScanned");
    const first = d.roots[0];
    return {
      value: d.key, label: d.name, href: `/folders/${first.id}`,
      icon: d.online ? "external-drive-fill" : "external-drive", muted: !d.online,
      trailing, progress: d.scanning ? (d.progress ?? true) : null,
      meter: d.capacity ? d.bytes / d.capacity : null,
      sub: [d.capacity ? t("drive.capacity", { used: formatBytes(d.bytes), total: formatBytes(d.capacity) }) : "", sub],
      draggable: true, folder: { root_id: first.id, path: "", name: d.name },
      children: d.roots.length > 1 ? d.roots.map((r) => ({ value: `root:${r.id}`, label: r.name, href: `/folders/${r.id}`, icon: "folder", muted: !r.online,
        draggable: true, folder: { root_id: r.id, path: "", name: r.name } })) : undefined,
    };
  }

  // 類型：六個分組（RAW 算照片，App 與套件算其他），每項顯示檔案數與總大小
  const KIND_GROUPS = { video: ["video"], photo: ["photo", "raw"], document: ["document"], audio: ["audio"], archive: ["archive"], other: ["package", "other"] };
  const KIND_ICONS = { video: "video", photo: "photo", document: "document", audio: "music-note", archive: "archive", other: "file" };
  const kindItems = $derived(Object.entries(KIND_GROUPS).map(([group, kinds]) => {
    const rows = catalog.kinds.filter((k) => kinds.includes(k.kind));
    const files = rows.reduce((n, k) => n + k.files, 0);
    const bytes = rows.reduce((n, k) => n + k.bytes, 0);
    return { value: `kind:${group}`, label: t(`kind.${group}`), icon: KIND_ICONS[group], href: `/kind/${group}`, draggable: true,
      badge: files ? `${formatNumber(files, { notation: "compact", maximumFractionDigits: 1 })} · ${formatBytes(bytes)}` : "0" };
  }));

  const LABELS = ["red", "yellow", "green", "blue", "purple"];
  const libraryItems = $derived([
    { value: "files", label: t("nav.allFiles"), icon: "files", href: "/folders", draggable: true },
    { value: "assistant", label: t("nav.assistant"), icon: "sparkles", href: "/assistant", draggable: true },
    { value: "photos", label: t("nav.photos"), icon: "photo", href: "/", draggable: true },
    { value: "duplicates", label: t("nav.duplicates"), icon: "duplicate", href: "/duplicates", draggable: true },
    { value: "pending", label: t("nav.pending"), icon: "trash", href: "/pending", badge: catalog.pending ? formatNumber(catalog.pending) : undefined, draggable: true },
  ]);
  const smartItems = $derived(catalog.smart.map((sf) => ({
    value: `smart:${sf.id}`, label: sf.name, href: findHref(sf.query, sf.id), icon: "magnifyingglass", context: true, smart: sf, draggable: true,
  })));
  const labelItems = $derived((catalog.labels.length ? catalog.labels : LABELS.map((label) => ({ label, count: 0 }))).map((l) => ({
    value: `label:${l.label}`, label: t(`label.${l.label}`), dot: `var(--label-${l.label})`, href: `/label/${l.label}`, draggable: true,
    badge: l.count ? formatNumber(l.count) : undefined,
  })));

  // 分類：自動分類的主題（有資料夾的才列）；有 AI 沒把握的，最後一項是「請你確認」
  const categoryItems = $derived([
    ...catalog.categories.filter((c) => c.top > 0).map((c) => ({
      value: `category:${c.key}`, label: categoryName(c, t), icon: CATEGORY_ICONS[c.key] || "tag", href: `/category/${c.key}`, draggable: true,
      badge: formatNumber(c.top),
    })),
    ...(catalog.categoryReview ? [{ value: "category:review", label: t("cat.review.title"), icon: "exclamation-triangle", href: "/category/review",
      badge: formatNumber(catalog.categoryReview), draggable: true }] : []),
  ]);

  // 喜好項目裡的捷徑：名稱與圖示跟著原本那一項（換語言、智慧資料夾改名都跟著變）
  const linkSource = $derived(new Map([...libraryItems, ...kindItems, ...categoryItems, ...smartItems, ...labelItems].map((it) => [it.value, it])));
  const favorites = $derived(app.server?.favorites || []);
  const pins = $derived(favorites.filter((f) => f.kind !== "album")); // 可以排順序的：資料夾、檔案、捷徑
  const pinKey = (f) => f.href;
  function favItem(f) {
    const base = { value: `fav:${f.href}`, href: f.href, fav: f, context: true, draggable: f.kind !== "album", droppable: f.kind !== "album" };
    if (f.kind === "album") return { ...base, label: f.name, icon: "photo" };
    if (f.kind === "folder") return { ...base, label: f.name, icon: "folder" };
    if (f.kind === "file") return { ...base, label: f.name, icon: f.icon || "file" };
    const src = linkSource.get(f.ref);
    if (f.ref?.startsWith("smart:") && !src) return { ...base, label: f.name, icon: "magnifyingglass", muted: true }; // 智慧資料夾已經移除
    return { ...base, label: src?.label || f.name, icon: src?.dot ? undefined : src?.icon || f.icon || "file", dot: src?.dot, href: src?.href || f.href };
  }

  let dropping = $state(false); // 正在拖可以釘選的東西
  let fromSidebar = false; // 是從側邊欄本身拖的（只有放進「喜好項目」才算）
  let menu = $state(null);

  const job = $derived(app.server?.jobs?.current);
  const sections = $derived([
    { id: "favorites", title: t("nav.favorites"), collapsible: true, open: dropping, droppable: true, items: favorites.map(favItem),
      note: dropping ? t("fav.dropHere") : !favorites.length ? t("fav.empty") : "" },
    { id: "library", title: t("nav.library"), collapsible: true, items: libraryItems },
    ...(catalog.drives.length ? [{ id: "kinds", title: t("nav.kinds"), collapsible: true, items: kindItems }] : []),
    ...(categoryItems.length ? [{ id: "categories", title: t("nav.categories"), collapsible: true, items: categoryItems }] : []),
    { id: "drives", title: t("nav.drives"), collapsible: true, href: "/drives", current: page === "drives", items: catalog.drives.map(driveItem),
      note: catalog.loaded && !catalog.drives.length ? t("drive.noDrives") : "" },
    // 智慧資料夾：儲存起來的搜尋；按一下重新搜尋，按右鍵移除（只移除搜尋，不影響檔案）
    ...(smartItems.length ? [{ id: "smart", title: t("nav.smartFolders"), collapsible: true, items: smartItems }] : []),
    ...(catalog.drives.length ? [{ id: "labels", title: t("nav.labels"), collapsible: true, items: labelItems }] : []),
  ]);

  const PIN_TYPES = [DRAG_FOLDER, DRAG_LINK, DRAG_FAV];
  const canPin = (e) => [...(e.dataTransfer?.types || [])].some((x) => PIN_TYPES.includes(x));
  async function save(fn, message) {
    try {
      await fn();
      if (message) toast(message);
      refresh();
    } catch (e) {
      toast(e.message, "error");
    }
  }
  const orderOf = (f) => (f.kind === "folder" ? { kind: "folder", root_id: f.root_id, path: f.path } : { kind: f.kind, href: f.href });
  const read = (e, type) => {
    try {
      const raw = e.dataTransfer.getData(type);
      return raw ? JSON.parse(raw) : null;
    } catch {
      return null;
    }
  };
  /** 把東西放進「喜好項目」：before＝放在哪一項前面（沒有就放最後）。已經在裡面的只是換位置。 */
  function drop(e, before) {
    dropping = false;
    fromSidebar = false;
    const moved = read(e, DRAG_FAV);
    const folder = moved ? null : read(e, DRAG_FOLDER);
    const link = moved || folder ? null : read(e, DRAG_LINK);
    let entry, add;
    if (moved) entry = pins.find((p) => pinKey(p) === moved.key);
    else if (folder) {
      entry = pins.find((p) => p.kind === "folder" && p.root_id === folder.root_id && p.path === (folder.path || ""));
      if (!entry) {
        entry = { kind: "folder", root_id: folder.root_id, path: folder.path || "", href: `__new_folder__` };
        add = () => pinFolder(folder.root_id, folder.path || "", true);
      }
    } else if (link?.href) {
      entry = pins.find((p) => p.href === link.href);
      if (!entry) {
        entry = { kind: link.kind, href: link.href };
        add = () => pinLink(link, true);
      }
    }
    if (!entry) return;
    const rest = pins.filter((p) => p !== entry);
    const at = before && before !== entry ? rest.indexOf(before) : -1;
    const order = at < 0 ? [...rest, entry] : [...rest.slice(0, at), entry, ...rest.slice(at)];
    const name = folder?.name || link?.name || "";
    save(async () => {
      if (add) await add();
      await orderFavorites(order.map(orderOf));
    }, add ? t("fav.added", { name }) : "");
  }
  function dragStart(e, it) {
    fromSidebar = true;
    dropping = true;
    if (it.fav) e.dataTransfer.setData(DRAG_FAV, JSON.stringify({ key: pinKey(it.fav) }));
    else if (it.folder) e.dataTransfer.setData(DRAG_FOLDER, JSON.stringify(it.folder));
    else e.dataTransfer.setData(DRAG_LINK, JSON.stringify({ kind: "link", ref: it.value, href: it.href, name: it.label, icon: it.icon || "" }));
    e.dataTransfer.effectAllowed = it.fav ? "move" : "copy";
  }
  function dragEnd() {
    fromSidebar = false;
    dropping = false;
  }
  function removeFav(f) {
    const remove = f.kind === "folder" ? () => pinFolder(f.root_id, f.path, false) : f.kind === "album" ? null : () => pinLink({ kind: f.kind, href: f.href }, false);
    if (remove) save(remove, t("fav.removed", { name: favItem(f).label }));
  }
  function itemMenu(e, it) {
    if (it.smart) {
      menu = { x: e.clientX, y: e.clientY, items: [
        { label: t("smart.remove"), onSelect: () => save(async () => {
          await deleteSmartFolder(it.smart.id);
          await loadCatalog();
          if (route.query.smart === String(it.smart.id)) navigate(findHref(route.query), { replace: true });
        }, t("smart.removed", { name: it.smart.name })) },
      ] };
      return;
    }
    if (it.fav && it.fav.kind !== "album") menu = { x: e.clientX, y: e.clientY, items: [{ label: t("fav.removeFromFavorites"), onSelect: () => removeFav(it.fav) }] };
  }

  const bottom = $derived([
    {
      value: "scan", label: t("nav.scanProgress"), icon: "clock", href: "/activity",
      progress: job ? (job.total ? job.done / job.total : true) : null,
      trailing: job?.total ? `${Math.round((job.done / job.total) * 100)}%` : "",
    },
    { value: "settings", label: t("nav.settings"), icon: "gear", href: "/settings" },
  ]);

  // 目前在哪一項：收藏的資料夾優先，其次是硬碟，再來是資料庫的三項
  const value = $derived.by(() => {
    const fav = favorites.find((f) => f.kind === "folder" && f.href === hereKey);
    if (fav) return `fav:${fav.href}`;
    if (page === "find" && route.query.smart) return `smart:${route.query.smart}`;
    if (page === "assistant") return "assistant";
    if (page === "settings") return "settings";
    if (page === "duplicates") return "duplicates";
    if (page === "pending") return "pending";
    if (page === "activity") return "scan";
    if (page === "kind") return `kind:${route.path.split("/")[2]}`;
    if (page === "label") return `label:${route.path.split("/")[2]}`;
    if (page === "category") return `category:${route.path.split("/")[2]}`;
    if (page === "folders" && rootId) {
      const d = catalog.drives.find((x) => x.roots.some((r) => r.id === rootId));
      if (d) return d.roots.length > 1 ? `root:${rootId}` : d.key;
    }
    if (page === "folders") return "files";
    if (PHOTO_PAGES.has(page)) return "photos";
    return "";
  });

  function go(_, it) {
    frame.drawer = false;
    navigate(it.href);
  }
</script>

<!-- svelte-ignore a11y_no_static_element_interactions -->
<!-- 從內容區拖進來：放在側邊欄任何地方都算放進「喜好項目」；從側邊欄本身拖的，要放進「喜好項目」那一組才算 -->
<div class="drop" class:dropping
  ondragover={(e) => { if (canPin(e)) { e.preventDefault(); dropping = true; } }}
  ondragleave={(e) => { if (!fromSidebar && !e.currentTarget.contains(e.relatedTarget)) dropping = false; }}
  ondragend={dragEnd}
  ondrop={(e) => { if (!canPin(e)) return; e.preventDefault(); if (fromSidebar) dragEnd(); else drop(e, null); }}>
<Sidebar {sections} {bottom} {value} {width} {collapsed} label={t("nav.main")} onchange={go} class="app-sidebar"
  ontogglesection={toggleSection} onsectiondrop={(e, s) => { if (s.id === "favorites") drop(e, null); }}
  onitemdragstart={dragStart} onitemdrop={(e, it) => drop(e, it.fav)} onitemcontext={itemMenu}>
  {#snippet header()}
    <a class="brand" href="/folders" onclick={(e) => { e.preventDefault(); go(null, { href: "/folders" }); }} aria-label="Re'memor">
      <img src="/icon.png" alt="" width="24" height="24" /><Wordmark size={18} />
    </a>
  {/snippet}
</Sidebar>
</div>
{#if menu}<ContextMenu x={menu.x} y={menu.y} items={menu.items} onclose={() => (menu = null)} />{/if}

<style>
  .brand { display: flex; align-items: center; gap: var(--space-2); padding: var(--space-1) var(--space-1) var(--space-2); text-decoration: none; border-radius: var(--radius-sm); }
  .brand img { display: block; border-radius: var(--radius-sm); }
  :global(.app-sidebar) { height: 100%; }
  .drop { height: 100%; display: flex; border-radius: var(--radius-lg); }
  .drop.dropping { box-shadow: 0 0 0 2px var(--accent); }
</style>
