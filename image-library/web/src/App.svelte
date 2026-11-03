<script>
  import { onMount } from "svelte";
  import Icon from "./components/Icon.svelte";
  import Viewer from "./components/Viewer.svelte";
  import SelectionBar from "./components/SelectionBar.svelte";
  import Toasts from "./components/Toasts.svelte";
  import Dialogs from "./components/Dialogs.svelte";
  import JobIndicator from "./components/JobIndicator.svelte";
  import Timeline from "./pages/Timeline.svelte";
  import Explore from "./pages/Explore.svelte";
  import Search from "./pages/Search.svelte";
  import Folders from "./pages/Folders.svelte";
  import Albums from "./pages/Albums.svelte";
  import Album from "./pages/Album.svelte";
  import MapPage from "./pages/MapPage.svelte";
  import People from "./pages/People.svelte";
  import Duplicates from "./pages/Duplicates.svelte";
  import SmartAlbum from "./pages/SmartAlbum.svelte";
  import Person from "./pages/Person.svelte";
  import Settings from "./pages/Settings.svelte";
  import Login from "./pages/Login.svelte";
  import { api } from "./lib/api.js";
  import { app, selection, viewer, refresh } from "./lib/state.svelte.js";
  import { route, navigate, link } from "./lib/router.svelte.js";
  import {
    mdiImageMultipleOutline, mdiCompassOutline, mdiMapOutline, mdiFolderOutline, mdiImageAlbum, mdiHeartOutline,
    mdiVideoOutline, mdiCogOutline, mdiMagnify, mdiClose, mdiHarddisk, mdiAccountBoxOutline, mdiContentDuplicate,
  } from "./lib/icons.js";

  const NAV = [
    { href: "/", label: "照片", icon: mdiImageMultipleOutline, mobile: true },
    { href: "/explore", label: "探索", icon: mdiCompassOutline, mobile: true },
    { href: "/people", label: "人物", icon: mdiAccountBoxOutline },
    { href: "/map", label: "地圖", icon: mdiMapOutline },
    { href: "/folders", label: "資料夾", icon: mdiFolderOutline, mobile: true },
    { href: "/albums", label: "相簿", icon: mdiImageAlbum, mobile: true },
    { href: "/favorites", label: "我的最愛", icon: mdiHeartOutline },
    { href: "/videos", label: "影片", icon: mdiVideoOutline },
    { href: "/duplicates", label: "重複照片", icon: mdiContentDuplicate },
  ];

  let q = $state(route.query.q || "");
  let lastFinished = null;
  let wasRunning = false;
  let lastTotal = null;
  let lastRefresh = 0;
  let timer;

  const seg = $derived(route.path.split("/").filter(Boolean));
  const page = $derived(seg[0] || "");

  function active(href) {
    if (href === "/") return page === "";
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

  async function poll() {
    clearTimeout(timer);
    try {
      const s = await api("/api/server");
      app.server = s;
      const running = !!s.jobs.current;
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
      {#each NAV as n (n.href)}
        <a href={n.href} use:link class:active={active(n.href)}><Icon path={n.icon} /><span>{n.label}</span></a>
      {/each}
      <div class="divider"></div>
      <p class="side-title">圖庫</p>
      {#each app.server?.roots || [] as r (r.id)}
        <a href={`/folders/${r.id}`} use:link class:active={route.path === `/folders/${r.id}`} class="root" title={r.path}>
          <Icon path={mdiHarddisk} /><span>{r.name}</span>{#if !r.online}<em>未連接</em>{/if}
        </a>
      {/each}
      <a href="/settings" use:link class="add-root">+ 加入資料夾</a>
      {#if app.server}
        <p class="stats">{app.server.stats.photos.toLocaleString()} 張照片 · {app.server.stats.videos.toLocaleString()} 部影片</p>
      {/if}
    </nav>

    <main class="scroll-area">
      {#key route.path}
        {#if page === ""}
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
          <Settings />
        {:else}
          <div class="empty"><h2>找不到頁面</h2><a href="/" use:link>回到照片</a></div>
        {/if}
      {/key}
    </main>

    <nav class="bottom" aria-label="主選單">
      {#each NAV.filter((n) => n.mobile) as n (n.href)}
        <a href={n.href} use:link class:active={active(n.href)}><Icon path={n.icon} /><span>{n.label}</span></a>
      {/each}
    </nav>
  </div>

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
    padding-top: env(safe-area-inset-top); background: var(--bg); border-bottom: 1px solid var(--line); z-index: 20;
  }
  .brand { display: flex; align-items: center; gap: 10px; text-decoration: none; color: var(--text); width: calc(var(--sidebar) - 32px); flex-shrink: 0; }
  .brand span { font-size: 18px; white-space: nowrap; }
  .brand b { font-weight: 700; color: var(--primary); }
  .search {
    flex: 1; max-width: 720px; display: flex; align-items: center; gap: 10px; height: 46px; padding: 0 6px 0 16px;
    background: var(--bg-2); border-radius: 999px; color: var(--muted); border: 1px solid transparent;
  }
  .search:focus-within { background: var(--bg); border-color: var(--primary); box-shadow: var(--shadow); }
  .search input { flex: 1; border: 0; outline: none; background: none; color: var(--text); min-width: 0; font-size: 15px; }
  .search input::-webkit-search-cancel-button { display: none; }
  .clear { width: 34px; height: 34px; }
  .right { margin-left: auto; display: flex; align-items: center; gap: 6px; }
  .right .icon-btn { color: var(--text); }

  .sidebar { grid-area: side; padding: 12px 12px 24px 0; overflow-y: auto; display: flex; flex-direction: column; gap: 2px; }
  .sidebar a {
    display: flex; align-items: center; gap: 18px; padding: 11px 22px; border-radius: 0 999px 999px 0;
    text-decoration: none; color: var(--text); font-size: 15px;
  }
  .sidebar a:hover { background: var(--bg-2); }
  .sidebar a.active { background: var(--primary-soft); color: var(--primary); font-weight: 600; }
  .sidebar .root span { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .sidebar .root em { font-style: normal; font-size: 11px; color: var(--danger); }
  .add-root { color: var(--muted) !important; font-size: 14px !important; }
  .divider { height: 1px; background: var(--line); margin: 12px 0 8px 22px; }
  .side-title { margin: 6px 22px; font-size: 12px; color: var(--muted); font-weight: 600; letter-spacing: .05em; }
  .stats { margin: 12px 22px 0; font-size: 12px; color: var(--muted); }

  main { grid-area: main; position: relative; }
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
      display: flex; position: fixed; left: 0; right: 0; bottom: 0; z-index: 30; background: var(--bg);
      border-top: 1px solid var(--line); padding-bottom: env(safe-area-inset-bottom);
    }
    .bottom a {
      flex: 1; display: flex; flex-direction: column; align-items: center; gap: 2px; padding: 8px 0 6px;
      text-decoration: none; color: var(--muted); font-size: 11px;
    }
    .bottom a.active { color: var(--primary); font-weight: 600; }
  }
</style>
