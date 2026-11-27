<script>
  /**
   * 待辦：所有等你決定的事在同一頁，依急迫程度排。
   * 1. 硬碟有狀況（先決定怎麼處理）　2. 計畫卡　3. 分類請你確認　4. 待刪除　5. 提醒（只提醒，不算在件數裡）
   * 每一項都能在這裡直接處理，也可以到原本的頁面看。確認的規則和原本一樣：會動到硬碟的，照樣會再跳一次確認。
   */
  import { Button, Icon, List, ListRow, ProgressIndicator } from "../ui/index.js";
  import ActionCard from "../views/ActionCard.svelte";
  import HealthAlert from "../views/HealthAlert.svelte";
  import { loadInbox, snoozeReminder } from "../data/inbox.js";
  import { loadReview, acceptReview } from "../data/category.svelte.js";
  import { loadCatalog } from "../data/catalog.svelte.js";
  import { setFrame } from "../shell/frame.svelte.js";
  import { t, formatNumber, formatBytes } from "../i18n/index.svelte.js";
  import { app, toast, refresh } from "../lib/state.svelte.js";
  import { link, navigate } from "../lib/router.svelte.js";
  import { prettyName } from "../lib/names.js";

  let box = $state(null);
  let error = $state("");
  let busy = $state("");

  async function load() {
    try {
      box = await loadInbox();
      error = "";
    } catch (e) {
      error = e.message;
    }
    loadCatalog(); // 側邊欄的件數跟著更新
  }
  $effect(() => {
    app.refreshKey;
    load();
  });
  $effect(() => {
    setFrame({ crumbs: [], status: box ? t("inbox.status", { n: formatNumber(box.total) }) : "", location: null, info: null });
  });
  // 計畫卡處理完（執行、不要、復原）：重新整理清單
  const settled = $derived(box ? box.actions.filter((a) => a.state !== "proposed").length : 0);
  let lastSettled = 0;
  $effect(() => {
    if (settled > lastSettled) setTimeout(load, 1500);
    lastSettled = settled;
  });

  async function acceptAll() {
    busy = "review";
    try {
      const d = await loadReview();
      const ids = d.items.map((x) => x.folder_id);
      await acceptReview(ids);
      toast(t("inbox.reviewAccepted", { n: formatNumber(ids.length) }));
      refresh();
      await load();
    } catch (e) {
      toast(e.message, "error");
    } finally {
      busy = "";
    }
  }
  async function snooze(n) {
    box = { ...box, reminders: box.reminders.filter((x) => x.key !== n.key) };
    await snoozeReminder(n.key).catch(() => {});
  }
  const empty = $derived(box && !box.total && !box.reminders.length);
  const order = $derived(box ? ["health", "actions", "review", "pending"].filter((k) =>
    k === "review" ? box.review.count : box[k].length) : []);
  const no = (k) => order.indexOf(k) + 1;
</script>

<div class="inbox">
  <header>
    <h1 class="mac-large-title">{t("inbox.title")}</h1>
    <p class="mac-body sub">{box ? (box.total ? t("inbox.lead", { n: formatNumber(box.total) }) : t("inbox.leadNone")) : ""}</p>
  </header>

  {#if error}
    <p class="mac-body err" role="alert">{error} <Button size="small" variant="bordered" onclick={load}>{t("view.retry")}</Button></p>
  {:else if !box}
    <div class="state"><ProgressIndicator kind="spinner" label={t("view.loading")} /></div>
  {:else if empty}
    <div class="state">
      <span class="done"><Icon name="checkmark" size={28} /></span>
      <h2 class="mac-title-3">{t("inbox.empty")}</h2>
      <p class="mac-body sub">{t("inbox.emptyHint")}</p>
    </div>
  {:else}
    {#if box.health.length}
      <section>
        <h2 class="mac-headline"><span class="num lv-fail">{no("health")}</span>{t("inbox.health")}</h2>
        <p class="mac-callout sub">{t("inbox.healthHint")}</p>
        {#each box.health as h (h.key)}<HealthAlert health={h} onchange={load} />{/each}
      </section>
    {/if}

    {#if box.actions.length}
      <section>
        <h2 class="mac-headline"><span class="num">{no("actions")}</span>{t("inbox.plans", { n: formatNumber(box.actions.length) })}</h2>
        <p class="mac-callout sub">{t("inbox.plansHint")}</p>
        {#each box.actions as _, k (box.actions[k].id)}
          <ActionCard bind:action={box.actions[k]} />
        {/each}
      </section>
    {/if}

    {#if box.review.count}
      <section>
        <h2 class="mac-headline"><span class="num">{no("review")}</span>{t("inbox.review")}</h2>
        <List footer={t("inbox.reviewHint")}>
          <ListRow title={t("inbox.reviewCount", { n: formatNumber(box.review.count) })}
            subtitle={box.review.examples.map((e) => prettyName(e.name)).join("、") + (box.review.count > box.review.examples.length ? "…" : "")}
            icon="exclamation-triangle" iconTint="orange">
            {#snippet trailing()}<span class="acts">
              <Button size="small" variant="bordered" loading={busy === "review"} disabled={!!busy} onclick={acceptAll}>{t("inbox.reviewAll")}</Button>
              <Button size="small" variant="borderedProminent" onclick={() => navigate("/category/review")}>{t("inbox.reviewOne")}</Button>
            </span>{/snippet}
          </ListRow>
        </List>
      </section>
    {/if}

    {#if box.pending.length}
      <section>
        <h2 class="mac-headline"><span class="num">{no("pending")}</span>{t("inbox.pending")}</h2>
        <List footer={t("inbox.pendingHint")}>
          {#each box.pending as d (d.drive)}
            <ListRow title={d.drive} icon={d.online ? "external-drive-fill" : "external-drive"} accessory="disclosure" onclick={() => navigate("/pending")}
              subtitle={[t("inbox.pendingCount", { n: formatNumber(d.count), size: formatBytes(d.bytes) || "0 KB" }),
                d.stale ? t("inbox.pendingStale", { n: formatNumber(d.stale) }) : "", !d.online ? t("inbox.pendingOffline") : "",
                d.read_only ? t("drive.readOnly") : ""].filter(Boolean).join(" · ")} />
          {/each}
        </List>
      </section>
    {/if}

    {#if box.reminders.length}
      <section>
        <h2 class="mac-headline"><span class="num soft">·</span>{t("inbox.reminders")}</h2>
        <ul class="notes mac-callout">
          {#each box.reminders as n (n.key)}
            <li class="lv-{n.level}"><Icon name={n.icon || "info"} size={14} /><a href={n.href} use:link>{n.text}</a>
              <button type="button" class="snooze" title={t("ov.snooze")} aria-label={t("ov.snooze")} onclick={() => snooze(n)}><Icon name="xmark" size={10} /></button></li>
          {/each}
        </ul>
        <p class="mac-caption-1 sub">{t("inbox.remindersHint")}</p>
      </section>
    {/if}
  {/if}
</div>

<style>
  .inbox { padding: var(--space-5) var(--space-6) var(--space-8); max-width: 980px; color: var(--label-primary); display: flex; flex-direction: column; gap: var(--space-5); }
  h1, h2, p { margin: 0; }
  header p { margin-top: var(--space-1); }
  .sub { color: var(--label-secondary); }
  .err { color: var(--destructive); }
  section { display: flex; flex-direction: column; gap: var(--space-2); }
  section > h2 { display: flex; align-items: center; gap: var(--space-2); }
  .num { flex: none; width: var(--space-5); height: var(--space-5); display: inline-flex; align-items: center; justify-content: center; border-radius: var(--radius-capsule);
    background: var(--accent); color: var(--on-accent); font-feature-settings: "tnum"; }
  .num.lv-fail { background: var(--system-red); }
  .num.soft { background: var(--fill-tertiary); color: var(--label-secondary); }
  .acts { display: inline-flex; align-items: center; gap: var(--space-2); flex-wrap: wrap; justify-content: flex-end; }
  .notes { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: var(--space-2); }
  .notes li { display: flex; align-items: center; gap: var(--space-2); min-width: 0; padding: var(--space-2) var(--space-3); border-radius: var(--radius-md); background: var(--fill-quaternary); }
  .notes li > :global(svg) { flex: none; color: var(--label-secondary); }
  .notes li.lv-warn > :global(svg) { color: var(--system-orange); }
  .notes a { color: var(--label-primary); text-decoration: none; min-width: 0; }
  .notes a:hover { color: var(--accent); text-decoration: underline; }
  .snooze { flex: none; margin-left: auto; width: var(--space-5); height: var(--space-5); display: inline-flex; align-items: center; justify-content: center;
    border: 0; border-radius: var(--radius-capsule); background: none; color: var(--label-tertiary); cursor: pointer; }
  .snooze:hover { background: var(--fill-tertiary); color: var(--label-primary); }
  .state { display: flex; flex-direction: column; align-items: center; gap: var(--space-3); padding: var(--space-10) var(--space-6); text-align: center; }
  .done { width: 56px; height: 56px; border-radius: var(--radius-capsule); display: inline-flex; align-items: center; justify-content: center;
    background: color-mix(in srgb, var(--system-green) 18%, transparent); color: var(--system-green); }
  @media (max-width: 640px) { .inbox { padding: var(--space-4); } }
</style>
