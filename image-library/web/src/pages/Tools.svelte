<script>
  import { slider } from "../lib/slider.js";
  import Loading from "../components/Loading.svelte";
  import BackButton from "../components/BackButton.svelte";
  /**
   * 整理工具：截圖與文件、大檔案、重複照片、批次匯出。
   * 偵測結果都是「建議」，由使用者勾選後再決定要不要處理。
   */
  import Grid from "../components/Grid.svelte";
  import Icon from "../components/Icon.svelte";
  import JobList from "../components/JobList.svelte";
  import Treemap from "../components/Treemap.svelte";
  import KindBar from "../components/KindBar.svelte";
  import { fadeThrough } from "../lib/motion.js";
  import { api, thumbUrl } from "../lib/api.js";
  import { app, selection, refresh, toast, openViewer } from "../lib/state.svelte.js";
  import { navigate, link } from "../lib/router.svelte.js";
  import { trashAssets, reveal } from "../lib/actions.js";
  import { bytes, count } from "../lib/format.js";
  import { TOOLS, pinnedKeys } from "../lib/toolkit.js";
  import { pinnable, pin, unpin } from "../lib/pin.svelte.js";
  import {
    mdiFileExportOutline, mdiCheckAll, mdiDeleteOutline, mdiFolderOpenOutline,
    mdiChevronRight, mdiVideoOutline, mdiPinOutline, mdiPinOffOutline, mdiSortDescending,
  } from "../lib/icons.js";

  let { sub = "" } = $props();

  let summary = $state(null);
  let items = $state(null);
  let largeKind = $state("all");
  let largeTab = $state("files");
  let largeSort = $state("size");
  let kinds = $state([]);
  let tree = $state(null);
  let treeAt = $state({ root_id: null, path: "" });

  const DESC = {
    screens: "螢幕截圖、文件、收據，一次移出作品集。",
    large: "最佔空間的影片、照片與資料夾。",
    duplicates: "完全相同或幾乎一樣的照片。",
  };
  function countText(key) {
    const s = summary;
    if (key === "screens") return `${count(s.screens)} 張`;
    if (key === "large") return `影片共 ${bytes(s.videos_bytes) || "0 KB"}`;
    return s.dups === null ? "尚未尋找" : `${count(s.dups)} 組`;
  }
  const pinnedSet = $derived(new Set(pinnedKeys(app.server)));

  const TITLES = { screens: "截圖與文件", large: "大檔案" };

  $effect(() => {
    app.refreshKey;
    sub; largeKind; largeSort;
    load();
  });

  async function load() {
    try {
      if (!sub) summary = await api("/api/tools/summary");
      else if (sub === "screens") items = await api("/api/tools/screens");
      else if (sub === "large") {
        items = await api("/api/tools/large", { params: { kind: largeKind, sort: largeSort } });
        kinds = await api("/api/tools/size-by-kind");
        await loadTree();
      }
    } catch (e) {
      toast(e.message, "error");
    }
  }

  async function loadTree() {
    const params = treeAt.root_id === null ? {} : { root_id: treeAt.root_id, path: treeAt.path };
    tree = await api("/api/tools/folder-tree", { params });
  }

  function openTree(it) {
    if (!it.folder) {
      navigate(`/folders/${it.root_id}${it.path ? `?path=${encodeURIComponent(it.path)}` : ""}`);
      return;
    }
    treeAt = { root_id: it.root_id, path: it.path };
    loadTree().catch((e) => toast(e.message, "error"));
  }

  function treeUp(level) {
    if (level < 0) treeAt = { root_id: null, path: "" };
    else treeAt = { root_id: treeAt.root_id, path: treeAt.path.split("/").slice(0, level).join("/") };
    loadTree().catch((e) => toast(e.message, "error"));
  }

  const crumbs = $derived(treeAt.path ? treeAt.path.split("/") : []);

  function shortDate(at) {
    if (!at) return "";
    const [d] = at.split("T");
    const [y, m, day] = d.split("-");
    return `${y}/${Number(m)}/${Number(day)}`;
  }

  function selectAll(list) {
    for (const a of list) selection.add(a.id);
    toast(`已選取 ${list.length} 張，可以在上方選擇要做什麼`);
  }

  async function trashAll(list) {
    if (!list.length) return;
    await trashAssets(list.map((a) => a.id));
    refresh();
  }

  // 依理由分組（截圖）
  const groups = $derived.by(() => {
    if (!items || sub !== "screens") return [];
    const map = new Map();
    for (const a of items) map.set(a.reason, [...(map.get(a.reason) || []), a]);
    return [...map.entries()].map(([reason, list]) => ({ reason, list }));
  });


  function toggleRow(a) {
    selection.has(a.id) ? selection.delete(a.id) : selection.add(a.id);
  }
</script>

<div class="page tools">
  {#if !sub}
    <div class="page-head"><h1>整理工具</h1><span class="muted small hint">長按卡片拖到左側「工具」，或按圖釘，就能加入側邊欄</span></div>

    {#if summary}
      <JobList kinds={["export", "dups"]} compact />

      <div class="cards m3-stagger">
        {#each TOOLS as t (t.key)}
          {@const pinned = pinnedSet.has(t.key)}
          <a class="tool m3-state" href={t.href} use:link use:pinnable={t.key} title="長按可拖到左側「工具」">
            <span class="ic"><Icon path={t.icon} /></span>
            <button class="icon-btn pin-btn" class:on={pinned} onclick={(e) => { e.preventDefault(); e.stopPropagation(); pinned ? unpin(t.key) : pin(t.key); }}
              aria-label={pinned ? `從側邊欄移除${t.label}` : `把${t.label}加到側邊欄`} title={pinned ? "從側邊欄移除" : "加到側邊欄"}>
              <Icon path={pinned ? mdiPinOffOutline : mdiPinOutline} size={20} />
            </button>
            <b>{t.label}</b>
            <span class="muted small">{DESC[t.key]}</span>
            <span class="count">{countText(t.key)}</span>
          </a>
        {/each}
        <div class="tool">
          <span class="ic"><Icon path={mdiFileExportOutline} /></span>
          <b>批次匯出交件</b>
          <span class="muted small">選取照片後，按上方的「匯出」：指定長邊尺寸、浮水印、移除 GPS、重新命名。</span>
          <span class="count">在任何頁面選取照片即可</span>
        </div>
      </div>
    {:else}
      <Loading kind="rows" count={6} />
    {/if}
  {:else}
    <div class="page-head">
      <BackButton to="/tools" label="回到整理工具" />
      <h1>{TITLES[sub] || "整理工具"}</h1>
      {#if items}<span class="muted small">{count(items.length)} 個</span>{/if}
    </div>

    {#if !items}
      <Loading kind="grid" />
    {:else if sub === "screens"}
      {#if !items.length}
        <div class="empty"><h2>沒有找到截圖或文件</h2>
          <p>AI 分析完更多照片後，這裡會找到更多。</p></div>
      {/if}
      {#each groups as g (g.reason)}
        <section class="group-sec">
          <div class="group-head">
            <h2 class="section-title">{g.reason}<span class="muted small">{count(g.list.length)} 張</span></h2>
            <span class="spacer"></span>
            <button class="btn text small" onclick={() => selectAll(g.list)}><Icon path={mdiCheckAll} size={18} />全選</button>
            <button class="btn text small danger-text" onclick={() => trashAll(g.list)}><Icon path={mdiDeleteOutline} size={18} />垃圾桶</button>
          </div>
          <Grid assets={g.list} />
        </section>
      {/each}
    {:else if sub === "large"}
      <div class="bar">
        <div class="seg" role="tablist" aria-label="檢視" use:slider>
          <button role="tab" aria-selected={largeTab === "files"} class:on={largeTab === "files"} onclick={() => (largeTab = "files")}>檔案</button>
          <button role="tab" aria-selected={largeTab === "folders"} class:on={largeTab === "folders"} onclick={() => (largeTab = "folders")}>資料夾</button>
        </div>
        {#if largeTab === "files"}
          <span class="spacer"></span>
          <label class="sort"><Icon path={mdiSortDescending} size={18} />
            <select bind:value={largeSort} aria-label="排序">
              <option value="size">依大小</option>
              <option value="newest">依拍攝時間（新到舊）</option>
              <option value="oldest">依拍攝時間（舊到新）</option>
            </select>
          </label>
        {/if}
      </div>
      {#if largeTab === "files"}
        <KindBar {kinds} selected={largeKind} onpick={(k) => (largeKind = k)} />
        <p class="muted tiny list-note">最大的 {count(items.length)} 個{largeKind === "all" ? "檔案" : kinds.find((k) => k.key === largeKind)?.label || ""}{largeSort === "size" ? "" : "，依拍攝時間排列"}</p>
        <ul class="rows m3-stagger">
          {#each items as a, i (a.id)}
            <li class:sel={selection.has(a.id)}>
              <input type="checkbox" checked={selection.has(a.id)} onchange={() => toggleRow(a)} aria-label="選取 {a.name}" />
              <button class="thumb-btn" onclick={() => openViewer(items, i)} aria-label="檢視 {a.name}">
                <img src={thumbUrl(a)} alt="" loading="lazy" />
                {#if a.type === "video"}<span class="vid"><Icon path={mdiVideoOutline} size={14} /></span>{/if}
                {#if a.raw}<span class="rawb">RAW</span>{/if}
              </button>
              <div class="grow">
                <b>{a.name}</b>
                <span class="muted tiny path">{a.rel_path}</span>
              </div>
              <span class="date muted small">{shortDate(a.at)}</span>
              <span class="size">{bytes(a.size)}</span>
              <button class="icon-btn" title="在 Finder 中顯示" aria-label="在 Finder 中顯示" onclick={() => reveal(a.id)}><Icon path={mdiFolderOpenOutline} size={20} /></button>
            </li>
          {/each}
        </ul>
        <p class="muted tiny">勾選後可以在上方移到垃圾桶（會先問你）。</p>
      {:else if tree}
        <nav class="tcrumbs" aria-label="位置">
          <button class="btn text small" onclick={() => treeUp(-1)} disabled={treeAt.root_id === null}>全部資料夾</button>
          {#if treeAt.root_id !== null}
            <Icon path={mdiChevronRight} size={16} />
            <button class="btn text small" onclick={() => treeUp(0)} disabled={!crumbs.length}>{tree.root_name}</button>
            {#each crumbs as c, i (i)}
              <Icon path={mdiChevronRight} size={16} />
              <button class="btn text small" onclick={() => treeUp(i + 1)} disabled={i === crumbs.length - 1}>{c}</button>
            {/each}
          {/if}
          <span class="spacer"></span>
          <span class="muted small">共 {bytes(tree.bytes) || "0 KB"}</span>
        </nav>
        {#if tree.items.length}
          {#key treeAt.root_id + "/" + treeAt.path}
            <div class="tm" in:fadeThrough><Treemap items={tree.items} total={tree.bytes} onopen={openTree} /></div>
          {/key}
          <p class="muted tiny">格子越大越佔空間；點資料夾往下一層，斜線格是直接放在這層的檔案。</p>
          <ul class="rows m3-stagger">
            {#each tree.items as f (f.path + f.name)}
              <li>
                <button class="frow m3-state" onclick={() => openTree(f)}>
                  <div class="grow">
                    <b>{f.name}</b>
                    <span class="meter"><span style:width="{(f.bytes / (tree.items[0]?.bytes || 1)) * 100}%"></span></span>
                    <span class="muted tiny">{count(f.files)} 個檔案</span>
                  </div>
                  <span class="size">{bytes(f.bytes)}</span>
                  <Icon path={mdiChevronRight} />
                </button>
              </li>
            {/each}
          </ul>
        {:else}
          <div class="empty"><h2>這裡沒有檔案</h2></div>
        {/if}
      {/if}
    {/if}
  {/if}
</div>

<style>
  .cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap: 12px; margin-top: 16px; }
  .tool {
    display: flex; flex-direction: column; gap: 6px; padding: 20px; border-radius: var(--corner-large);
    background: var(--surface-container-low); color: var(--on-surface); text-decoration: none; min-height: 170px;
    transition: border-radius var(--spring-expressive-default-spatial-duration) var(--spring-expressive-default-spatial),
      background-color var(--spring-effects-default-duration) var(--spring-effects-default);
  }
  a.tool:hover { border-radius: var(--corner-extra-large); background: var(--surface-container); }
  .tool { position: relative; touch-action: manipulation; -webkit-touch-callout: none; user-select: none; }
  .tool .pin-btn { position: absolute; top: 12px; right: 12px; width: 40px; height: 40px; color: var(--on-surface-variant); opacity: 0; transition: opacity var(--spring-effects-fast-duration) var(--spring-effects-fast); }
  .tool:hover .pin-btn, .tool .pin-btn.on, .tool .pin-btn:focus-visible { opacity: 1; }
  .tool .pin-btn.on { color: var(--primary); }
  @media (hover: none) { .tool .pin-btn { opacity: 1; } }
  :global(.tool.pin-lifting) { transform: scale(.96); opacity: .6; transition: transform .2s, opacity .2s; }
  .hint { flex-basis: 100%; margin-top: -10px; }
  .tool b { font-size: 16px; line-height: 24px; font-weight: 500; }
  .tool .ic {
    width: 48px; height: 48px; border-radius: var(--corner-large); display: flex; align-items: center; justify-content: center;
    background: var(--secondary-container); color: var(--on-secondary-container); margin-bottom: 6px;
  }
  .tool .count { margin-top: auto; font-size: 14px; font-weight: 500; color: var(--primary); }
  .back { color: var(--on-surface); }
  .bar { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin: 0 0 14px; }
  .spacer { flex: 1; }
  .seg { display: inline-flex; border: 1px solid var(--outline); border-radius: var(--corner-full); overflow: hidden; }
  .seg button { border: 0; background: none; color: var(--on-surface); padding: 0 16px; height: 36px; font-size: 14px; font-weight: 500; cursor: pointer; }
  .seg button + button { border-left: 1px solid var(--outline); }
  .seg button.on { background: var(--secondary-container); color: var(--on-secondary-container); }
  .group-sec { margin-bottom: 24px; }
  .group-head { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
  .group-head .section-title { display: flex; align-items: baseline; gap: 10px; margin: 16px 0 10px; }
  .rows { list-style: none; padding: 0; margin: 0 0 10px; display: flex; flex-direction: column; background: var(--surface-container-low); border-radius: var(--corner-large); overflow: hidden; }
  .rows li { display: flex; align-items: center; gap: 12px; padding: 8px 14px; transition: background-color var(--spring-effects-fast-duration) var(--spring-effects-fast); }
  .rows li + li { border-top: 1px solid var(--outline-variant); }
  .rows li.sel { background: var(--secondary-container); }
  .thumb-btn { position: relative; border: 0; padding: 0; background: var(--surface-container); width: 56px; height: 56px; border-radius: var(--corner-small); overflow: hidden; cursor: pointer; flex-shrink: 0; }
  .thumb-btn img { width: 100%; height: 100%; object-fit: cover; display: block; }
  .vid { position: absolute; right: 3px; bottom: 3px; background: rgb(0 0 0 / .55); color: #fff; border-radius: var(--corner-extra-small); display: flex; padding: 1px; }
  .rawb { position: absolute; right: 3px; bottom: 3px; font-size: 8px; line-height: 12px; font-weight: 500; color: #fff; background: rgb(0 0 0 / .4); border: 1px solid rgb(255 255 255 / .45); border-radius: 3px; padding: 0 3px; }
  .grow { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
  .grow b { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-weight: 500; }
  .path { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .size { min-width: 84px; text-align: right; font-variant-numeric: tabular-nums; font-weight: 500; }
  .frow { display: flex; align-items: center; gap: 12px; width: 100%; border: 0; background: none; color: inherit; text-align: left; padding: 6px 0; cursor: pointer; border-radius: var(--corner-small); }
  .rows li:has(.frow) { padding: 4px 10px; }
  .sort { display: inline-flex; align-items: center; gap: 6px; height: 36px; padding: 0 6px 0 12px; border: 1px solid var(--outline); border-radius: var(--corner-full); color: var(--on-surface-variant); }
  .sort select { border: 0; background: none; color: var(--on-surface); font-size: 14px; font-weight: 500; height: 34px; cursor: pointer; outline: none; }
  .list-note { margin: 0 0 8px; }
  .date { min-width: 84px; text-align: right; font-variant-numeric: tabular-nums; }
  .tcrumbs { display: flex; align-items: center; flex-wrap: wrap; gap: 0; margin: 0 0 8px; color: var(--on-surface-variant); }
  .tcrumbs .btn:disabled { color: var(--on-surface); background: none; opacity: 1; }
  .tm { margin-bottom: 6px; }
  @media (max-width: 600px) { .date { display: none; } }
  .meter { display: block; height: 6px; border-radius: 3px; background: var(--surface-container-highest); overflow: hidden; margin: 4px 0; max-width: 420px; }
  .meter span { display: block; height: 100%; background: var(--primary); border-radius: 3px; }
  .skeleton { height: 220px; border-radius: var(--corner-large); background: var(--surface-container-low); animation: pulse 1.2s ease-in-out infinite; }
  @keyframes pulse { 50% { opacity: .5; } }
</style>
