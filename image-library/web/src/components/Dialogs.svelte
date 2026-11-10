<script>
  import Modal from "./Modal.svelte";
  import Icon from "./Icon.svelte";
  import { api, thumbUrl } from "../lib/api.js";
  import { dialogs, closeDialog } from "../lib/state.svelte.js";
  import { mdiImageAlbum, mdiPlus } from "../lib/icons.js";

  const d = $derived(dialogs.current);

  // ---- 相簿 ----
  let albums = $state([]);
  let newName = $state("");
  let people = $state([]);
  let personQuery = $state("");
  const filteredPeople = $derived(
    people.filter((p) => p.id !== d?.props?.exclude && (!personQuery || (p.name || "").toLowerCase().includes(personQuery.toLowerCase()))),
  );

  $effect(() => {
    if (d?.kind === "person") {
      personQuery = "";
      api("/api/people").then((p) => (people = p));
    }
    if (d?.kind === "album") {
      newName = "";
      api("/api/albums").then((a) => (albums = a));
    }
  });
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
{:else if d?.kind === "person"}
  <Modal title={d.props.title || "選擇人物"} onclose={() => closeDialog(null)}>
    <input class="input" bind:value={personQuery} placeholder="輸入名字篩選" />
    {#if d.props.allowNew && personQuery.trim()}
      <button class="item" onclick={() => closeDialog({ name: personQuery.trim() })}>
        <span class="thumb"><Icon path={mdiPlus} /></span><span class="label"><b>新增「{personQuery.trim()}」</b></span>
      </button>
    {/if}
    <div class="list">
      {#each filteredPeople as p (p.id)}
        <button class="item" onclick={() => closeDialog(p)}>
          <span class="thumb round"><img src={`/api/faces/${p.cover_face_id}/thumb`} alt="" /></span>
          <span class="label"><b>{p.name || "未命名"}</b><span class="muted small">{p.count} 張</span></span>
        </button>
      {:else}
        <p class="muted small">沒有符合的人物。</p>
      {/each}
    </div>
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
{/if}

<style>
  .msg { margin: 0; white-space: pre-wrap; word-break: break-word; color: var(--on-surface-variant); }
  .new { display: flex; gap: 8px; margin: 4px 0 12px; }
  .list { display: flex; flex-direction: column; gap: 2px; max-height: 46vh; overflow-y: auto; }
  .item {
    display: flex; align-items: center; gap: 12px; padding: 8px; border: 0; background: none;
    border-radius: var(--corner-medium); cursor: pointer; text-align: left; color: inherit;
  }
  .item:hover { background: var(--surface-container); }
  .thumb {
    width: 48px; height: 48px; border-radius: var(--corner-medium); overflow: hidden; background: var(--surface-container);
    display: flex; align-items: center; justify-content: center; color: var(--on-surface-variant); flex-shrink: 0;
  }
  .thumb img { width: 100%; height: 100%; object-fit: cover; }
  .thumb.round { border-radius: 50%; }
  .label { display: flex; flex-direction: column; min-width: 0; flex: 1; }
  .label b { font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .label span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
</style>
