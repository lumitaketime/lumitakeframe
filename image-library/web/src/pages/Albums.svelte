<script>
  import Icon from "../components/Icon.svelte";
  import { api, thumbUrl } from "../lib/api.js";
  import { navigate, link } from "../lib/router.svelte.js";
  import { app, showDialog, toast } from "../lib/state.svelte.js";
  import { mdiImageAlbum, mdiPlus, mdiAutoFix } from "../lib/icons.js";

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
  {#if albums && !albums.length}
    <div class="empty">
      <h2>用相簿整理作品</h2>
      <p>也可以在搜尋結果按「存成智慧相簿」，例如 <code>rating:4 camera:x100vi</code>，新照片符合就自動加入。<br />相簿只是收藏清單，不會複製或搬動檔案；同一張照片可以放進多個相簿。<br />想實際整理硬碟資料夾，請用「資料夾」或「搬移」。</p>
    </div>
  {/if}
  <div class="card-grid">
    {#each albums || [] as a (a.id)}
      <a class="cover-card" href={`/albums/${a.id}`} use:link>
        <div class="cover">
          {#if a.cover}<img src={thumbUrl({ id: a.cover })} alt="" loading="lazy" />{:else}<Icon path={mdiImageAlbum} size={48} />{/if}
        </div>
        <div class="name">{a.name}</div>
        <div class="sub">{a.count} 個項目{range(a) ? ` · ${range(a)}` : ""}</div>
      </a>
    {/each}
  </div>
</div>

<style>
  a.cover-card { text-decoration: none; }
  .smart { margin-bottom: 8px; }
  .smart-badge { position: absolute; right: 8px; top: 8px; background: var(--primary); color: var(--on-primary); border-radius: 50%; width: 24px; height: 24px; display: flex; align-items: center; justify-content: center; }
</style>
