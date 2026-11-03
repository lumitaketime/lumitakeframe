<script>
  import BackButton from "../components/BackButton.svelte";
  /**
   * 人物頁（參考 Google 相簿）：上方直接輸入名字按「完成」，下方是分類與依日期分組的照片。
   * 輸入的名字和現有人物相同時，詢問是否為同一個人並合併。
   */
  import DateGroups from "../components/DateGroups.svelte";
  import Icon from "../components/Icon.svelte";
  import { api } from "../lib/api.js";
  import { navigate, link } from "../lib/router.svelte.js";
  import { app, showDialog, toast, refresh } from "../lib/state.svelte.js";
  import { confirm } from "../lib/actions.js";
  import { undoable } from "../lib/undo.svelte.js";
  import { count } from "../lib/format.js";
  import { mdiArrowLeft, mdiEyeOffOutline, mdiEyeOutline, mdiAccountMultiplePlusOutline, mdiPlus, mdiCheck } from "../lib/icons.js";

  let { id } = $props();
  let person = $state(null);
  let error = $state("");
  let groups = $state([]);
  let draft = $state("");
  let saving = $state(false);
  let input = $state();

  $effect(() => {
    app.context = { person: id };
  });
  $effect(() => {
    app.refreshKey;
    api("/api/people/groups").then((g) => (groups = g)).catch(() => {});
    api(`/api/people/${id}`)
      .then((p) => {
        const first = !person || person.id !== p.id;
        person = p;
        if (first || document.activeElement !== input) draft = p.name || "";
      })
      .catch((e) => (error = e.message));
  });

  const changed = $derived(!!person && draft.trim() !== (person.name || ""));

  async function save() {
    const name = draft.trim();
    if (!changed || saving) return;
    saving = true;
    try {
      if (name) {
        const all = await api("/api/people", { params: { all: 1 } });
        const same = all.find((p) => p.id !== person.id && (p.name || "").trim().toLowerCase() === name.toLowerCase());
        if (same) {
          const ok = await confirm(`已經有一位「${same.name}」`, "是同一個人嗎？合併後，兩邊的照片都會歸到同一個人物。", { ok: "是，合併", cancel: "不是" });
          if (ok) {
            const res = await api("/api/people/merge", { body: { target: same.id, sources: [person.id] } });
            const back = person.id;
            undoable(`已合併到「${same.name}」`, async () => {
              await api("/api/people/unmerge", { body: { undo: res.undo } });
              navigate(`/people/${back}`, { replace: true });
            });
            refresh();
            navigate(`/people/${same.id}`, { replace: true });
            return;
          }
        }
      }
      await api(`/api/people/${id}`, { body: { name } });
      toast(name ? `已命名為「${name}」，可以直接搜尋名字` : "已清除名字");
      refresh();
      input?.blur();
    } catch (e) {
      toast(e.message, "error");
    } finally {
      saving = false;
    }
  }

  function onkey(e) {
    if (e.key === "Enter") save();
    if (e.key === "Escape") {
      draft = person?.name || "";
      input?.blur();
    }
  }

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

  async function toggleHidden() {
    await api(`/api/people/${id}`, { body: { hidden: !person.hidden } });
    toast(person.hidden ? "已取消隱藏" : "已隱藏，可在人物頁勾選「顯示已隱藏」找回");
    refresh();
  }

  async function merge() {
    const target = await showDialog("person", { exclude: id, title: "和誰是同一個人？" });
    if (!target) return;
    const res = await api("/api/people/merge", { body: { target: target.id, sources: [id] } });
    const back = id;
    undoable(`已合併到「${target.name || "另一位人物"}」`, async () => {
      await api("/api/people/unmerge", { body: { undo: res.undo } });
      navigate(`/people/${back}`, { replace: true });
    });
    navigate(`/people/${target.id}`, { replace: true });
  }

  const allGroups = $derived(person ? [...new Set([...groups.map((g) => g.name), ...person.groups])] : []);
</script>

<div class="page">
  {#if error}
    <div class="empty"><h2>{error}</h2><a href="/people" use:link>回到人物</a></div>
  {:else if person}
    <div class="name-row">
      <BackButton to="/people" label="回到人物" />
      <img class="avatar" src={`/api/faces/${person.cover_face_id}/thumb`} alt="" />
      <input
        class="name-input"
        bind:this={input}
        bind:value={draft}
        onkeydown={onkey}
        placeholder="新名稱或暱稱"
        aria-label="人物名稱"
        maxlength="60"
      />
      {#if changed}
        <button class="done" onclick={save} disabled={saving}>{saving ? "儲存中…" : "完成"}</button>
      {/if}
      <span class="spacer"></span>
      <button class="icon-btn" onclick={merge} title="和其他人物合併"><Icon path={mdiAccountMultiplePlusOutline} /></button>
      <button class="icon-btn" onclick={toggleHidden} title={person.hidden ? "取消隱藏" : "隱藏這個人物"}>
        <Icon path={person.hidden ? mdiEyeOutline : mdiEyeOffOutline} />
      </button>
    </div>

    <div class="pills" aria-label="人物分類">
      {#each allGroups as g (g)}
        <button class="pill" class:on={person.groups.includes(g)} onclick={() => toggleGroup(g)} aria-pressed={person.groups.includes(g)}>
          {#if person.groups.includes(g)}<Icon path={mdiCheck} size={16} />{/if}{g}
        </button>
      {/each}
      <button class="pill add" onclick={newGroup}><Icon path={mdiPlus} size={16} />分類</button>
      <span class="muted small cnt">{count(person.count)} 張照片</span>
    </div>

    {#key id}<DateGroups assets={person.assets} storeKey={`person:${id}`} defaultGroup="day" />{/key}
    <p class="muted tiny tip">認錯人？打開那張照片的資訊，在「人物」按鉛筆更正。名字和分類都可以直接搜尋，例如「客戶 海邊」。</p>
  {:else}
    <p class="muted"><span class="spinner"></span></p>
  {/if}
</div>

<style>
  .name-row { display: flex; align-items: center; gap: 10px; margin: 8px 0 10px; flex-wrap: wrap; }
  .back { color: var(--text); }
  .avatar { width: 40px; height: 40px; border-radius: 50%; object-fit: cover; background: var(--bg-2); flex-shrink: 0; }
  .name-input {
    font-size: 20px; font-weight: 600; color: var(--text); background: none; border: 0; border-bottom: 2px solid var(--line);
    padding: 6px 2px; min-width: 0; width: min(320px, 60vw); outline: none;
  }
  .name-input::placeholder { color: var(--muted); font-weight: 400; }
  .name-input:focus { border-bottom-color: var(--primary); }
  .done { border: 0; background: none; color: var(--primary); font-weight: 600; font-size: 14px; cursor: pointer; padding: 6px 10px; border-radius: 8px; }
  .done:hover { background: var(--primary-soft); }
  .spacer { flex: 1; }
  .pills { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin: 0 0 8px 50px; }
  .pill {
    display: inline-flex; align-items: center; gap: 4px; border: 1px solid var(--line); background: none; color: var(--text);
    border-radius: 999px; padding: 5px 14px; font-size: 13px; cursor: pointer;
  }
  .pill.on { background: var(--primary-soft); color: var(--primary); border-color: transparent; font-weight: 600; }
  .pill.add { color: var(--muted); }
  .cnt { margin-left: 4px; }
  .tip { margin-top: 18px; }
  @media (max-width: 760px) { .pills { margin-left: 0; } }
</style>
