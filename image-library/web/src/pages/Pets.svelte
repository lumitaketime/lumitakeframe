<script>
  /**
   * 寵物（像「人物」）：上方是認出來的每一隻毛孩，點進去可以命名；下方依 AI 描述分成狗、貓、鳥…
   * 還沒開啟寵物辨識時，先說明並提供一鍵下載。
   */
  import BackButton from "../components/BackButton.svelte";
  import DateGroups from "../components/DateGroups.svelte";
  import ExploreTabs from "../components/ExploreTabs.svelte";
  import JobList from "../components/JobList.svelte";
  import Icon from "../components/Icon.svelte";
  import { api, thumbUrl } from "../lib/api.js";
  import { app, refresh, toast } from "../lib/state.svelte.js";
  import { link } from "../lib/router.svelte.js";
  import { count } from "../lib/format.js";
  import { mdiPaw, mdiEyeOffOutline } from "../lib/icons.js";

  let { kind = "" } = $props();
  let data = $state(null);
  let detail = $state(null);
  let showHidden = $state(false);
  let hiddenPets = $state([]);
  let starting = $state(false);

  const busy = $derived((app.server?.jobs?.active || []).some((j) => j.kind === "pet_model" || j.kind === "pets"));

  $effect(() => {
    app.refreshKey;
    if (kind) api(`/api/pets/${kind}`).then((d) => (detail = d)).catch(() => (detail = { label: "找不到", assets: [] }));
    else api("/api/pets").then((d) => (data = d));
  });

  $effect(() => {
    if (showHidden) api("/api/petid/all").then((all) => (hiddenPets = all.filter((p) => p.hidden)));
  });

  async function setup() {
    starting = true;
    try {
      await api("/api/settings", { body: { pet_enabled: 1 } });
      if (data.installed) await api("/api/jobs", { body: { kind: "pets" } });
      else await api("/api/jobs", { body: { kind: "pet_model", model: data.model || "standard" } });
      toast(data.installed ? "開始辨識照片裡的貓狗" : "開始下載寵物辨識模型，完成後會自動辨識");
      refresh();
    } catch (e) {
      toast(e.message, "error");
    } finally {
      starting = false;
    }
  }

  async function runPending() {
    await api("/api/jobs", { body: { kind: "pets" } });
    toast(`開始辨識 ${count(data.pending)} 張照片裡的貓狗`);
    refresh();
  }
</script>

<div class="page">
  {#if !kind}
    <div class="page-head"><h1>探索</h1></div>
    <ExploreTabs />
    {#if !data}
      <p class="muted"><span class="spinner"></span></p>
    {:else}
      <section class="sec">
        <div class="sec-head">
          <h2 class="section-title">你的毛孩</h2>
          {#if data.pets.length}<span class="muted small">{count(data.pets.length)} 隻</span>{/if}
          <span class="spacer"></span>
          {#if data.enabled && data.installed && data.pending && !busy}
            <button class="btn ghost small" onclick={runPending}>辨識 {count(data.pending)} 張新照片</button>
          {/if}
        </div>

        {#if !data.enabled || !data.installed}
          <div class="setup">
            <span class="paw"><Icon path={mdiPaw} size={32} /></span>
            <div class="grow">
              <b>認出每一隻貓狗，像人物一樣命名</b>
              <p class="muted small">在這台電腦上找出照片裡的貓和狗，依長相分組。替牠取名後，搜尋名字就能找到所有照片。需要下載約 124 MB 的模型，照片不會上傳。</p>
            </div>
            <button class="btn" onclick={setup} disabled={starting || busy}>
              {#if starting || busy}<span class="spinner"></span>{/if}{data.installed ? "開始辨識" : "下載並開始"}
            </button>
          </div>
        {/if}
        <JobList kinds={["pet_model", "pets", "pet_cluster"]} compact />

        {#if data.pets.length}
          <div class="pets m3-stagger">
            {#each data.pets as p (p.id)}
              <a class="pet" href={`/pets/id/${p.id}`} use:link>
                <img src={`/api/pet-thumbs/${p.cover}`} alt="" loading="lazy" />
                <span class="pname" class:unnamed={!p.name}>{p.name || "新增名字"}</span>
                <span class="muted tiny">{p.kind_label} · {count(p.count)} 張</span>
              </a>
            {/each}
          </div>
          {#if data.hidden}
            <button class="btn text small" onclick={() => (showHidden = !showHidden)}><Icon path={mdiEyeOffOutline} size={18} />{showHidden ? "收起已隱藏" : `已隱藏 ${data.hidden} 隻`}</button>
            {#if showHidden}
              <div class="pets">
                {#each hiddenPets as p (p.id)}
                  <a class="pet dim" href={`/pets/id/${p.id}`} use:link>
                    <img src={`/api/pet-thumbs/${p.cover}`} alt="" loading="lazy" />
                    <span class="pname" class:unnamed={!p.name}>{p.name || "未命名"}</span>
                  </a>
                {/each}
              </div>
            {/if}
          {/if}
        {:else if data.enabled && data.installed && !busy}
          <p class="muted small">還沒有認出寵物。同一隻出現在兩張以上的照片，就會出現在這裡。</p>
        {/if}
      </section>

      <section class="sec">
        <h2 class="section-title">依種類</h2>
        {#if !data.kinds.length}
          <p class="muted small">AI 分析過的照片中出現狗、貓、鳥、兔子等動物時，會自動整理在這裡。</p>
        {:else}
          <div class="card-grid m3-stagger">
            {#each data.kinds as k (k.key)}
              <a class="cover-card" href={`/pets/${k.key}`} use:link>
                <div class="cover"><img src={thumbUrl({ id: k.cover })} alt="" loading="lazy" /></div>
                <div class="name">{k.label}</div>
                <div class="sub">{count(k.count)} 張</div>
              </a>
            {/each}
          </div>
          <p class="muted tiny">依 AI 寫下的描述與關鍵字分類，包含鳥、兔子、魚等不在個別辨識範圍內的動物。</p>
        {/if}
      </section>
    {/if}
  {:else}
    {#if detail}
      {#key kind}
        <DateGroups assets={detail.assets} storeKey={`pets:${kind}`} title={detail.label} back="/pets" crumbs={[{ label: "寵物", href: "/pets" }]} />
      {/key}
    {:else}
      <div class="page-head"><BackButton to="/pets" /></div>
      <p class="muted"><span class="spinner"></span></p>
    {/if}
  {/if}
</div>

<style>
  .sec { margin-bottom: 28px; }
  .sec-head { display: flex; align-items: baseline; gap: 10px; }
  .spacer { flex: 1; }
  .setup {
    display: flex; align-items: center; gap: 16px; flex-wrap: wrap; padding: 20px; margin-bottom: 12px;
    background: var(--surface-container-low); border-radius: var(--corner-large);
  }
  .setup .grow { flex: 1; min-width: 240px; display: flex; flex-direction: column; gap: 4px; }
  .setup b { font-size: 16px; font-weight: 500; }
  .setup p { margin: 0; max-width: 64ch; }
  .paw { width: 56px; height: 56px; border-radius: 50%; display: flex; align-items: center; justify-content: center; background: var(--tertiary-container); color: var(--on-tertiary-container); flex-shrink: 0; }
  .pets { display: grid; grid-template-columns: repeat(auto-fill, minmax(112px, 1fr)); gap: 16px 12px; margin: 8px 0 12px; }
  .pet { display: flex; flex-direction: column; align-items: center; gap: 4px; text-decoration: none; color: var(--on-surface); text-align: center; border-radius: var(--corner-medium); padding: 4px; }
  .pet img {
    width: 96px; height: 96px; border-radius: 50%; object-fit: cover; background: var(--surface-container-high);
    transition: border-radius var(--spring-expressive-default-spatial-duration) var(--spring-expressive-default-spatial);
  }
  .pet:hover img { border-radius: var(--corner-extra-large); }
  .pet.dim { opacity: .6; }
  .pname { font-size: 14px; font-weight: 500; max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .pname.unnamed { color: var(--primary); }
  a.cover-card { text-decoration: none; }
</style>
