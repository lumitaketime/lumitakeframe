<script>
  import { api } from "../lib/api.js";
  import { app } from "../lib/state.svelte.js";
  import { link } from "../lib/router.svelte.js";

  let people = $state(null);
  let showHidden = $state(false);
  $effect(() => {
    app.refreshKey;
    api("/api/people", { params: { all: showHidden ? 1 : 0 } }).then((p) => (people = p));
  });
  const named = $derived((people || []).filter((p) => p.name));
  const unnamed = $derived((people || []).filter((p) => !p.name));
</script>

<div class="page">
  <div class="page-head">
    <h1>人物</h1>
    <label class="small muted"><input type="checkbox" bind:checked={showHidden} /> 顯示已隱藏</label>
  </div>
  {#if people && !people.length}
    <div class="empty">
      <h2>還沒有人物</h2>
      <p>到 <a href="/settings#faces" use:link>設定 → 人臉辨識</a> 下載模型並開始偵測。<br />同一個人出現 3 次以上就會自動成為一個人物，點進去即可命名。</p>
    </div>
  {/if}
  {#if named.length}
    <h2 class="section-title">已命名</h2>
    <div class="people">
      {#each named as p (p.id)}
        <a class="person" class:hidden-person={p.hidden} href={`/people/${p.id}`} use:link>
          <img src={`/api/faces/${p.cover_face_id}/thumb`} alt="" loading="lazy" />
          <b>{p.name}</b><span>{p.count} 張</span>
        </a>
      {/each}
    </div>
  {/if}
  {#if unnamed.length}
    <h2 class="section-title">尚未命名（{unnamed.length}）</h2>
    <div class="people">
      {#each unnamed as p (p.id)}
        <a class="person" class:hidden-person={p.hidden} href={`/people/${p.id}`} use:link>
          <img src={`/api/faces/${p.cover_face_id}/thumb`} alt="" loading="lazy" />
          <b class="muted">新增名稱</b><span>{p.count} 張</span>
        </a>
      {/each}
    </div>
  {/if}
</div>

<style>
  .people { display: grid; grid-template-columns: repeat(auto-fill, minmax(120px, 1fr)); gap: 22px 14px; }
  .person { display: flex; flex-direction: column; align-items: center; text-decoration: none; color: var(--text); gap: 2px; min-width: 0; }
  .person img { width: 100%; max-width: 132px; aspect-ratio: 1; border-radius: 50%; object-fit: cover; background: var(--bg-2); transition: transform .2s; }
  .person:hover img { transform: scale(1.04); }
  .person b { margin-top: 8px; font-weight: 600; font-size: 14px; max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .person span { font-size: 12px; color: var(--muted); }
  .hidden-person { opacity: .45; }
  label { display: flex; align-items: center; gap: 6px; }
  @media (max-width: 760px) { .people { grid-template-columns: repeat(auto-fill, minmax(96px, 1fr)); } }
</style>
