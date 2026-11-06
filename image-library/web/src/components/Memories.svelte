<script>
  import { hscroll } from "../lib/hscroll.js";
  import { api, thumbUrl } from "../lib/api.js";
  import { app, openViewer } from "../lib/state.svelte.js";

  let items = $state([]);
  $effect(() => {
    app.refreshKey;
    api("/api/memories").then((m) => (items = m)).catch(() => {});
  });
</script>

{#if items.length}
  <div class="hs"><section class="memories" aria-label="那年今日" use:hscroll>
    {#each items as m (m.year)}
      <button class="card" onclick={() => openViewer(m.assets, 0)}>
        <img src={thumbUrl(m.assets[0])} alt="" loading="lazy" />
        <span class="label"><b>{m.years_ago} 年前</b><small>{m.year} · {m.count} 張</small></span>
      </button>
    {/each}
  </section></div>
{/if}

<style>
  .memories { display: flex; gap: 10px; overflow-x: auto; padding: 14px 0 4px; scrollbar-width: none; }
  .card {
    position: relative; flex-shrink: 0; width: 140px; height: 200px; border: 0; padding: 0; border-radius: var(--corner-medium);
    overflow: hidden; cursor: pointer; background: var(--surface-container);
  }
  .card img { width: 100%; height: 100%; object-fit: cover; transition: transform .3s; }
  .card:hover img { transform: scale(1.05); }
  .label {
    position: absolute; inset: auto 0 0 0; padding: 30px 10px 10px; color: #fff; text-align: left;
    background: linear-gradient(transparent, rgba(0,0,0,.7)); display: flex; flex-direction: column;
  }
  .label b { font-size: 16px; }
  .label small { opacity: .85; font-size: 12px; }
  @media (max-width: 760px) { .card { width: 112px; height: 160px; } .memories { padding: 10px 6px 0; } }
</style>
