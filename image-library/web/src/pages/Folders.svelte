<script>
  import Grid from "../components/Grid.svelte";
  import Icon from "../components/Icon.svelte";
  import { api, thumbUrl } from "../lib/api.js";
  import { route, navigate, link } from "../lib/router.svelte.js";
  import { app, showDialog, toast, refresh } from "../lib/state.svelte.js";
  import { analyzeAssets } from "../lib/actions.js";
  import { mdiFolderOutline, mdiFolderOpenOutline, mdiFolderPlusOutline, mdiCreation, mdiHarddisk, mdiChevronRight } from "../lib/icons.js";

  let { rootId = null } = $props();
  let data = $state(null);
  let error = $state("");
  const path = $derived(route.query.path || "");

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
    <p class="muted"><span class="spinner"></span></p>
  {:else if !rootId}
    <div class="page-head"><h1>資料夾</h1><a class="btn ghost small" href="/settings" use:link>+ 加入資料夾</a></div>
    {#if !data.roots.length}
      <div class="empty"><h2>還沒有加入任何資料夾</h2><p><a class="btn" href="/settings" use:link>加入照片資料夾</a></p></div>
    {/if}
    <div class="card-grid">
      {#each data.roots as r (r.id)}
        <a class="cover-card" href={`/folders/${r.id}`} use:link>
          <div class="cover">
            {#if r.cover}<img src={thumbUrl({ id: r.cover })} alt="" loading="lazy" />{:else}<Icon path={mdiHarddisk} size={48} />{/if}
            {#if !r.online}<span class="offline">未連接</span>{/if}
          </div>
          <div class="name">{r.name}</div>
          <div class="sub">{r.count.toLocaleString()} 個項目</div>
        </a>
      {/each}
    </div>
  {:else}
    <div class="page-head">
      <h1>
        <nav class="crumbs">
          <a href="/folders" use:link>資料夾</a><Icon path={mdiChevronRight} size={18} />
          <a href={`/folders/${rootId}`} use:link class:current={!path}>{data.root.name}</a>
          {#each data.crumbs as c (c.path)}
            <Icon path={mdiChevronRight} size={18} />
            <a href={`/folders/${rootId}?path=${encodeURIComponent(c.path)}`} use:link class:current={c.path === path}>{c.name}</a>
          {/each}
        </nav>
      </h1>
      <div class="actions">
        <button class="btn ghost small" onclick={newFolder} disabled={!data.root.online}><Icon path={mdiFolderPlusOutline} size={18} />新增資料夾</button>
        <button class="btn ghost small" onclick={analyzeFolder}><Icon path={mdiCreation} size={18} />AI 分析</button>
        <button class="btn ghost small" onclick={revealFolder} disabled={!data.root.online}>
          <Icon path={mdiFolderOpenOutline} size={18} />{app.server?.local ? "在 Finder 中打開" : "在 Mac 上打開"}
        </button>
      </div>
    </div>
    <p class="abs muted tiny">{data.abs_path}{data.root.online ? "" : "（硬碟未連接，顯示的是上次掃描的內容）"}</p>

    {#if data.folders.length}
      <div class="card-grid folders">
        {#each data.folders as f (f.path)}
          <button class="cover-card" onclick={() => open(f.path)}>
            <div class="cover">
              {#if f.cover}<img src={thumbUrl({ id: f.cover })} alt="" loading="lazy" />{:else}<Icon path={mdiFolderOutline} size={48} />{/if}
            </div>
            <div class="name">{f.name}</div>
            <div class="sub">{f.count.toLocaleString()} 個項目</div>
          </button>
        {/each}
      </div>
    {/if}
    {#if data.assets.length}
      {#if data.folders.length}<h2 class="section-title">這個資料夾中的檔案（{data.assets.length}）</h2>{/if}
      <Grid assets={data.assets} />
    {:else if !data.folders.length}
      <div class="empty"><p>這個資料夾裡沒有照片或影片。</p></div>
    {/if}
  {/if}
</div>

<style>
  .crumbs { display: flex; align-items: center; flex-wrap: wrap; gap: 2px; font-size: 20px; }
  .crumbs a { text-decoration: none; color: var(--muted); }
  .crumbs a.current, .crumbs a:last-child { color: var(--text); }
  .crumbs :global(svg) { color: var(--muted); }
  .actions { display: flex; gap: 6px; flex-wrap: wrap; }
  .abs { margin: -6px 0 16px; font-family: ui-monospace, Menlo, monospace; word-break: break-all; }
  .folders { margin-bottom: 28px; }
  .offline { position: absolute; top: 8px; left: 8px; background: rgba(0,0,0,.6); color: #fff; font-size: 12px; padding: 2px 8px; border-radius: 999px; }
  a.cover-card { text-decoration: none; }
  @media (max-width: 760px) { .crumbs { font-size: 16px; } }
</style>
