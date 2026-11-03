<script>
  import { onMount } from "svelte";
  import Icon from "./Icon.svelte";
  import InfoPanel from "./InfoPanel.svelte";
  import { api, originalUrl, previewUrl, thumbUrl } from "../lib/api.js";
  import { app, viewer, refresh, toast, isMacApp } from "../lib/state.svelte.js";
  import { addToAlbum, analyzeAssets, moveAssets, reveal, setFavorite, trashAssets, copyText } from "../lib/actions.js";
  import { LABEL_COLORS, LABEL_KEYS, LABEL_NAMES } from "../lib/format.js";
  import {
    mdiArrowLeft, mdiChevronLeft, mdiChevronRight, mdiDeleteOutline, mdiDotsVertical, mdiDownload, mdiFolderOpenOutline,
    mdiHeart, mdiHeartOutline, mdiInformationOutline, mdiImageAlbum, mdiFolderMoveOutline, mdiCreation, mdiContentCopy,
    mdiMagnifyPlusOutline, mdiMagnifyMinusOutline, mdiStar, mdiStarOutline, mdiFlagRemove, mdiLayers,
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
    history.pushState({ viewer: true }, "");
    pushed = true;
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => (document.body.style.overflow = prevOverflow);
  });

  $effect(() => {
    const it = item;
    if (!it) return;
    const id = it.id;
    detail = null;
    loaded = false;
    zoom = 1;
    tx = ty = 0;
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

  function close() {
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
    if (e.target.closest?.("input, textarea")) return;
    if (!e.metaKey && !e.ctrlKey && !e.altKey) {
      if ("012345".includes(e.key) && e.key.length === 1) return setXmp({ rating: Number(e.key) });
      const labelKey = { 6: "red", 7: "yellow", 8: "green", 9: "blue" }[e.key];
      if (labelKey) return labelOf(labelKey);
      if (e.key === "x") return setXmp({ rating: -1 });
      if (e.key === "u" && detail?.rating === -1) return setXmp({ rating: 0 });
    }
    if (e.key === "Escape") close();
    else if (e.key === "ArrowRight") go(1);
    else if (e.key === "ArrowLeft") go(-1);
    else if (e.key === "i") toggleInfo();
    else if (e.key === "f") toggleFav();
    else if (e.key === "Delete" || e.key === "Backspace") remove();
  }

  function onpop() {
    if (pushed) {
      pushed = false;
      viewer.open = false;
    }
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
    if (isVideo || e.target.closest("button")) return;
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

<div class="viewer" role="dialog" aria-modal="true" aria-label="檢視">
  <div class="stage-wrap">
    <div class="top" class:hidden={!chrome}>
      <button class="icon-btn" onclick={close} aria-label="返回"><Icon path={mdiArrowLeft} /></button>
      <span class="count">{viewer.index + 1} / {viewer.list.length}</span>
      <span class="spacer"></span>
      {#if !isVideo}
        <button class="icon-btn desktop" onclick={() => setZoom(zoom > 1 ? 1 : 2.5)} aria-label="縮放">
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

<style>
  .viewer {
    position: fixed; inset: 0; z-index: 100; background: #000; color: #fff; display: flex;
    animation: fade .15s ease-out;
  }
  @keyframes fade { from { opacity: 0; } }
  .stage-wrap { position: relative; flex: 1; min-width: 0; display: flex; flex-direction: column; }
  .top {
    position: absolute; top: 0; left: 0; right: 0; z-index: 3; display: flex; align-items: center; gap: 2px;
    padding: max(8px, env(safe-area-inset-top)) 8px 24px; background: linear-gradient(rgba(0,0,0,.55), transparent);
    transition: opacity .2s;
  }
  .top .icon-btn { color: #fff; text-decoration: none; }
  .count { font-size: 13px; opacity: .7; margin-left: 4px; }
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
    padding: 10px 16px; border-radius: 12px; display: flex; gap: 12px; align-items: center; font-size: 14px;
  }
  .nav {
    position: absolute; top: 50%; transform: translateY(-50%); z-index: 2; border: 0; cursor: pointer;
    width: 48px; height: 48px; border-radius: 50%; background: rgba(0,0,0,.35); color: #fff;
    display: flex; align-items: center; justify-content: center; transition: opacity .2s, background .2s;
  }
  .nav:hover { background: rgba(255,255,255,.2); }
  .nav.left { left: 16px; }
  .nav.right { right: 16px; }
  .rate-bar {
    position: absolute; left: 50%; bottom: 18px; transform: translateX(-50%); z-index: 3; display: flex; align-items: center;
    gap: 2px; background: rgba(0,0,0,.55); border-radius: 999px; padding: 4px 10px; transition: opacity .2s;
  }
  .rate-bar button { border: 0; background: none; color: rgba(255,255,255,.75); cursor: pointer; padding: 4px; display: flex; }
  .rate-bar .star.on { color: #f5c518; }
  .rate-bar .reject.on { color: #ff6b6b; }
  .rate-bar .sep { width: 1px; height: 18px; background: rgba(255,255,255,.3); margin: 0 6px; }
  .rate-bar .label { width: 18px; height: 18px; border-radius: 50%; padding: 0; margin: 0 3px; background: var(--c); opacity: .45; }
  .rate-bar .label.on { opacity: 1; box-shadow: 0 0 0 2px #fff; }
  .stack-strip {
    position: absolute; left: 50%; bottom: 70px; transform: translateX(-50%); z-index: 3; display: flex; align-items: center;
    gap: 6px; background: rgba(0,0,0,.6); border-radius: 14px; padding: 6px 10px; max-width: 92%; overflow-x: auto;
  }
  .stack-title { display: flex; align-items: center; gap: 4px; font-size: 12px; white-space: nowrap; margin-right: 4px; }
  .member { position: relative; border: 2px solid transparent; border-radius: 8px; padding: 0; background: none; cursor: pointer; flex-shrink: 0; }
  .member.current { border-color: #fff; }
  .member img { width: 52px; height: 52px; object-fit: cover; border-radius: 6px; display: block; }
  .member span { position: absolute; left: 2px; bottom: 2px; font-size: 9px; background: rgba(0,0,0,.6); color: #fff; padding: 0 3px; border-radius: 3px; }
  .btn.dark { color: #fff; border-color: rgba(255,255,255,.4); }
  .menu-wrap { position: relative; }
  .menu {
    position: absolute; right: 0; top: 44px; background: var(--panel); color: var(--text); border-radius: 14px;
    box-shadow: var(--shadow); padding: 6px; min-width: 220px; display: flex; flex-direction: column; z-index: 5;
  }
  .menu button, .menu a {
    display: flex; align-items: center; gap: 12px; padding: 10px 12px; border: 0; background: none;
    border-radius: 10px; cursor: pointer; text-align: left; color: inherit; text-decoration: none; font-size: 14px;
  }
  .menu button:hover, .menu a:hover { background: var(--bg-2); }
  .side { height: 100%; }
  @media (max-width: 900px) {
    .rate-bar { bottom: calc(10px + env(safe-area-inset-bottom)); }
    .stack-strip { bottom: calc(62px + env(safe-area-inset-bottom)); }
    .viewer { flex-direction: column; }
    .side { position: absolute; left: 0; right: 0; bottom: 0; height: auto; z-index: 4; }
    .desktop { display: none !important; }
    .nav { display: none; }
  }
</style>
