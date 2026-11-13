<script>
  import ExpandGrid from "../components/ExpandGrid.svelte";
  import Loading from "../components/Loading.svelte";
  import ExploreTabs from "../components/ExploreTabs.svelte";
  import { api, thumbUrl } from "../lib/api.js";
  import { navigate, link } from "../lib/router.svelte.js";
  import { app } from "../lib/state.svelte.js";

  let data = $state(null);
  $effect(() => {
    app.refreshKey;
    api("/api/explore").then((d) => (data = d));
  });

  const q = (s) => (/\s/.test(s) ? `"${s}"` : s);
  const go = (query) => navigate(`/search?q=${encodeURIComponent(query)}`);
</script>

<div class="page">
  <div class="page-head"><h1>探索</h1></div>
  <ExploreTabs />
  {#if !data}
    <Loading kind="cards" />
  {:else}
    {#if data.people?.length}
      <h2 class="section-title"><a href="/people" use:link class="more">人物 →</a></h2>
      <ExpandGrid min={104} items={data.people} key={(p) => p.id}>
        {#snippet item(p)}
        <a class="person" href={`/people/${p.id}`} use:link>
          <img src={`/api/faces/${p.cover_face_id}/thumb`} alt="" loading="lazy" />
          <span>{p.name || "未命名"}</span>
        </a>
        {/snippet}
      </ExpandGrid>
    {/if}

    {#if data.tags.length}
      <h2 class="section-title">事物</h2>
      <ExpandGrid min={156} items={data.tags} key={(t) => t.value}>
        {#snippet item(t)}
        <button class="tile" onclick={() => go(`tag:${q(t.value)}`)}>
          <img src={thumbUrl({ id: t.cover })} alt="" loading="lazy" />
          <span>{t.value}</span>
        </button>
        {/snippet}
      </ExpandGrid>
    {:else}
      <div class="empty small">
        <h2>AI 分析後，這裡會整理出照片中的事物與場景</h2>
        <p>到 <a href="/settings/ai" use:link>設定 → AI 分析</a> 選擇模型並開始分析。</p>
      </div>
    {/if}

    {#if data.scenes.length}
      <h2 class="section-title">場景</h2>
      <ExpandGrid min={156} items={data.scenes} key={(s) => s.value}>
        {#snippet item(s)}
        <button class="tile" onclick={() => go(`"${s.value}"`)}>
          <img src={thumbUrl({ id: s.cover })} alt="" loading="lazy" /><span>{s.value}</span>
        </button>
        {/snippet}
      </ExpandGrid>
    {/if}

    {#if data.places?.length}
      <h2 class="section-title">地點</h2>
      <ExpandGrid min={156} items={data.places} key={(p) => p.value}>
        {#snippet item(p)}
        <button class="tile" onclick={() => go(`place:${q(p.value)}`)}>
          <img src={thumbUrl({ id: p.cover })} alt="" loading="lazy" /><span>{p.value}<small>{p.count.toLocaleString()}</small></span>
        </button>
        {/snippet}
      </ExpandGrid>
    {/if}

    {#if data.years.length}
      <h2 class="section-title">年份</h2>
      <ExpandGrid min={156} items={data.years} key={(y) => y.value}>
        {#snippet item(y)}
        <button class="tile" onclick={() => go(`year:${y.value}`)}>
          <img src={thumbUrl({ id: y.cover })} alt="" loading="lazy" /><span>{y.value}<small>{y.count.toLocaleString()}</small></span>
        </button>
        {/snippet}
      </ExpandGrid>
    {/if}

  {/if}
</div>

<style>
  .tile { position: relative; border: 0; padding: 0; border-radius: var(--radius); overflow: hidden; aspect-ratio: 1; cursor: pointer; background: var(--surface-container); }
  .tile img { width: 100%; height: 100%; object-fit: cover; transition: transform var(--dur); }
  .tile:hover img { transform: scale(1.05); }
  .tile span {
    position: absolute; left: 0; right: 0; bottom: 0; padding: 24px 10px 8px; color: var(--media-fg); font-weight: 500; text-align: left;
    background: linear-gradient(transparent, var(--media-scrim-strong)); font-size: var(--text-body); display: flex; flex-direction: column;
  }
  .tile small { font-weight: 400; opacity: .8; font-size: var(--text-callout); }
  .more { color: var(--on-surface); text-decoration: none; }
  .person { display: flex; flex-direction: column; align-items: center; gap: 6px; text-decoration: none; color: var(--on-surface); font-size: var(--text-body); }
  .person img { width: 96px; height: 96px; border-radius: 50%; object-fit: cover; background: var(--surface-container); }
  .person span { max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
</style>
