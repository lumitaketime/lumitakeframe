<script>
  /**
   * 一隻寵物的頁面（像人物頁）：上方直接輸入名字按「完成」；名字和另一隻相同時詢問是否合併。
   * 選取照片後可以「不是牠」把照片移出。
   */
  import DateGroups from "../components/DateGroups.svelte";
  import { api } from "../lib/api.js";
  import { navigate, link } from "../lib/router.svelte.js";
  import { app, selection, toast, refresh } from "../lib/state.svelte.js";
  import { confirm } from "../lib/actions.js";
  import { undoable } from "../lib/undo.svelte.js";
  import { count } from "../lib/format.js";
  import { mdiEyeOffOutline, mdiEyeOutline, mdiImageRemoveOutline, mdiPencilOutline } from "../lib/icons.js";

  let { id } = $props();
  let pet = $state(null);
  let error = $state("");
  let draft = $state("");
  let saving = $state(false);
  let input = $state();

  $effect(() => {
    app.refreshKey;
    api(`/api/petid/${id}`)
      .then((p) => {
        const first = !pet || pet.id !== p.id;
        pet = p;
        if (first || document.activeElement !== input) draft = p.name || "";
      })
      .catch((e) => (error = e.message));
  });

  const changed = $derived(!!pet && draft.trim() !== (pet.name || ""));

  async function save() {
    const name = draft.trim();
    if (!changed || saving) return;
    saving = true;
    try {
      if (name) {
        const all = await api("/api/petid/all");
        const same = all.find((p) => p.id !== pet.id && (p.name || "").trim().toLowerCase() === name.toLowerCase());
        if (same) {
          const ok = await confirm(`已經有一隻「${same.name}」`, "是同一隻嗎？合併後，兩邊的照片都會歸到同一隻。", { ok: "是，合併", cancel: "不是" });
          if (!ok) return;
        }
      }
      const res = await api(`/api/petid/${id}`, { body: { name } });
      if (res.merged) {
        const back = pet.id;
        undoable(`已合併到「${name}」`, async () => {
          await api("/api/petid/unmerge", { body: { undo: res.undo } });
          navigate(`/pets/id/${back}`, { replace: true });
        });
      } else toast(name ? `已命名為「${name}」，可以直接搜尋名字` : "已清除名字");
      refresh();
      input?.blur();
      if (res.merged) navigate(`/pets/id/${res.id}`, { replace: true });
    } catch (e) {
      toast(e.message, "error");
    } finally {
      saving = false;
    }
  }

  function onkey(e) {
    if (e.key === "Enter") save();
    if (e.key === "Escape") {
      draft = pet?.name || "";
      input?.blur();
    }
  }

  async function toggleHidden() {
    await api(`/api/petid/${id}`, { body: { hidden: !pet.hidden } });
    toast(pet.hidden ? "已取消隱藏" : "已隱藏，可在寵物頁的「已隱藏」找回");
    refresh();
  }

  async function notThisPet() {
    const ids = [...selection];
    if (!ids.length) {
      toast("先選取不是牠的照片（按住 ⌘ 點選，或長按），再按一次");
      return;
    }
    const ok = await confirm(`把 ${ids.length} 張移出？`, `這些照片裡的不是${pet.name ? `「${pet.name}」` : "這隻"}。之後重新分群也不會再歸進來。`, { ok: "移出" });
    if (!ok) return;
    const res = await api(`/api/petid/${id}`, { body: { remove: ids } });
    selection.clear();
    toast(`已移出 ${res.removed} 張`);
    refresh();
  }
</script>

<div class="page">
  {#if error}
    <div class="empty"><h2>{error}</h2><a href="/pets" use:link>回到寵物</a></div>
  {:else if pet}
    {#snippet nameField()}
      <div class="name-wrap">
        <img class="avatar" src={`/api/pet-thumbs/${pet.cover}`} alt="" />
        <input
          class="name-input"
          bind:this={input}
          bind:value={draft}
          onkeydown={onkey}
          placeholder="替牠取名字"
          aria-label="寵物名字"
          maxlength="60"
        />
        {#if changed}<button class="btn text small" onclick={save} disabled={saving}>{saving ? "儲存中…" : "完成"}</button>{/if}
      </div>
    {/snippet}
    {#key id}
      <DateGroups
        assets={pet.assets}
        storeKey={`pet:${id}`}
        defaultGroup="day"
        title=""
        titleExtra={nameField}
        subtitle={`${pet.kind_label} · ${count(pet.assets.length)} 張照片`}
        back="/pets"
        crumbs={[{ label: "寵物", href: "/pets" }]}
        menu={[
          { label: "改名字", icon: mdiPencilOutline, run: () => input?.focus() },
          { label: "選取的照片不是牠", icon: mdiImageRemoveOutline, run: notThisPet },
          { label: pet.hidden ? "取消隱藏" : "隱藏這隻", icon: pet.hidden ? mdiEyeOutline : mdiEyeOffOutline, run: toggleHidden },
        ]}
      />
    {/key}
    <p class="muted tiny tip">名字可以直接搜尋，例如「豆豆 海邊」。認錯了？選取那些照片，在右上角「⋮」選「選取的照片不是牠」。</p>
  {:else}
    <p class="muted"><span class="spinner"></span></p>
  {/if}
</div>

<style>
  .name-wrap { display: flex; align-items: center; gap: 10px; min-width: 0; }
  .avatar { width: 44px; height: 44px; border-radius: 50%; object-fit: cover; background: var(--surface-container-high); flex-shrink: 0; }
  .name-input {
    font-size: 24px; line-height: 32px; font-weight: 400; color: var(--on-surface); background: none; border: 0;
    border-bottom: 1px solid transparent; padding: 2px 2px; min-width: 0; width: min(320px, 50vw); outline: none;
    transition: border-color var(--spring-effects-fast-duration) var(--spring-effects-fast);
  }
  .name-input:hover { border-bottom-color: var(--outline); }
  .name-input::placeholder { color: var(--primary); }
  .name-input:focus { border-bottom: 2px solid var(--primary); }
  .tip { margin-top: 18px; }
</style>
