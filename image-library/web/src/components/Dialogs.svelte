<script>
  import Modal from "./Modal.svelte";
  import Icon from "./Icon.svelte";
  import { api, thumbUrl } from "../lib/api.js";
  import { dialogs, closeDialog, toast } from "../lib/state.svelte.js";
  import { mdiFolderOutline, mdiFolderPlusOutline, mdiImageAlbum, mdiPlus, mdiChevronRight, mdiHarddisk } from "../lib/icons.js";

  const d = $derived(dialogs.current);

  // ---- 相簿 ----
  let albums = $state([]);
  let newName = $state("");
  // ---- 搬移 ----
  let roots = $state([]);
  let root = $state(null);
  let path = $state("");
  let dirs = $state([]);
  let newFolder = $state("");
  let loadingDirs = $state(false);

  $effect(() => {
    if (d?.kind === "album") {
      newName = "";
      api("/api/albums").then((a) => (albums = a));
    }
    if (d?.kind === "move") {
      root = null;
      path = "";
      api("/api/roots").then((r) => (roots = r.filter((x) => x.online)));
    }
  });

  async function openDir(r, p) {
    root = r;
    path = p;
    loadingDirs = true;
    try {
      dirs = (await api("/api/fs/dirs", { params: { root: r.id, path: p } })).dirs;
    } catch (e) {
      toast(e.message, "error");
      dirs = [];
    } finally {
      loadingDirs = false;
    }
  }

  async function createFolder() {
    const name = newFolder.trim();
    if (!name) return;
    const target = path ? `${path}/${name}` : name;
    try {
      await api("/api/folders", { body: { root_id: root.id, path: target } });
      newFolder = "";
      await openDir(root, target);
    } catch (e) {
      toast(e.message, "error");
    }
  }

  const crumbs = $derived(path ? path.split("/") : []);
</script>

{#if d?.kind === "confirm"}
  <Modal title={d.props.title} onclose={() => closeDialog(false)}>
    <p class="msg">{d.props.message}</p>
    {#snippet actions()}
      {#if !d.props.noCancel}<button class="btn ghost" onclick={() => closeDialog(false)}>取消</button>{/if}
      <button class="btn" class:danger={d.props.danger} onclick={() => closeDialog(true)}>{d.props.ok}</button>
    {/snippet}
  </Modal>
{:else if d?.kind === "prompt"}
  <Modal title={d.props.title} onclose={() => closeDialog(null)}>
    <!-- svelte-ignore a11y_autofocus -->
    <input class="input" bind:value={d.props.value} placeholder={d.props.placeholder || ""} autofocus
      onkeydown={(e) => e.key === "Enter" && closeDialog(d.props.value)} />
    {#snippet actions()}
      <button class="btn ghost" onclick={() => closeDialog(null)}>取消</button>
      <button class="btn" onclick={() => closeDialog(d.props.value)}>{d.props.ok || "確定"}</button>
    {/snippet}
  </Modal>
{:else if d?.kind === "album"}
  <Modal title="加到相簿（{d.props.count} 個項目）" onclose={() => closeDialog(null)}>
    <div class="new">
      <input class="input" bind:value={newName} placeholder="新相簿名稱"
        onkeydown={(e) => e.key === "Enter" && newName.trim() && closeDialog({ name: newName.trim() })} />
      <button class="btn" disabled={!newName.trim()} onclick={() => closeDialog({ name: newName.trim() })}>
        <Icon path={mdiPlus} size={18} />建立
      </button>
    </div>
    <div class="list">
      {#each albums as a (a.id)}
        <button class="item" onclick={() => closeDialog({ id: a.id, name: a.name })}>
          <span class="thumb">
            {#if a.cover}<img src={thumbUrl({ id: a.cover })} alt="" />{:else}<Icon path={mdiImageAlbum} />{/if}
          </span>
          <span class="label"><b>{a.name}</b><span class="muted small">{a.count} 個項目</span></span>
        </button>
      {:else}
        <p class="muted small">還沒有相簿，輸入名稱建立第一個。</p>
      {/each}
    </div>
  </Modal>
{:else if d?.kind === "move"}
  <Modal title="搬移 {d.props.count} 個檔案到…" wide onclose={() => closeDialog(null)}>
    {#if !root}
      <p class="muted small">選擇目的地硬碟或資料夾。檔案會真的在硬碟上搬移，.xmp 附屬檔會一起帶走。</p>
      <div class="list">
        {#each roots as r (r.id)}
          <button class="item" onclick={() => openDir(r, "")}>
            <span class="thumb"><Icon path={mdiHarddisk} /></span>
            <span class="label"><b>{r.name}</b><span class="muted tiny">{r.path}</span></span>
            <Icon path={mdiChevronRight} />
          </button>
        {:else}
          <p class="muted">沒有可用的資料夾（硬碟可能未連接）。</p>
        {/each}
      </div>
    {:else}
      <nav class="crumbs">
        <button class="chip" onclick={() => (root = null)}>全部</button>
        <button class="chip" onclick={() => openDir(root, "")}>{root.name}</button>
        {#each crumbs as c, i (i)}
          <span class="muted">/</span>
          <button class="chip" onclick={() => openDir(root, crumbs.slice(0, i + 1).join("/"))}>{c}</button>
        {/each}
      </nav>
      <div class="list">
        {#if loadingDirs}<p class="muted"><span class="spinner"></span></p>{/if}
        {#each dirs as name (name)}
          <button class="item" onclick={() => openDir(root, path ? `${path}/${name}` : name)}>
            <span class="thumb"><Icon path={mdiFolderOutline} /></span>
            <span class="label"><b>{name}</b></span>
            <Icon path={mdiChevronRight} />
          </button>
        {/each}
        {#if !loadingDirs && !dirs.length}<p class="muted small">這裡沒有子資料夾。</p>{/if}
      </div>
      <div class="new">
        <input class="input" bind:value={newFolder} placeholder="在這裡建立新資料夾"
          onkeydown={(e) => e.key === "Enter" && createFolder()} />
        <button class="btn ghost" disabled={!newFolder.trim()} onclick={createFolder}>
          <Icon path={mdiFolderPlusOutline} size={18} />建立
        </button>
      </div>
    {/if}
    {#snippet actions()}
      <button class="btn ghost" onclick={() => closeDialog(null)}>取消</button>
      <button class="btn" disabled={!root}
        onclick={() => closeDialog({ root: root.id, path, label: path ? `${root.name}/${path}` : root.name })}>
        搬到這裡
      </button>
    {/snippet}
  </Modal>
{/if}

<style>
  .msg { margin: 0; white-space: pre-wrap; word-break: break-word; color: var(--muted); }
  .new { display: flex; gap: 8px; margin: 4px 0 12px; }
  .list { display: flex; flex-direction: column; gap: 2px; max-height: 46vh; overflow-y: auto; }
  .item {
    display: flex; align-items: center; gap: 12px; padding: 8px; border: 0; background: none;
    border-radius: 12px; cursor: pointer; text-align: left; color: inherit;
  }
  .item:hover { background: var(--bg-2); }
  .thumb {
    width: 48px; height: 48px; border-radius: 10px; overflow: hidden; background: var(--bg-2);
    display: flex; align-items: center; justify-content: center; color: var(--muted); flex-shrink: 0;
  }
  .thumb img { width: 100%; height: 100%; object-fit: cover; }
  .label { display: flex; flex-direction: column; min-width: 0; flex: 1; }
  .label b { font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .label span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .crumbs { display: flex; flex-wrap: wrap; align-items: center; gap: 4px; margin-bottom: 10px; }
</style>
