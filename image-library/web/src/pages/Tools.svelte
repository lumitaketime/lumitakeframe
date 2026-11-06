<script>
  import Loading from "../components/Loading.svelte";
  import BackButton from "../components/BackButton.svelte";
  /**
   * 整理工具：模糊照片、曝光問題、截圖與文件、大檔案、重複照片、批次匯出。
   * 偵測結果都是「建議」，由使用者勾選後再決定拒絕、搬移或刪除。
   */
  import Grid from "../components/Grid.svelte";
  import Icon from "../components/Icon.svelte";
  import JobList from "../components/JobList.svelte";
  import QualitySettings from "../components/QualitySettings.svelte";
  import Treemap from "../components/Treemap.svelte";
  import KindBar from "../components/KindBar.svelte";
  import { fadeThrough } from "../lib/motion.js";
  import { api, thumbUrl } from "../lib/api.js";
  import { app, selection, refresh, toast, openViewer } from "../lib/state.svelte.js";
  import { navigate, link } from "../lib/router.svelte.js";
  import { confirm, moveAssets, trashAssets, reveal } from "../lib/actions.js";
  import { bytes, count } from "../lib/format.js";
  import { TOOLS, pinnedKeys } from "../lib/toolkit.js";
  import { pinnable, pin, unpin } from "../lib/pin.svelte.js";
  import {
   
    mdiFileExportOutline, mdiFlagRemove, mdiCheckAll, mdiFolderMoveOutline, mdiDeleteOutline, mdiFolderOpenOutline,
    mdiChevronRight, mdiVideoOutline, mdiPinOutline, mdiPinOffOutline, mdiSortDescending, mdiFileDocumentEditOutline,
  } from "../lib/icons.js";

  let { sub = "" } = $props();

  let summary = $state(null);
  let items = $state(null);
  let showStd = $state(false);
  let largeKind = $state("all");
  let largeTab = $state("files");
  let largeSort = $state("size");
  let kinds = $state([]);
  let tree = $state(null);
  let treeAt = $state({ root_id: null, path: "" });
  let busy = $state(false);

  const DESC = {
    blurry: "失焦或手震的照片，連拍挑片時特別省時間。",
    exposure: "嚴重過曝、欠曝，或誤按快門拍到的全黑、全白照片。",
    screens: "螢幕截圖、文件、收據，一次移出作品集。",
    large: "最佔空間的影片、照片與資料夾。",
    duplicates: "完全相同或幾乎一樣的照片。",
  };
  function countText(key) {
    const s = summary;
    if (key === "blurry") return s.quality_done ? `${count(s.blurry)} 張建議檢查` : "尚未檢查";
    if (key === "exposure") return s.quality_done ? `${count(s.exposure)} 張` : "尚未檢查";
    if (key === "screens") return `${count(s.screens)} 張`;
    if (key === "large") return `影片共 ${bytes(s.videos_bytes) || "0 KB"}`;
    return s.dups === null ? "尚未尋找" : `${count(s.dups)} 組`;
  }
  const pinnedSet = $derived(new Set(pinnedKeys(app.server)));

  const TITLES = { blurry: "模糊照片", exposure: "曝光問題", screens: "截圖與文件", large: "大檔案" };
  const qualityRunning = $derived((app.server?.jobs?.active || []).some((j) => j.kind === "quality"));

  $effect(() => {
    app.refreshKey;
    sub; largeKind; largeSort;
    load();
  });

  async function load() {
    try {
      if (!sub) summary = await api("/api/tools/summary");
      else if (sub === "blurry") items = await api("/api/tools/blurry");
      else if (sub === "exposure") items = await api("/api/tools/exposure");
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

  async function runQuality(redo = false) {
    await api("/api/jobs", { body: { kind: "quality", redo } });
    toast(redo ? "開始重新檢查所有照片" : "開始檢查照片的清晰度與曝光");
    refresh();
  }

  function selectAll(list) {
    for (const a of list) selection.add(a.id);
    toast(`已選取 ${list.length} 張，可以在上方選擇要做什麼`);
  }

  /** 全部標為拒絕（Lightroom 的 X），附「復原」 */
  async function rejectAll(list) {
    if (!list.length) return;
    const ok = await confirm(`把 ${list.length} 張標為「拒絕」？`, "拒絕會同步到 Lightroom（X 標記），照片不會被刪除，隨時可以復原。", { ok: "標為拒絕" });
    if (!ok) return;
    busy = true;
    const before = new Map();
    for (const a of list) before.set(a.id, a.rating || 0);
    try {
      await api("/api/assets/bulk", { body: { ids: list.map((a) => a.id), action: "rating", value: -1 } });
      toast(`已把 ${list.length} 張標為拒絕`, "info", 8000, { label: "復原", run: () => undoReject(before) });
      refresh();
    } catch (e) {
      toast(e.message, "error");
    } finally {
      busy = false;
    }
  }

  async function undoReject(before) {
    const groups = new Map();
    for (const [id, r] of before) groups.set(r, [...(groups.get(r) || []), id]);
    for (const [r, ids] of groups) await api("/api/assets/bulk", { body: { ids, action: "rating", value: r } });
    toast("已復原");
    refresh();
  }

  async function moveAll(list) {
    if (!list.length) return;
    await moveAssets(list.map((a) => a.id));
    refresh();
  }

  async function trashAll(list) {
    if (!list.length) return;
    await trashAssets(list.map((a) => a.id));
    refresh();
  }

  // 依理由分組（曝光、截圖）
  const groups = $derived.by(() => {
    if (!items || (sub !== "exposure" && sub !== "screens")) return [];
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
      <section class="status">
        <div class="grow">
          <b>品質檢查</b>
          <span class="muted small">
            {#if summary.photos && summary.quality_done >= summary.photos}已檢查全部 {count(summary.photos)} 張照片的清晰度與曝光。
            {:else}已檢查 {count(summary.quality_done)} / {count(summary.photos)} 張。在這台電腦上計算，不用 AI 模型，十萬張約需數十分鐘。{/if}
          </span>
        </div>
        {#if summary.quality_done < summary.photos}
          <button class="btn" onclick={() => runQuality(false)} disabled={qualityRunning}>{qualityRunning ? "檢查中…" : "開始檢查"}</button>
        {:else}
          <button class="btn ghost" onclick={() => runQuality(true)} disabled={qualityRunning}>重新檢查</button>
        {/if}
      </section>
      <JobList kinds={["quality", "export", "dups"]} compact />

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
          <span class="ic"><Icon path={mdiFileDocumentEditOutline} /></span>
          <b>EXIF 編輯器</b>
          <span class="muted small">一次修改多張的檔名、拍攝時間、相機、鏡頭、GPS 地點、標題、作者與版權。RAW 寫進 .xmp，JPEG 直接寫入。</span>
          <span class="count">選取照片後按上方的 <Icon path={mdiFileDocumentEditOutline} size={16} /></span>
        </div>
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

    {#if sub === "blurry" || sub === "exposure"}
      <p class="muted small intro">
        {#if sub === "blurry"}依清晰度由低到高排列。淺景深人像只要主體清楚就不會列入；刻意的動態模糊作品也可能出現，請勾選確認後再處理。
        {:else}只列出明顯的問題。低調、高調或夜景作品也可能出現，請確認後再處理。{/if}
      </p>
    {/if}

    {#if sub === "blurry"}
      <div class="bar">
        <button class="btn ghost small" onclick={() => (showStd = !showStd)} aria-expanded={showStd}>{showStd ? "收起判定標準" : "調整判定標準"}</button>
        <span class="spacer"></span>
        {#if items?.length}
          <button class="btn ghost small" onclick={() => selectAll(items)}><Icon path={mdiCheckAll} size={18} />全選</button>
          <button class="btn small" onclick={() => rejectAll(items)} disabled={busy}><Icon path={mdiFlagRemove} size={18} />全部標為拒絕</button>
        {/if}
      </div>
    {/if}

    {#if sub === "exposure"}
      <div class="bar"><button class="btn ghost small" onclick={() => (showStd = !showStd)} aria-expanded={showStd}>{showStd ? "收起判定標準" : "調整判定標準"}</button></div>
    {/if}
    {#if showStd && (sub === "blurry" || sub === "exposure")}
      <div class="std"><QualitySettings only={sub === "blurry" ? "blur" : "exposure"} /></div>
    {/if}

    {#if !items}
      <Loading kind="grid" />
    {:else if sub === "blurry"}
      {#if items.length}
        <Grid assets={items} />
      {:else}
        <div class="empty"><h2>沒有找到模糊的照片</h2><p>如果還沒做過品質檢查，請回到「整理工具」按「開始檢查」。</p></div>
      {/if}
    {:else if sub === "exposure" || sub === "screens"}
      {#if !items.length}
        <div class="empty"><h2>{sub === "exposure" ? "沒有找到曝光問題" : "沒有找到截圖或文件"}</h2>
          <p>{sub === "exposure" ? "如果還沒做過品質檢查，請回到「整理工具」按「開始檢查」。" : "AI 分析完更多照片後，這裡會找到更多。"}</p></div>
      {/if}
      {#each groups as g (g.reason)}
        <section class="group-sec">
          <div class="group-head">
            <h2 class="section-title">{g.reason}<span class="muted small">{count(g.list.length)} 張</span></h2>
            <span class="spacer"></span>
            <button class="btn text small" onclick={() => selectAll(g.list)}><Icon path={mdiCheckAll} size={18} />全選</button>
            {#if sub === "exposure"}
              <button class="btn ghost small" onclick={() => rejectAll(g.list)} disabled={busy}><Icon path={mdiFlagRemove} size={18} />標為拒絕</button>
            {:else}
              <button class="btn ghost small" onclick={() => moveAll(g.list)}><Icon path={mdiFolderMoveOutline} size={18} />移到其他資料夾…</button>
            {/if}
            <button class="btn text small danger-text" onclick={() => trashAll(g.list)}><Icon path={mdiDeleteOutline} size={18} />垃圾桶</button>
          </div>
          <Grid assets={g.list} />
        </section>
      {/each}
    {:else if sub === "large"}
      <div class="bar">
        <div class="seg" role="tablist" aria-label="檢視">
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
        <p class="muted tiny">勾選後可以在上方移到垃圾桶或搬到外接硬碟。</p>
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
  .status {
    display: flex; align-items: center; gap: 16px; flex-wrap: wrap; background: var(--surface-container-low);
    border-radius: var(--corner-large); padding: 16px 20px; margin-bottom: 8px;
  }
  .status .grow { display: flex; flex-direction: column; gap: 2px; flex: 1; min-width: 220px; }
  .status b { font-size: 16px; font-weight: 500; }
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
  .intro { margin: -4px 0 12px; max-width: 72ch; }
  .bar { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin: 0 0 14px; }
  .spacer { flex: 1; }
  .seg { display: inline-flex; border: 1px solid var(--outline); border-radius: var(--corner-full); overflow: hidden; }
  .seg button { border: 0; background: none; color: var(--on-surface); padding: 0 16px; height: 36px; font-size: 14px; font-weight: 500; cursor: pointer; }
  .seg button + button { border-left: 1px solid var(--outline); }
  .seg button.on { background: var(--secondary-container); color: var(--on-secondary-container); }
  .group-sec { margin-bottom: 24px; }
  .std { background: var(--surface-container-low); border-radius: var(--corner-large); padding: 16px 20px; margin-bottom: 16px; animation: m3-enter var(--duration-medium4) var(--easing-emphasized-decelerate); }
  .group-head { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
  .group-head .section-title { display: flex; align-items: baseline; gap: 10px; margin: 16px 0 10px; }
  .rows { list-style: none; padding: 0; margin: 0 0 10px; display: flex; flex-direction: column; background: var(--surface-container-low); border-radius: var(--corner-large); overflow: hidden; }
  .rows li { display: flex; align-items: center; gap: 12px; padding: 8px 14px; transition: background-color var(--spring-effects-fast-duration) var(--spring-effects-fast); }
  .rows li + li { border-top: 1px solid var(--outline-variant); }
  .rows li.sel { background: var(--secondary-container); }
  .thumb-btn { position: relative; border: 0; padding: 0; background: var(--surface-container); width: 56px; height: 56px; border-radius: var(--corner-small); overflow: hidden; cursor: pointer; flex-shrink: 0; }
  .thumb-btn img { width: 100%; height: 100%; object-fit: cover; display: block; }
  .vid { position: absolute; right: 3px; bottom: 3px; background: rgb(0 0 0 / .55); color: #fff; border-radius: 4px; display: flex; padding: 1px; }
  .rawb { position: absolute; right: 3px; bottom: 3px; font-size: 8px; line-height: 12px; font-weight: 600; color: #fff; background: rgb(0 0 0 / .4); border: 1px solid rgb(255 255 255 / .45); border-radius: 3px; padding: 0 3px; }
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
