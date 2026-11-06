<script>
  import { onMount, tick } from "svelte";
  import { findThumb, fly, heroDuration } from "../lib/hero.js";
  import Icon from "./Icon.svelte";
  import InfoPanel from "./InfoPanel.svelte";
  import ExifDialog from "./ExifDialog.svelte";
  import { api, originalUrl, previewUrl, thumbUrl } from "../lib/api.js";
  import { app, viewer, refresh, toast, isMacApp } from "../lib/state.svelte.js";
  import { addToAlbum, analyzeAssets, moveAssets, reveal, setFavorite, trashAssets, copyText } from "../lib/actions.js";
  import { LABEL_COLORS, LABEL_KEYS, LABEL_NAMES } from "../lib/format.js";
  import {
    mdiArrowLeft, mdiChevronLeft, mdiChevronRight, mdiDeleteOutline, mdiDotsVertical, mdiDownload, mdiFolderOpenOutline,
    mdiHeart, mdiHeartOutline, mdiInformationOutline, mdiImageAlbum, mdiFolderMoveOutline, mdiCreation, mdiContentCopy,
    mdiMagnifyPlusOutline, mdiMagnifyMinusOutline, mdiStar, mdiStarOutline, mdiFlagRemove, mdiLayers, mdiFileDocumentEditOutline,
  } from "../lib/icons.js";

  let detail = $state(null);
  let showInfo = $state(readPref());
  let menu = $state(false);
  let zoom = $state(1);
  let tx = $state(0);
  let ty = $state(0);
  let loaded = $state(false);
  let chrome = $state(true);
  let pushed = false;
  let editingExif = $state(false);
  // 開關動畫：opening＝照片從縮圖長出來；closing＝縮回縮圖
  let phase = $state("opening");
  let stageEl = $state();

  const item = $derived(viewer.list[viewer.index]);
  const isVideo = $derived((item?.type || detail?.media_type) === "video");
  const hiRes = $derived(zoom > 1.6);

  function readPref() {
    try {
      const v = localStorage.getItem("viewer-info");
      return v === null ? window.innerWidth > 1100 : v === "1";
    } catch {
      return false;
    }
  }

  onMount(() => {
    history.pushState({ viewer: true, idx: history.state?.idx ?? 0 }, "");
    pushed = true;
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    heroIn();
    return () => (document.body.style.overflow = prevOverflow);
  });

  /** 照片在畫面上 100% 時的位置 */
  function targetRect() {
    const r = stageEl?.getBoundingClientRect();
    if (!r || !item) return null;
    // 和畫面上的圖片一樣：縮小到放得下，但不會放大超過原尺寸（預覽最大 2048px）
    const w = item.w || 1;
    const h = item.h || 1;
    const natural = Math.min(1, 2048 / Math.max(w, h));
    const f = Math.min(r.width / w, r.height / h, natural);
    const W = w * f;
    const H = h * f;
    return { left: r.left + (r.width - W) / 2, top: r.top + (r.height - H) / 2, width: W, height: H };
  }

  async function heroIn() {
    const it = item;
    const thumb = it && it.type !== "video" ? findThumb(it.id) : null;
    await tick();
    const to = targetRect();
    if (!thumb || !to) {
      phase = "open";
      return;
    }
    const overlay = await fly({ src: thumb.src, from: thumb.rect, to, fromRadius: thumb.radius, duration: heroDuration });
    phase = "open";
    // 等真正的圖片畫出來再拿掉覆蓋的那張，避免閃一下
    requestAnimationFrame(() => requestAnimationFrame(() => overlay?.remove?.()));
  }

  /** 關閉：縮回網格裡的位置（找不到縮圖或放大中就直接淡出） */
  async function heroOut() {
    if (phase === "closing") return;
    const it = item;
    const media = stageEl?.querySelector(".media.show") || stageEl?.querySelector(".placeholder");
    const from = media?.getBoundingClientRect();
    phase = "closing";
    const thumb = it && it.type !== "video" && zoom <= 1 && from?.width ? findThumb(it.id, { scroll: true }) : null;
    if (thumb) {
      thumb.el.style.visibility = "hidden";
      const overlay = await fly({ src: media.currentSrc || media.src, from, to: thumb.rect, toRadius: thumb.radius, duration: heroDuration - 40 });
      thumb.el.style.visibility = "";
      overlay?.remove?.();
    } else {
      await new Promise((r) => setTimeout(r, 140));
    }
  }

  $effect(() => {
    const it = item;
    if (!it) return;
    const id = it.id;
    detail = null;
    loaded = false;
    zoom = 1;
    tx = ty = 0;
    zoomOpen = false;
    menu = false;
    api(`/api/assets/${id}`)
      .then((d) => {
        if (viewer.list[viewer.index]?.id === id) detail = d;
      })
      .catch((e) => toast(e.message, "error"));
    // 預先載入前後兩張
    for (const j of [viewer.index + 1, viewer.index - 1]) {
      const n = viewer.list[j];
      if (n && n.type !== "video") new Image().src = previewUrl(n);
    }
  });

  async function close() {
    if (phase === "closing") return;
    await heroOut();
    if (pushed) {
      pushed = false;
      history.back();
    }
    viewer.open = false;
  }

  function go(step) {
    const next = viewer.index + step;
    if (next >= 0 && next < viewer.list.length) viewer.index = next;
  }

  function toggleInfo() {
    showInfo = !showInfo;
    try {
      localStorage.setItem("viewer-info", showInfo ? "1" : "0");
    } catch {
      /* 忽略 */
    }
  }

  async function toggleFav() {
    if (!detail) return;
    const on = !detail.favorite;
    await setFavorite([detail.id], on);
    detail.favorite = on ? 1 : 0;
    if (viewer.list[viewer.index]) viewer.list[viewer.index].fav = on;
  }

  async function remove() {
    if (!detail) return;
    const done = await trashAssets([detail.id]);
    if (done.length) {
      viewer.list.splice(viewer.index, 1);
      if (!viewer.list.length) close();
      else if (viewer.index >= viewer.list.length) viewer.index = viewer.list.length - 1;
    }
  }

  async function move() {
    menu = false;
    if (detail && (await moveAssets([detail.id]))) {
      detail = await api(`/api/assets/${detail.id}`);
    }
  }

  // ---- 星等、顏色標籤（與 Lightroom 相同的快捷鍵）----
  async function setXmp(fields) {
    if (!detail) return;
    try {
      const d = await api(`/api/assets/${detail.id}/xmp`, { body: fields });
      detail = d;
      const cur = viewer.list[viewer.index];
      if (cur) {
        cur.rating = d.rating || 0;
        cur.label = d.label;
      }
      if (d.written_to === "sidecar") toast("已寫入 Lightroom 的 .xmp", "info", 1500);
      else if (d.written_to === "embedded") toast("已寫入檔案的 XMP", "info", 1500);
    } catch (e) {
      toast(e.message, "error");
    }
  }

  function rate(n) {
    setXmp({ rating: detail?.rating === n ? 0 : n });
  }

  function labelOf(key) {
    setXmp({ label: detail?.label === key ? "" : key });
  }

  // ---- 疊放 ----
  function showMember(m) {
    viewer.list[viewer.index] = m;
  }

  async function stackAction(action) {
    if (!detail) return;
    detail = await api(`/api/assets/${detail.id}/stack`, { body: { action } });
    toast(action === "unstack" ? "已解除疊放" : "已設為疊放封面");
    refresh();
  }

  function onkey(e) {
    if (e.target.closest?.("input:not([type=range]), textarea, select")) return;
    if (!e.metaKey && !e.ctrlKey && !e.altKey) {
      if ("012345".includes(e.key) && e.key.length === 1) return setXmp({ rating: Number(e.key) });
      const labelKey = { 6: "red", 7: "yellow", 8: "green", 9: "blue" }[e.key];
      if (labelKey) return labelOf(labelKey);
      if (e.key === "x") return setXmp({ rating: -1 });
      if (e.key === "u" && detail?.rating === -1) return setXmp({ rating: 0 });
    }
    if ((e.key === "+" || e.key === "=") && !isVideo) return setZoom(zoom * 1.25);
    if ((e.key === "-" || e.key === "_") && !isVideo) return setZoom(zoom / 1.25);
    if (e.key === "Escape") close();
    else if (e.key === "ArrowRight") go(1);
    else if (e.key === "ArrowLeft") go(-1);
    else if (e.key === "i") toggleInfo();
    else if (e.key === "f") toggleFav();
    else if (e.key === "Delete" || e.key === "Backspace") remove();
  }

  async function onpop() {
    if (pushed) {
      pushed = false;
      await heroOut();
      viewer.open = false;
    }
  }

  // ---- 縮放面板（照片導覽縮圖＋縮放條，像 Google 相簿） ----
  let stageW = $state(0);
  let stageH = $state(0);
  let zoomOpen = $state(false);
  let navDrag = false;
  // 照片在 100% 時實際顯示的大小
  const fit = $derived(item ? Math.min(stageW / (item.w || 1), stageH / (item.h || 1)) : 1);
  const dispW = $derived((item?.w || 1) * fit);
  const dispH = $derived((item?.h || 1) * fit);
  // 目前看到的範圍（以整張照片 0–1 表示）
  const view = $derived.by(() => {
    const w = Math.min(1, stageW / (dispW * zoom || 1));
    const h = Math.min(1, stageH / (dispH * zoom || 1));
    const cx = 0.5 - tx / (dispW * zoom || 1);
    const cy = 0.5 - ty / (dispH * zoom || 1);
    return {
      x: Math.min(Math.max(cx - w / 2, 0), 1 - w), y: Math.min(Math.max(cy - h / 2, 0), 1 - h), w, h,
    };
  });

  // 導覽縮圖的大小：寬最多 160、高最多 120，維持照片比例
  const navSize = $derived.by(() => {
    const ar = (item?.w || 1) / (item?.h || 1);
    return ar >= 160 / 120 ? { w: 160, h: Math.round(160 / ar) } : { w: Math.round(120 * ar), h: 120 };
  });

  function toggleZoom() {
    if (zoom > 1 || zoomOpen) {
      setZoom(1);
      zoomOpen = false;
    } else {
      zoomOpen = true;
      setZoom(2);
    }
  }
  function panTo(nx, ny) {
    tx = (0.5 - Math.min(Math.max(nx, 0), 1)) * dispW * zoom;
    ty = (0.5 - Math.min(Math.max(ny, 0), 1)) * dispH * zoom;
  }
  function navPoint(e) {
    const r = e.currentTarget.getBoundingClientRect();
    panTo((e.clientX - r.left) / r.width, (e.clientY - r.top) / r.height);
  }
  function navDown(e) {
    if (zoom <= 1) return;
    navDrag = true;
    e.currentTarget.setPointerCapture(e.pointerId);
    navPoint(e);
  }
  function navMove(e) {
    if (navDrag) navPoint(e);
  }

  // ---- 縮放與手勢 ----
  const pointers = new Map();
  let start = null;
  let pinch = null;

  function setZoom(z, cx = 0, cy = 0) {
    const nz = Math.min(Math.max(z, 1), 8);
    if (nz === 1) {
      tx = ty = 0;
    } else {
      // 以游標位置為中心縮放
      tx = cx - ((cx - tx) * nz) / zoom;
      ty = cy - ((cy - ty) * nz) / zoom;
    }
    zoom = nz;
  }

  function center(e, el) {
    const r = el.getBoundingClientRect();
    return [e.clientX - r.left - r.width / 2, e.clientY - r.top - r.height / 2];
  }

  function wheel(e) {
    if (isVideo) return;
    e.preventDefault();
    const [cx, cy] = center(e, e.currentTarget);
    setZoom(zoom * (e.deltaY < 0 ? 1.18 : 1 / 1.18), cx, cy);
  }

  function down(e) {
    if (isVideo || e.target.closest("button, input, .zoom-panel, .rate-bar")) return;
    e.currentTarget.setPointerCapture(e.pointerId);
    pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (pointers.size === 1) start = { x: e.clientX, y: e.clientY, tx, ty, t: Date.now() };
    if (pointers.size === 2) {
      const [a, b] = [...pointers.values()];
      pinch = { d: Math.hypot(a.x - b.x, a.y - b.y), z: zoom };
    }
  }

  function moveP(e) {
    if (!pointers.has(e.pointerId)) return;
    pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (pinch && pointers.size === 2) {
      const [a, b] = [...pointers.values()];
      setZoom((pinch.z * Math.hypot(a.x - b.x, a.y - b.y)) / pinch.d);
    } else if (start && zoom > 1) {
      tx = start.tx + (e.clientX - start.x);
      ty = start.ty + (e.clientY - start.y);
    }
  }

  function up(e) {
    if (!pointers.has(e.pointerId)) return;
    pointers.delete(e.pointerId);
    if (pointers.size < 2) pinch = null;
    if (start && pointers.size === 0) {
      const dx = e.clientX - start.x;
      const dy = e.clientY - start.y;
      const quick = Date.now() - start.t < 600;
      if (zoom === 1 && quick && Math.abs(dx) > 60 && Math.abs(dx) > Math.abs(dy)) go(dx < 0 ? 1 : -1);
      else if (zoom === 1 && quick && dy > 110 && Math.abs(dy) > Math.abs(dx)) close();
      else if (Math.abs(dx) < 6 && Math.abs(dy) < 6 && e.pointerType === "touch") chrome = !chrome;
      start = null;
    }
  }

  function dbl(e) {
    if (isVideo) return;
    const [cx, cy] = center(e, e.currentTarget);
    setZoom(zoom > 1 ? 1 : 2.5, cx, cy);
  }
</script>

<svelte:window onkeydown={onkey} onpopstate={onpop} />

<div class="viewer" class:opening={phase === "opening"} class:closing={phase === "closing"} role="dialog" aria-modal="true" aria-label="檢視">
  <div class="stage-wrap">
    <div class="top" class:hidden={!chrome}>
      <button class="icon-btn" onclick={close} aria-label="返回"><Icon path={mdiArrowLeft} /></button>
      <span class="count">{viewer.index + 1} / {viewer.list.length}</span>
      {#if item?.raw}<span class="raw-tag" title="RAW 檔">RAW</span>{/if}
      <span class="spacer"></span>
      {#if !isVideo}
        <button class="icon-btn desktop" class:active={zoomOpen || zoom > 1} onclick={toggleZoom} aria-label="縮放" title="縮放">
          <Icon path={zoom > 1 ? mdiMagnifyMinusOutline : mdiMagnifyPlusOutline} />
        </button>
      {/if}
      <button class="icon-btn" onclick={toggleFav} aria-label="我的最愛" disabled={!detail}>
        <Icon path={detail?.favorite ? mdiHeart : mdiHeartOutline} />
      </button>
      <button class="icon-btn" class:active={showInfo} onclick={toggleInfo} aria-label="資訊"><Icon path={mdiInformationOutline} /></button>
      {#if !isMacApp}
        <a class="icon-btn desktop" href={item ? originalUrl(item, true) : "#"} aria-label="下載原檔" title="下載原檔"><Icon path={mdiDownload} /></a>
      {/if}
      <button class="icon-btn" onclick={remove} aria-label="移到垃圾桶" disabled={!detail}><Icon path={mdiDeleteOutline} /></button>
      <div class="menu-wrap">
        <button class="icon-btn" onclick={() => (menu = !menu)} aria-label="更多"><Icon path={mdiDotsVertical} /></button>
        {#if menu}
          <div class="menu" role="menu">
            <button onclick={() => { menu = false; reveal(item.id); }}><Icon path={mdiFolderOpenOutline} size={20} />{app.server?.local ? "在 Finder 中顯示" : "在 Mac 上顯示"}</button>
            <button onclick={() => { menu = false; editingExif = true; }}><Icon path={mdiFileDocumentEditOutline} size={20} />編輯資訊</button>
            <button onclick={() => { menu = false; addToAlbum([item.id]).then(() => api(`/api/assets/${item.id}`).then((d) => (detail = d))); }}><Icon path={mdiImageAlbum} size={20} />加到相簿</button>
            <button onclick={move}><Icon path={mdiFolderMoveOutline} size={20} />搬移到資料夾</button>
            <button onclick={() => { menu = false; analyzeAssets([item.id]); }}><Icon path={mdiCreation} size={20} />重新 AI 分析</button>
            <button onclick={() => { menu = false; detail && copyText(detail.path); }}><Icon path={mdiContentCopy} size={20} />複製檔案路徑</button>
            {#if !isMacApp}
              <a href={item ? originalUrl(item, true) : "#"} onclick={() => (menu = false)}><Icon path={mdiDownload} size={20} />{app.server?.local ? "下載原檔" : "存到這台裝置"}</a>
            {/if}
          </div>
        {/if}
      </div>
    </div>

    <!-- svelte-ignore a11y_no_static_element_interactions -->
    <div
      class="stage"
      bind:this={stageEl}
      bind:clientWidth={stageW}
      bind:clientHeight={stageH}
      onwheel={wheel}
      onpointerdown={down}
      onpointermove={moveP}
      onpointerup={up}
      onpointercancel={up}
      ondblclick={dbl}
    >
      {#if item}
        {#if isVideo && detail}
          {#if detail.playable && detail.exists}
            <!-- svelte-ignore a11y_media_has_caption -->
            <video src={originalUrl(item)} poster={previewUrl(item, 1280)} controls autoplay playsinline></video>
          {:else}
            <img class="media" src={previewUrl(item, 1600)} alt="" />
            <div class="notice">
              {detail.exists ? "瀏覽器無法直接播放這個影片格式" : "影片檔目前無法存取"}
              {#if detail.exists}<button class="btn small" onclick={() => reveal(item.id, "open")}>在 Mac 上播放</button>{/if}
            </div>
          {/if}
        {:else if !isVideo}
          <img class="placeholder" src={thumbUrl(item)} alt="" class:gone={loaded} />
          {#key item.id}
            <img
              class="media"
              class:show={loaded}
              src={previewUrl(item, hiRes ? 4096 : 2048)}
              alt={detail?.description || item.name || ""}
              draggable="false"
              onload={() => (loaded = true)}
              style:transform="translate({tx}px, {ty}px) scale({zoom})"
            />
          {/key}
        {/if}
      {/if}
      {#if !isVideo && item && (zoomOpen || zoom > 1)}
        <!-- svelte-ignore a11y_no_static_element_interactions -->
        <div class="zoom-panel" onpointerdown={(e) => e.stopPropagation()} onwheel={(e) => e.stopPropagation()}>
          <div
            class="znav"
            style:width="{navSize.w}px"
            style:height="{navSize.h}px"
            role="slider"
            tabindex="-1"
            aria-label="目前看到的範圍"
            aria-valuenow={Math.round(zoom * 100)}
            onpointerdown={navDown}
            onpointermove={navMove}
            onpointerup={() => (navDrag = false)}
            onpointercancel={() => (navDrag = false)}
          >
            <img src={thumbUrl(item)} alt="" draggable="false" />
            {#if zoom > 1}
              <span class="view" style:left="{view.x * 100}%" style:top="{view.y * 100}%" style:width="{view.w * 100}%" style:height="{view.h * 100}%"></span>
            {/if}
          </div>
          <div class="zrow">
            <button onclick={() => setZoom(zoom / 1.25)} disabled={zoom <= 1} aria-label="縮小（-）" title="縮小（-）">−</button>
            <input type="range" min="0" max="1000" step="1" value={Math.round((Math.log(zoom) / Math.log(8)) * 1000)} aria-label="縮放比例"
              oninput={(e) => setZoom(Math.pow(8, Number(e.currentTarget.value) / 1000))} />
            <button onclick={() => setZoom(zoom * 1.25)} disabled={zoom >= 8} aria-label="放大（+）" title="放大（+）">+</button>
          </div>
          <button class="pct" onclick={() => setZoom(1)} title="符合視窗">{Math.round(zoom * 100)}%</button>
        </div>
      {/if}
      {#if detail && !isVideo && app.server?.ui?.viewer_rating_bar !== 0}
        <div class="rate-bar" class:hidden={!chrome}>
          <button class="reject" class:on={detail.rating === -1} title="拒絕（X）" onclick={() => setXmp({ rating: detail.rating === -1 ? 0 : -1 })}>
            <Icon path={mdiFlagRemove} size={20} />
          </button>
          {#each [1, 2, 3, 4, 5] as n (n)}
            <button class="star" class:on={(detail.rating || 0) >= n} title="{n} 星（{n}）" onclick={() => rate(n)}>
              <Icon path={(detail.rating || 0) >= n ? mdiStar : mdiStarOutline} size={22} />
            </button>
          {/each}
          <span class="sep"></span>
          {#each LABEL_KEYS as key (key)}
            <button class="label" class:on={detail.label === key} title="{LABEL_NAMES[key]}色標籤" style:--c={LABEL_COLORS[key]} onclick={() => labelOf(key)}></button>
          {/each}
        </div>
      {/if}
      {#if detail?.stack?.length > 1}
        <div class="stack-strip" class:hidden={!chrome}>
          <span class="stack-title"><Icon path={mdiLayers} size={16} />疊放 {detail.stack.length} 張</span>
          {#each detail.stack as m (m.id)}
            <button class="member" class:current={m.id === detail.id} onclick={() => showMember(m)} title={m.name}>
              <img src={thumbUrl(m)} alt="" />
              {#if m.raw}<span>RAW</span>{/if}
            </button>
          {/each}
          <button class="btn small ghost dark" onclick={() => stackAction("cover")}>設為封面</button>
          <button class="btn small ghost dark" onclick={() => stackAction("unstack")}>解除疊放</button>
        </div>
      {/if}
      {#if viewer.index > 0}
        <button class="nav left" class:hidden={!chrome} onclick={() => go(-1)} aria-label="上一張"><Icon path={mdiChevronLeft} size={32} /></button>
      {/if}
      {#if viewer.index < viewer.list.length - 1}
        <button class="nav right" class:hidden={!chrome} onclick={() => go(1)} aria-label="下一張"><Icon path={mdiChevronRight} size={32} /></button>
      {/if}
    </div>
  </div>
  {#if showInfo}
    <div class="side">
      <InfoPanel {detail} onclose={toggleInfo} onchange={(d) => { detail = d; refresh(); }} />
    </div>
  {/if}
</div>

{#if editingExif && item}
  <ExifDialog ids={[item.id]} onclose={() => { editingExif = false; }} />
{/if}

<style>
  .viewer {
    position: fixed; inset: 0; z-index: 100; background: #000; color: #fff; display: flex;
    animation: bg-in .28s cubic-bezier(.2,0,0,1);
    transition: background-color .26s cubic-bezier(.3,0,.8,.15);
  }
  @keyframes bg-in { from { background-color: rgb(0 0 0 / 0); } }
  /* 動畫進行中：真正的照片先藏起來，由覆蓋的那張負責移動 */
  .viewer.opening .stage :global(img), .viewer.closing .stage :global(img), .viewer.closing video { opacity: 0 !important; transition: none !important; }
  .viewer.closing { background-color: rgb(0 0 0 / 0); pointer-events: none; }
  .viewer.opening .top, .viewer.closing .top, .viewer.closing .nav, .viewer.closing .side { opacity: 0; transition: opacity .15s; }
  .viewer .top { transition: opacity .2s; }
  .stage-wrap { position: relative; flex: 1; min-width: 0; display: flex; flex-direction: column; }
  /* 工具列自己一條，照片從它下面開始：不在照片上加任何漸層或遮罩 */
  .top {
    position: relative; flex-shrink: 0; z-index: 3; display: flex; align-items: center; gap: 2px;
    padding: max(8px, env(safe-area-inset-top)) 8px 8px; background: none;
    transition: opacity .2s;
  }
  .top .icon-btn { color: #fff; text-decoration: none; }
  .count { font-size: 14px; opacity: .7; margin-left: 4px; }
  .raw-tag { margin-left: 8px; font-size: 10px; line-height: 16px; font-weight: 500; letter-spacing: .06em; border: 1px solid rgb(255 255 255 / .5); border-radius: var(--corner-extra-small); padding: 0 5px; opacity: .85; }
  .spacer { flex: 1; }
  .hidden { opacity: 0; pointer-events: none; }
  .stage {
    flex: 1; position: relative; overflow: hidden; display: flex; align-items: center; justify-content: center;
    touch-action: none; user-select: none;
  }
  .media, .placeholder, video {
    position: absolute; max-width: 100%; max-height: 100%; width: auto; height: auto; object-fit: contain;
  }
  .placeholder { width: 100%; height: 100%; filter: blur(8px); opacity: .7; transition: opacity .3s; }
  .placeholder.gone { opacity: 0; }
  .media { opacity: 0; transition: opacity .2s; will-change: transform; }
  .media.show { opacity: 1; }
  video { width: 100%; height: 100%; background: #000; }
  .notice {
    position: absolute; bottom: 40px; left: 50%; transform: translateX(-50%); background: rgba(0,0,0,.7);
    padding: 10px 16px; border-radius: var(--corner-medium); display: flex; gap: 12px; align-items: center; font-size: 14px;
  }
  .nav {
    position: absolute; top: 50%; transform: translateY(-50%); z-index: 2; border: 0; cursor: pointer;
    width: 48px; height: 48px; border-radius: 50%; background: rgba(0,0,0,.35); color: #fff;
    display: flex; align-items: center; justify-content: center; transition: opacity .2s, background .2s;
  }
  .nav:hover { background: rgba(255,255,255,.2); }
  .nav.left { left: 16px; }
  .nav.right { right: 16px; }
  .top .icon-btn.active { background: rgba(255, 255, 255, .2); }
  .zoom-panel {
    position: absolute; top: 72px; right: 16px; z-index: 4; width: 176px; padding: 8px; border-radius: var(--corner-medium);
    background: rgb(20 20 24 / .88); color: #fff; display: flex; flex-direction: column; gap: 6px;
    border: 1px solid rgb(255 255 255 / .12); cursor: default;
  }
  .znav { position: relative; flex-shrink: 0; align-self: center; overflow: hidden; border-radius: var(--corner-extra-small); cursor: crosshair; touch-action: none; }
  .znav img { width: 100%; height: 100%; object-fit: cover; display: block; opacity: .55; pointer-events: none; }
  .znav .view { position: absolute; border: 2px solid #fff; box-shadow: 0 0 0 999px rgba(0, 0, 0, .35); pointer-events: none; }
  .zrow { display: flex; align-items: center; gap: 4px; }
  .zrow button { border: 0; background: none; color: #fff; width: 24px; height: 24px; border-radius: 50%; font-size: 18px; line-height: 1; cursor: pointer; }
  .zrow button:hover:not(:disabled) { background: rgba(255, 255, 255, .15); }
  .zrow button:disabled { opacity: .35; cursor: default; }
  .zrow input { flex: 1; min-width: 0; accent-color: #fff; }
  .zoom-panel .pct { align-self: center; border: 0; background: none; color: rgba(255, 255, 255, .8); font-size: 12px; cursor: pointer; font-variant-numeric: tabular-nums; }
  @media (max-width: 760px) { .zoom-panel { display: none; } }
  .rate-bar {
    position: absolute; left: 50%; bottom: 18px; transform: translateX(-50%); z-index: 3; display: flex; align-items: center;
    gap: 2px; background: rgba(0,0,0,.55); border-radius: var(--corner-full); padding: 4px 10px; transition: opacity .2s;
  }
  .rate-bar button { border: 0; background: none; color: rgba(255,255,255,.75); cursor: pointer; padding: 4px; display: flex; }
  .rate-bar .star.on { color: #f5c518; }
  .rate-bar .reject.on { color: #ff6b6b; }
  .rate-bar .sep { width: 1px; height: 18px; background: rgba(255,255,255,.3); margin: 0 6px; }
  .rate-bar .label { width: 18px; height: 18px; border-radius: 50%; padding: 0; margin: 0 3px; background: var(--c); opacity: .45; }
  .rate-bar .label.on { opacity: 1; box-shadow: 0 0 0 2px #fff; }
  .stack-strip {
    position: absolute; left: 50%; bottom: 70px; transform: translateX(-50%); z-index: 3; display: flex; align-items: center;
    gap: 6px; background: rgba(0,0,0,.6); border-radius: var(--corner-medium); padding: 6px 10px; max-width: 92%; overflow-x: auto;
  }
  .stack-title { display: flex; align-items: center; gap: 4px; font-size: 12px; white-space: nowrap; margin-right: 4px; }
  .member { position: relative; border: 2px solid transparent; border-radius: var(--corner-small); padding: 0; background: none; cursor: pointer; flex-shrink: 0; }
  .member.current { border-color: #fff; }
  .member img { width: 52px; height: 52px; object-fit: cover; border-radius: var(--corner-small); display: block; }
  .member span { position: absolute; left: 2px; bottom: 2px; font-size: 9px; background: rgba(0,0,0,.6); color: #fff; padding: 0 3px; border-radius: 3px; }
  .btn.dark { color: #fff; border-color: rgba(255,255,255,.4); }
  .menu-wrap { position: relative; }
  .menu {
    position: absolute; right: 0; top: 44px; background: var(--surface-container); color: var(--on-surface); border-radius: var(--corner-large);
    border: 1px solid var(--outline-variant); padding: 6px; min-width: 220px; display: flex; flex-direction: column; z-index: 5;
  }
  .menu button, .menu a {
    display: flex; align-items: center; gap: 12px; padding: 10px 12px; border: 0; background: none;
    border-radius: var(--corner-medium); cursor: pointer; text-align: left; color: inherit; text-decoration: none; font-size: 14px;
  }
  .menu button:hover, .menu a:hover { background: var(--surface-container); }
  .side { height: 100%; animation: side-in .32s cubic-bezier(.2,0,0,1); }
  @keyframes side-in { from { transform: translateX(24px); opacity: 0; } }
  @media (max-width: 900px) {
    .rate-bar { bottom: calc(10px + env(safe-area-inset-bottom)); }
    .stack-strip { bottom: calc(62px + env(safe-area-inset-bottom)); }
    .viewer { flex-direction: column; }
    .side { position: absolute; left: 0; right: 0; bottom: 0; height: auto; z-index: 4; }
    .desktop { display: none !important; }
    .nav { display: none; }
  }
</style>
