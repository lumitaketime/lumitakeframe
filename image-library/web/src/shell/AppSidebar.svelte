<script>
  /**
   * App 的側邊欄：資料庫、硬碟（不論是否接上都列出）、收藏；底部固定「掃描進度」與「設定」。
   * 還沒有頁面的項目（待刪除、類型、智慧資料夾）做到那一步才出現。
   */
  import { Sidebar } from "../ui/index.js";
  import Wordmark from "../components/Wordmark.svelte";
  import { t, formatBytes, formatDate, formatNumber } from "../i18n/index.svelte.js";
  import { app } from "../lib/state.svelte.js";
  import { route, navigate } from "../lib/router.svelte.js";
  import { catalog } from "../data/catalog.svelte.js";
  import { frame } from "./frame.svelte.js";
  import ContextMenu from "../views/ContextMenu.svelte";
  import { pinFolder, orderPins, DRAG_FOLDER } from "../data/browse.js";
  import { toast, refresh } from "../lib/state.svelte.js";

  let { width = 240 } = $props();

  // 照片圖庫沿用的頁面，都算在「照片」底下
  const PHOTO_PAGES = new Set(["", "welcome", "favorites", "videos", "albums", "explore", "people", "keywords", "tools"]);
  const page = $derived(route.path.split("/").filter(Boolean)[0] || "");
  const rootId = $derived(page === "folders" ? Number(route.path.split("/")[2]) || null : null);
  const hereKey = $derived(route.path + (route.query.path ? `?path=${encodeURIComponent(route.query.path)}` : ""));

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
      children: d.roots.length > 1 ? d.roots.map((r) => ({ value: `root:${r.id}`, label: r.name, href: `/folders/${r.id}`, icon: "folder", muted: !r.online })) : undefined,
    };
  }

  // 類型：六個分組（RAW 算照片，App 與套件算其他），每項顯示檔案數與總大小
  const KIND_GROUPS = { video: ["video"], photo: ["photo", "raw"], document: ["document"], audio: ["audio"], archive: ["archive"], other: ["package", "other"] };
  const KIND_ICONS = { video: "video", photo: "photo", document: "document", audio: "music-note", archive: "archive", other: "file" };
  const kindItems = $derived(Object.entries(KIND_GROUPS).map(([group, kinds]) => {
    const rows = catalog.kinds.filter((k) => kinds.includes(k.kind));
    const files = rows.reduce((n, k) => n + k.files, 0);
    const bytes = rows.reduce((n, k) => n + k.bytes, 0);
    return { value: `kind:${group}`, label: t(`kind.${group}`), icon: KIND_ICONS[group], href: `/kind/${group}`,
      badge: files ? `${formatNumber(files, { notation: "compact", maximumFractionDigits: 1 })} · ${formatBytes(bytes)}` : "0" };
  }));

  const job = $derived(app.server?.jobs?.current);
  const sections = $derived([
    { title: t("nav.library"), items: [
      { value: "files", label: t("nav.allFiles"), icon: "files", href: "/folders" },
      { value: "photos", label: t("nav.photos"), icon: "photo", href: "/" },
      { value: "duplicates", label: t("nav.duplicates"), icon: "duplicate", href: "/duplicates" },
    ] },
    ...(catalog.drives.length ? [{ title: t("nav.kinds"), items: kindItems }] : []),
    { title: t("nav.drives"), href: "/drives", current: page === "drives", items: catalog.drives.map(driveItem), note: catalog.loaded && !catalog.drives.length ? t("drive.noDrives") : "" },
    // 喜好項目：從內容區把資料夾拖進來就釘選；拖曳排順序；按右鍵移除
    ...(favorites.length || dropping ? [{ title: t("nav.favorites"), items: favorites.map((f) => ({
      value: `fav:${f.href}`, label: f.name, href: f.href, icon: f.kind === "album" ? "photo" : "folder",
      draggable: f.kind === "folder", droppable: f.kind === "folder", context: f.kind === "folder", fav: f,
    })), note: dropping && !favorites.length ? t("fav.dropHere") : "" }] : []),
    ...(catalog.drives.length ? [{ title: t("nav.labels"), items: (catalog.labels.length ? catalog.labels : LABELS.map((label) => ({ label, count: 0 }))).map((l) => ({
      value: `label:${l.label}`, label: t(`label.${l.label}`), dot: `var(--label-${l.label})`, href: `/label/${l.label}`,
      badge: l.count ? formatNumber(l.count) : undefined,
    })) }] : []),
  ]);
  const LABELS = ["red", "yellow", "green", "blue", "purple"];
  const favorites = $derived(app.server?.favorites || []);
  const pins = $derived(favorites.filter((f) => f.kind === "folder"));
  let dropping = $state(false); // 正在把資料夾拖過側邊欄
  let menu = $state(null);

  const isFolderDrag = (e) => [...(e.dataTransfer?.types || [])].includes(DRAG_FOLDER);
  const samePin = (a, b) => a.root_id === b.root_id && a.path === b.path;
  async function save(fn, message) {
    try {
      await fn();
      if (message) toast(message);
      refresh();
    } catch (e) {
      toast(e.message, "error");
    }
  }
  /** 把資料夾放進側邊欄：before＝放在哪一個喜好項目前面（沒有就放最後） */
  function dropFolder(e, before) {
    dropping = false;
    let data;
    try {
      data = JSON.parse(e.dataTransfer.getData(DRAG_FOLDER));
    } catch {
      return;
    }
    const rest = pins.filter((p) => !samePin(p, data));
    const at = before ? rest.findIndex((p) => samePin(p, before)) : -1;
    const order = at < 0 ? [...rest, data] : [...rest.slice(0, at), data, ...rest.slice(at)];
    const isNew = !pins.some((p) => samePin(p, data));
    save(async () => {
      if (isNew) await pinFolder(data.root_id, data.path, true);
      await orderPins(order.map((p) => ({ root_id: p.root_id, path: p.path })));
    }, isNew ? t("fav.added", { name: data.name }) : "");
  }
  function dragStart(e, it) {
    e.dataTransfer.setData(DRAG_FOLDER, JSON.stringify({ root_id: it.fav.root_id, path: it.fav.path, name: it.fav.name }));
    e.dataTransfer.effectAllowed = "move";
  }
  function itemMenu(e, it) {
    menu = { x: e.clientX, y: e.clientY, items: [
      { label: t("fav.remove"), onSelect: () => save(() => pinFolder(it.fav.root_id, it.fav.path, false), t("fav.removed", { name: it.fav.name })) },
    ] };
  }

  const bottom = $derived([
    {
      value: "scan", label: job ? job.label : t("nav.scanProgress"), icon: "clock", href: "/settings/ai",
      progress: job ? (job.total ? job.done / job.total : true) : null,
      trailing: job?.total ? `${Math.round((job.done / job.total) * 100)}%` : "",
    },
    { value: "settings", label: t("nav.settings"), icon: "gear", href: "/settings" },
  ]);

  // 目前在哪一項：收藏的資料夾優先，其次是硬碟，再來是資料庫的三項
  const value = $derived.by(() => {
    const fav = app.server?.favorites?.find((f) => f.href === hereKey);
    if (fav) return `fav:${fav.href}`;
    if (page === "settings") return "settings";
    if (page === "duplicates") return "duplicates";
    if (page === "kind") return `kind:${route.path.split("/")[2]}`;
    if (page === "label") return `label:${route.path.split("/")[2]}`;
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
<div class="drop" class:dropping
  ondragover={(e) => { if (isFolderDrag(e)) { e.preventDefault(); dropping = true; } }}
  ondragleave={(e) => { if (!e.currentTarget.contains(e.relatedTarget)) dropping = false; }}
  ondrop={(e) => { if (isFolderDrag(e)) { e.preventDefault(); dropFolder(e, null); } }}>
<Sidebar {sections} {bottom} {value} {width} label={t("nav.main")} onchange={go} class="app-sidebar"
  onitemdragstart={dragStart} onitemdrop={(e, it) => dropFolder(e, it.fav)} onitemcontext={itemMenu}>
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
