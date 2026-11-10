<script>
  /**
   * 資料夾裡照片以外的檔案（文件、音樂、壓縮檔…）：名稱、類型、大小、日期。
   * 只畫出看得到的列，幾萬個檔案的資料夾捲動也一樣順；資料來自目錄，硬碟拔掉也看得到。
   * files：[[id, 名稱, 類型, 大小, 修改時間（秒）], …]
   */
  import Icon from "./Icon.svelte";
  import { bytes, count } from "../lib/format.js";
  import {
    mdiFileDocumentOutline, mdiMusicNote, mdiFolderZipOutline, mdiPackageVariantClosed, mdiFileOutline,
    mdiImageOutline, mdiVideoOutline, mdiCameraOutline,
  } from "../lib/icons.js";

  let { files = [], total = 0 } = $props();

  const ROW = 44;
  const MAX_ROWS = 10; // 超過就在框內捲動
  const ICONS = {
    document: mdiFileDocumentOutline, audio: mdiMusicNote, archive: mdiFolderZipOutline, package: mdiPackageVariantClosed,
    photo: mdiImageOutline, raw: mdiCameraOutline, video: mdiVideoOutline, other: mdiFileOutline,
  };
  const KIND_LABELS = { document: "文件", audio: "音樂", archive: "壓縮檔", package: "套件", photo: "照片", raw: "RAW", video: "影片", other: "其他" };

  let scrollTop = $state(0);
  const height = $derived(Math.min(files.length, MAX_ROWS) * ROW);
  const first = $derived(Math.max(0, Math.floor(scrollTop / ROW) - 5));
  const last = $derived(Math.min(files.length, Math.ceil((scrollTop + height) / ROW) + 5));
  const shown = $derived(files.slice(first, last));

  function date(sec) {
    if (!sec) return "";
    const d = new Date(sec * 1000);
    return `${d.getFullYear()}/${d.getMonth() + 1}/${d.getDate()}`;
  }
</script>

<div class="box" style:height="{height}px" onscroll={(e) => (scrollTop = e.currentTarget.scrollTop)} role="list" aria-label="檔案">
  <div class="spacer" style:height="{files.length * ROW}px">
    {#each shown as f, i (f[0])}
      <div class="row" role="listitem" style:top="{(first + i) * ROW}px" title={f[1]}>
        <span class="ic"><Icon path={ICONS[f[2]] || mdiFileOutline} size={20} /></span>
        <span class="name">{f[1]}</span>
        <span class="kind muted small">{KIND_LABELS[f[2]] || ""}</span>
        <span class="date muted small">{date(f[4])}</span>
        <span class="size">{bytes(f[3]) || "0 KB"}</span>
      </div>
    {/each}
  </div>
</div>
{#if total > files.length}<p class="muted tiny more">只列出前 {count(files.length)} 個，共 {count(total)} 個檔案。</p>{/if}

<style>
  .box { position: relative; overflow-y: auto; background: var(--surface-container-low); border-radius: var(--corner-large); overscroll-behavior: contain; }
  .spacer { position: relative; }
  .row {
    position: absolute; left: 0; right: 0; height: 44px; display: flex; align-items: center; gap: 12px; padding: 0 14px;
    border-bottom: 1px solid var(--outline-variant);
  }
  .ic { color: var(--on-surface-variant); display: flex; flex-shrink: 0; }
  .name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .kind { width: 56px; flex-shrink: 0; }
  .date { width: 92px; text-align: right; font-variant-numeric: tabular-nums; flex-shrink: 0; }
  .size { width: 84px; text-align: right; font-variant-numeric: tabular-nums; font-weight: 500; flex-shrink: 0; }
  .more { margin: 6px 0 0; }
  @media (max-width: 600px) { .kind, .date { display: none; } }
</style>
