<script>
  import Icon from "./Icon.svelte";
  import MiniMap from "./MiniMap.svelte";
  import { api } from "../lib/api.js";
  import { navigate, link } from "../lib/router.svelte.js";
  import { app, viewer, toast, showDialog, refresh } from "../lib/state.svelte.js";
  import { analyzeAssets, copyText, reveal } from "../lib/actions.js";
  import { bytes, dateTime, duration, shutter } from "../lib/format.js";
  import {
    mdiCalendarOutline, mdiCameraIris, mdiCamera, mdiClose, mdiContentCopy, mdiCreation, mdiFileOutline,
    mdiFolderOpenOutline, mdiImageAlbum, mdiMapMarkerOutline, mdiPencilOutline, mdiTagOutline, mdiAlertCircleOutline,
    mdiTranslate, mdiCheck,
  } from "../lib/icons.js";

  let { detail, onclose, onchange } = $props();
  let note = $state("");
  let noteState = $state("");  // "" | "saving" | "saved"
  let newTag = $state("");
  let addingTag = $state(false);
  let translated = $state(null);
  let translating = $state(false);
  let editFaces = $state(false);

  function openFace(f) {
    if (editFaces || !f.person_id) return fixFace(f);
    viewer.open = false;
    navigate(`/people/${f.person_id}`);
  }

  const myKeywords = $derived([...new Set([...(detail?.keywords || []), ...(detail?.user_tags || [])])]);

  let lastId = null;
  $effect(() => {
    if (detail?.id !== lastId) {
      lastId = detail?.id;
      note = detail?.note || "";
      noteState = "";
      newTag = "";
      addingTag = false;
      translated = null;
    }
  });

  // ---- 說明（備註）：像 Google 相簿，直接在空白處輸入，離開時自動儲存 ----
  async function saveNote() {
    if (!detail || note === (detail.note || "")) return;
    noteState = "saving";
    try {
      const d = await api(`/api/assets/${detail.id}`, { body: { note: note.trim() } });
      onchange?.(d);
      noteState = "saved";
      setTimeout(() => (noteState = noteState === "saved" ? "" : noteState), 1800);
    } catch (e) {
      noteState = "";
      toast(e.message, "error");
    }
  }
  function noteKey(e) {
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) e.currentTarget.blur();
    if (e.key === "Escape") {
      note = detail?.note || "";
      e.stopPropagation();
      e.currentTarget.blur();
    }
  }
  function grow(node) {
    const fit = () => {
      node.style.height = "auto";
      node.style.height = `${node.scrollHeight}px`;
    };
    fit();
    node.addEventListener("input", fit);
    return { update: fit, destroy: () => node.removeEventListener("input", fit) };
  }

  // ---- 我的標籤：直接新增、移除，RAW 會寫入 .xmp ----
  async function setTags(list, message) {
    try {
      const x = await api(`/api/assets/${detail.id}/xmp`, { body: { keywords: list } });
      onchange?.(await api(`/api/assets/${detail.id}`));
      toast(message + (x.written_to === "sidecar" ? "（已寫入 .xmp）" : x.written_to === "embedded" ? "（已寫入檔案）" : ""));
      refresh();
    } catch (e) {
      toast(e.message, "error");
    }
  }
  function addTag() {
    const t = newTag.trim().replace(/^#+/, "").trim();
    newTag = "";
    if (!t || myKeywords.some((k) => k.toLowerCase() === t.toLowerCase())) return;
    setTags([...myKeywords, t], `已加上 #${t}`);
  }
  function tagKey(e) {
    if (e.key === "Enter" && !e.isComposing) {
      e.preventDefault();
      addTag();
    } else if (e.key === "Escape") {
      e.stopPropagation();
      newTag = "";
      addingTag = false;
    }
  }

  // 描述不是中文（例如換過語言或模型）時提供翻譯
  const needsTranslate = $derived(
    app.server?.models?.language === "zh-TW" && detail?.description && !/[\u4e00-\u9fff]/.test(detail.description),
  );

  async function translate() {
    translating = true;
    try {
      translated = await api(`/api/assets/${detail.id}/translate`, { body: {} });
    } catch (e) {
      toast(e.message, "error");
    } finally {
      translating = false;
    }
  }

  async function fixFace(face) {
    const choice = await showDialog("person", { title: face.name ? `這不是 ${face.name}？選擇正確的人` : "這是誰？", allowNew: true });
    if (!choice) return;
    await api(`/api/faces/${face.id}`, { body: choice.id ? { person_id: choice.id } : { name: choice.name } });
    onchange?.(await api(`/api/assets/${detail.id}`));
    refresh();
  }

  async function removeFace(face) {
    await api(`/api/faces/${face.id}`, { body: { person_id: null } });
    onchange?.(await api(`/api/assets/${detail.id}`));
    refresh();
  }

  const exposure = $derived(
    [
      detail?.aperture ? `ƒ/${Number(detail.aperture.toFixed(1))}` : "",
      detail?.exposure_time ? shutter(detail.exposure_time) : "",
      detail?.focal_length ? `${Math.round(detail.focal_length)}mm` : "",
      detail?.iso ? `ISO ${detail.iso}` : "",
    ].filter(Boolean),
  );
  const megapixels = $derived(detail?.width && detail?.height ? ((detail.width * detail.height) / 1e6).toFixed(1) : null);
  const tags = $derived((detail?.tags || []).filter((t) => !myKeywords.includes(t)));

  function searchTag(t) {
    viewer.open = false;
    navigate(`/search?q=${encodeURIComponent(`tag:${/\s/.test(t) ? `"${t}"` : t}`)}`);
  }

</script>

<aside class="info">
  <header>
    <button class="icon-btn" onclick={onclose} aria-label="關閉資訊"><Icon path={mdiClose} /></button>
    <h3>資訊</h3>
  </header>
  {#if !detail}
    <p class="muted pad"><span class="spinner"></span></p>
  {:else}
    <div class="pad">
      <div class="note" class:has={!!note}>
        <textarea use:grow bind:value={note} onblur={saveNote} onkeydown={noteKey} rows="1"
          placeholder="新增說明" aria-label="說明" maxlength="2000"></textarea>
        <span class="note-state" aria-live="polite">{noteState === "saving" ? "儲存中…" : noteState === "saved" ? "已儲存" : ""}</span>
      </div>
      {#if detail.faces?.length}
        <div class="people-head">
          <h4>人物</h4>
          <button class="icon-btn" class:on={editFaces} onclick={() => (editFaces = !editFaces)}
            title={editFaces ? "完成" : "編輯人物"} aria-label={editFaces ? "完成編輯人物" : "編輯人物"}>
            <Icon path={editFaces ? mdiCheck : mdiPencilOutline} size={18} />
          </button>
        </div>
        <div class="faces">
          {#each detail.faces as f (f.id)}
            <div class="face">
              <button class="face-img" title={f.name || (f.person_id ? "還沒命名，點一下命名" : "這是誰？")} onclick={() => openFace(f)}>
                <img src={`/api/faces/${f.id}/thumb`} alt={f.name || ""} />
              </button>
              <span class="face-name" class:unnamed={!f.name}>{f.name || (f.person_id ? "" : "這是誰？")}</span>
              {#if editFaces && f.person_id}<button class="face-x" onclick={() => removeFace(f)} title="不是這個人" aria-label="不是這個人">×</button>{/if}
            </div>
          {/each}
        </div>
        {#if editFaces}<p class="muted tiny edit-tip">點臉可以改成正確的人，按 × 表示不是這個人。</p>{/if}
      {/if}
      {#if detail.pets?.length}
        <div class="people-head"><h4>寵物</h4></div>
        <div class="faces">
          {#each detail.pets as p (p.detection)}
            <a class="face pet-link" href={`/pets/id/${p.pet_id}`} use:link title={p.name || `這隻${p.kind_label}還沒命名`}>
              <span class="face-img"><img src={`/api/pet-thumbs/${p.detection}`} alt={p.name || p.kind_label} /></span>
              <span class="face-name" class:unnamed={!p.name}>{p.name || `${p.kind_label}・新增名字`}</span>
            </a>
          {/each}
        </div>
      {/if}
      {#if translated}
        <p class="desc">{translated.description}</p>
        <div class="chips">{#each translated.tags as t (t)}<button class="chip" onclick={() => searchTag(t)}>{t}</button>{/each}</div>
        <p class="muted tiny">AI 翻譯（原文：{detail.description}）</p>
      {:else if detail.description}
        <p class="desc">{detail.description}</p>
        {#if needsTranslate}
          <button class="btn small ghost tr" onclick={translate} disabled={translating}>
            <Icon path={mdiTranslate} size={16} />{translating ? "翻譯中…" : "翻譯成中文"}
          </button>
        {/if}
      {:else if detail.error && !detail.analyzed_at}
        <p class="warn"><Icon path={mdiAlertCircleOutline} size={18} />{detail.error}</p>
      {:else}
        <p class="muted small">尚未 AI 分析</p>
      {/if}

      {#if tags.length}
        <div class="chips">
          {#each tags as t (t)}<button class="chip" onclick={() => searchTag(t)}>{t}</button>{/each}
        </div>
      {/if}

      <div class="mytags">
        <h4>我的標籤</h4>
        <div class="chips">
          {#each myKeywords as t (t)}
            <span class="mytag">
              <button class="t" onclick={() => searchTag(t)} title="搜尋 #{t}">#{t}</button>
              <button class="x" onclick={() => setTags(myKeywords.filter((k) => k !== t), `已移除 #${t}`)} aria-label="移除 {t}"><Icon path={mdiClose} size={14} /></button>
            </span>
          {/each}
          {#if addingTag}
            <!-- svelte-ignore a11y_autofocus -->
            <input class="tag-input" bind:value={newTag} onkeydown={tagKey} onblur={() => { addTag(); addingTag = false; }}
              placeholder="輸入後按 Enter" aria-label="新增標籤" autofocus />
          {:else}
            <button class="chip add" onclick={() => (addingTag = true)}><Icon path={mdiTagOutline} size={16} />新增標籤</button>
          {/if}
        </div>
        <p class="muted tiny">和 AI 關鍵字一起被搜尋；RAW 會寫入 .xmp，Lightroom 看得到。</p>
      </div>

      <h4>詳細資料</h4>
      <dl>
        {#if detail.sort_at}
          <div class="item">
            <Icon path={mdiCalendarOutline} />
            <div><b>{dateTime(detail.taken_at || detail.sort_at, detail.tz_offset)}</b>
              {#if !detail.taken_at}<span class="muted small">（無拍攝時間，使用檔案時間）</span>{/if}</div>
          </div>
        {/if}
        <div class="item">
          <Icon path={mdiFileOutline} />
          <div class="min">
            <b class="break">{detail.filename}</b>
            <span class="muted small">
              {[megapixels && `${megapixels}MP`, detail.width && `${detail.width} × ${detail.height}`, bytes(detail.size),
                detail.duration && duration(detail.duration), detail.fps && `${Math.round(detail.fps)}fps`, detail.codec].filter(Boolean).join(" · ")}
            </span>
            {#if detail.sidecars.length}<span class="muted tiny">附屬檔：{detail.sidecars.join("、")}</span>{/if}
          </div>
        </div>
        <div class="item">
          <Icon path={mdiFolderOpenOutline} />
          <div class="min">
            <button class="path" title="複製完整路徑" onclick={() => copyText(detail.path)}>{detail.path}</button>
            <div class="btns">
              <button class="btn small soft" disabled={!detail.exists} onclick={() => reveal(detail.id)}>
                {app.server?.local ? "在 Finder 中顯示" : "在 Mac 的 Finder 中顯示"}
              </button>
              <button class="btn small ghost" onclick={() => { viewer.open = false; navigate(`/folders/${detail.root_id}?path=${encodeURIComponent(detail.folder)}`); }}>
                前往資料夾
              </button>
              <button class="icon-btn sm" onclick={() => copyText(detail.path)} aria-label="複製路徑"><Icon path={mdiContentCopy} size={18} /></button>
            </div>
            {#if !detail.exists}<span class="warn small">目前找不到檔案：硬碟可能未連接，或已被移動。</span>{/if}
          </div>
        </div>
        {#if detail.camera || detail.lens}
          <div class="item">
            <Icon path={mdiCamera} />
            <div class="min">
              <b>{detail.camera || "相機不明"}</b>
              {#if detail.lens}<span class="muted small">{detail.lens}</span>{/if}
              {#if exposure.length}<span class="exp">{exposure.join("　")}</span>{/if}
            </div>
          </div>
        {/if}
        {#if detail.lat != null}
          <div class="item">
            <Icon path={mdiMapMarkerOutline} />
            <div class="min">
              {#if detail.place || detail.country_name}
                <b>{[detail.place, detail.country_name].filter(Boolean).join("，")}</b>
              {/if}
              <span class="small muted">{detail.lat.toFixed(5)}, {detail.lon.toFixed(5)}{detail.altitude ? ` · 海拔 ${Math.round(detail.altitude)}m` : ""}</span>
              <a class="small" href={`https://www.openstreetmap.org/?mlat=${detail.lat}&mlon=${detail.lon}#map=15/${detail.lat}/${detail.lon}`} target="_blank" rel="noopener">在地圖上開啟</a>
            </div>
          </div>
          <MiniMap lat={detail.lat} lon={detail.lon} />
        {/if}
        {#if detail.albums.length}
          <div class="item">
            <Icon path={mdiImageAlbum} />
            <div class="chips">
              {#each detail.albums as a (a.id)}
                <button class="chip" onclick={() => { viewer.open = false; navigate(`/albums/${a.id}`); }}>{a.name}</button>
              {/each}
            </div>
          </div>
        {/if}
        {#if detail.objects.length || detail.scene || detail.ocr_text}
          <div class="item">
            <Icon path={mdiCameraIris} />
            <div class="min small">
              {#if detail.scene}<span>場景：{detail.scene}</span>{/if}
              {#if detail.objects.length}<span>物品：{detail.objects.join("、")}</span>{/if}
              {#if detail.ocr_text}<span class="break">圖中文字：{detail.ocr_text}</span>{/if}
            </div>
          </div>
        {/if}
        {#if detail.title || detail.caption || detail.artist || detail.copyright}
          <div class="item"><Icon path={mdiPencilOutline} />
            <div class="min small">
              {#if detail.title}<b>{detail.title}</b>{/if}
              {#if detail.caption}<span>{detail.caption}</span>{/if}
              {#if detail.artist}<span class="muted">作者：{detail.artist}</span>{/if}
              {#if detail.copyright}<span class="muted">{detail.copyright}</span>{/if}
            </div>
          </div>
        {/if}
        <div class="item">
          <Icon path={mdiCreation} />
          <div class="min small">
            {#if detail.analyzed_at}<span class="muted">AI：{detail.model}（{detail.analyzed_at.slice(0, 10)}）</span>{/if}
            <button class="btn small ghost" onclick={() => analyzeAssets([detail.id])}>{detail.analyzed_at ? "重新 AI 分析" : "立即 AI 分析"}</button>
          </div>
        </div>
      </dl>
    </div>
  {/if}
</aside>

<style>
  .info { width: 360px; background: var(--surface-container-low); color: var(--on-surface); height: 100%; overflow-y: auto; flex-shrink: 0; }
  header { display: flex; align-items: center; gap: 4px; padding: 8px; position: sticky; top: 0; background: var(--surface-container-low); z-index: 2; }
  h3 { margin: 0; font-size: 16px; font-weight: 500; }
  h4 { margin: 22px 0 10px; font-size: 14px; color: var(--on-surface-variant); font-weight: 500; letter-spacing: .03em; }
  .pad { padding: 0 18px 28px; }
  .desc { margin: 0 0 12px; line-height: 1.65; }
  .tr { margin: -4px 0 12px; }
  .note { position: relative; margin: 0 0 14px; }
  .note textarea {
    width: 100%; resize: none; overflow: hidden; border: 0; border-bottom: 1px solid var(--outline-variant);
    background: transparent; color: var(--on-surface); font-size: 16px; line-height: 24px; padding: 8px 0 8px 28px;
    outline: none; min-height: 40px;
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='%23747780'%3E%3Cpath d='M14.06 9.02l.92.92L5.92 19H5v-.92l9.06-9.06M17.66 3c-.25 0-.51.1-.7.29l-1.83 1.83 3.75 3.75 1.83-1.83a.996.996 0 0 0 0-1.41l-2.34-2.34c-.2-.2-.45-.29-.71-.29zm-3.6 3.19L3 17.25V21h3.75L17.81 9.94l-3.75-3.75z'/%3E%3C/svg%3E");
    background-repeat: no-repeat; background-position: 0 10px; background-size: 18px;
    transition: border-color var(--spring-effects-fast-duration) var(--spring-effects-fast);
  }
  .note textarea::placeholder { color: var(--on-surface-variant); opacity: .7; }
  .note.has textarea { background-image: none; padding-left: 0; }
  .note textarea:hover { border-bottom-color: var(--outline); }
  .note textarea:focus { border-bottom: 2px solid var(--primary); padding-left: 0; background-image: none; }
  .note-state { position: absolute; right: 0; bottom: -18px; font-size: 11px; color: var(--on-surface-variant); }
  .mytags { margin: 6px 0 4px; }
  .mytags h4 { margin: 14px 0 8px; }
  .mytag {
    display: inline-flex; align-items: center; height: 32px; border-radius: var(--corner-small);
    background: var(--secondary-container); color: var(--on-secondary-container); overflow: hidden;
    animation: m3-pop var(--spring-expressive-fast-spatial-duration) var(--spring-expressive-fast-spatial);
  }
  .mytag .t { border: 0; background: none; color: inherit; font-weight: 500; padding: 0 4px 0 12px; height: 100%; cursor: pointer; }
  .mytag .x { border: 0; background: none; color: inherit; display: flex; padding: 0 8px 0 4px; height: 100%; align-items: center; cursor: pointer; opacity: .7; }
  .mytag .x:hover, .mytag .t:hover { background: color-mix(in srgb, currentColor 8%, transparent); opacity: 1; }
  .chip.add { border-style: dashed; }
  .tag-input { height: 32px; border: 1px solid var(--primary); border-radius: var(--corner-small); padding: 0 10px; background: none; outline: none; font-size: 14px; min-width: 140px; }
  .people-head { display: flex; align-items: center; justify-content: space-between; margin: 4px 0 6px; }
  .people-head h4 { margin: 0; }
  .people-head .icon-btn { width: 32px; height: 32px; color: var(--on-surface-variant); }
  .people-head .icon-btn.on { color: var(--primary); background: var(--secondary-container); }
  .faces { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px 10px; margin-bottom: 12px; }
  .face { position: relative; display: flex; flex-direction: column; align-items: center; min-width: 0; }
  .face-img { border: 0; padding: 0; background: none; cursor: pointer; width: 100%; }
  .face-img img { width: 100%; aspect-ratio: 1; border-radius: var(--corner-medium); object-fit: cover; background: var(--surface-container); display: block; }
  .face-img:hover img { outline: 2px solid var(--primary); outline-offset: 2px; }
  .face-name { font-size: 12px; max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; padding: 4px 0 0; min-height: 20px; }
  .face-name.unnamed { color: var(--on-surface-variant); }
  .face-x {
    position: absolute; top: -6px; right: -6px; width: 22px; height: 22px; border-radius: 50%; border: 0; cursor: pointer;
    background: var(--on-surface); color: var(--surface); font-size: 14px; line-height: 1;
  }
  .edit-tip { margin: -4px 0 12px; }
  .pet-link { text-decoration: none; color: inherit; }
  .pet-link .face-img { display: block; }
  .pet-link .face-img img { border-radius: 50%; }
  .warn { color: var(--error); display: flex; gap: 6px; align-items: flex-start; }
  .icon-btn.sm { width: 32px; height: 32px; }
  dl { margin: 0; display: flex; flex-direction: column; gap: 14px; }
  .item { display: flex; gap: 14px; align-items: flex-start; color: var(--on-surface-variant); }
  .item > div { color: var(--on-surface); display: flex; flex-direction: column; gap: 2px; }
  .min { min-width: 0; flex: 1; }
  .break { word-break: break-all; }
  .exp { font-size: 14px; margin-top: 2px; }
  .btns { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin-top: 6px; }
  .path {
    border: 0; background: none; padding: 0; text-align: left; cursor: copy; color: var(--on-surface);
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; word-break: break-all;
  }
  .path:hover { color: var(--primary); }
  @media (max-width: 900px) {
    .info { width: 100%; height: auto; max-height: 62vh; border-radius: var(--corner-large-increased) var(--corner-large-increased) 0 0; }
  }
</style>
