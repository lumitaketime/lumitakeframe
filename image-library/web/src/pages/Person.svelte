<script>
  import Grid from "../components/Grid.svelte";
  import Icon from "../components/Icon.svelte";
  import { api } from "../lib/api.js";
  import { navigate, link } from "../lib/router.svelte.js";
  import { app, showDialog, toast, refresh } from "../lib/state.svelte.js";
  import { mdiArrowLeft, mdiPencilOutline, mdiEyeOffOutline, mdiEyeOutline, mdiAccountMultiplePlusOutline } from "../lib/icons.js";

  let { id } = $props();
  let person = $state(null);
  let error = $state("");
  let groups = $state([]);

  $effect(() => {
    app.refreshKey;
    api("/api/people/groups").then((g) => (groups = g));
  });

  async function toggleGroup(name) {
    const next = person.groups.includes(name) ? person.groups.filter((g) => g !== name) : [...person.groups, name];
    await api(`/api/people/${id}`, { body: { groups: next } });
    person.groups = next;
    refresh();
  }

  async function newGroup() {
    const name = await showDialog("prompt", { title: "新增分類", placeholder: "例如：客戶、模特兒、大學同學", ok: "加入", value: "" });
    if (name?.trim()) await toggleGroup(name.trim());
  }

  $effect(() => {
    app.context = { person: id };
  });
  $effect(() => {
    app.refreshKey;
    api(`/api/people/${id}`).then((p) => (person = p)).catch((e) => (error = e.message));
  });

  async function rename() {
    const name = await showDialog("prompt", { title: person.name ? "重新命名" : "這是誰？", value: person.name || "", placeholder: "名字", ok: "儲存" });
    if (name === null || name === undefined) return;
    await api(`/api/people/${id}`, { body: { name } });
    refresh();
  }

  async function toggleHidden() {
    await api(`/api/people/${id}`, { body: { hidden: !person.hidden } });
    toast(person.hidden ? "已取消隱藏" : "已隱藏，可在人物頁勾選「顯示已隱藏」找回");
    refresh();
  }

  async function merge() {
    const target = await showDialog("person", { exclude: id, title: "和誰是同一個人？" });
    if (!target) return;
    await api("/api/people/merge", { body: { target: target.id, sources: [id] } });
    toast("已合併");
    navigate(`/people/${target.id}`, { replace: true });
  }
</script>

<div class="page">
  {#if error}
    <div class="empty"><h2>{error}</h2><a href="/people" use:link>回到人物</a></div>
  {:else if person}
    <div class="head">
      <a class="icon-btn" href="/people" use:link aria-label="回到人物"><Icon path={mdiArrowLeft} /></a>
      <img src={`/api/faces/${person.cover_face_id}/thumb`} alt="" />
      <div class="grow">
        <button class="name" onclick={rename}>{person.name || "新增名稱"}<Icon path={mdiPencilOutline} size={18} /></button>
        <div class="muted small">{person.count} 張照片</div>
      </div>
      <button class="btn ghost small" onclick={merge}><Icon path={mdiAccountMultiplePlusOutline} size={18} />合併</button>
      <button class="icon-btn" onclick={toggleHidden} title={person.hidden ? "取消隱藏" : "隱藏這個人物"}>
        <Icon path={person.hidden ? mdiEyeOutline : mdiEyeOffOutline} />
      </button>
    </div>
    <div class="chips groups">
      <span class="muted small">分類：</span>
      {#each [...new Set([...groups.map((g) => g.name), ...person.groups])] as g (g)}
        <button class="chip" class:on={person.groups.includes(g)} onclick={() => toggleGroup(g)}>{person.groups.includes(g) ? "✓ " : ""}{g}</button>
      {/each}
      <button class="chip" onclick={newGroup}>＋新分類</button>
    </div>
    <p class="muted tiny tip">認錯人？選取那些照片後按上方的「不是這個人」。分類名稱可以直接搜尋，例如「客戶 海邊」或 <code>group:客戶</code>。</p>
    <Grid assets={person.assets} />
  {:else}
    <p class="muted"><span class="spinner"></span></p>
  {/if}
</div>

<style>
  .head { display: flex; align-items: center; gap: 14px; margin: 12px 0 6px; flex-wrap: wrap; }
  .head a.icon-btn { color: var(--text); }
  .head img { width: 72px; height: 72px; border-radius: 50%; object-fit: cover; background: var(--bg-2); }
  .grow { flex: 1; min-width: 160px; }
  .name { display: flex; align-items: center; gap: 8px; border: 0; background: none; padding: 0; cursor: pointer; font-size: 24px; font-weight: 600; color: var(--text); }
  .name :global(svg) { color: var(--muted); }
  .tip { margin: 0 0 12px 54px; }
  .groups { margin: 4px 0 8px 54px; align-items: center; }
  code { background: var(--bg-2); padding: 1px 5px; border-radius: 5px; }
</style>
