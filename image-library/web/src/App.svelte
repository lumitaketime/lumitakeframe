<script>
  import { onMount } from "svelte";
  import { fade } from "svelte/transition";
  import Viewer from "./components/Viewer.svelte";
  import SelectionBar from "./components/SelectionBar.svelte";
  import Toasts from "./components/Toasts.svelte";
  import Dialogs from "./components/Dialogs.svelte";
  import Onboarding from "./components/Onboarding.svelte";
  import Timeline from "./pages/Timeline.svelte";
  import Explore from "./pages/Explore.svelte";
  import Search from "./pages/Search.svelte";
  import Browse from "./pages/Browse.svelte";
  import Drives from "./pages/Drives.svelte";
  import Albums from "./pages/Albums.svelte";
  import Album from "./pages/Album.svelte";
  import People from "./pages/People.svelte";
  import Similar from "./pages/Duplicates.svelte";
  import Dupes from "./pages/Dupes.svelte";
  import Pending from "./pages/Pending.svelte";
  import Activity from "./pages/Activity.svelte";
  import Tools from "./pages/Tools.svelte";
  import Keywords from "./pages/Keywords.svelte";
  import SmartAlbum from "./pages/SmartAlbum.svelte";
  import Person from "./pages/Person.svelte";
  import Settings from "./pages/Settings.svelte";
  import Login from "./pages/Login.svelte";
  import AppSidebar from "./shell/AppSidebar.svelte";
  import AppToolbar from "./shell/AppToolbar.svelte";
  import PathBar from "./shell/PathBar.svelte";
  import PhotoTabs from "./shell/PhotoTabs.svelte";
  import Inspector from "./shell/Inspector.svelte";
  import StatusBar from "./shell/StatusBar.svelte";
  import { frame, pageFrame, toggleSidebar, toggleInfo, setSidebarWidth, SIDEBAR_MIN, SIDEBAR_MAX, INFO_BREAK, DRAWER_BREAK } from "./shell/frame.svelte.js";
  import { loadCatalog } from "./data/catalog.svelte.js";
  import { setView } from "./views/prefs.svelte.js";
  import { t } from "./i18n/index.svelte.js";
  import { api } from "./lib/api.js";
  import { app, selection, viewer, refresh, toast, macOverlayTitleBar } from "./lib/state.svelte.js";
  import { route, navigate, link } from "./lib/router.svelte.js";
  import { undoLast } from "./lib/undo.svelte.js";
  import { DUR, slidePanel } from "./lib/motion.js";
  import { rubberBand, installShake } from "./lib/alive.js";

  // 設定的各分類是同一頁的不同區塊：換分類不重建整頁（避免閃一下、狀態卡重新載入）
  const routeKey = $derived(route.path.startsWith("/settings") ? "/settings" : route.path);

  // 視窗外框（手冊「視窗結構」）：側邊欄｜工具列、路徑列、內容、狀態列｜資訊欄。
  // 寬度小於 800：側邊欄收成抽屜、工具列出現 ≡；小於 1100：資訊欄自動收起（按了才浮在內容上）。
  let winW = $state(typeof window === "undefined" ? 1400 : window.innerWidth);
  const compact = $derived(winW < DRAWER_BREAK);
  const infoDocked = $derived(winW >= INFO_BREAK);
  let infoFloat = $state(false); // 窄視窗時暫時打開的資訊欄
  const infoOpen = $derived(!compact && (infoDocked ? frame.info : infoFloat));
  function onToggleInfo() {
    if (infoDocked) toggleInfo();
    else infoFloat = !infoFloat;
  }
  // 換頁或換版面後收起抽屜與浮動的資訊欄，避免留下看不見的遮罩擋住畫面
  $effect(() => {
    route.path;
    compact;
    infoDocked;
    frame.drawer = false;
    infoFloat = false;
  });

  const seg = $derived(route.path.split("/").filter(Boolean));
  const page = $derived(seg[0] || "");
  // 照片圖庫沿用的頁面：收在「照片」底下，用分頁切換
  const PHOTO_PAGES = new Set(["", "welcome", "favorites", "videos", "albums", "explore", "people", "keywords", "tools", "similar"]);
  const photoPage = $derived(PHOTO_PAGES.has(page));
  const pf = $derived(pageFrame());
  const crumbs = $derived(pf?.crumbs || []);
  const title = $derived(
    page === "folders" ? (crumbs.length > 1 ? crumbs[crumbs.length - 1].label : t("nav.allFiles"))
      : photoPage ? t("nav.photos")
        : page === "duplicates" ? t("nav.duplicates")
          : page === "kind" ? t(`kind.${seg[1]}`)
          : page === "label" ? t(`label.${seg[1]}`)
          : page === "pending" ? t("nav.pending")
          : page === "activity" ? t("nav.scanProgress")
          : page === "drives" ? t("nav.drives")
          : page === "settings" ? t("nav.settings")
            : page === "search" ? t("nav.search") : "");

  // 側邊欄寬度：拖曳右邊緣，或聚焦後用左右方向鍵（200–320）
  let dragging = $state(false);
  function startResize(e) {
    e.preventDefault();
    dragging = true;
    const move = (ev) => setSidebarWidth(ev.clientX - 16);
    const up = () => {
      dragging = false;
      removeEventListener("pointermove", move);
      removeEventListener("pointerup", up);
    };
    addEventListener("pointermove", move);
    addEventListener("pointerup", up);
  }
  function resizeKey(e) {
    const d = e.key === "ArrowRight" ? 10 : e.key === "ArrowLeft" ? -10 : 0;
    if (!d) return;
    e.preventDefault();
    setSidebarWidth(frame.sidebarWidth + d);
  }

  // 捲到底的回彈只在觸控裝置保留；Mac 上交給系統
  const touch = typeof matchMedia === "function" && matchMedia("(pointer: coarse)").matches;
  const touchBounce = (node) => (touch ? rubberBand(node) : undefined);

  // Mac App 的覆蓋式標題列：在工具列或側邊欄頂端的空白處按下就拖曳視窗，按兩下放大（由 App 外殼處理）
  function windowDrag(e) {
    if (!macOverlayTitleBar || e.button !== 0) return;
    if (e.target.closest("button, a, input, select, textarea, [role='radiogroup'], [role='combobox'], [role='listbox'], .lg-slider, .panel")) return;
    location.href = e.detail >= 2 ? "lumitake://zoom" : "lumitake://drag";
  }

  function onKey(e) {
    const typing = e.target.closest?.("input, textarea, select, [contenteditable]");
    const mod = e.metaKey || e.ctrlKey;
    const key = e.key.toLowerCase();
    if (mod && !e.shiftKey && !e.altKey && key === "z" && !typing && !viewer.open) {
      e.preventDefault();
      undoLast();
    } else if (viewer.open || app.needLogin) {
      return;
    } else if (((e.metaKey && e.ctrlKey) || (e.ctrlKey && e.altKey)) && key === "s") {
      e.preventDefault(); // ⌘⌃S：收合／顯示側邊欄
      if (compact) frame.drawer = !frame.drawer;
      else toggleSidebar();
    } else if (mod && !e.shiftKey && !e.altKey && key === "i" && !typing) {
      e.preventDefault(); // ⌘I：資訊欄
      onToggleInfo();
    } else if (mod && !e.shiftKey && !e.altKey && e.key === ",") {
      e.preventDefault(); // ⌘,：設定
      navigate("/settings");
    } else if (mod && !e.shiftKey && !e.altKey && key === "f") {
      const input = document.querySelector(".app-toolbar input");
      if (input) {
        e.preventDefault(); // ⌘F：搜尋
        input.focus();
      }
    } else if (mod && !e.shiftKey && !e.altKey && "12345".includes(e.key) && pf?.browse && !typing) {
      e.preventDefault(); // ⌘1 圖像、⌘2 列表、⌘3 直欄、⌘4 樹狀、⌘5 佔比
      setView(pf.browse, ["icons", "list", "columns", "tree", "treemap"][Number(e.key) - 1]);
    } else if (mod && e.key === "ArrowUp" && !typing && crumbs.length > 1) {
      e.preventDefault(); // ⌘↑：回上層
      navigate(crumbs[crumbs.length - 2].href);
    } else if (e.key === "Escape" && (frame.drawer || infoFloat)) {
      frame.drawer = false;
      infoFloat = false;
    }
  }

  // 側邊欄的硬碟清單：伺服器狀態有變（掃描進度、工作結束）或頁面要求重新整理時更新
  $effect(() => {
    app.server;
    app.refreshKey;
    if (app.authChecked && !app.needLogin) loadCatalog();
  });

  let lastFinished = null;
  let wasRunning = false;
  let lastTotal = null;
  let lastRefresh = 0;
  let timer;

  // 第一次在這台 Mac 上開啟時顯示設定引導（手機、平板不顯示）
  const welcome = $derived(page === "welcome" || (app.server?.local && app.server?.ui?.onboarded === 0 && page !== "settings"));

  // 換頁時清除選取與情境
  $effect(() => {
    route.path;
    selection.clear();
    app.context = null;
  });

  // 完成通知：使用者自己啟動、會跑一陣子的工作，結束時跳出 Snackbar
  const NOTIFY = new Set(["export", "pull", "face_model", "clip_model", "dups", "cluster"]);
  let seenJob = null;
  function notifyFinished(recent) {
    const ids = recent.map((j) => j.id);
    if (seenJob === null) {
      seenJob = Math.max(0, ...ids);
      return;
    }
    for (const j of [...recent].reverse()) {
      if (j.id <= seenJob) continue;
      if (j.error) toast(`${j.label}失敗：${j.error}`, "error");
      else if (j.kind === "export" && j.result?.dest && app.server?.local) {
        const dest = j.result.dest;
        toast(j.message, "info", 10000, { label: "在 Finder 中顯示", run: () => api("/api/reveal-path", { body: { path: dest } }).catch((e) => toast(e.message, "error")) });
      } else if (NOTIFY.has(j.kind)) toast(`${j.label}完成：${j.message}`, "info", 6000);
    }
    seenJob = Math.max(seenJob, ...ids);
  }

  async function answerConfirm(start) {
    try {
      app.server.jobs = await api("/api/analysis/confirm", { body: { start } });
      toast(start ? "開始 AI 分析" : "好的，下次掃描到新照片時再問你；也可以在設定按「掃描並分析全部」");
    } catch (e) {
      toast(e.message, "error");
    }
  }

  // 這些工作結束時不會改變照片內容，不必重新載入頁面（四萬張以上時重新載入很有感）
  const NO_RELOAD = new Set(["pull", "face_model", "clip_model", "export", "delete_model"]);
  let lastSnap = "";
  let seenFinish = null;

  async function poll() {
    clearTimeout(timer);
    try {
      const s = await api("/api/server");
      // 內容沒變就不要換掉整個物件，避免整個介面跟著重新計算
      const snap = JSON.stringify(s);
      if (snap !== lastSnap) {
        lastSnap = snap;
        app.server = s;
      }
      notifyFinished(s.jobs.recent || []);
      const running = !!s.jobs.running;
      const fin = s.jobs.last?.finished_at;
      const total = s.stats.images;
      // 新結束的工作裡，有會改變照片內容的才重新載入頁面
      const recent = s.jobs.recent || [];
      const newly = seenFinish === null ? [] : recent.filter((j) => j.id > seenFinish);
      if (recent.length) seenFinish = Math.max(seenFinish ?? 0, ...recent.map((j) => j.id));
      const contentChanged = newly.some((j) => !NO_RELOAD.has(j.kind));
      if (contentChanged || (wasRunning && !running && !newly.length && fin !== lastFinished)) {
        lastRefresh = Date.now();
        refresh();
      } else if (running && lastTotal !== null && total !== lastTotal && Date.now() - lastRefresh > 15000) {
        // 掃描途中照片數變了：每 15 秒讓新照片陸續出現一次
        lastRefresh = Date.now();
        refresh();
      }
      lastTotal = total;
      wasRunning = running;
      lastFinished = fin || lastFinished;
      // 背景執行時慢一點；視窗不在前景時更慢
      const hidden = typeof document !== "undefined" && document.hidden;
      timer = setTimeout(poll, hidden ? 30000 : running ? 2500 : 12000);
    } catch {
      timer = setTimeout(poll, 5000);
    }
  }

  // 回到前景時立刻更新一次
  function onVisible() {
    if (!document.hidden && app.server && !app.needLogin) poll();
  }

  onMount(async () => {
    try {
      const st = await api("/api/auth/status");
      app.needLogin = !st.authenticated;
    } catch {
      /* 伺服器未啟動時稍後重試 */
    }
    app.authChecked = true;
    if (!app.needLogin) poll();
    document.addEventListener("visibilitychange", onVisible);
    const removeShake = installShake();
    return () => {
      removeShake();
      clearTimeout(timer);
      document.removeEventListener("visibilitychange", onVisible);
    };
  });

  $effect(() => {
    // 登入成功後開始輪詢
    if (app.authChecked && !app.needLogin && !app.server) poll();
  });

  // 頁面上的動作（例如換相簿）會呼叫 refresh()，順便更新統計
  $effect(() => {
    if (app.refreshKey) api("/api/server").then((s) => {
      lastSnap = JSON.stringify(s);
      app.server = s;
    }).catch(() => {});
  });
</script>

<svelte:window bind:innerWidth={winW} onkeydown={onKey} />

{#if !app.authChecked}
  <div class="boot"><span class="spinner"></span></div>
{:else if app.needLogin}
  <Login />
{:else}
  <div class="frame" class:compact class:resizing={dragging} class:mac-titlebar={macOverlayTitleBar} class:no-side={compact || !frame.sidebar}>
    {#if !compact && frame.sidebar}
      <!-- svelte-ignore a11y_no_static_element_interactions -->
      <div class="side" transition:slidePanel={{ x: -(frame.sidebarWidth + 16) }} onmousedown={(e) => { if (e.target.closest(".lg-side-top") && !e.target.closest(".brand")) windowDrag(e); }}>
        <AppSidebar width={frame.sidebarWidth} />
        <!-- svelte-ignore a11y_no_noninteractive_tabindex, a11y_no_noninteractive_element_interactions -->
        <div class="resizer" role="separator" aria-orientation="vertical" aria-label={t("nav.resizeSidebar")} tabindex="0"
          aria-valuemin={SIDEBAR_MIN} aria-valuemax={SIDEBAR_MAX} aria-valuenow={frame.sidebarWidth}
          onpointerdown={startResize} onkeydown={resizeKey}></div>
      </div>
    {/if}

    <div class="pane">
      <!-- svelte-ignore a11y_no_static_element_interactions -->
      <div class="bar" onmousedown={windowDrag}>
      <AppToolbar {title} {compact} narrowSearch={winW <= 600} place={pf?.browse || ""} {infoOpen} ontoggleinfo={onToggleInfo} />
      </div>
      {#if photoPage}<PhotoTabs />{:else if crumbs.length}<PathBar {crumbs} />{/if}
      <div class="body">
        <main class="scroll-area" use:touchBounce>
          <div class="load-bar" class:on={app.busy} aria-hidden="true"><span></span></div>
          {#key routeKey}
            <div class="route" class:fill={page === "folders" || page === "kind" || page === "label"}>
            {#if page === "" || page === "welcome"}
              <Timeline />
            {:else if page === "favorites"}
              <Timeline scope={{ fav: "1" }} title="我的最愛" emptyText="點照片右上角的愛心，作品就會出現在這裡。" />
            {:else if page === "videos"}
              <Timeline scope={{ type: "video" }} title="影片" emptyText="還沒有影片。" />
            {:else if page === "explore"}
              <Explore />
            {:else if page === "search"}
              <Search />
            {:else if page === "folders"}
              <Browse scope={seg[1] ? { type: "folder", root: Number(seg[1]), path: route.query.path || "" } : { type: "roots" }} />
            {:else if page === "label" && seg[1]}
              <Browse scope={{ type: "label", label: seg[1] }} />
            {:else if page === "drives"}
              <Drives />
            {:else if page === "kind" && seg[1]}
              <Browse scope={{ type: "kind", kind: seg[1] }} />
            {:else if page === "albums" && seg[1] === "smart" && seg[2]}
              <SmartAlbum id={Number(seg[2])} />
            {:else if page === "keywords"}
              <Keywords />
            {:else if page === "tools"}
              <Tools sub={seg[1] || ""} />
            {:else if page === "duplicates"}
              <Dupes />
            {:else if page === "activity"}
              <Activity />
            {:else if page === "pending"}
              <Pending />
            {:else if page === "similar"}
              <Similar />
            {:else if page === "albums" && seg[1]}
              <Album id={Number(seg[1])} />
            {:else if page === "albums"}
              <Albums />
            {:else if page === "people" && seg[1]}
              <Person id={Number(seg[1])} />
            {:else if page === "people"}
              <People />
            {:else if page === "settings"}
              <Settings section={seg[1] || ""} />
            {:else}
              <div class="empty"><h2>{t("nav.notFound")}</h2><a href="/folders" use:link>{t("nav.backToFiles")}</a></div>
            {/if}
            </div>
          {/key}
        </main>
        {#if infoOpen}
          <div class="info" class:float={!infoDocked} transition:slidePanel={{ x: 280, duration: DUR.slow }}>
            <Inspector info={pf?.info || null} />
          </div>
        {/if}
      </div>
      <StatusBar status={pf?.status || ""} location={pf?.location || null} />
    </div>

    {#if compact && frame.drawer}
      <button class="scrim" onclick={() => (frame.drawer = false)} aria-label={t("nav.closeMenu")} transition:fade={{ duration: DUR.fast }}></button>
      <div class="drawer" transition:slidePanel={{ x: -320 }}>
        <AppSidebar width={Math.min(300, winW - 48)} />
      </div>
    {/if}
  </div>

  {#if welcome}<Onboarding startStep={route.query.step || ""} />{/if}
  {#if selection.size}<SelectionBar />{/if}
  {#if viewer.open}<Viewer />{/if}
  <Dialogs />
{/if}
{#if app.server?.jobs?.confirm && !app.needLogin}
  <div class="ask" role="alertdialog" aria-label="開始 AI 分析？">
    <span class="msg">有 {app.server.jobs.confirm.pending.toLocaleString()} 張新照片還沒 AI 分析，要現在開始嗎？</span>
    <button class="act" onclick={() => answerConfirm(false)}>稍後</button>
    <button class="act strong" onclick={() => answerConfirm(true)}>開始分析</button>
  </div>
{/if}
<Toasts />

<style>
  .boot { height: 100vh; display: flex; align-items: center; justify-content: center; color: var(--label-secondary); }
  /* 外框：視窗底色上浮著玻璃側邊欄；右邊的內容窗格不透明 */
  .frame { display: flex; height: 100vh; height: 100dvh; background: var(--window-bg); color: var(--label-primary); overflow: hidden; }
  .frame.resizing { cursor: col-resize; user-select: none; }
  /* 側邊欄：浮動面板，與視窗邊緣留 8，圓角 radius-lg */
  .side { position: relative; flex: none; padding: var(--space-2); padding-top: calc(var(--space-2) + env(safe-area-inset-top)); display: flex; }
  .side :global(.lg-sidebar-floating), .drawer :global(.lg-sidebar-floating) { border-radius: var(--radius-lg); }
  .resizer { position: absolute; top: var(--space-4); bottom: var(--space-4); right: 0; width: var(--space-2); cursor: col-resize; border-radius: var(--radius-capsule); touch-action: none; }
  .resizer:hover, .frame.resizing .resizer { background: var(--fill-secondary); }

  /* Mac App：紅綠燈按鈕在左上角（約 70×28）。側邊欄的標誌往下讓位；側邊欄收起時，工具列往右讓位 */
  .mac-titlebar .side :global(.lg-side-top:first-child) { padding-top: var(--space-6); }
  .mac-titlebar.no-side .bar { padding-left: 72px; }
  /* 工具列的選單（排序、搜尋建議）要蓋在內容上面 */
  .bar { flex: none; position: relative; z-index: 40; }
  .pane { flex: 1; min-width: 0; display: flex; flex-direction: column; background: var(--control-bg); }
  .frame:not(.compact) .pane { box-shadow: -1px 0 0 var(--separator); }
  .body { flex: 1; min-height: 0; display: flex; position: relative; }
  main { flex: 1; min-width: 0; position: relative; overflow-y: auto; overscroll-behavior-y: none; }
  .route { min-height: 100%; }
  .route.fill { height: 100%; min-height: 0; }
  /* 資訊欄：寬視窗時佔一欄；窄視窗時浮在內容右側 */
  .info { flex: none; width: 280px; border-left: 1px solid var(--separator); background: var(--control-bg); }
  .info.float { position: absolute; z-index: 40; top: 0; bottom: 0; right: 0; box-shadow: var(--shadow-popover); }

  /* 窄視窗：≡ 滑出的側邊欄 */
  .scrim { position: fixed; inset: 0; z-index: 250; border: 0; padding: 0; background: var(--media-scrim-light); cursor: default; }
  .drawer { position: fixed; z-index: 260; left: 0; top: 0; bottom: 0; padding: var(--space-2); padding-top: calc(var(--space-2) + env(safe-area-inset-top));
    padding-bottom: calc(var(--space-2) + env(safe-area-inset-bottom)); display: flex; will-change: transform; }

  /* 頂端的 M3 線性載入條：請求超過一下子還沒回來才出現 */
  .load-bar { position: sticky; top: 0; height: 0; z-index: 30; pointer-events: none; }
  .load-bar span {
    position: absolute; left: 0; right: 0; top: 0; height: 4px; overflow: hidden; opacity: 0;
    background: var(--secondary-container); transition: opacity var(--duration-short4) var(--easing-standard);
  }
  .load-bar.on span { opacity: 1; }
  .load-bar span::before, .load-bar span::after {
    content: ""; position: absolute; top: 0; bottom: 0; border-radius: var(--radius-xs); background: var(--primary);
  }
  .load-bar.on span::before { animation: lb-a 2s cubic-bezier(.65, .815, .735, .395) infinite; }
  .load-bar.on span::after { animation: lb-b 2s var(--ease-out) 1.15s infinite; }
  @keyframes lb-a { 0% { left: -35%; right: 100%; } 60%, 100% { left: 100%; right: -90%; } }
  @keyframes lb-b { 0% { left: -200%; right: 100%; } 60%, 100% { left: 107%; right: -8%; } }

  /* 「每次先問我」：掃描到新照片時的詢問列（和 Snackbar 同樣式，不會自己消失） */
  .ask {
    position: fixed; left: 50%; transform: translateX(-50%); bottom: calc(24px + env(safe-area-inset-bottom)); z-index: 290;
    display: flex; align-items: center; gap: 4px; flex-wrap: wrap; width: min(600px, calc(100% - 32px)); min-height: 48px;
    padding: 6px 8px 6px 16px; border-radius: var(--corner-extra-small); background: var(--inverse-surface); color: var(--inverse-on-surface);
    font-size: var(--text-body); line-height: 20px; animation: m3-enter var(--duration-medium2) var(--easing-emphasized-decelerate);
  }
  .ask .msg { flex: 1; min-width: 200px; padding: 8px 0; }
  .ask .act { border: 0; background: none; color: var(--inverse-primary); font-weight: 500; padding: 10px 12px; border-radius: var(--corner-full); cursor: pointer; }
  .ask .act:hover { background: color-mix(in srgb, var(--inverse-primary) 8%, transparent); }
</style>
