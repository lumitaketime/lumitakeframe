<script>
  /**
   * 整理工具：模糊照片、曝光問題、截圖與文件、大檔案、重複照片、批次匯出。
   * 偵測結果都是「建議」，由使用者勾選後再決定拒絕、搬移或刪除。
   */
  import Grid from "../components/Grid.svelte";
  import Icon from "../components/Icon.svelte";
  import JobList from "../components/JobList.svelte";
  import { api, thumbUrl } from "../lib/api.js";
  import { app, selection, refresh, toast, openViewer } from "../lib/state.svelte.js";
  import { navigate, link } from "../lib/router.svelte.js";
  import { confirm, moveAssets, trashAssets, reveal } from "../lib/actions.js";
  import { bytes, count } from "../lib/format.js";
  import {
    mdiArrowLeft, mdiBlur, mdiBrightness6, mdiCellphoneScreenshot, mdiChartBoxOutline, mdiContentDuplicate,
    mdiFileExportOutline, mdiFlagRemove, mdiCheckAll, mdiFolderMoveOutline, mdiDeleteOutline, mdiFolderOpenOutline,
    mdiChevronRight, mdiVideoOutline,
  } from "../lib/icons.js";

  let { sub = "" } = $props();

  let summary = $state(null);
  let items = $state(null);
  let folders = $state(null);
  let level = $state("standard");
  let largeKind = $state("all");
  let largeTab = $state("files");
  let busy = $state(false);

  const TITLES = { blurry: "模糊照片", exposure: "曝光問題", screens: "截圖與文件", large: "大檔案" };
  const qualityRunning = $derived((app.server?.jobs?.active || []).some((j) => j.kind === "quality"));

  $effect(() => {
    app.refreshKey;
    sub; level; largeKind;
    load();
  });

  async function load() {
    try {
      if (!sub) summary = await api("/api/tools/summary");
      else if (sub === "blurry") items = await api("/api/tools/blurry", { params: { level } });
      else if (sub === "exposure") items = await api("/api/tools/exposure");
      else if (sub === "screens") items = await api("/api/tools/screens");
      else if (sub === "large") {
        items = await api("/api/tools/large", { params: { kind: largeKind } });
        folders = await api("/api/tools/large-folders");
      }
    } catch (e) {
      toast(e.message, "error");
    }
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

  const maxFolder = $derived(Math.max(1, ...(folders || []).map((f) => f.bytes)));

  function toggleRow(a) {
    selection.has(a.id) ? selection.delete(a.id) : selection.add(a.id);
  }
</script>

<div class="page tools">
  {#if !sub}
    <div class="page-head"><h1>整理工具</h1></div>

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
        <a class="tool m3-state" href="/tools/blurry" use:link>
          <span class="ic"><Icon path={mdiBlur} /></span>
          <b>模糊照片</b>
          <span class="muted small">失焦或手震的照片，連拍挑片時特別省時間。</span>
          <span class="count">{summary.quality_done ? `${count(summary.blurry)} 張建議檢查` : "尚未檢查"}</span>
        </a>
        <a class="tool m3-state" href="/tools/exposure" use:link>
          <span class="ic"><Icon path={mdiBrightness6} /></span>
          <b>曝光問題</b>
          <span class="muted small">嚴重過曝、欠曝，或誤按快門拍到的全黑、全白照片。</span>
          <span class="count">{summary.quality_done ? `${count(summary.exposure)} 張` : "尚未檢查"}</span>
        </a>
        <a class="tool m3-state" href="/tools/screens" use:link>
          <span class="ic"><Icon path={mdiCellphoneScreenshot} /></span>
          <b>截圖與文件</b>
          <span class="muted small">螢幕截圖、文件、收據，一次移出作品集。</span>
          <span class="count">{count(summary.screens)} 張</span>
        </a>
        <a class="tool m3-state" href="/tools/large" use:link>
          <span class="ic"><Icon path={mdiChartBoxOutline} /></span>
          <b>大檔案</b>
          <span class="muted small">最佔空間的影片、照片與資料夾。</span>
          <span class="count">影片共 {bytes(summary.videos_bytes) || "0 KB"}</span>
        </a>
        <a class="tool m3-state" href="/duplicates" use:link>
          <span class="ic"><Icon path={mdiContentDuplicate} /></span>
          <b>重複照片</b>
          <span class="muted small">完全相同或幾乎一樣的照片。</span>
          <span class="count">{summary.dups === null ? "尚未尋找" : `${count(summary.dups)} 組`}</span>
        </a>
        <div class="tool">
          <span class="ic"><Icon path={mdiFileExportOutline} /></span>
          <b>批次匯出交件</b>
          <span class="muted small">選取照片後，按上方的「匯出」：指定長邊尺寸、浮水印、移除 GPS、重新命名。</span>
          <span class="count">在任何頁面選取照片即可</span>
        </div>
      </div>
    {:else}
      <div class="skeleton"></div>
    {/if}
  {:else}
    <div class="page-head">
      <a class="icon-btn back" href="/tools" use:link aria-label="回到整理工具"><Icon path={mdiArrowLeft} /></a>
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
        <div class="seg" role="group" aria-label="嚴格程度">
          {#each [["loose", "只列很糊的"], ["standard", "標準"], ["strict", "嚴格"]] as [v, label] (v)}
            <button class:on={level === v} onclick={() => (level = v)}>{label}</button>
          {/each}
        </div>
        <span class="spacer"></span>
        {#if items?.length}
          <button class="btn ghost small" onclick={() => selectAll(items)}><Icon path={mdiCheckAll} size={18} />全選</button>
          <button class="btn small" onclick={() => rejectAll(items)} disabled={busy}><Icon path={mdiFlagRemove} size={18} />全部標為拒絕</button>
        {/if}
      </div>
    {/if}

    {#if !items}
      <div class="skeleton"></div>
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
          <button class:on={largeTab === "files"} onclick={() => (largeTab = "files")}>檔案</button>
          <button class:on={largeTab === "folders"} onclick={() => (largeTab = "folders")}>資料夾</button>
        </div>
        {#if largeTab === "files"}
          <div class="seg" role="group" aria-label="類型">
            {#each [["all", "全部"], ["video", "影片"], ["photo", "照片"], ["raw", "RAW"]] as [v, label] (v)}
              <button class:on={largeKind === v} onclick={() => (largeKind = v)}>{label}</button>
            {/each}
          </div>
        {/if}
      </div>
      {#if largeTab === "files"}
        <ul class="rows m3-stagger">
          {#each items as a, i (a.id)}
            <li class:sel={selection.has(a.id)}>
              <input type="checkbox" checked={selection.has(a.id)} onchange={() => toggleRow(a)} aria-label="選取 {a.name}" />
              <button class="thumb-btn" onclick={() => openViewer(items, i)} aria-label="檢視 {a.name}">
                <img src={thumbUrl(a)} alt="" loading="lazy" />
                {#if a.type === "video"}<span class="vid"><Icon path={mdiVideoOutline} size={14} /></span>{/if}
              </button>
              <div class="grow">
                <b>{a.name}</b>
                <span class="muted tiny path">{a.rel_path}</span>
              </div>
              <span class="size">{bytes(a.size)}</span>
              <button class="icon-btn" title="在 Finder 中顯示" aria-label="在 Finder 中顯示" onclick={() => reveal(a.id)}><Icon path={mdiFolderOpenOutline} size={20} /></button>
            </li>
          {/each}
        </ul>
        <p class="muted tiny">勾選後可以在上方移到垃圾桶或搬到外接硬碟。</p>
      {:else if folders}
        <ul class="rows m3-stagger">
          {#each folders as f (f.root_id + f.path)}
            <li>
              <button class="frow m3-state" onclick={() => navigate(`/folders/${f.root_id}${f.path ? `?path=${encodeURIComponent(f.path)}` : ""}`)}>
                <div class="grow">
                  <b>{f.name}</b>
                  <span class="muted tiny path">{f.root}{f.path ? ` / ${f.path}` : ""}</span>
                  <span class="meter"><span style:width="{(f.bytes / maxFolder) * 100}%"></span></span>
                  <span class="muted tiny">{count(f.files)} 個檔案{f.videos ? `，其中 ${count(f.videos)} 部影片` : ""}</span>
                </div>
                <span class="size">{bytes(f.bytes)}</span>
                <Icon path={mdiChevronRight} />
              </button>
            </li>
          {/each}
        </ul>
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
  .group-head { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
  .group-head .section-title { display: flex; align-items: baseline; gap: 10px; margin: 16px 0 10px; }
  .rows { list-style: none; padding: 0; margin: 0 0 10px; display: flex; flex-direction: column; background: var(--surface-container-low); border-radius: var(--corner-large); overflow: hidden; }
  .rows li { display: flex; align-items: center; gap: 12px; padding: 8px 14px; transition: background-color var(--spring-effects-fast-duration) var(--spring-effects-fast); }
  .rows li + li { border-top: 1px solid var(--outline-variant); }
  .rows li.sel { background: var(--secondary-container); }
  .thumb-btn { position: relative; border: 0; padding: 0; background: var(--surface-container); width: 56px; height: 56px; border-radius: var(--corner-small); overflow: hidden; cursor: pointer; flex-shrink: 0; }
  .thumb-btn img { width: 100%; height: 100%; object-fit: cover; display: block; }
  .vid { position: absolute; right: 3px; bottom: 3px; background: rgb(0 0 0 / .55); color: #fff; border-radius: 4px; display: flex; padding: 1px; }
  .grow { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
  .grow b { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-weight: 500; }
  .path { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .size { min-width: 84px; text-align: right; font-variant-numeric: tabular-nums; font-weight: 500; }
  .frow { display: flex; align-items: center; gap: 12px; width: 100%; border: 0; background: none; color: inherit; text-align: left; padding: 6px 0; cursor: pointer; border-radius: var(--corner-small); }
  .rows li:has(.frow) { padding: 4px 10px; }
  .meter { display: block; height: 6px; border-radius: 3px; background: var(--surface-container-highest); overflow: hidden; margin: 4px 0; max-width: 420px; }
  .meter span { display: block; height: 100%; background: var(--primary); border-radius: 3px; }
  .skeleton { height: 220px; border-radius: var(--corner-large); background: var(--surface-container-low); animation: pulse 1.2s ease-in-out infinite; }
  @keyframes pulse { 50% { opacity: .5; } }
</style>
