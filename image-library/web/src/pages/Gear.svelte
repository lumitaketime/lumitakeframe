<script>
  import Grid from "../components/Grid.svelte";
  import Icon from "../components/Icon.svelte";
  import { api, thumbUrl } from "../lib/api.js";
  import { route, navigate } from "../lib/router.svelte.js";
  import { app } from "../lib/state.svelte.js";
  import { mdiCameraOutline, mdiCloseCircle } from "../lib/icons.js";

  let stats = $state(null);
  let result = $state(null);
  const KEYS = ["camera", "lens", "focal", "aperture", "iso"];
  const filters = $derived(Object.fromEntries(KEYS.filter((k) => route.query[k]).map((k) => [k, route.query[k]])));
  const active = $derived(Object.keys(filters).length > 0);

  $effect(() => {
    app.refreshKey;
    api("/api/gear").then((s) => (stats = s));
  });

  $effect(() => {
    const f = filters;
    if (!Object.keys(f).length) {
      result = null;
      return;
    }
    api("/api/gear/assets", { params: f }).then((r) => (result = r));
  });

  function toggle(key, value) {
    const next = { ...filters };
    if (next[key] === String(value)) delete next[key];
    else next[key] = String(value);
    const qs = new URLSearchParams(next).toString();
    navigate(`/gear${qs ? `?${qs}` : ""}`, { replace: true });
  }

  const years = (c) => {
    const a = (c.first || "").slice(0, 4);
    const b = (c.last || "").slice(0, 4);
    return a && b ? (a === b ? a : `${a}–${b}`) : "";
  };
  const range = (b) => `${b.min}-${b.max}`;
  const labelOf = (key, value) => {
    const list = { focal: stats?.focal, aperture: stats?.aperture, iso: stats?.iso }[key];
    return list?.find((b) => range(b) === value)?.label || value;
  };
</script>

<div class="page">
  <div class="page-head"><h1>器材</h1></div>
  {#if !stats}
    <p class="muted"><span class="spinner"></span></p>
  {:else if !stats.cameras.length}
    <div class="empty"><Icon path={mdiCameraOutline} size={56} /><h2>還沒有相機資訊</h2><p>照片的 EXIF 有相機與鏡頭資料時，這裡會依器材整理。</p></div>
  {:else}
    {#if active}
      <div class="active">
        {#each Object.entries(filters) as [k, v] (k)}
          <button class="chip on" onclick={() => toggle(k, v)}>
            {k === "camera" || k === "lens" ? v : labelOf(k, v)}<Icon path={mdiCloseCircle} size={16} />
          </button>
        {/each}
        <button class="btn small ghost" onclick={() => navigate("/gear", { replace: true })}>清除篩選</button>
        {#if result}<span class="muted small">{result.count.toLocaleString()} 張</span>{/if}
      </div>
    {/if}

    <h2 class="section-title">相機</h2>
    <div class="cams">
      {#each stats.cameras as c (c.name)}
        <button class="cam" class:on={filters.camera === c.name} onclick={() => toggle("camera", c.name)}>
          <img src={thumbUrl({ id: c.cover })} alt="" loading="lazy" />
          <span class="cam-info"><b>{c.name}</b><small>{c.count.toLocaleString()} 張 · {years(c)}</small></span>
        </button>
      {/each}
    </div>

    {#if stats.lenses.length}
      <h2 class="section-title">鏡頭</h2>
      <div class="lenses">
        {#each stats.lenses as l (l.name)}
          <button class="lens" class:on={filters.lens === l.name} onclick={() => toggle("lens", l.name)}>
            <b>{l.name}</b>
            <span class="muted tiny">{l.cameras.join("、")}</span>
            <span class="n">{l.count.toLocaleString()}</span>
          </button>
        {/each}
      </div>
    {/if}

    {#if stats.combos.length}
      <h2 class="section-title">常用組合</h2>
      <div class="chips">
        {#each stats.combos as c (c.camera + c.lens)}
          <button class="chip" class:on={filters.camera === c.camera && filters.lens === c.lens}
            onclick={() => navigate(`/gear?${new URLSearchParams({ camera: c.camera, lens: c.lens })}`, { replace: true })}>
            {c.camera} ＋ {c.lens}<span class="muted">{c.count}</span>
          </button>
        {/each}
      </div>
    {/if}

    <div class="ranges">
      {#each [["focal", "焦段（等效 35mm）"], ["aperture", "光圈"], ["iso", "ISO"]] as [key, title] (key)}
        <div>
          <h2 class="section-title">{title}</h2>
          <div class="chips">
            {#each stats[key] as b (b.label)}
              <button class="chip" class:on={filters[key] === range(b)} disabled={!b.count} onclick={() => toggle(key, range(b))}>
                {b.label}<span class="muted">{b.count}</span>
              </button>
            {/each}
          </div>
        </div>
      {/each}
    </div>
    {#if stats.no_exif}<p class="muted tiny">另有 {stats.no_exif.toLocaleString()} 個項目沒有相機資訊（截圖、掃描檔或資訊被移除的照片）。</p>{/if}

    {#if result}
      <h2 class="section-title">篩選結果（{result.count.toLocaleString()}）</h2>
      <Grid assets={result.assets} />
    {/if}
  {/if}
</div>

<style>
  .active { position: sticky; top: 0; z-index: 5; background: var(--bg); display: flex; flex-wrap: wrap; gap: 6px; align-items: center; padding: 8px 0; }
  .active .chip { gap: 6px; }
  .cams { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 12px; }
  .cam {
    display: flex; gap: 12px; align-items: center; padding: 8px; border-radius: 16px; border: 2px solid transparent;
    background: var(--bg-2); cursor: pointer; text-align: left; color: inherit;
  }
  .cam.on { border-color: var(--primary); background: var(--primary-soft); }
  .cam img { width: 64px; height: 64px; border-radius: 12px; object-fit: cover; flex-shrink: 0; background: var(--bg-3); }
  .cam-info { display: flex; flex-direction: column; min-width: 0; }
  .cam-info b { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .cam-info small { color: var(--muted); }
  .lenses { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 6px; }
  .lens {
    display: grid; grid-template-columns: 1fr auto; grid-template-rows: auto auto; gap: 0 8px; padding: 8px 12px;
    border-radius: 12px; border: 2px solid transparent; background: var(--bg-2); cursor: pointer; text-align: left; color: inherit;
  }
  .lens.on { border-color: var(--primary); background: var(--primary-soft); }
  .lens b { font-weight: 600; font-size: 14px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .lens .n { grid-row: 1 / 3; grid-column: 2; align-self: center; font-weight: 600; color: var(--muted); }
  .ranges { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 0 24px; }
  .chip span { margin-left: 4px; font-size: 12px; }
  .chip:disabled { opacity: .4; cursor: default; }
  .empty :global(svg) { color: var(--muted); margin: 0 auto; }
</style>
