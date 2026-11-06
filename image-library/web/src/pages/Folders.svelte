<script>
  import Loading from "../components/Loading.svelte";
  import DateGroups from "../components/DateGroups.svelte";
  import Icon from "../components/Icon.svelte";
  import CoverPicker from "../components/CoverPicker.svelte";
  import Menu from "../components/Menu.svelte";
  import { flip } from "svelte/animate";
  import { reorder, sortCards, moveKey } from "../lib/reorder.js";
  import { api, thumbUrl } from "../lib/api.js";
  import { route, navigate, link } from "../lib/router.svelte.js";
  import { app, showDialog, toast, refresh } from "../lib/state.svelte.js";
  import { analyzeAssets } from "../lib/actions.js";
  import { mdiFolderOutline, mdiFolderOpenOutline, mdiFolderPlusOutline, mdiCreation, mdiHarddisk, mdiContentCopy, mdiImageOutline, mdiSort, mdiStar, mdiStarOutline } from "../lib/icons.js";
  import { count } from "../lib/format.js";

  let { rootId = null } = $props();
  let data = $state(null);
  let error = $state("");
  const path = $derived(route.query.path || "");
  let picking = $state(false);

  // ---- 排序、收藏、拖曳（只改變顯示順序，不會動到硬碟上的檔案） ----
  const SORTS = [["name", "名稱"], ["updated", "最近更新"], ["count", "照片數量"], ["custom", "自訂"]];
  const sortMode = $derived(app.server?.ui?.folder_sort || "name");
  let dragOrder = $state(null);
  const keyOf = (it) => (it.path !== undefined ? it.path : `root:${it.id}`);
  const fields = (it) => ({ name: it.name, updated: it.latest || it.last_scan, count: it.count, position: it.position });
  function arrange(list) {
    if (!list) return [];
    if (dragOrder) {
      const by = new Map(list.map((it) => [keyOf(it), it]));
      return dragOrder.map((k) => by.get(k)).filter(Boolean);
    }
    const sorted = sortCards(list, sortMode, fields);
    return [...sorted.filter((it) => it.favorite), ...sorted.filter((it) => !it.favorite)]; // 收藏的排最前面
  }
  const rootsShown = $derived(arrange(data?.roots));
  const foldersShown = $derived(arrange(data?.folders));

  async function setSort(mode) {
    if (app.server?.ui) app.server.ui.folder_sort = mode;
    await api("/api/settings", { body: { folder_sort: mode } });
  }
  const sortItems = $derived([{ section: "排序" }, ...SORTS.map(([v, label]) => ({ label, checked: sortMode === v, run: () => setSort(v) }))]);

  async function toggleFav(e, it, isRoot) {
    e.preventDefault();
    e.stopPropagation();
    it.favorite = !it.favorite;
    await api("/api/folders/prefs", { body: { root_id: isRoot ? it.id : rootId, path: isRoot ? "" : it.path, favorite: it.favorite } });
    toast(it.favorite ? `已收藏「${it.name}」，也會出現在側邊欄` : `已取消收藏「${it.name}」`);
    refresh();
  }

  const dragOpts = (shown, isRoot) => ({
    onmove(from, to) {
      dragOrder = moveKey(dragOrder || shown().map(keyOf), from, to);
    },
    async ondrop() {
      if (!dragOrder) return;
      const order = dragOrder;
      const list = isRoot ? data.roots : data.folders;
      order.forEach((k, i) => { const it = list.find((x) => keyOf(x) === k); if (it) it.position = i; });
      dragOrder = null;
      const items = order.map((k) => (isRoot ? { root_id: Number(k.slice(5)), path: "" } : { root_id: rootId, path: k }));
      await api("/api/folders/order", { body: { items } });
      if (sortMode !== "custom") {
        await setSort("custom");
        toast("已改成「自訂」排序（只改變顯示順序，不會搬動硬碟上的資料夾）");
      }
    },
  });

  // 選取一張照片時，選取列會出現「設為資料夾封面」
  $effect(() => {
    app.context = rootId ? { folder: { root: rootId, path } } : null;
  });

  async function saveCover(imageId) {
    await api("/api/folders/cover", { body: { root_id: rootId, path, image_id: imageId || null } });
    toast(imageId ? "已更換資料夾封面" : "封面改回自動（最新的照片）");
    refresh();
  }

  $effect(() => {
    rootId;
    path;
    app.refreshKey;
    load();
  });

  async function load() {
    error = "";
    try {
      data = await api("/api/folders", { params: rootId ? { root: rootId, path } : {} });
    } catch (e) {
      error = e.message;
    }
  }

  const open = (p) => navigate(`/folders/${rootId}${p ? `?path=${encodeURIComponent(p)}` : ""}`);

  async function newFolder() {
    const name = await showDialog("prompt", { title: "新增資料夾", placeholder: "資料夾名稱", ok: "建立", value: "" });
    if (!name?.trim()) return;
    try {
      const created = await api("/api/folders", { body: { root_id: rootId, path: path ? `${path}/${name.trim()}` : name.trim() } });
      toast(`已在硬碟上建立「${name.trim()}」，把照片搬進來後就會出現在這裡`);
      open(created.path);
    } catch (e) {
      toast(e.message, "error");
    }
  }

  async function revealFolder() {
    try {
      await api("/api/folders/reveal", { body: { root_id: rootId, path } });
    } catch (e) {
      toast(e.message, "error");
    }
  }

  async function copyPath() {
    try {
      await navigator.clipboard.writeText(data.abs_path);
      toast("已複製路徑");
    } catch {
      toast(data.abs_path);
    }
  }

  async function analyzeFolder() {
    await api("/api/jobs", { body: { kind: "analyze", root_id: rootId, folder: path } });
    toast("已排入 AI 分析（這個資料夾與子資料夾中尚未分析的項目）");
    refresh();
  }
</script>

<div class="page">
  {#if error}
    <div class="empty"><h2>無法開啟</h2><p>{error}</p></div>
  {:else if !data}
    <Loading kind="grid" />
  {:else if !rootId}
    <div class="page-head"><h1>資料夾</h1>{#if data.roots.length > 1}<Menu icon={mdiSort} label="排序" items={sortItems} />{/if}<a class="btn ghost small" href="/settings/library" use:link>+ 加入資料夾</a></div>
    {#if !data.roots.length}
      <div class="empty"><h2>還沒有加入任何資料夾</h2><p><a class="btn" href="/settings/library" use:link>加入照片資料夾</a></p></div>
    {/if}
    <div class="card-grid" use:reorder={dragOpts(() => rootsShown, true)}>
      {#each rootsShown as r (r.id)}
        <div class="slot" animate:flip={{ duration: 220 }}>
          <a class="cover-card" href={`/folders/${r.id}`} use:link data-reorder-key={keyOf(r)} draggable="false">
            <div class="cover">
              {#if r.cover}<img src={thumbUrl({ id: r.cover })} alt="" loading="lazy" draggable="false" />{:else}<Icon path={mdiHarddisk} size={48} />{/if}
              {#if !r.online}<span class="offline">未連接</span>{/if}
              <button class="fav-btn" class:on={r.favorite} onclick={(e) => toggleFav(e, r, true)} aria-pressed={!!r.favorite} aria-label={r.favorite ? "取消收藏" : "收藏"}>
                <Icon path={r.favorite ? mdiStar : mdiStarOutline} size={20} />
              </button>
            </div>
            <div class="name">{r.name}</div>
            <div class="sub">{r.count.toLocaleString()} 個項目</div>
          </a>
        </div>
      {/each}
    </div>
  {:else}
    {#snippet subfolders()}
      {#if !data.root.online}<p class="offline-note muted small">硬碟未連接，顯示的是上次掃描的內容。</p>{/if}
      {#if data.folders.length}
        {#if data.folders.length > 1}
          <div class="sub-head"><h2 class="section-title">資料夾</h2><Menu icon={mdiSort} label="資料夾排序" items={sortItems} /></div>
        {/if}
        <div class="card-grid folders" use:reorder={dragOpts(() => foldersShown, false)}>
          {#each foldersShown as f (f.path)}
            <div class="slot" animate:flip={{ duration: 220 }}>
              <div class="cover-card" role="button" tabindex="0" data-reorder-key={f.path}
                onclick={() => open(f.path)} onkeydown={(e) => e.key === "Enter" && open(f.path)}>
                <div class="cover">
                  {#if f.cover}<img src={thumbUrl({ id: f.cover })} alt="" loading="lazy" draggable="false" />{:else}<Icon path={mdiFolderOutline} size={48} />{/if}
                  <button class="fav-btn" class:on={f.favorite} onclick={(e) => toggleFav(e, f, false)} aria-pressed={!!f.favorite} aria-label={f.favorite ? "取消收藏" : "收藏"}>
                    <Icon path={f.favorite ? mdiStar : mdiStarOutline} size={20} />
                  </button>
                </div>
                <div class="name">{f.name}</div>
                <div class="sub">{f.count.toLocaleString()} 個項目</div>
              </div>
            </div>
          {/each}
        </div>
        {#if data.assets.length}<h2 class="section-title">這層的檔案</h2>{/if}
      {/if}
      {#if !data.assets.length && !data.folders.length}
        <div class="empty"><p>這個資料夾裡沒有照片或影片。</p></div>
      {/if}
    {/snippet}
    {#key `${rootId}:${path}`}
      <DateGroups
        assets={data.assets}
        storeKey={`folder:${rootId}:${path}`}
        title={data.crumbs.length ? data.crumbs[data.crumbs.length - 1].name : data.root.name}
        subtitle={data.assets.length ? null : `${count(data.folders.length)} 個資料夾`}
        back={path ? `/folders/${rootId}${path.includes("/") ? `?path=${encodeURIComponent(path.slice(0, path.lastIndexOf("/")))}` : ""}` : "/folders"}
        crumbs={[{ label: "資料夾", href: "/folders" },
          ...(path ? [{ label: data.root.name, href: `/folders/${rootId}` }] : []),
          ...data.crumbs.slice(0, -1).map((c) => ({ label: c.name, href: `/folders/${rootId}?path=${encodeURIComponent(c.path)}` }))]}
        menu={[
          { label: "新增資料夾", icon: mdiFolderPlusOutline, run: newFolder, disabled: !data.root.online },
          { label: "AI 分析這個資料夾", icon: mdiCreation, run: analyzeFolder },
          { label: app.server?.local ? "在 Finder 中打開" : "在 Mac 上打開", icon: mdiFolderOpenOutline, run: revealFolder, disabled: !data.root.online },
          { label: "複製路徑", icon: mdiContentCopy, run: copyPath },
          { label: "更換封面…", icon: mdiImageOutline, run: () => (picking = true), disabled: !data.assets.length && !data.folders.length },
        ]}
        above={subfolders}
      />
    {/key}
  {/if}
</div>

{#if picking && data}
  <CoverPicker title={data.crumbs.length ? data.crumbs[data.crumbs.length - 1].name : data.root.name} scope={`folder:${rootId}:${path}`}
    current={data.cover_custom ? data.cover : null} onsave={saveCover} onclose={() => (picking = false)} />
{/if}

<style>
  .offline-note { margin: 0 0 12px; }
  .folders { margin-bottom: 28px; }
  .offline { position: absolute; top: 8px; left: 8px; background: rgba(0,0,0,.6); color: #fff; font-size: 12px; padding: 2px 8px; border-radius: var(--corner-full); }
  a.cover-card { text-decoration: none; display: block; }
  div.cover-card { cursor: pointer; }
  .sub-head { display: flex; align-items: center; gap: 8px; }
  .sub-head .section-title { flex: 1; }
</style>
