<script>
  import Icon from "./Icon.svelte";
  import MiniMap from "./MiniMap.svelte";
  import { api } from "../lib/api.js";
  import { navigate } from "../lib/router.svelte.js";
  import { app, viewer, toast, showDialog, refresh } from "../lib/state.svelte.js";
  import { analyzeAssets, copyText, reveal } from "../lib/actions.js";
  import { bytes, dateTime, duration, shutter } from "../lib/format.js";
  import {
    mdiCalendarOutline, mdiCameraIris, mdiCamera, mdiClose, mdiContentCopy, mdiCreation, mdiFileOutline,
    mdiFolderOpenOutline, mdiImageAlbum, mdiMapMarkerOutline, mdiPencilOutline, mdiTagOutline, mdiAlertCircleOutline,
    mdiTranslate,
  } from "../lib/icons.js";

  let { detail, onclose, onchange } = $props();
  let editing = $state(false);
  let tagsText = $state("");
  let note = $state("");
  let translated = $state(null);
  let translating = $state(false);

  $effect(() => {
    tagsText = (detail?.user_tags || []).join(", ");
    note = detail?.note || "";
    editing = false;
    translated = null;
  });

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
  const tags = $derived([...(detail?.keywords || []), ...(detail?.tags || [])]);

  function searchTag(t) {
    viewer.open = false;
    navigate(`/search?q=${encodeURIComponent(`tag:${/\s/.test(t) ? `"${t}"` : t}`)}`);
  }

  async function save() {
    try {
      const d = await api(`/api/assets/${detail.id}`, { body: { user_tags: tagsText, note } });
      onchange?.(d);
      editing = false;
      toast("已儲存");
    } catch (e) {
      toast(e.message, "error");
    }
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
      {#if detail.faces?.length}
        <div class="faces">
          {#each detail.faces as f (f.id)}
            <div class="face">
              <button class="face-img" title={f.name || "未命名"} onclick={() => {
                if (f.person_id) { viewer.open = false; navigate(`/people/${f.person_id}`); } else fixFace(f);
              }}>
                <img src={`/api/faces/${f.id}/thumb`} alt="" />
              </button>
              <button class="face-name" onclick={() => fixFace(f)} title="更正">{f.name || (f.person_id ? "未命名" : "這是誰？")}</button>
              {#if f.person_id}<button class="face-x" onclick={() => removeFace(f)} title="不是這個人">×</button>{/if}
            </div>
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

      <div class="block">
        <div class="row-title">
          <Icon path={mdiTagOutline} size={18} /><span>我的標籤與備註</span>
          <button class="icon-btn sm" onclick={() => (editing = !editing)} aria-label="編輯"><Icon path={mdiPencilOutline} size={18} /></button>
        </div>
        {#if editing}
          <input class="input" bind:value={tagsText} placeholder="以逗號分隔，例如：作品集, 婚禮, 2024" />
          <textarea class="input" rows="2" bind:value={note} placeholder="備註"></textarea>
          <div class="btns"><button class="btn small" onclick={save}>儲存</button><button class="btn small ghost" onclick={() => (editing = false)}>取消</button></div>
        {:else if detail.user_tags.length || detail.note}
          <div class="chips">{#each detail.user_tags as t (t)}<button class="chip on" onclick={() => searchTag(t)}>{t}</button>{/each}</div>
          {#if detail.note}<p class="small">{detail.note}</p>{/if}
        {:else}
          <p class="muted small">點鉛筆新增，之後可直接搜尋。</p>
        {/if}
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
  .info { width: 360px; background: var(--panel); color: var(--text); height: 100%; overflow-y: auto; flex-shrink: 0; }
  header { display: flex; align-items: center; gap: 4px; padding: 8px; position: sticky; top: 0; background: var(--panel); z-index: 2; }
  h3 { margin: 0; font-size: 17px; font-weight: 600; }
  h4 { margin: 22px 0 10px; font-size: 13px; color: var(--muted); font-weight: 600; letter-spacing: .03em; }
  .pad { padding: 0 18px 28px; }
  .desc { margin: 0 0 12px; line-height: 1.65; }
  .tr { margin: -4px 0 12px; }
  .faces { display: flex; flex-wrap: wrap; gap: 12px; margin-bottom: 14px; }
  .face { position: relative; display: flex; flex-direction: column; align-items: center; width: 64px; }
  .face-img { border: 0; padding: 0; background: none; cursor: pointer; }
  .face-img img { width: 56px; height: 56px; border-radius: 50%; object-fit: cover; background: var(--bg-2); display: block; }
  .face-name { border: 0; background: none; color: var(--text); font-size: 12px; cursor: pointer; max-width: 64px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; padding: 2px 0; }
  .face-x {
    position: absolute; top: -4px; right: 0; width: 20px; height: 20px; border-radius: 50%; border: 0; cursor: pointer;
    background: var(--bg-3); color: var(--text); font-size: 13px; line-height: 1; opacity: 0; transition: opacity .15s;
  }
  .face:hover .face-x { opacity: 1; }
  @media (hover: none) { .face-x { opacity: .8; } }
  .warn { color: var(--danger); display: flex; gap: 6px; align-items: flex-start; }
  .block { margin-top: 16px; background: var(--bg-2); border-radius: 14px; padding: 10px 12px; display: flex; flex-direction: column; gap: 8px; }
  .row-title { display: flex; align-items: center; gap: 6px; font-size: 14px; font-weight: 600; }
  .row-title span { flex: 1; }
  .icon-btn.sm { width: 32px; height: 32px; }
  dl { margin: 0; display: flex; flex-direction: column; gap: 14px; }
  .item { display: flex; gap: 14px; align-items: flex-start; color: var(--muted); }
  .item > div { color: var(--text); display: flex; flex-direction: column; gap: 2px; }
  .min { min-width: 0; flex: 1; }
  .break { word-break: break-all; }
  .exp { font-size: 13px; margin-top: 2px; }
  .btns { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin-top: 6px; }
  .path {
    border: 0; background: none; padding: 0; text-align: left; cursor: copy; color: var(--text);
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; word-break: break-all;
  }
  .path:hover { color: var(--primary); }
  textarea.input { resize: vertical; }
  @media (max-width: 900px) {
    .info { width: 100%; height: auto; max-height: 62vh; border-radius: 20px 20px 0 0; }
  }
</style>
