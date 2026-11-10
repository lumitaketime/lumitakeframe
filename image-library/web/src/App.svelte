<script>
  import { onMount, tick } from "svelte";
  import { fade, fly } from "svelte/transition";
  import { cubicOut } from "svelte/easing";
  import Icon from "./components/Icon.svelte";
  import Viewer from "./components/Viewer.svelte";
  import SelectionBar from "./components/SelectionBar.svelte";
  import Toasts from "./components/Toasts.svelte";
  import Dialogs from "./components/Dialogs.svelte";
  import JobIndicator from "./components/JobIndicator.svelte";
  import Onboarding from "./components/Onboarding.svelte";
  import SearchBox from "./components/SearchBox.svelte";
  import FilterButton from "./components/FilterButton.svelte";
  import { filterUI } from "./lib/filter.svelte.js";
  import Timeline from "./pages/Timeline.svelte";
  import Explore from "./pages/Explore.svelte";
  import Search from "./pages/Search.svelte";
  import Folders from "./pages/Folders.svelte";
  import Albums from "./pages/Albums.svelte";
  import Album from "./pages/Album.svelte";
  import People from "./pages/People.svelte";
  import Duplicates from "./pages/Duplicates.svelte";
  import Tools from "./pages/Tools.svelte";
  import Keywords from "./pages/Keywords.svelte";
  import SmartAlbum from "./pages/SmartAlbum.svelte";
  import Person from "./pages/Person.svelte";
  import Settings from "./pages/Settings.svelte";
  import Login from "./pages/Login.svelte";
  import { api } from "./lib/api.js";
  import { app, selection, viewer, refresh, toast } from "./lib/state.svelte.js";
  import { route, navigate, link } from "./lib/router.svelte.js";
  import { TOOLS, pinnedKeys, toolByKey } from "./lib/toolkit.js";
  import { drag, unpin } from "./lib/pin.svelte.js";
  import { undoLast } from "./lib/undo.svelte.js";
  import { fadeThrough } from "./lib/motion.js";
  // 設定的各分類是同一頁的不同區塊：換分類不重建整頁（避免閃一下、狀態卡重新載入）
  const routeKey = $derived(route.path.startsWith("/settings") ? "/settings" : route.path);
  import { rubberBand, installShake } from "./lib/alive.js";
  import {
    mdiImageMultipleOutline, mdiCompassOutline, mdiFolderOutline, mdiImageAlbum, mdiHeartOutline,
    mdiVideoOutline, mdiCogOutline, mdiMagnify, mdiClose, mdiHarddisk, mdiContentDuplicate,
    mdiChevronRight, mdiChevronDown, mdiToolboxOutline, mdiMenu, mdiPinOutline, mdiArrowLeft,
    filled,
  } from "./lib/icons.js";

  // 左側選單分組；fixed＝一定顯示，其他可在「設定 → 功能與選單」關掉
  const NAV_GROUPS = [
    { id: "library", label: "圖庫", items: [
      { href: "/", label: "照片", icon: mdiImageMultipleOutline, mobile: true, fixed: true },
      { href: "/explore", label: "探索", icon: mdiCompassOutline, mobile: true },
    ] },
    { id: "organize", label: "整理", items: [
      { href: "/folders", label: "資料夾", icon: mdiFolderOutline, mobile: true, fixed: true },
      { href: "/albums", label: "相簿", icon: mdiImageAlbum, mobile: true, fixed: true },
      { href: "/favorites", label: "我的最愛", icon: mdiHeartOutline },
      { href: "/videos", label: "影片", icon: mdiVideoOutline },
    ] },
    { id: "tools", label: "工具", items: [
      { href: "/tools", label: "整理工具", icon: mdiToolboxOutline },
    ] },
  ];
  const NAV = NAV_GROUPS.flatMap((g) => g.items);
  // 人物、關鍵字整合在「探索」的分頁裡
  const EXPLORE_PAGES = ["/explore", "/people", "/keywords"];

  const hidden = $derived(new Set((app.server?.ui?.nav_hidden || "").split(",").filter(Boolean)));
  const visible = (n) => n.fixed || !hidden.has(n.href);
  const pinned = $derived(pinnedKeys(app.server).map(toolByKey));
  // 「工具」群組：整理工具＋使用者拖進來的常用工具
  function groupItems(g) {
    const items = g.items.filter(visible);
    return g.id === "tools" ? [...items, ...pinned.map((t) => ({ ...t, pinned: true }))] : items;
  }

  // 三種版面（像 Google 相簿）：
  // 電腦（≥1200）：完整選單，≡ 可收成圖示列；
  // 平板（841–1199）：只有圖示的窄欄，≡ 從左邊滑出完整選單；
  // 手機（≤840）：選單收起，下方保留小圖示分頁，≡ 滑出和平板相同的選單。
  let rail = $state(readRail());
  let drawer = $state(false);
  let winW = $state(typeof window === "undefined" ? 1400 : window.innerWidth);
  const wide = $derived(winW >= 1200);
  const narrow = $derived(winW <= 840);
  const showRail = $derived(!narrow && (!wide || rail));
  let searchOpen = $state(false);
  function readRail() {
    try {
      return localStorage.getItem("navRail") === "1";
    } catch {
      return false;
    }
  }
  function toggleNav() {
    if (!wide) {
      drawer = !drawer;
      return;
    }
    animateNav(() => (rail = !rail));
    try {
      localStorage.setItem("navRail", rail ? "1" : "0");
    } catch {
      /* 只影響這次 */
    }
  }

  // 收合／展開的動畫：版面只重算一次，內容區用 transform 滑過去，選單用 clip-path 展開，不會掉幀
  async function animateNav(change) {
    const main = document.querySelector("main.scroll-area");
    const side = document.querySelector("nav.sidebar:not(.drawer)");
    const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
    const before = main?.getBoundingClientRect().left ?? 0;
    const sideBefore = side?.getBoundingClientRect().width ?? 0;
    change();
    await tick();
    if (reduce || !main || !side) return;
    const after = main.getBoundingClientRect().left;
    const sideAfter = side.getBoundingClientRect().width;
    const opts = { duration: 280, easing: "cubic-bezier(0.2, 0, 0, 1)" };
    main.animate([{ transform: `translateX(${before - after}px)` }, { transform: "none" }], opts);
    if (sideAfter > sideBefore) {
      side.animate([{ clipPath: `inset(0 ${sideAfter - sideBefore}px 0 0)` }, { clipPath: "inset(0 0 0 0)" }], opts);
    } else {
      side.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 200, easing: "linear" });
    }
  }
  // 換版面（電腦／平板／手機）時收起抽屜與展開的搜尋，避免留下看不見的遮罩擋住畫面
  const mode = $derived(wide ? "desktop" : narrow ? "phone" : "tablet");
  let lastMode = "";
  $effect(() => {
    const m = mode;
    if (lastMode && m !== lastMode) {
      drawer = false;
      searchOpen = false;
    }
    lastMode = m;
  });
  // 換頁後收起抽屜
  $effect(() => {
    route.path;
    drawer = false;
  });
  let collapsed = $state(readCollapsed());

  function readCollapsed() {
    try {
      return new Set(JSON.parse(localStorage.getItem("navCollapsed") || "[]"));
    } catch {
      return new Set();
    }
  }
  function toggleGroup(id) {
    const next = new Set(collapsed);
    next.has(id) ? next.delete(id) : next.add(id);
    collapsed = next;
    try {
      localStorage.setItem("navCollapsed", JSON.stringify([...next]));
    } catch {
      /* 只影響這次 */
    }
  }

  let lastFinished = null;
  let wasRunning = false;
  let lastTotal = null;
  let lastRefresh = 0;
  let timer;

  const seg = $derived(route.path.split("/").filter(Boolean));
  const page = $derived(seg[0] || "");
  // 第一次在這台 Mac 上開啟時顯示設定引導（手機、平板不顯示）
  const welcome = $derived(page === "welcome" || (app.server?.local && app.server?.ui?.onboarded === 0 && page !== "settings"));

  function active(href) {
    if (href === "/") return page === "";
    if (href === "/tools") return (page === "tools" || page === "duplicates") && !pinned.some((t) => t.href === route.path);
    if (href === "/explore") return EXPLORE_PAGES.some((p) => route.path === p || route.path.startsWith(p + "/"));
    return route.path === href || route.path.startsWith(href + "/");
  }

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

<svelte:window bind:innerWidth={winW} onkeydown={(e) => {
  if ((e.metaKey || e.ctrlKey) && !e.shiftKey && !e.altKey && e.key.toLowerCase() === "z"
    && !e.target.closest?.("input, textarea, select, [contenteditable]") && !viewer.open) {
    e.preventDefault();
    undoLast();
  }
}} />

{#if !app.authChecked}
  <div class="boot"><span class="spinner"></span></div>
{:else if app.needLogin}
  <Login />
{:else}
  <div class="shell" class:mode-desktop={wide} class:mode-tablet={!wide && !narrow} class:mode-phone={narrow} class:rail={showRail}>
    <header class="topbar">
      <button class="icon-btn menu-btn" onclick={toggleNav} aria-label={!wide ? "打開選單" : rail ? "展開選單" : "收合選單"}
        aria-expanded={!wide ? drawer : !rail} title={!wide ? "選單" : rail ? "展開選單" : "收合選單"}><Icon path={mdiMenu} /></button>
      <a class="brand" href="/" use:link aria-label="Lumitake Library">
        <img src="/icon.svg" alt="" width="32" height="32" />
        <span>Lumitake <b>Library</b></span>
      </a>
      {#if narrow && !searchOpen}<span class="spacer"></span>{/if}
      <SearchBox narrow={winW <= 600} bind:expanded={searchOpen} />
      {#if filterUI.pages && !(searchOpen && winW <= 600)}<FilterButton />{/if}
      <div class="right">
        <JobIndicator />
        <a class="icon-btn" class:active={page === "settings"} href="/settings" use:link aria-label="設定"><Icon path={mdiCogOutline} /></a>
      </div>
    </header>

    {#snippet navContent(isRail)}
      {#each NAV_GROUPS as g (g.id)}
        {@const items = groupItems(g)}
        {@const isTools = g.id === "tools"}
        {@const shut = collapsed.has(g.id) && !(isTools && drag.key)}
        {#if items.length || (isTools && drag.key)}
          <div class="nav-group" class:drop={isTools && drag.key} class:over={isTools && drag.over} data-pin-drop={isTools ? "" : undefined}>
            <button class="group" onclick={() => toggleGroup(g.id)} aria-expanded={!shut}>
              <span>{g.label}</span><Icon path={shut ? mdiChevronRight : mdiChevronDown} size={16} />
            </button>
            {#each items.filter((n) => !shut || active(n.href)) as n (n.href)}
              <a href={n.href} use:link class:active={active(n.href)} class:pinned={n.pinned} title={isRail ? n.label : undefined}>
                <span class="ind"><Icon path={active(n.href) ? filled(n.icon) : n.icon} /></span><span class="lbl">{n.label}</span>
                {#if n.pinned}
                  <button class="unpin" onclick={(e) => { e.preventDefault(); e.stopPropagation(); unpin(n.key); }} aria-label="從側邊欄移除{n.label}" title="從側邊欄移除"><Icon path={mdiClose} size={16} /></button>
                {/if}
              </a>
            {/each}
            {#if isTools && drag.key}
              <div class="drop-hint"><Icon path={mdiPinOutline} size={18} /><span>放開以加入「{toolByKey(drag.key)?.label}」</span></div>
            {/if}
          </div>
        {/if}
      {/each}
      {#if app.server?.favorites?.length}
        <div class="roots-group">
          <button class="group" onclick={() => toggleGroup("favs")} aria-expanded={!collapsed.has("favs")}>
            <span>收藏</span><Icon path={collapsed.has("favs") ? mdiChevronRight : mdiChevronDown} size={16} />
          </button>
          {#each collapsed.has("favs") ? [] : app.server.favorites as f (f.href)}
            {@const on = route.path + (route.query.path ? `?path=${encodeURIComponent(route.query.path)}` : "") === f.href}
            <a href={f.href} use:link class:active={on} title={isRail ? f.name : undefined}>
              <span class="ind"><Icon path={f.kind === "album" ? mdiImageAlbum : on ? filled(mdiFolderOutline) : mdiFolderOutline} /></span><span class="lbl">{f.name}</span>
            </a>
          {/each}
        </div>
      {/if}
      <div class="roots-group">
        <button class="group" onclick={() => toggleGroup("roots")} aria-expanded={!collapsed.has("roots")}>
          <span>資料夾來源</span><Icon path={collapsed.has("roots") ? mdiChevronRight : mdiChevronDown} size={16} />
        </button>
        {#each collapsed.has("roots") ? [] : app.server?.roots || [] as r (r.id)}
          <a href={`/folders/${r.id}`} use:link class:active={route.path === `/folders/${r.id}`} class="root" title={r.path}>
            <span class="ind"><Icon path={mdiHarddisk} /></span><span class="lbl">{r.name}</span>{#if !r.online}<em>未連接</em>{/if}
          </a>
        {/each}
        {#if !collapsed.has("roots")}<a href="/settings/library" use:link class="add-root">+ 加入資料夾</a>{/if}
        {#if app.server}
          <p class="stats">{app.server.stats.photos.toLocaleString()} 張照片 · {app.server.stats.videos.toLocaleString()} 部影片</p>
        {/if}
      </div>
    {/snippet}
    <nav class="sidebar" class:rail={showRail} aria-label="主選單" aria-hidden={narrow} use:rubberBand={{ targets: (n) => [...n.children] }}>
      {@render navContent(showRail)}
    </nav>
    {#if drawer}
      <button class="scrim" onclick={() => (drawer = false)} aria-label="關閉選單"></button>
      <nav class="sidebar drawer" aria-label="主選單" use:rubberBand={{ targets: (n) => [...n.children] }} transition:fly={{ x: -300, duration: 240, opacity: 1, easing: cubicOut }}>
        {@render navContent(false)}
      </nav>
    {/if}

    {#if drag.key}
      {@const t = toolByKey(drag.key)}
      <div class="drag-ghost" class:over={drag.over} style:left="{drag.x}px" style:top="{drag.y}px"><Icon path={t.icon} size={20} />{t.label}</div>
      {#if narrow && !drawer}
        <div class="drop-float" class:over={drag.over} data-pin-drop><Icon path={mdiPinOutline} />放到這裡，加入側邊欄</div>
      {/if}
    {/if}

    <main class="scroll-area" use:rubberBand>
      <div class="load-bar" class:on={app.busy} aria-hidden="true"><span></span></div>
      {#key routeKey}
        <div class="route" in:fadeThrough>
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
          <Folders rootId={seg[1] ? Number(seg[1]) : null} />
        {:else if page === "albums" && seg[1] === "smart" && seg[2]}
          <SmartAlbum id={Number(seg[2])} />
        {:else if page === "keywords"}
          <Keywords />
        {:else if page === "tools"}
          <Tools sub={seg[1] || ""} />
        {:else if page === "duplicates"}
          <Duplicates />
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
          <div class="empty"><h2>找不到頁面</h2><a href="/" use:link>回到照片</a></div>
        {/if}
        </div>
      {/key}
    </main>

    <nav class="bottom" aria-label="主選單">
      {#each NAV.filter((n) => n.mobile && visible(n)) as n (n.href)}
        <a href={n.href} use:link class:active={active(n.href)}><span class="ind"><Icon path={active(n.href) ? filled(n.icon) : n.icon} /></span><span>{n.label}</span></a>
      {/each}
    </nav>
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
  .boot { height: 100vh; display: flex; align-items: center; justify-content: center; color: var(--on-surface-variant); }
  /* 外框（頂欄＋選單）是一層淡色，內容區是另一層、圓角浮在上面，深淺色都看得出分層 */
  .shell {
    --nav-w: var(--sidebar);
    display: grid; height: 100vh; height: 100dvh; background: var(--surface-container);
    grid-template-columns: var(--nav-w) minmax(0, 1fr); grid-template-rows: var(--topbar) minmax(0, 1fr);
    grid-template-areas: "top top" "side main";
  }
  /* 版面由程式依視窗寬度加上 class 決定（不用 :has() 或 CSS 斷點），Safari 縮放來回也不會卡住 */
  .shell.rail { --nav-w: 80px; }
  .topbar {
    grid-area: top; display: flex; align-items: center; gap: 8px; padding: 0 16px 0 12px;
    padding-top: env(safe-area-inset-top); z-index: 20;
  }
  .menu-btn { color: var(--on-surface-variant); flex-shrink: 0; }
  .brand { display: flex; align-items: center; gap: 12px; text-decoration: none; color: var(--on-surface); min-width: calc(var(--sidebar) - 64px); padding-right: 16px; flex-shrink: 0; }
  .brand span { font-size: 22px; line-height: 28px; white-space: nowrap; }
  .brand b { font-weight: 500; color: var(--primary); }
  .right { margin-left: auto; display: flex; align-items: center; gap: 6px; }
  .right .icon-btn { color: var(--on-surface-variant); }

  /* 導覽抽屜：膠囊形指示器從中心展開 */
  .sidebar { grid-area: side; padding: 0 12px 24px; overflow-y: auto; overflow-x: hidden; overscroll-behavior-y: none; display: flex; flex-direction: column; }
  .nav-group, .roots-group { display: flex; flex-direction: column; border-radius: var(--corner-large); }
  .sidebar a {
    position: relative; display: flex; align-items: center; gap: 12px; height: 56px; padding: 0 16px; border-radius: var(--corner-full);
    text-decoration: none; color: var(--on-surface-variant); font-size: 14px; line-height: 20px; font-weight: 500; letter-spacing: 0.1px;
    flex-shrink: 0; isolation: isolate;
  }
  .sidebar .ind { display: flex; }
  .sidebar .lbl { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .sidebar a.active { color: var(--on-secondary-container); }
  .sidebar a.active::after {
    content: ""; position: absolute; inset: 0; border-radius: inherit; background: var(--secondary-container); z-index: -1;
    animation: nav-pill var(--spring-expressive-fast-spatial-duration) var(--spring-expressive-fast-spatial);
  }
  @keyframes nav-pill { from { transform: scaleX(0.3); opacity: 0.4; } }
  .unpin { border: 0; background: none; color: inherit; width: 28px; height: 28px; border-radius: 50%; display: flex; align-items: center; justify-content: center; cursor: pointer; opacity: 0; margin-right: -6px; }
  .sidebar a:hover .unpin, .unpin:focus-visible { opacity: .8; }
  .unpin:hover { background: color-mix(in srgb, currentColor 12%, transparent); opacity: 1; }
  .sidebar .root em { font-style: normal; font-size: 11px; color: var(--error); }
  .add-root { color: var(--on-surface-variant) !important; font-weight: 400 !important; height: 44px !important; }
  .group {
    display: flex; align-items: center; justify-content: space-between; border: 0; background: none; cursor: pointer;
    margin: 12px 0 2px; padding: 8px 16px; font-size: 14px; line-height: 20px; color: var(--on-surface-variant); font-weight: 500; letter-spacing: 0.1px;
    border-radius: var(--corner-full);
    transition: background-color var(--spring-effects-fast-duration) var(--spring-effects-fast);
  }
  .nav-group:first-child .group { margin-top: 4px; }
  .group:hover { background: color-mix(in srgb, var(--on-surface) 8%, transparent); }
  .stats { margin: 12px 16px 0; font-size: 12px; line-height: 16px; color: var(--on-surface-variant); }

  /* 拖曳工具卡片時：「工具」區變成放置區 */
  .nav-group.drop { outline: 2px dashed var(--outline); outline-offset: -2px; background: color-mix(in srgb, var(--primary) 6%, transparent); padding-bottom: 6px;
    transition: background-color var(--spring-effects-fast-duration) var(--spring-effects-fast), outline-color var(--spring-effects-fast-duration) var(--spring-effects-fast); }
  .nav-group.over { outline-color: var(--primary); background: color-mix(in srgb, var(--primary) 14%, transparent); }
  .drop-hint { display: flex; align-items: center; gap: 8px; padding: 8px 16px; font-size: 14px; color: var(--primary); }
  .drag-ghost {
    position: fixed; z-index: 400; pointer-events: none; transform: translate(-50%, -130%); display: flex; align-items: center; gap: 8px;
    padding: 10px 16px; border-radius: var(--corner-full); background: var(--inverse-surface); color: var(--inverse-on-surface);
    font-size: 14px; font-weight: 500; white-space: nowrap;
    animation: m3-pop var(--spring-expressive-fast-spatial-duration) var(--spring-expressive-fast-spatial);
  }
  .drag-ghost.over { background: var(--primary); color: var(--on-primary); }
  .drop-float {
    position: fixed; z-index: 390; left: 12px; top: 50%; transform: translateY(-50%); width: 132px; padding: 24px 12px; text-align: center;
    display: flex; flex-direction: column; align-items: center; gap: 8px; border-radius: var(--corner-extra-large);
    border: 2px dashed var(--outline); background: var(--surface-container-high); color: var(--on-surface-variant); font-size: 14px;
    animation: m3-enter var(--duration-medium2) var(--easing-emphasized-decelerate);
  }
  .drop-float.over { border-color: var(--primary); color: var(--primary); background: var(--primary-container); }

  /* 「每次先問我」：掃描到新照片時的詢問列（和 Snackbar 同樣式，不會自己消失） */
  .ask {
    position: fixed; left: 50%; transform: translateX(-50%); bottom: calc(24px + env(safe-area-inset-bottom)); z-index: 290;
    display: flex; align-items: center; gap: 4px; flex-wrap: wrap; width: min(600px, calc(100% - 32px)); min-height: 48px;
    padding: 6px 8px 6px 16px; border-radius: var(--corner-extra-small); background: var(--inverse-surface); color: var(--inverse-on-surface);
    font-size: 14px; line-height: 20px; animation: m3-enter var(--duration-medium2) var(--easing-emphasized-decelerate);
  }
  .ask .msg { flex: 1; min-width: 200px; padding: 8px 0; }
  .ask .act { border: 0; background: none; color: var(--inverse-primary); font-weight: 500; padding: 10px 12px; border-radius: var(--corner-full); cursor: pointer; }
  .ask .act:hover { background: color-mix(in srgb, var(--inverse-primary) 8%, transparent); }
  :global(.shell.mode-phone) ~ .ask { bottom: calc(96px + env(safe-area-inset-bottom)); }

  /* 平板：只有圖示的窄欄（像 Google 相簿）——圓形指示、分組之間一條短線 */
  .sidebar.rail { padding: 0 12px 24px; align-items: center; }
  .sidebar.rail .group, .sidebar.rail .roots-group, .sidebar.rail .unpin, .sidebar.rail .drop-hint, .sidebar.rail .lbl { display: none; }
  .sidebar.rail .nav-group { align-items: center; gap: 4px; border-radius: 0; width: 100%; }
  .sidebar.rail .nav-group + .nav-group { margin-top: 12px; padding-top: 12px; position: relative; }
  .sidebar.rail .nav-group + .nav-group::before { content: ""; position: absolute; top: 0; left: 50%; width: 32px; height: 1px; margin-left: -16px; background: var(--outline-variant); }
  .sidebar.rail .nav-group:first-child { margin-top: 4px; }
  .sidebar.rail a { width: 56px; height: 56px; padding: 0; justify-content: center; border-radius: 50%; }
  .sidebar.rail a.active::after { animation: none; }
  .sidebar.rail a:hover:not(.active)::after { content: ""; position: absolute; inset: 0; border-radius: inherit; background: color-mix(in srgb, var(--on-surface) 8%, transparent); z-index: -1; }
  .sidebar.rail .nav-group.drop { outline: 2px dashed var(--outline); outline-offset: 2px; border-radius: var(--corner-extra-large); }

  main {
    grid-area: main; position: relative; overscroll-behavior-y: none; /* 到底的回彈由 rubberBand 處理，避免和系統回彈疊在一起 */ background: var(--surface); border-radius: var(--corner-extra-large) var(--corner-extra-large) 0 0;
    margin-right: 12px;
  }
  .route { min-height: 100%; }
  /* 頂端的 M3 線性載入條：請求超過一下子還沒回來才出現 */
  .load-bar { position: sticky; top: 0; height: 0; z-index: 30; }
  .load-bar span {
    position: absolute; left: 0; right: 0; top: 0; height: 4px; overflow: hidden; opacity: 0;
    background: var(--secondary-container); transition: opacity var(--duration-short4) var(--easing-standard);
  }
  .load-bar.on span { opacity: 1; }
  .load-bar span::before, .load-bar span::after {
    content: ""; position: absolute; top: 0; bottom: 0; border-radius: 2px; background: var(--primary);
  }
  .load-bar.on span::before { animation: lb-a 2s cubic-bezier(.65, .815, .735, .395) infinite; }
  .load-bar.on span::after { animation: lb-b 2s cubic-bezier(.165, .84, .44, 1) 1.15s infinite; }
  @keyframes lb-a { 0% { left: -35%; right: 100%; } 60%, 100% { left: 100%; right: -90%; } }
  @keyframes lb-b { 0% { left: -200%; right: 100%; } 60%, 100% { left: 107%; right: -8%; } }
  .bottom { display: none; }
  .spacer { flex: 1; }

  /* ≡ 滑出的完整選單（平板、手機相同）：在頂欄下方，和外框同色，不加陰影也不變暗 */
  .scrim { position: fixed; inset: var(--topbar) 0 0 0; z-index: 250; border: 0; padding: 0; background: transparent; cursor: default; }
  .sidebar.drawer {
    position: fixed; z-index: 260; left: 0; top: calc(var(--topbar) + env(safe-area-inset-top)); bottom: 0; width: 280px; max-width: 86vw;
    background: var(--surface-container); padding: 0 12px 24px; will-change: transform;
  }

  /* 手機：側邊欄收起，下方是浮起來的膠囊分頁列 */
  .shell.mode-phone { grid-template-columns: minmax(0, 1fr); grid-template-areas: "top" "main"; }
  .shell.mode-phone .sidebar:not(.drawer) { display: none; }
  .shell.mode-phone .brand { min-width: 0; padding-right: 0; }
  .shell.mode-phone main { margin: 0 8px; }
  .shell.mode-phone .route { padding-bottom: calc(96px + env(safe-area-inset-bottom)); }
  .shell.mode-phone .bottom {
    display: flex; position: fixed; z-index: 30; gap: 4px; padding: 6px;
    left: max(16px, env(safe-area-inset-left)); right: max(16px, env(safe-area-inset-right));
    bottom: calc(12px + env(safe-area-inset-bottom)); height: 68px;
    background: var(--surface-container-high); border: 1px solid var(--outline-variant); border-radius: var(--corner-full);
  }
  .shell.mode-phone .bottom a {
    flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 2px; border-radius: var(--corner-full);
    text-decoration: none; color: var(--on-surface-variant); font-size: 12px; line-height: 16px; font-weight: 500; letter-spacing: 0.3px;
    transition: background-color var(--spring-effects-fast-duration) var(--spring-effects-fast), color var(--spring-effects-fast-duration) var(--spring-effects-fast);
  }
  .shell.mode-phone .bottom .ind { display: flex; align-items: center; justify-content: center; }
  /* M3：選取的膠囊在新項目上由中間展開，圖示換成實心 */
  .shell.mode-phone .bottom a { position: relative; isolation: isolate; }
  .shell.mode-phone .bottom a.active { color: var(--on-secondary-container); }
  .shell.mode-phone .bottom a.active::after {
    content: ""; position: absolute; inset: 0; border-radius: inherit; background: var(--secondary-container); z-index: -1;
    animation: nav-pill var(--spring-expressive-fast-spatial-duration) var(--spring-expressive-fast-spatial);
  }
  .shell.mode-phone .bottom a:active { background: color-mix(in srgb, var(--on-surface) 10%, transparent); }
  @media (max-width: 600px) {
    .topbar { gap: 4px; padding: 0 4px; padding-top: env(safe-area-inset-top); }
    .brand span { font-size: 16px; }
    main { margin: 0; border-radius: var(--corner-large) var(--corner-large) 0 0; }
  }
  @media (max-width: 420px) { .brand span { display: none; } }
</style>
