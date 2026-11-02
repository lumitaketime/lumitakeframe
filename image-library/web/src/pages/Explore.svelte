<script>
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
  {#if !data}
    <p class="muted"><span class="spinner"></span></p>
  {:else}
    {#if data.tags.length}
      <h2 class="section-title">事物</h2>
      <div class="strip">
        {#each data.tags as t (t.value)}
          <button class="tile" onclick={() => go(`tag:${q(t.value)}`)}>
            <img src={thumbUrl({ id: t.cover })} alt="" loading="lazy" />
            <span>{t.value}</span>
          </button>
        {/each}
      </div>
    {:else}
      <div class="empty small">
        <h2>AI 分析後，這裡會整理出照片中的事物與場景</h2>
        <p>到 <a href="/settings" use:link>設定</a> 選擇模型並開始分析。</p>
      </div>
    {/if}

    {#if data.scenes.length}
      <h2 class="section-title">場景</h2>
      <div class="strip">
        {#each data.scenes as s (s.value)}
          <button class="tile" onclick={() => go(`"${s.value}"`)}>
            <img src={thumbUrl({ id: s.cover })} alt="" loading="lazy" /><span>{s.value}</span>
          </button>
        {/each}
      </div>
    {/if}

    {#if data.gps}
      <h2 class="section-title">地點</h2>
      <a class="map-link" href="/map" use:link>在地圖上瀏覽 {data.gps.toLocaleString()} 個有 GPS 的項目 →</a>
    {/if}

    {#if data.years.length}
      <h2 class="section-title">年份</h2>
      <div class="strip">
        {#each data.years as y (y.value)}
          <button class="tile" onclick={() => go(`year:${y.value}`)}>
            <img src={thumbUrl({ id: y.cover })} alt="" loading="lazy" /><span>{y.value}<small>{y.count.toLocaleString()}</small></span>
          </button>
        {/each}
      </div>
    {/if}

    {#if data.cameras.length}
      <h2 class="section-title">相機</h2>
      <div class="chips">
        {#each data.cameras as c (c.value)}
          <button class="chip" onclick={() => go(`camera:${q(c.value)}`)}>{c.value}<span class="muted">{c.count}</span></button>
        {/each}
      </div>
    {/if}
    {#if data.lenses.length}
      <h2 class="section-title">鏡頭</h2>
      <div class="chips">
        {#each data.lenses as l (l.value)}
          <button class="chip" onclick={() => go(`lens:${q(l.value)}`)}>{l.value}<span class="muted">{l.count}</span></button>
        {/each}
      </div>
    {/if}
  {/if}
</div>

<style>
  .strip { display: grid; grid-auto-flow: column; grid-auto-columns: 156px; gap: 12px; overflow-x: auto; padding-bottom: 8px; scrollbar-width: thin; }
  .tile { position: relative; border: 0; padding: 0; border-radius: var(--radius); overflow: hidden; aspect-ratio: 1; cursor: pointer; background: var(--bg-2); }
  .tile img { width: 100%; height: 100%; object-fit: cover; transition: transform .25s; }
  .tile:hover img { transform: scale(1.05); }
  .tile span {
    position: absolute; left: 0; right: 0; bottom: 0; padding: 24px 10px 8px; color: #fff; font-weight: 600; text-align: left;
    background: linear-gradient(transparent, rgba(0,0,0,.7)); font-size: 14px; display: flex; flex-direction: column;
  }
  .tile small { font-weight: 400; opacity: .8; font-size: 12px; }
  .chip span { margin-left: 4px; font-size: 12px; }
  .map-link { display: inline-block; padding: 14px 18px; background: var(--bg-2); border-radius: var(--radius); text-decoration: none; }
  @media (max-width: 760px) { .strip { grid-auto-columns: 124px; } }
</style>
