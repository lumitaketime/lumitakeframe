<script>
  import Loading from "../components/Loading.svelte";
  import Icon from "../components/Icon.svelte";
  import { api, thumbUrl } from "../lib/api.js";
  import { navigate, link } from "../lib/router.svelte.js";
  import { app, showDialog, toast } from "../lib/state.svelte.js";
  import Menu from "../components/Menu.svelte";
  import { flip } from "svelte/animate";
  import { DUR } from "../lib/motion.js";
  import { mdiImageAlbum, mdiPlus, mdiAutoFix, mdiSort, mdiStar, mdiStarOutline } from "../lib/icons.js";
  import { reorder, sortCards, moveKey } from "../lib/reorder.js";
  import { refresh } from "../lib/state.svelte.js";

  // ---- 排序、收藏、拖曳 ----
  const SORTS = [["updated", "最近更新"], ["name", "名稱"], ["created", "建立日期"], ["count", "照片數量"], ["custom", "自訂"]];
  const sortMode = $derived(app.server?.ui?.album_sort || "updated");
  let dragOrder = $state(null); // 拖曳中的順序（album id）
  const fields = (a) => ({ name: a.name, updated: a.updated_at, created: a.created_at, count: a.count, position: a.position });
  const display = $derived.by(() => {
    if (!albums) return [];
    if (!dragOrder) return sortCards(albums, sortMode, fields);
    const byId = new Map(albums.map((a) => [a.id, a]));
    return dragOrder.map((id) => byId.get(Number(id))).filter(Boolean);
  });
  const favs = $derived(display.filter((a) => a.favorite));
  const rest = $derived(display.filter((a) => !a.favorite));

  async function setSort(mode) {
    if (app.server?.ui) app.server.ui.album_sort = mode;
    await api("/api/settings", { body: { album_sort: mode } });
  }
  const sortItems = $derived([{ section: "排序" }, ...SORTS.map(([v, label]) => ({ label, checked: sortMode === v, run: () => setSort(v) }))]);

  async function toggleFav(e, a) {
    e.preventDefault();
    e.stopPropagation();
    a.favorite = a.favorite ? 0 : 1;
    await api(`/api/albums/${a.id}`, { body: { favorite: !!a.favorite } });
    toast(a.favorite ? `已收藏「${a.name}」，也會出現在側邊欄` : `已取消收藏「${a.name}」`);
    refresh();
  }

  const dragOpts = {
    onmove(from, to) {
      dragOrder = moveKey(dragOrder || display.map((a) => String(a.id)), from, to).map(String);
    },
    async ondrop() {
      if (!dragOrder) return;
      const ids = dragOrder.map(Number);
      ids.forEach((id, i) => { const a = albums.find((x) => x.id === id); if (a) a.position = i; });
      dragOrder = null;
      await api("/api/albums/order", { body: { ids } });
      if (sortMode !== "custom") {
        await setSort("custom");
        toast("已改成「自訂」排序，會記住你排的順序");
      }
    },
  };

  let albums = $state(null);
  let smart = $state([]);
  $effect(() => {
    app.refreshKey;
    api("/api/albums").then((a) => (albums = a));
    api("/api/smart-albums").then((a) => (smart = a));
  });

  async function create() {
    const name = await showDialog("prompt", { title: "建立相簿", placeholder: "相簿名稱，例如：2024 作品集", ok: "建立", value: "" });
    if (!name?.trim()) return;
    const a = await api("/api/albums", { body: { name: name.trim() } });
    toast("相簿已建立，在照片中選取後按「加到相簿」即可加入");
    navigate(`/albums/${a.id}`);
  }

  const range = (a) => {
    if (!a.start_at) return "";
    const s = a.start_at.slice(0, 7).replace("-", "/");
    const e = a.end_at.slice(0, 7).replace("-", "/");
    return s === e ? s : `${s} – ${e}`;
  };
</script>

<div class="page">
  <div class="page-head">
    <h1>相簿</h1>
    {#if albums?.length > 1}<Menu icon={mdiSort} label="排序" items={sortItems} />{/if}
    <button class="btn" onclick={create}><Icon path={mdiPlus} size={18} />建立相簿</button>
  </div>
  {#if smart.length}
    <h2 class="section-title">智慧相簿 <span class="muted small">（依搜尋條件自動更新）</span></h2>
    <div class="card-grid smart">
      {#each smart as a (a.id)}
        <a class="cover-card" href={`/albums/smart/${a.id}`} use:link>
          <div class="cover">
            {#if a.cover}<img src={thumbUrl({ id: a.cover })} alt="" loading="lazy" />{:else}<Icon path={mdiAutoFix} size={48} />{/if}
            <span class="smart-badge"><Icon path={mdiAutoFix} size={14} /></span>
          </div>
          <div class="name">{a.name}</div>
          <div class="sub">{a.count} 個項目 · {a.query}</div>
        </a>
      {/each}
    </div>
    <h2 class="section-title">相簿</h2>
  {/if}
  {#if !albums}<Loading kind="cards" />{/if}
  {#if albums && !albums.length}
    <div class="empty">
      <h2>用相簿整理作品</h2>
      <p>也可以在搜尋結果按「存成智慧相簿」，例如 <code>rating:4 camera:x100vi</code>，新照片符合就自動加入。<br />相簿只是收藏清單，不會複製或搬動檔案；同一張照片可以放進多個相簿。<br />想實際整理硬碟資料夾，請用「資料夾」或「搬移」。</p>
    </div>
  {/if}
  {#snippet card(a)}
    <a class="cover-card" href={`/albums/${a.id}`} use:link data-reorder-key={a.id} draggable="false">
      <div class="cover">
        {#if a.cover}<img src={thumbUrl({ id: a.cover })} alt="" loading="lazy" draggable="false" />{:else}<Icon path={mdiImageAlbum} size={48} />{/if}
        <button class="fav-btn" class:on={a.favorite} onclick={(e) => toggleFav(e, a)} aria-pressed={!!a.favorite}
          aria-label={a.favorite ? "取消收藏" : "收藏"} title={a.favorite ? "取消收藏" : "收藏（排在最前面，也會出現在側邊欄）"}>
          <Icon path={a.favorite ? mdiStar : mdiStarOutline} size={20} />
        </button>
      </div>
      <div class="name">{a.name}</div>
      <div class="sub">{a.count} 個項目{range(a) ? ` · ${range(a)}` : ""}</div>
    </a>
  {/snippet}
  {#if favs.length}
    <h2 class="section-title">收藏的相簿</h2>
    <div class="card-grid favs" use:reorder={dragOpts}>
      {#each favs as a (a.id)}<div class="slot" animate:flip={{ duration: DUR.quick }}>{@render card(a)}</div>{/each}
    </div>
    {#if rest.length}<h2 class="section-title">所有相簿</h2>{/if}
  {/if}
  <div class="card-grid" use:reorder={dragOpts}>
    {#each rest as a (a.id)}<div class="slot" animate:flip={{ duration: DUR.quick }}>{@render card(a)}</div>{/each}
  </div>
  {#if albums?.length > 1}<p class="muted tiny tip">按住相簿一下就可以拖曳排序（排完會改成「自訂」排序並記住）。</p>{/if}
</div>

<style>
  a.cover-card { text-decoration: none; display: block; }
  .favs { margin-bottom: 8px; }
  .tip { margin-top: 20px; }
  .smart { margin-bottom: 8px; }
  .smart-badge { position: absolute; right: 8px; top: 8px; background: var(--primary); color: var(--on-primary); border-radius: 50%; width: 24px; height: 24px; display: flex; align-items: center; justify-content: center; }
</style>
