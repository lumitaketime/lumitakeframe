<script>
  import { onMount } from "svelte";
  import Icon from "./components/Icon.svelte";
  import Viewer from "./components/Viewer.svelte";
  import SelectionBar from "./components/SelectionBar.svelte";
  import Toasts from "./components/Toasts.svelte";
  import Dialogs from "./components/Dialogs.svelte";
  import JobIndicator from "./components/JobIndicator.svelte";
  import Onboarding from "./components/Onboarding.svelte";
  import Timeline from "./pages/Timeline.svelte";
  import Explore from "./pages/Explore.svelte";
  import Search from "./pages/Search.svelte";
  import Folders from "./pages/Folders.svelte";
  import Albums from "./pages/Albums.svelte";
  import Album from "./pages/Album.svelte";
  import MapPage from "./pages/MapPage.svelte";
  import People from "./pages/People.svelte";
  import Duplicates from "./pages/Duplicates.svelte";
  import Tools from "./pages/Tools.svelte";
  import Gear from "./pages/Gear.svelte";
  import Keywords from "./pages/Keywords.svelte";
  import SmartAlbum from "./pages/SmartAlbum.svelte";
  import Person from "./pages/Person.svelte";
  import Settings from "./pages/Settings.svelte";
  import Login from "./pages/Login.svelte";
  import { api } from "./lib/api.js";
  import { app, selection, viewer, refresh, toast } from "./lib/state.svelte.js";
  import { route, navigate, link } from "./lib/router.svelte.js";
  import { fadeThrough } from "./lib/motion.js";
  import {
    mdiImageMultipleOutline, mdiCompassOutline, mdiMapOutline, mdiFolderOutline, mdiImageAlbum, mdiHeartOutline,
    mdiVideoOutline, mdiCogOutline, mdiMagnify, mdiClose, mdiHarddisk, mdiContentDuplicate,
    mdiChevronRight, mdiChevronDown, mdiToolboxOutline,
  } from "./lib/icons.js";

  // 左側選單分組；fixed＝一定顯示，其他可在「設定 → 功能與選單」關掉
  const NAV_GROUPS = [
    { id: "library", label: "圖庫", items: [
      { href: "/", label: "照片", icon: mdiImageMultipleOutline, mobile: true, fixed: true },
      { href: "/explore", label: "探索", icon: mdiCompassOutline, mobile: true },
      { href: "/map", label: "地圖", icon: mdiMapOutline },
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
  // 人物、器材、關鍵字整合在「探索」的分頁裡
  const EXPLORE_PAGES = ["/explore", "/people", "/gear", "/keywords"];

  const hidden = $derived(new Set((app.server?.ui?.nav_hidden || "").split(",").filter(Boolean)));
  const visible = (n) => n.fixed || !hidden.has(n.href);
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

  let q = $state(route.query.q || "");
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
    if (href === "/tools") return page === "tools" || page === "duplicates";
    if (href === "/explore") return EXPLORE_PAGES.some((p) => route.path === p || route.path.startsWith(p + "/"));
    return route.path === href || route.path.startsWith(href + "/");
  }

  $effect(() => {
    q = page === "search" ? route.query.q || "" : "";
  });

  // 換頁時清除選取與情境
  $effect(() => {
    route.path;
    selection.clear();
    app.context = null;
  });

  // 完成通知：使用者自己啟動、會跑一陣子的工作，結束時跳出 Snackbar
  const NOTIFY = new Set(["export", "pull", "face_model", "clip_model", "quality", "dups", "cluster"]);
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

  async function poll() {
    clearTimeout(timer);
    try {
      const s = await api("/api/server");
      app.server = s;
      notifyFinished(s.jobs.recent || []);
      const running = !!s.jobs.running;
      const fin = s.jobs.last?.finished_at;
      const total = s.stats.images;
      if ((wasRunning && !running) || (fin && lastFinished && fin !== lastFinished)) {
        refresh();
      } else if (running && lastTotal !== null && total !== lastTotal && Date.now() - lastRefresh > 5000) {
        // 掃描途中照片數變了：讓新照片陸續出現
        lastRefresh = Date.now();
        refresh();
      }
      lastTotal = total;
      wasRunning = running;
      lastFinished = fin || lastFinished;
      timer = setTimeout(poll, running ? 1500 : 12000);
    } catch {
      timer = setTimeout(poll, 5000);
    }
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
    return () => clearTimeout(timer);
  });

  $effect(() => {
    // 登入成功後開始輪詢
    if (app.authChecked && !app.needLogin && !app.server) poll();
  });

  // 頁面上的動作（例如換相簿）會呼叫 refresh()，順便更新統計
  $effect(() => {
    if (app.refreshKey) api("/api/server").then((s) => (app.server = s)).catch(() => {});
  });

  function submit(e) {
    e.preventDefault();
    const text = q.trim();
    navigate(text ? `/search?q=${encodeURIComponent(text)}` : "/search");
    document.activeElement?.blur?.();
  }
</script>

{#if !app.authChecked}
  <div class="boot"><span class="spinner"></span></div>
{:else if app.needLogin}
  <Login />
{:else}
  <div class="shell">
    <header class="topbar">
      <a class="brand" href="/" use:link aria-label="Lumitake Library">
        <img src="/icon.svg" alt="" width="32" height="32" />
        <span>Lumitake <b>Library</b></span>
      </a>
      <form class="search" onsubmit={submit} role="search">
        <Icon path={mdiMagnify} />
        <input bind:value={q} type="search" placeholder="搜尋照片、地點、物品、文字…" aria-label="搜尋" enterkeyhint="search" />
        {#if q}<button type="button" class="icon-btn clear" onclick={() => (q = "")} aria-label="清除"><Icon path={mdiClose} size={20} /></button>{/if}
      </form>
      <div class="right">
        <JobIndicator />
        <a class="icon-btn" class:active={page === "settings"} href="/settings" use:link aria-label="設定"><Icon path={mdiCogOutline} /></a>
      </div>
    </header>

    <nav class="sidebar" aria-label="主選單">
      {#each NAV_GROUPS as g (g.id)}
        {@const items = g.items.filter(visible)}
        {#if items.length}
          <button class="group" onclick={() => toggleGroup(g.id)} aria-expanded={!collapsed.has(g.id)}>
            <span>{g.label}</span><Icon path={collapsed.has(g.id) ? mdiChevronRight : mdiChevronDown} size={16} />
          </button>
          {#each items.filter((n) => !collapsed.has(g.id) || active(n.href)) as n (n.href)}
            <a href={n.href} use:link class:active={active(n.href)}><Icon path={n.icon} /><span>{n.label}</span></a>
          {/each}
        {/if}
      {/each}
      <button class="group" onclick={() => toggleGroup("roots")} aria-expanded={!collapsed.has("roots")}>
        <span>資料夾來源</span><Icon path={collapsed.has("roots") ? mdiChevronRight : mdiChevronDown} size={16} />
      </button>
      {#each collapsed.has("roots") ? [] : app.server?.roots || [] as r (r.id)}
        <a href={`/folders/${r.id}`} use:link class:active={route.path === `/folders/${r.id}`} class="root" title={r.path}>
          <Icon path={mdiHarddisk} /><span>{r.name}</span>{#if !r.online}<em>未連接</em>{/if}
        </a>
      {/each}
      {#if !collapsed.has("roots")}<a href="/settings/library" use:link class="add-root">+ 加入資料夾</a>{/if}
      {#if app.server}
        <p class="stats">{app.server.stats.photos.toLocaleString()} 張照片 · {app.server.stats.videos.toLocaleString()} 部影片</p>
      {/if}
    </nav>

    <main class="scroll-area">
      {#key route.path}
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
        {:else if page === "gear"}
          <Gear />
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
        {:else if page === "map"}
          <MapPage />
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
        <a href={n.href} use:link class:active={active(n.href)}><span class="ind"><Icon path={n.icon} /></span><span>{n.label}</span></a>
      {/each}
    </nav>
  </div>

  {#if welcome}<Onboarding startStep={route.query.step || ""} />{/if}
  {#if selection.size}<SelectionBar />{/if}
  {#if viewer.open}<Viewer />{/if}
  <Dialogs />
{/if}
<Toasts />

<style>
  .boot { height: 100vh; display: flex; align-items: center; justify-content: center; color: var(--muted); }
  .shell {
    display: grid; height: 100vh; height: 100dvh;
    grid-template-columns: var(--sidebar) 1fr; grid-template-rows: var(--topbar) 1fr;
    grid-template-areas: "top top" "side main";
  }
  .topbar {
    grid-area: top; display: flex; align-items: center; gap: 16px; padding: 0 16px;
    padding-top: env(safe-area-inset-top); background: var(--surface); z-index: 20;
  }
  .brand { display: flex; align-items: center; gap: 12px; text-decoration: none; color: var(--on-surface); width: calc(var(--sidebar) - 32px); flex-shrink: 0; }
  .brand span { font-size: 22px; line-height: 28px; white-space: nowrap; }
  .brand b { font-weight: 500; color: var(--primary); }
  .search {
    flex: 1; max-width: 720px; display: flex; align-items: center; gap: 12px; height: 48px; padding: 0 6px 0 16px;
    background: var(--surface-container-high); border-radius: var(--corner-full); color: var(--on-surface-variant);
    transition: background-color var(--spring-effects-default-duration) var(--spring-effects-default),
      box-shadow var(--spring-effects-default-duration) var(--spring-effects-default);
  }
  .search:hover { background: color-mix(in srgb, var(--on-surface) 8%, var(--surface-container-high)); }
  .search:focus-within { background: var(--surface-container-highest); box-shadow: var(--elevation-level2); }
  .search input { flex: 1; border: 0; outline: none; background: none; color: var(--on-surface); min-width: 0; font-size: 16px; line-height: 24px; letter-spacing: 0.5px; }
  .search input::placeholder { color: var(--on-surface-variant); }
  .search input::-webkit-search-cancel-button { display: none; }
  .clear { width: 36px; height: 36px; }
  .right { margin-left: auto; display: flex; align-items: center; gap: 6px; }
  .right .icon-btn { color: var(--on-surface-variant); }

  /* 導覽抽屜：膠囊形指示器從中心展開 */
  .sidebar { grid-area: side; padding: 8px 12px 24px; overflow-y: auto; display: flex; flex-direction: column; gap: 0; }
  .sidebar a {
    display: flex; align-items: center; gap: 12px; height: 56px; padding: 0 16px 0 16px; border-radius: var(--corner-full);
    text-decoration: none; color: var(--on-surface-variant); font-size: 14px; line-height: 20px; font-weight: 500; letter-spacing: 0.1px;
    flex-shrink: 0;
  }
  .sidebar a.active { color: var(--on-secondary-container); }
  .sidebar a.active::after {
    content: ""; position: absolute; inset: 0; border-radius: inherit; background: var(--secondary-container); z-index: -1;
    animation: nav-pill var(--spring-expressive-fast-spatial-duration) var(--spring-expressive-fast-spatial);
  }
  @keyframes nav-pill { from { transform: scaleX(0.3); opacity: 0.4; } }
  .sidebar .root span { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .sidebar .root em { font-style: normal; font-size: 11px; color: var(--error); }
  .add-root { color: var(--on-surface-variant) !important; font-weight: 400 !important; height: 44px !important; }
  .group {
    display: flex; align-items: center; justify-content: space-between; border: 0; background: none; cursor: pointer;
    margin: 12px 0 2px; padding: 8px 16px; font-size: 14px; line-height: 20px; color: var(--on-surface-variant); font-weight: 500; letter-spacing: 0.1px;
    border-radius: var(--corner-full);
    transition: background-color var(--spring-effects-fast-duration) var(--spring-effects-fast);
  }
  .group:first-child { margin-top: 0; }
  .group:hover { background: color-mix(in srgb, var(--on-surface) 8%, transparent); }
  .group :global(svg) { transition: transform var(--spring-standard-fast-spatial-duration) var(--spring-standard-fast-spatial); }
  .stats { margin: 12px 16px 0; font-size: 12px; line-height: 16px; color: var(--on-surface-variant); }

  main { grid-area: main; position: relative; background: var(--surface); }
  .route { min-height: 100%; }
  .bottom { display: none; }

  @media (max-width: 900px) {
    .shell { grid-template-columns: 1fr; grid-template-areas: "top" "main"; }
    .sidebar { display: none; }
    .brand { width: auto; }
    .brand span { display: none; }
  }
  @media (max-width: 760px) {
    .topbar { gap: 8px; padding: 0 8px; padding-top: env(safe-area-inset-top); }
    .search { height: 42px; }
    .bottom {
      display: flex; position: fixed; left: 0; right: 0; bottom: 0; z-index: 30; background: var(--surface-container);
      padding-bottom: env(safe-area-inset-bottom); height: calc(80px + env(safe-area-inset-bottom));
    }
    .bottom a {
      flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 4px;
      text-decoration: none; color: var(--on-surface-variant); font-size: 12px; line-height: 16px; font-weight: 500; letter-spacing: 0.5px;
    }
    .bottom .ind { position: relative; display: flex; align-items: center; justify-content: center; width: 64px; height: 32px; border-radius: var(--corner-full); }
    .bottom a.active { color: var(--on-surface); }
    .bottom a.active .ind { color: var(--on-secondary-container); background: var(--secondary-container);
      animation: nav-pill var(--spring-expressive-fast-spatial-duration) var(--spring-expressive-fast-spatial); }
  }
</style>
