<script>
  /**
   * 快速預覽（空白鍵）：不離開目前的清單，直接看選取的項目。
   * 照片、影片、音樂、PDF、文字檔可以直接看；其他檔案顯示類型圖示與目錄資訊。
   * 硬碟沒接上時只顯示縮圖與目錄資訊，不讀原檔。再按一次空白鍵或 Escape 關閉；方向鍵換上一個、下一個。
   */
  import { Button, ProgressIndicator } from "../ui/index.js";
  import KindIcon from "./KindIcon.svelte";
  import { t, formatBytes, formatDate } from "../i18n/index.svelte.js";
  import { previewUrl, thumbUrl, originalUrl } from "../lib/api.js";
  import { loadText, loadArchive, loadMusic, rawUrl, photoUrl } from "../data/browse.js";
  import { popIn, popOut, scrim } from "../lib/motion.js";

  let { item, online = true, driveName = "", canOpen = false, onclose, onmove, onopen, onreveal } = $props();

  // 照片：還沒進照片圖庫（沒有 image_id）、或從佔比圖打開時，直接從硬碟讀原檔做預覽（硬碟要接著）
  const PHOTO = new Set(["jpg", "jpeg", "jpe", "png", "webp", "gif", "bmp", "tif", "tiff", "heic", "heif", "avif",
    "cr2", "cr3", "crw", "nef", "nrw", "arw", "srf", "sr2", "raf", "orf", "rw2", "dng", "pef", "srw", "x3f", "3fr", "iiq", "rwl", "erf", "mos", "kdc", "mrw"]);
  const AUDIO = new Set(["mp3", "m4a", "aac", "wav", "flac", "ogg"]);
  // 壓縮檔：顯示掃描時記下的檔案清單（沒有解開，硬碟沒接上也看得到）
  const ARCHIVE = new Set(["zip", "rar", "7z", "tar", "tgz", "tbz", "tbz2", "txz", "gz", "bz2", "xz", "iso", "cab", "lha", "lzh", "xar"]);
  const TEXT = new Set(["txt", "md", "csv", "tsv", "json", "log", "xml", "html", "htm", "css", "js", "py", "srt", "yml", "yaml", "ini", "conf", "sh", "tex"]);
  const ext = $derived((item?.name.includes(".") ? item.name.split(".").pop() : "").toLowerCase());
  // 怎麼預覽：photo／video／audio／pdf／text 會顯示內容，info 只顯示圖示與資訊
  const mode = $derived(
    !item || item.type === "folder" ? "info"
      : item.id && ARCHIVE.has(ext) ? "archive"
      : item.image_id ? (item.kind === "video" ? (online ? "video" : "photo") : "photo")
        : !online ? "info"
          : PHOTO.has(ext) && item.path != null ? "file-photo"
          : AUDIO.has(ext) ? "audio" : ext === "pdf" ? "pdf" : TEXT.has(ext) ? "text" : "info");

  let text = $state(null);
  let tagsOf = $state({}); // 音樂的曲名、演出者、專輯
  let textError = $state("");
  let photoFailed = $state(false);
  $effect(() => {
    text = null;
    tagsOf = {};
    textError = "";
    photoFailed = false;
    if (mode === "audio" || (item && AUDIO.has(ext) && item.id)) {
      const it = item;
      if (it.id) loadMusic(it.id).then((d) => { if (item === it) tagsOf = d.tags || {}; }).catch(() => {});
    }
    if (mode === "archive") {
      const it = item;
      loadArchive(it.id).then((d) => { if (item === it) text = d; }).catch((e) => { if (item === it) textError = e.message; });
      return;
    }
    if (mode !== "text") return;
    const it = item;
    loadText(it).then((d) => { if (item === it) text = d; }).catch((e) => { if (item === it) textError = e.message; });
  });

  function onkeydown(e) {
    if (e.target.closest?.("input, textarea")) return;
    const d = e.key === "ArrowDown" || e.key === "ArrowRight" ? 1 : e.key === "ArrowUp" || e.key === "ArrowLeft" ? -1 : 0;
    if (e.key === "Escape" || e.key === " ") {
      if (e.key === " " && e.target.closest?.("button, audio, video")) return; // 空白鍵按在按鈕或播放器上：照原本的作用
      e.preventDefault();
      e.stopPropagation();
      onclose?.();
    } else if (d && !e.metaKey && !e.ctrlKey && !e.target.closest?.("audio, video")) {
      e.preventDefault();
      e.stopPropagation();
      onmove?.(d);
    } else if (e.key === "Enter") {
      e.preventDefault();
      e.stopPropagation();
      onopen?.();
    }
  }
</script>

<svelte:window onkeydowncapture={onkeydown} />

{#if item}
  <button class="scrim" onclick={onclose} aria-label={t("common.close")} transition:scrim></button>
  <div class="ql" class:media={mode === "photo" || mode === "video" || mode === "file-photo"} role="dialog" aria-label={t("quick.title", { name: item.name })} in:popIn={{ y: 0, scale: 0.96 }} out:popOut={{ y: 0, scale: 0.98 }}>
    <header>
      <Button variant="borderless" icon="xmark" iconOnly aria-label={t("common.close")} onclick={onclose} />
      <div class="name mac-headline" title={item.name}>{item.name}</div>
      {#if canOpen && item.type !== "folder"}
        <Button variant="bordered" size="small" disabled={!online} onclick={onreveal}>{t("menu.reveal")}</Button>
      {/if}
      <Button variant="borderedProminent" size="small" disabled={item.type !== "folder" && !item.image_id && (!canOpen || !online)} onclick={onopen}>{t("menu.open")}</Button>
    </header>
    <div class="stage">
      {#if mode === "photo"}
        {#key item.id}
          <img src={photoFailed || !online ? thumbUrl({ id: item.image_id }) : previewUrl({ id: item.image_id })} alt={item.name} onerror={() => (photoFailed = true)} draggable="false" />
        {/key}
      {:else if mode === "file-photo"}
        {#key item.path}
          {#if photoFailed}
            <div class="card"><KindIcon kind="photo" size={96} /><p class="mac-body note">{t("quick.photoFailed")}</p></div>
          {:else}
            <img src={photoUrl(item)} alt={item.name} onerror={() => (photoFailed = true)} draggable="false" />
          {/if}
        {/key}
      {:else if mode === "video"}
        {#key item.id}
          <!-- svelte-ignore a11y_media_has_caption -->
          <video src={originalUrl({ id: item.image_id })} poster={thumbUrl({ id: item.image_id })} controls preload="metadata"></video>
        {/key}
      {:else if mode === "pdf"}
        {#key item.id}<iframe src={rawUrl(item)} title={item.name}></iframe>{/key}
      {:else if mode === "archive"}
        {#if textError}
          <p class="mac-body note" role="alert">{textError}</p>
        {:else if !text}
          <ProgressIndicator kind="spinner" label={t("view.loading")} />
        {:else if text.status !== "ok"}
          <div class="card">
            <KindIcon kind="archive" size={96} />
            <p class="mac-body note">{text.status === "todo" ? t("quick.archiveTodo") : text.message || t("quick.archiveEmpty")}</p>
          </div>
        {:else}
          <div class="archive">
            <p class="mac-callout head">{t("quick.archiveCount", { n: text.total })}{text.more ? `（${text.more.replace("…", "")}）` : ""}</p>
            <!-- svelte-ignore a11y_no_noninteractive_tabindex（讓鍵盤可以捲動清單） -->
            <ul class="entries mac-callout" tabindex="0">
              {#each text.entries as e, k (k)}
                <li><KindIcon kind="other" size={13} /><span class="ename">{e.name}</span><span class="efolder">{e.folder}</span></li>
              {/each}
            </ul>
          </div>
        {/if}
      {:else if mode === "text"}
        {#if textError}
          <p class="mac-body note" role="alert">{textError}</p>
        {:else if !text}
          <ProgressIndicator kind="spinner" label={t("view.loading")} />
        {:else}
          <!-- svelte-ignore a11y_no_noninteractive_tabindex（讓鍵盤可以捲動文字） -->
          <pre class="text" tabindex="0">{text.text}{#if text.truncated}

{t("quick.truncated")}{/if}</pre>
        {/if}
      {:else}
        <div class="card">
          {#if item.cover}<img class="cover" src={`/api/files/${item.id}/cover`} alt={item.name} draggable="false" />
          {:else}<KindIcon kind={item.icon || (item.type === "folder" ? "folder" : item.kind)} size={96} />{/if}
          {#if tagsOf["曲名"] || tagsOf["演出者"]}
            <div class="tags">
              <b class="mac-title-3">{tagsOf["曲名"] || item.name}</b>
              <span class="mac-body">{[tagsOf["演出者"], tagsOf["專輯"]].filter(Boolean).join(" — ")}</span>
              <span class="mac-callout sub">{[tagsOf["年份"], tagsOf["類型"], tagsOf["長度"]].filter(Boolean).join(" · ")}</span>
            </div>
          {/if}
          {#if mode === "audio"}
            {#key item.id}<audio src={rawUrl(item)} controls preload="metadata"></audio>{/key}
          {/if}
        </div>
      {/if}
    </div>
    <footer class="mac-callout">
      <span>{item.kindLabel || (item.type === "folder" ? t("info.kind.folder") : t(`kind.${item.kind}`))}</span>
      {#if item.size}<span>{formatBytes(item.size)}</span>{/if}
      {#if item.mtime}<span>{formatDate(item.mtime)}</span>{/if}
      {#if driveName}<span>{driveName}</span>{/if}
      {#if !online}<span class="offline">{t("quick.offline", { name: driveName })}</span>{/if}
    </footer>
  </div>
{/if}

<style>
  .cover { max-width: min(320px, 80%); max-height: 50vh; object-fit: contain; border-radius: var(--radius-sm); box-shadow: var(--shadow-popover); background: var(--bg-primary); }
  .scrim { position: fixed; inset: 0; z-index: 310; border: 0; padding: 0; background: var(--media-scrim-light); cursor: default; }
  .ql { position: fixed; z-index: 311; left: 50%; top: 50%; translate: -50% -50%; width: min(880px, calc(100vw - var(--space-8))); height: min(640px, calc(100dvh - var(--space-8)));
    display: flex; flex-direction: column; overflow: hidden; border-radius: var(--radius-lg); background: var(--elevated-primary); color: var(--label-primary);
    box-shadow: var(--shadow-window); }
  header { flex: none; display: flex; align-items: center; gap: var(--space-2); padding: var(--space-2) var(--space-3); border-bottom: 1px solid var(--separator); }
  .name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .stage { flex: 1; min-height: 0; display: flex; align-items: center; justify-content: center; background: var(--control-bg); position: relative; }
  .ql.media .stage { background: var(--media-bg); }
  img, video { max-width: 100%; max-height: 100%; width: 100%; height: 100%; object-fit: contain; display: block; }
  iframe { width: 100%; height: 100%; border: 0; background: var(--control-bg); }
  .text { align-self: stretch; flex: 1; margin: 0; padding: var(--space-4); overflow: auto; white-space: pre-wrap; overflow-wrap: anywhere;
    font-family: var(--font-mono); font-size: var(--text-callout); line-height: 1.5; color: var(--label-primary); outline: none; }
  .card { display: flex; flex-direction: column; align-items: center; gap: var(--space-6); padding: var(--space-6); }
  audio { width: min(420px, 80vw); }
  .tags { display: flex; flex-direction: column; align-items: center; gap: var(--space-1); text-align: center; color: var(--label-primary); }
  .tags .sub { color: var(--label-secondary); }
  .archive { align-self: stretch; flex: 1; min-height: 0; display: flex; flex-direction: column; }
  .archive .head { margin: 0; padding: var(--space-3) var(--space-4) var(--space-2); color: var(--label-secondary); }
  .entries { flex: 1; min-height: 0; overflow: auto; list-style: none; margin: 0; padding: 0 var(--space-4) var(--space-4); outline: none; }
  .entries li { display: flex; align-items: center; gap: var(--space-2); padding: 2px 0; min-width: 0; }
  .ename { flex: none; max-width: 60%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--label-primary); }
  .efolder { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--label-secondary); }
  .note { color: var(--label-secondary); padding: var(--space-6); text-align: center; }
  footer { flex: none; display: flex; flex-wrap: wrap; gap: var(--space-1) var(--space-4); padding: var(--space-2) var(--space-4); border-top: 1px solid var(--separator); color: var(--label-secondary); }
  .offline { color: var(--label-primary); font-weight: 600; }
</style>
