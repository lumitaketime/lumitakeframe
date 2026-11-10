<script>
  /**
   * 頂欄搜尋框＋建議面板（參考 Google 相簿）：
   * - 還沒輸入：最近的搜尋、我的最愛／影片捷徑、常出現的人物頭像
   * - 輸入第一個字起：人物、相簿、地點、關鍵字、資料夾，開頭相符的排前面
   * 上下鍵選擇、Enter 開啟、Esc 關閉。
   */
  import Icon from "./Icon.svelte";
  import { api, thumbUrl } from "../lib/api.js";
  import { navigate, route } from "../lib/router.svelte.js";
  import { app } from "../lib/state.svelte.js";
  import { routeScope, searchHref } from "../lib/scope.js";
  import {
    mdiMagnify, mdiClose, mdiArrowLeft, mdiHistory, mdiHeartOutline, mdiVideoOutline, mdiMapMarkerOutline, mdiPound,
    mdiFolderOutline, mdiImageAlbum, mdiArrowRight, mdiStarOutline,
  } from "../lib/icons.js";

  let { narrow = false, expanded = $bindable(false) } = $props();

  let q = $state("");
  let open = $state(false);
  let sugg = $state(null);
  let active = $state(-1);
  let recent = $state(readRecent());
  let input = $state();
  let root = $state();
  let timer;
  let seq = 0;

  const page = $derived(route.path.split("/").filter(Boolean)[0] || "");
  $effect(() => {
    q = page === "search" ? route.query.q || "" : "";
  });

  // 搜尋範圍：在資料夾、相簿等頁面預設只搜尋這一頁，可切換成全部圖庫
  const here = $derived(routeScope(route, app.server));
  let wholeLibrary = $state(false);
  $effect(() => {
    route.path;
    wholeLibrary = false;
  });
  const scope = $derived(here && !wholeLibrary ? here : null);

  function readRecent() {
    try {
      return JSON.parse(localStorage.getItem("recentSearches") || "[]").slice(0, 6);
    } catch {
      return [];
    }
  }
  function remember(text) {
    recent = [text, ...recent.filter((r) => r !== text)].slice(0, 6);
    try {
      localStorage.setItem("recentSearches", JSON.stringify(recent));
    } catch {
      /* 只影響這次 */
    }
  }
  function forget(text) {
    recent = recent.filter((r) => r !== text);
    try {
      localStorage.setItem("recentSearches", JSON.stringify(recent));
    } catch {
      /* 只影響這次 */
    }
  }

  function load() {
    clearTimeout(timer);
    const text = q.trim();
    const mine = ++seq;
    timer = setTimeout(async () => {
      try {
        const data = await api("/api/search/suggest", { params: { q: text } });
        if (mine === seq) {
          sugg = data;
          active = -1;
        }
      } catch {
        /* 建議失敗不影響搜尋 */
      }
    }, text ? 60 : 0);
  }

  function focus() {
    open = true;
    load();
  }

  // 建議清單攤平成一列，方便上下鍵移動
  const items = $derived.by(() => {
    const text = q.trim();
    const out = [];
    if (!text) {
      for (const r of recent) out.push({ kind: "recent", label: r, run: () => go(r) });
      out.push({ kind: "link", label: "我的最愛", icon: mdiHeartOutline, run: () => to("/favorites") });
      out.push({ kind: "link", label: "影片", icon: mdiVideoOutline, run: () => to("/videos") });
      out.push({ kind: "link", label: "五星作品", icon: mdiStarOutline, run: () => go("rating:5") });
      return out;
    }
    out.push({ kind: "query", label: text, run: () => go(text) });
    if (!sugg) return out;
    for (const p of sugg.people) out.push({ kind: "person", label: p.name, sub: `人物 · ${p.n} 張`, img: `/api/faces/${p.cover}/thumb`, run: () => to(`/people/${p.id}`) });
    for (const a of sugg.albums) out.push({ kind: "album", label: a.name, sub: `相簿 · ${a.n} 張`, img: a.cover ? thumbUrl({ id: a.cover }) : null, icon: mdiImageAlbum, run: () => to(`/albums/${a.id}`) });
    for (const p of sugg.places) out.push({ kind: "place", label: p.name, sub: `地點 · ${p.n} 張`, icon: mdiMapMarkerOutline, run: () => go(`place:${p.name}`) });
    for (const t of sugg.tags) out.push({ kind: "tag", label: t.name, sub: `關鍵字 · ${t.n} 張`, icon: mdiPound, run: () => go(t.name) });
    for (const f of sugg.folders) out.push({ kind: "folder", label: f.name, sub: `資料夾 · ${f.path}`, icon: mdiFolderOutline, run: () => to(`/folders/${f.root_id}?path=${encodeURIComponent(f.path)}`) });
    return out;
  });
  const people = $derived(!q.trim() && sugg?.people?.length ? sugg.people.slice(0, 6) : []);

  function close() {
    open = false;
    active = -1;
    if (narrow) expanded = false;
    input?.blur();
  }
  function go(text) {
    remember(text);
    navigate(searchHref(text, scope));
    close();
  }
  function to(href) {
    if (q.trim()) remember(q.trim());
    navigate(href);
    close();
  }

  function submit(e) {
    e.preventDefault();
    if (active >= 0 && items[active]) return items[active].run();
    const text = q.trim();
    if (text) go(text);
    else to("/search");
  }

  function onkey(e) {
    if (e.isComposing) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      open = true;
      active = Math.min(items.length - 1, active + 1);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      active = Math.max(-1, active - 1);
    } else if (e.key === "Escape") {
      e.preventDefault();
      close();
    }
  }

  function outside(e) {
    if (open && root && !root.contains(e.target)) {
      open = false;
      if (narrow && !q.trim()) expanded = false;
    }
  }

  // 把符合的字加粗
  function parts(label) {
    const text = q.trim().toLowerCase();
    const i = text ? label.toLowerCase().indexOf(text) : -1;
    return i < 0 ? [label, "", ""] : [label.slice(0, i), label.slice(i, i + text.length), label.slice(i + text.length)];
  }

  export async function openSearch() {
    expanded = true;
    open = true;
    await Promise.resolve();
    input?.focus();
    load();
  }
</script>

<svelte:window onpointerdown={outside} />

<div class="sb" class:collapsed={narrow && !expanded} class:expanded={narrow && expanded} class:open={open && (items.length || people.length || here)} bind:this={root}>
  {#if narrow && !expanded}
    <button type="button" class="icon-btn" onclick={openSearch} aria-label="搜尋"><Icon path={mdiMagnify} /></button>
  {:else}
    <form class="field" onsubmit={submit} role="search">
      {#if narrow || open}
        <button type="button" class="icon-btn lead" onclick={close} aria-label="關閉搜尋"><Icon path={mdiArrowLeft} /></button>
      {:else}
        <span class="lead-icon"><Icon path={mdiMagnify} /></span>
      {/if}
      <input
        bind:this={input}
        bind:value={q}
        onfocus={focus}
        oninput={() => { open = true; load(); }}
        onkeydown={onkey}
        type="search"
        placeholder={scope ? `在「${scope.label}」中搜尋…` : "搜尋照片、人物、地點、物品、文字…"}
        aria-label="搜尋"
        aria-expanded={open}
        aria-controls="search-suggestions"
        aria-activedescendant={active >= 0 ? `sugg-${active}` : undefined}
        role="combobox"
        aria-autocomplete="list"
        autocomplete="off"
        enterkeyhint="search"
      />
      {#if q}<button type="button" class="icon-btn clear" onclick={() => { q = ""; input?.focus(); load(); }} aria-label="清除"><Icon path={mdiClose} size={20} /></button>{/if}
    </form>
    {#if open && (items.length || people.length || here)}
      <div class="panel" id="search-suggestions" role="listbox" aria-label="搜尋建議">
        {#if here}
          <div class="scope" role="radiogroup" aria-label="搜尋範圍">
            <span>搜尋範圍</span>
            <button type="button" class="chip" class:on={!wholeLibrary} role="radio" aria-checked={!wholeLibrary} onclick={() => { wholeLibrary = false; input?.focus(); }}>{here.label}</button>
            <button type="button" class="chip" class:on={wholeLibrary} role="radio" aria-checked={wholeLibrary} onclick={() => { wholeLibrary = true; input?.focus(); }}>全部圖庫</button>
          </div>
        {/if}
        {#each items as it, i (it.kind + it.label + i)}
          {#if (i > 0 && items[i - 1].kind === "recent" && it.kind !== "recent") || (i > 0 && items[i - 1].kind === "query")}<div class="divider"></div>{/if}
          {@const [a, b, c] = parts(it.label)}
          <div
            id={`sugg-${i}`}
            class="row"
            class:on={active === i}
            role="option"
            tabindex="-1"
            aria-selected={active === i}
            onpointerenter={() => (active = i)}
            onclick={it.run}
            onkeydown={(e) => e.key === "Enter" && it.run()}
          >
            {#if it.img}
              <span class="av" class:round={it.kind === "person"}>{it.label.slice(0, 1)}<img src={it.img} alt="" onerror={(e) => e.currentTarget.remove()} /></span>
            {:else}
              <span class="ic"><Icon path={it.kind === "recent" ? mdiHistory : it.kind === "query" ? mdiMagnify : it.icon} /></span>
            {/if}
            <span class="txt">
              <span class="lbl">{a}<b>{b}</b>{c}</span>
              {#if it.sub}<span class="sub">{it.sub}</span>{/if}
            </span>
            {#if it.kind === "recent"}
              <button class="icon-btn x" onclick={(e) => { e.stopPropagation(); forget(it.label); }} aria-label="移除 {it.label}"><Icon path={mdiClose} size={18} /></button>
            {/if}
          </div>
        {/each}
        {#if people.length}
          <div class="divider"></div>
          <div class="people">
            {#each people as p (p.id)}
              <button class="person" onclick={() => to(`/people/${p.id}`)} title={p.name}>
                <span class="pav">{p.name.slice(0, 1)}<img src={`/api/faces/${p.cover}/thumb`} alt="" onerror={(e) => e.currentTarget.remove()} /></span>
                <span>{p.name}</span>
              </button>
            {/each}
          </div>
          <button class="all" onclick={() => to("/people")}><Icon path={mdiArrowRight} size={18} />查看所有人物</button>
        {/if}
      </div>
    {/if}
  {/if}
</div>

<style>
  .sb { position: relative; flex: 1; max-width: 720px; min-width: 0; }
  .sb.collapsed { flex: 0 0 auto; }
  .field {
    display: flex; align-items: center; gap: 4px; height: 48px; padding: 0 4px; border-radius: var(--corner-full);
    background: var(--surface-container-high); color: var(--on-surface-variant);
    transition: background-color var(--spring-effects-default-duration) var(--spring-effects-default);
  }
  .field:hover { background: var(--surface-container-highest); }
  .sb.open .field { background: var(--surface-container-highest); border-radius: var(--corner-extra-large) var(--corner-extra-large) 0 0; }
  .lead-icon { width: 40px; display: flex; justify-content: center; }
  .lead { color: var(--on-surface-variant); }
  .field input { flex: 1; border: 0; outline: none; background: none; color: var(--on-surface); min-width: 0; font-size: 16px; line-height: 24px; }
  .field input::placeholder { color: var(--on-surface-variant); }
  .field input::-webkit-search-cancel-button { display: none; }
  .clear { width: 36px; height: 36px; color: var(--on-surface-variant); }
  .panel {
    position: absolute; left: 0; right: 0; top: 48px; z-index: 60; max-height: min(70vh, 560px); overflow-y: auto;
    background: var(--surface-container-highest); border-radius: 0 0 var(--corner-extra-large) var(--corner-extra-large);
    padding: 0 0 12px; border-top: 1px solid var(--outline-variant);
  }
  .row { display: flex; align-items: center; gap: 16px; min-height: 56px; padding: 4px 16px 4px 20px; cursor: pointer; color: var(--on-surface); }
  .row.on { background: color-mix(in srgb, var(--on-surface) 8%, transparent); }
  .ic { width: 24px; display: flex; justify-content: center; color: var(--on-surface-variant); flex-shrink: 0; }
  .av, .pav {
    position: relative; flex-shrink: 0; overflow: hidden; display: flex; align-items: center; justify-content: center;
    background: var(--secondary-container); color: var(--on-secondary-container); font-weight: 500;
  }
  .av { width: 40px; height: 40px; border-radius: var(--corner-small); margin-left: -8px; font-size: 16px; }
  .av img, .pav img { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; }
  .pav { width: 64px; height: 64px; border-radius: 50%; font-size: 24px; }
  .av.round { border-radius: 50%; }
  .txt { flex: 1; min-width: 0; display: flex; flex-direction: column; }
  .lbl { font-size: 16px; line-height: 24px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .lbl b { font-weight: 700; }
  .sub { font-size: 12px; line-height: 16px; color: var(--on-surface-variant); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .x { width: 32px; height: 32px; color: var(--on-surface-variant); }
  .scope { display: flex; align-items: center; gap: 8px; padding: 12px 20px 8px; flex-wrap: wrap; }
  .scope > span { font-size: 12px; color: var(--on-surface-variant); margin-right: 4px; }
  .scope .chip { max-width: 220px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .divider { height: 1px; background: var(--outline-variant); margin: 4px 0; }
  .people { display: flex; gap: 12px; padding: 12px 20px 4px; overflow-x: auto; overscroll-behavior-x: contain; }
  .person { border: 0; background: none; padding: 0; cursor: pointer; display: flex; flex-direction: column; align-items: center; gap: 6px; width: 72px; flex-shrink: 0; color: var(--on-surface); }
  .person span { font-size: 12px; max-width: 72px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .all { display: flex; align-items: center; gap: 8px; margin: 8px 20px 0; border: 0; background: none; color: var(--primary); font-size: 14px; font-weight: 500; cursor: pointer; padding: 8px 0; }
  .sb.expanded { position: absolute; left: 4px; right: 4px; top: calc(8px + env(safe-area-inset-top)); z-index: 40; max-width: none; }
</style>
