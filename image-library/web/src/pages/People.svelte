<script>
  import ExploreTabs from "../components/ExploreTabs.svelte";
  import Icon from "../components/Icon.svelte";
  import { api } from "../lib/api.js";
  import { app, refresh, showDialog, toast } from "../lib/state.svelte.js";
  import { link, navigate } from "../lib/router.svelte.js";
  import { mdiCheckCircle, mdiCheckboxBlankCircleOutline, mdiClose } from "../lib/icons.js";

  let people = $state(null);
  let groups = $state([]);
  let showHidden = $state(false);
  let filter = $state("");
  let selecting = $state(false);
  let picked = $state(new Set());

  $effect(() => {
    app.refreshKey;
    api("/api/people", { params: { all: showHidden ? 1 : 0 } }).then((p) => (people = p));
    api("/api/people/groups").then((g) => (groups = g));
  });

  const shown = $derived((people || []).filter((p) => !filter || p.groups.includes(filter)));
  const named = $derived(shown.filter((p) => p.name));
  const unnamed = $derived(shown.filter((p) => !p.name));

  function click(p, e) {
    if (e.metaKey || e.ctrlKey) return; // 新分頁開啟
    e.preventDefault();
    if (!selecting) return navigate(`/people/${p.id}`);
    const next = new Set(picked);
    next.has(p.id) ? next.delete(p.id) : next.add(p.id);
    picked = next;
  }

  async function assign(group, remove = false) {
    if (!group) {
      group = await showDialog("prompt", { title: "新增分類", placeholder: "例如：家人、客戶、2024 婚禮", ok: "加入", value: "" });
      if (!group?.trim()) return;
      group = group.trim();
    }
    await api("/api/people/groups", { body: { ids: [...picked], [remove ? "remove" : "add"]: [group] } });
    toast(remove ? `已從「${group}」移除 ${picked.size} 位` : `已把 ${picked.size} 位加入「${group}」`);
    picked = new Set();
    selecting = false;
    refresh();
  }
</script>

<div class="page">
  <div class="page-head">
    <h1>探索</h1>
    {#if selecting}
      <span class="muted small">已選 {picked.size} 位</span>
      <button class="icon-btn" onclick={() => { selecting = false; picked = new Set(); }} aria-label="取消"><Icon path={mdiClose} /></button>
    {:else}
      <button class="btn small ghost" onclick={() => (selecting = true)}>選取並分類</button>
    {/if}
    <label class="small muted"><input type="checkbox" bind:checked={showHidden} /> 顯示已隱藏</label>
  </div>
  <ExploreTabs />

  {#if selecting && picked.size}
    <div class="assign">
      <span class="small">加入分類：</span>
      {#each groups as g (g.name)}<button class="chip" onclick={() => assign(g.name)}>＋{g.name}</button>{/each}
      <button class="chip" onclick={() => assign(null)}>＋新分類…</button>
      {#if filter}<button class="chip" onclick={() => assign(filter, true)}>從「{filter}」移除</button>{/if}
    </div>
  {/if}

  {#if groups.some((g) => g.count)}
    <div class="chips groups">
      <button class="chip" class:on={!filter} onclick={() => (filter = "")}>全部</button>
      {#each groups.filter((g) => g.count) as g (g.name)}
        <button class="chip" class:on={filter === g.name} onclick={() => (filter = filter === g.name ? "" : g.name)}>{g.name}<span class="muted">{g.count}</span></button>
      {/each}
      {#if filter}<button class="chip" onclick={() => navigate(`/search?q=${encodeURIComponent(`group:${filter}`)}`)}>看「{filter}」的所有照片 →</button>{/if}
    </div>
  {/if}

  {#if people && !people.length}
    <div class="empty">
      <h2>還沒有人物</h2>
      <p>到 <a href="/settings/faces" use:link>設定 → 人臉辨識</a> 下載模型並開始偵測。<br />同一個人出現 3 次以上就會自動成為一個人物，點進去即可命名與分類。</p>
    </div>
  {/if}
  {#each [["已命名", named], [`尚未命名（${unnamed.length}）`, unnamed]] as [title, list] (title)}
    {#if list.length}
      <h2 class="section-title">{title}</h2>
      <div class="people">
        {#each list as p (p.id)}
          <a class="person" class:hidden-person={p.hidden} class:picked={picked.has(p.id)} href={`/people/${p.id}`} onclick={(e) => click(p, e)}>
            <span class="face">
              <img src={`/api/faces/${p.cover_face_id}/thumb`} alt="" loading="lazy" />
              {#if selecting}<span class="check"><Icon path={picked.has(p.id) ? mdiCheckCircle : mdiCheckboxBlankCircleOutline} size={24} /></span>{/if}
            </span>
            <b class:muted={!p.name}>{p.name || "新增名稱"}</b>
            <span>{p.count} 張</span>
            {#if p.groups.length}<span class="tags">{p.groups.join("・")}</span>{/if}
          </a>
        {/each}
      </div>
    {/if}
  {/each}
</div>

<style>
  .groups { margin-bottom: 8px; }
  .groups .chip span { margin-left: 4px; font-size: 12px; }
  .assign { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; background: var(--primary-soft); border-radius: 14px; padding: 10px 12px; margin-bottom: 12px; position: sticky; top: 0; z-index: 3; }
  .people { display: grid; grid-template-columns: repeat(auto-fill, minmax(120px, 1fr)); gap: 22px 14px; }
  .person { display: flex; flex-direction: column; align-items: center; text-decoration: none; color: var(--text); gap: 2px; min-width: 0; }
  .face { position: relative; width: 100%; max-width: 132px; }
  .face img { width: 100%; aspect-ratio: 1; border-radius: 50%; object-fit: cover; background: var(--bg-2); transition: transform .2s; display: block; }
  .person:hover img { transform: scale(1.04); }
  .person.picked img { outline: 4px solid var(--primary); outline-offset: 2px; }
  .check { position: absolute; top: 0; left: 0; color: var(--primary); background: var(--bg); border-radius: 50%; }
  .person b { margin-top: 8px; font-weight: 600; font-size: 14px; max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .person span { font-size: 12px; color: var(--muted); }
  .tags { color: var(--primary) !important; max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .hidden-person { opacity: .45; }
  label { display: flex; align-items: center; gap: 6px; }
  @media (max-width: 760px) { .people { grid-template-columns: repeat(auto-fill, minmax(96px, 1fr)); } }
</style>
