<script>
  /** 寵物：依 AI 描述與關鍵字分成狗、貓、鳥…（個別寵物的辨識之後加入）。 */
  import DateGroups from "../components/DateGroups.svelte";
  import ExploreTabs from "../components/ExploreTabs.svelte";
  import Icon from "../components/Icon.svelte";
  import { api, thumbUrl } from "../lib/api.js";
  import { app } from "../lib/state.svelte.js";
  import { link } from "../lib/router.svelte.js";
  import { count } from "../lib/format.js";
  import { mdiArrowLeft } from "../lib/icons.js";

  let { kind = "" } = $props();
  let kinds = $state(null);
  let detail = $state(null);

  $effect(() => {
    app.refreshKey;
    if (kind) api(`/api/pets/${kind}`).then((d) => (detail = d)).catch(() => (detail = { label: "找不到", assets: [] }));
    else api("/api/pets").then((d) => (kinds = d));
  });
</script>

<div class="page">
  {#if !kind}
    <div class="page-head"><h1>探索</h1></div>
    <ExploreTabs />
    {#if !kinds}
      <p class="muted"><span class="spinner"></span></p>
    {:else if !kinds.length}
      <div class="empty">
        <h2>還沒有找到寵物</h2>
        <p>AI 分析過的照片中出現狗、貓、鳥、兔子等動物時，會自動整理在這裡。</p>
      </div>
    {:else}
      <div class="card-grid m3-stagger">
        {#each kinds as k (k.key)}
          <a class="cover-card" href={`/pets/${k.key}`} use:link>
            <div class="cover"><img src={thumbUrl({ id: k.cover })} alt="" loading="lazy" /></div>
            <div class="name">{k.label}</div>
            <div class="sub">{count(k.count)} 張</div>
          </a>
        {/each}
      </div>
      <p class="muted tiny note">依 AI 寫下的描述與關鍵字分類。分辨「是哪一隻」的個別寵物辨識會在之後的版本加入。</p>
    {/if}
  {:else}
    <div class="page-head">
      <a class="icon-btn back" href="/pets" use:link aria-label="回到寵物"><Icon path={mdiArrowLeft} /></a>
      <h1>{detail?.label || ""}</h1>
      {#if detail}<span class="muted small">{count(detail.assets.length)} 張</span>{/if}
    </div>
    {#if detail}
      {#key kind}<DateGroups assets={detail.assets} storeKey={`pets:${kind}`} />{/key}
    {:else}
      <p class="muted"><span class="spinner"></span></p>
    {/if}
  {/if}
</div>

<style>
  .back { color: var(--on-surface); }
  .note { margin-top: 20px; }
  a.cover-card { text-decoration: none; }
</style>
