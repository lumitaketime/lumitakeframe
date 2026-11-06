<script>
  import Loading from "../components/Loading.svelte";
  import DateGroups from "../components/DateGroups.svelte";
  import Icon from "../components/Icon.svelte";
  import { api } from "../lib/api.js";
  import { navigate, link } from "../lib/router.svelte.js";
  import { app, showDialog, toast, refresh } from "../lib/state.svelte.js";
  import { confirm } from "../lib/actions.js";
  import { mdiPencilOutline, mdiDeleteOutline, mdiCreation } from "../lib/icons.js";

  let { id } = $props();
  let album = $state(null);
  let error = $state("");

  $effect(() => {
    app.context = { album: id };
  });

  $effect(() => {
    app.refreshKey;
    api(`/api/albums/${id}`).then((a) => (album = a)).catch((e) => (error = e.message));
  });

  async function rename() {
    const name = await showDialog("prompt", { title: "重新命名相簿", value: album.name, ok: "儲存" });
    if (!name?.trim()) return;
    await api(`/api/albums/${id}`, { body: { name: name.trim() } });
    refresh();
  }

  async function remove() {
    if (!(await confirm("刪除相簿？", `只會刪除「${album.name}」這個相簿，裡面的照片與影片都不會被刪除。`, { ok: "刪除相簿", danger: true }))) return;
    await api(`/api/albums/${id}`, { method: "DELETE" });
    toast("相簿已刪除");
    navigate("/albums");
  }

  async function analyze() {
    await api("/api/jobs", { body: { kind: "analyze", album_id: id } });
    toast("已排入 AI 分析（相簿中尚未分析的項目）");
    refresh();
  }
</script>

<div class="page">
  {#if error}
    <div class="empty"><h2>{error}</h2><a href="/albums" use:link>回到相簿</a></div>
  {:else if album}
    <DateGroups
      assets={album.assets}
      storeKey={`album:${id}`}
      title={album.name}
      back="/albums"
      crumbs={[{ label: "相簿", href: "/albums" }]}
      menu={[
        { label: "重新命名", icon: mdiPencilOutline, run: rename },
        { label: "AI 分析相簿", icon: mdiCreation, run: analyze },
        { label: "刪除相簿", icon: mdiDeleteOutline, run: remove, danger: true },
      ]}
    />
    {#if !album.assets.length}
      <div class="empty"><p>相簿是空的。到「照片」或「資料夾」選取項目，按上方的「加到相簿」。</p></div>
    {/if}
  {:else}
    <Loading kind="grid" />
  {/if}
</div>

<style>
  .page-head a.icon-btn { color: var(--text); }
  .sub { margin: -8px 0 16px 52px; }
</style>
