<script>
  /**
   * 請你確認：AI 沒把握的分類集中在這裡。按「對」就變成你的設定（之後不會再被改）；不對就直接選別的分類。
   * 只改目錄裡的分類，不改硬碟上的檔案。
   */
  import { Button, Icon, PopUpButton, ProgressIndicator } from "../ui/index.js";
  import { loadReview, acceptReview, setCategory, categoryName, loadPlans } from "../data/category.svelte.js";
  import InboxLink from "../views/InboxLink.svelte";
  import { catalog, loadCatalog } from "../data/catalog.svelte.js";
  import { setFrame } from "../shell/frame.svelte.js";
  import { navigate } from "../lib/router.svelte.js";
  import { t, formatNumber, formatBytes } from "../i18n/index.svelte.js";
  import { app, toast, refresh } from "../lib/state.svelte.js";

  let items = $state(null);
  let error = $state("");
  let busy = $state(0);
  let plans = $state([]);
  function load() {
    loadReview().then((d) => { items = d.items; error = ""; }).catch((e) => (error = e.message));
    loadPlans().then((d) => (plans = d.plans)).catch(() => {});
  }
  $effect(() => {
    app.refreshKey;
    load();
  });
  $effect(() => {
    setFrame({ crumbs: [], location: null, info: null, status: items ? t("cat.review.count", { n: formatNumber(items.length) }) : "" });
  });
  const nameOf = (k) => categoryName(catalog.categories.find((c) => c.key === k) || { key: k }, t);
  const href = (it) => `/folders/${it.root_id}?path=${encodeURIComponent(it.path)}`;
  async function act(id, fn) {
    busy = id;
    try {
      await fn();
      items = items.filter((x) => x.folder_id !== id && id !== -1);
      if (id === -1) items = [];
      loadCatalog();
      refresh();
    } catch (e) {
      toast(e.message, "error");
    } finally {
      busy = 0;
    }
  }
  const ok = (it) => act(it.folder_id, () => acceptReview([it.folder_id]));
  const change = (it, v) => act(it.folder_id, () => setCategory({ folder: it.folder_id }, v === "none" ? null : v));
  const all = () => act(-1, () => acceptReview(items.map((x) => x.folder_id)));
  const options = $derived([...catalog.categories.map((c) => ({ value: c.key, label: categoryName(c, t) })), { value: "none", label: t("cat.none") }]);
</script>

<div class="review">
  <header>
    <h1 class="mac-title-2">{t("cat.review.title")}</h1>
    <p class="mac-body sub">{t("cat.review.lead")}</p>
  </header>
  {#if plans.length}<InboxLink text={t("inbox.linkPlans", { n: formatNumber(plans.length) })} />{/if}
  {#if error}
    <div class="state" role="alert"><p class="mac-body">{error}</p><Button onclick={load}>{t("view.retry")}</Button></div>
  {:else if !items}
    <div class="state"><ProgressIndicator kind="spinner" label={t("view.loading")} /></div>
  {:else if !items.length}
    <div class="state">
      <Icon name="checkmark" size={28} weight="bold" />
      <h2 class="mac-title-3">{t("cat.review.empty")}</h2>
      <p class="mac-body sub">{t("cat.review.emptyHint")}</p>
    </div>
  {:else}
    <div class="bar"><span class="grow"></span><Button variant="bordered" loading={busy === -1} disabled={!!busy} onclick={all}>{t("cat.review.acceptAll", { n: formatNumber(items.length) })}</Button></div>
    <ul class="list">
      {#each items as it (it.folder_id)}
        <li>
          <Icon name="folder" size={18} weight="medium" />
          <div class="text">
            <a class="mac-body name" href={href(it)} onclick={(e) => { e.preventDefault(); navigate(href(it)); }}>{it.name}</a>
            <p class="mac-callout sub">{it.root} › {it.path} · {formatBytes(it.total_bytes) || "0 KB"}</p>
            <p class="mac-callout ai">{t("cat.review.ai", { name: nameOf(it.category) })}{it.reason ? `：${it.reason}` : ""}</p>
          </div>
          <Button size="small" variant="borderedProminent" loading={busy === it.folder_id} disabled={!!busy} onclick={() => ok(it)}>{t("cat.review.ok")}</Button>
          <PopUpButton value={it.category} {options} disabled={!!busy} onchange={(v) => change(it, v)} />
        </li>
      {/each}
    </ul>
  {/if}
</div>

<style>
  .review { padding: var(--space-4) var(--space-6) var(--space-8); max-width: 960px; color: var(--label-primary); }
  header { display: flex; flex-direction: column; gap: var(--space-1); margin-bottom: var(--space-4); }
  h1, h2, p { margin: 0; }
  .sub { color: var(--label-secondary); }
  .ai { color: var(--label-secondary); }
  .state { display: flex; flex-direction: column; align-items: center; gap: var(--space-2); padding: var(--space-8) 0; color: var(--label-secondary); text-align: center; }
  .bar { display: flex; margin-bottom: var(--space-2); }
  .grow { flex: 1; }
  .list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: var(--space-2); }
  li { display: flex; align-items: center; gap: var(--space-3); padding: var(--space-3) var(--space-4); border-radius: var(--radius-md); background: var(--fill-quaternary); color: var(--label-secondary); }
  .text { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
  .text p { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .name { color: var(--label-primary); text-decoration: none; font-weight: 600; }
  .name:hover { text-decoration: underline; }
</style>
