<script>
  import BackButton from "../components/BackButton.svelte";
  import Grid from "../components/Grid.svelte";
  import Icon from "../components/Icon.svelte";
  import { api } from "../lib/api.js";
  import { navigate, link } from "../lib/router.svelte.js";
  import { app, showDialog, toast, refresh } from "../lib/state.svelte.js";
  import { confirm } from "../lib/actions.js";
  import { mdiArrowLeft, mdiPencilOutline, mdiDeleteOutline, mdiAutoFix } from "../lib/icons.js";

  let { id } = $props();
  let album = $state(null);
  let error = $state("");

  $effect(() => {
    app.refreshKey;
    api(`/api/smart-albums/${id}`).then((a) => (album = a)).catch((e) => (error = e.message));
  });

  async function edit() {
    const name = await showDialog("prompt", { title: "智慧相簿名稱", value: album.name, ok: "下一步" });
    if (name === null || name === undefined) return;
    const query = await showDialog("prompt", { title: "搜尋條件", value: album.query, ok: "儲存" });
    if (!query) return;
    await api("/api/smart-albums", { body: { id, name, query } });
    refresh();
  }

  async function remove() {
    if (!(await confirm("刪除智慧相簿？", "只刪除這個搜尋條件，照片不受影響。", { ok: "刪除", danger: true }))) return;
    await api(`/api/smart-albums/${id}`, { method: "DELETE" });
    toast("已刪除");
    navigate("/albums");
  }
</script>

<div class="page">
  {#if error}
    <div class="empty"><h2>{error}</h2><a href="/albums" use:link>回到相簿</a></div>
  {:else if album}
    <div class="page-head">
      <BackButton to="/albums" label="回到相簿" />
      <h1><Icon path={mdiAutoFix} size={22} />{album.name}</h1>
      <button class="icon-btn" onclick={edit} title="編輯"><Icon path={mdiPencilOutline} /></button>
      <button class="icon-btn" onclick={remove} title="刪除"><Icon path={mdiDeleteOutline} /></button>
    </div>
    <p class="muted small sub">{album.count} 個項目 · 條件：<code>{album.query}</code> · 新照片符合條件就會自動加入</p>
    {#if album.assets.length}
      <Grid assets={album.assets} />
    {:else}
      <div class="empty"><p>目前沒有符合條件的照片。</p></div>
    {/if}
  {:else}
    <p class="muted"><span class="spinner"></span></p>
  {/if}
</div>

<style>
  .page-head a.icon-btn { color: var(--text); }
  h1 { display: flex; align-items: center; gap: 8px; }
  h1 :global(svg) { color: var(--primary); }
  .sub { margin: -8px 0 16px 52px; }
  code { background: var(--bg-2); padding: 1px 6px; border-radius: 6px; }
</style>
