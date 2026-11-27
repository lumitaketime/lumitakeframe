<script>
  /**
   * 設定 → 分類（由上到下照使用的順序）：
   * 1. 分類清單：每一類都能改名、刪除、新增；還沒分類的有幾個；AI 的建議（計畫卡）等你確認。
   * 2. 讓 AI 看資料夾：放得進分類的直接分好，放不進去的 AI 建議新分類（計畫卡，確認才建立）。
   * 3. 自動分類：掃描完要不要自動分、要不要交給 AI。
   * 4. 我的規則、5. 你的身分與習慣。
   * 分類只記在目錄裡，不改硬碟上的檔案；本人設定的永遠優先。
   */
  import { Alert, Button, List, ListRow, Toggle, TextField } from "../ui/index.js";
  import { loadCategories, editCategory, categoryName, CATEGORY_ICONS, reviewEstimate, runReview, loadPlans } from "../data/category.svelte.js";
  import { loadRules, deleteRule, loadProfile, saveProfile } from "../data/analysis.js";
  import { undoAction } from "../data/assistant.js";
  import { loadCatalog } from "../data/catalog.svelte.js";
  import { navigate } from "../lib/router.svelte.js";
  import InboxLink from "./InboxLink.svelte";
  import { t, formatNumber } from "../i18n/index.svelte.js";
  import { app, toast, refresh } from "../lib/state.svelte.js";

  let { settings, set } = $props();
  let st = $state(null);
  let busy = $state("");
  let editing = $state(null); // {key, name} 或 {add: true, name}
  let removing = $state(null);
  let ruleList = $state([]);
  let prof = $state(null);
  let removingRule = $state(null);
  let plans = $state(0);
  function load() {
    loadCategories().then((d) => (st = d)).catch(() => {});
    loadPlans().then((d) => (plans = d.plans.length)).catch(() => {});
    loadRules().then((d) => (ruleList = d.rules)).catch(() => {});
    loadProfile().then((d) => (prof = { identity: d.identity || "", teach_start_year: d.teach_start_year ? String(d.teach_start_year) : "" })).catch(() => {});
  }
  const nameOfKey = (k) => categoryName((st?.categories || []).find((c) => c.key === k) || { key: k }, t);
  const ruleYears = (r) => (r.year_from && r.year_to ? t("rule.between", { a: r.year_from, b: r.year_to })
    : r.year_from ? t("rule.after", { y: r.year_from }) : r.year_to ? t("rule.before", { y: r.year_to }) : "");
  async function dropRule() {
    const r = removingRule;
    removingRule = null;
    try {
      await deleteRule(r.id);
      toast(t("rule.deleted", { word: r.pattern }));
      await loadCatalog();
      load();
      refresh();
    } catch (e) {
      toast(e.message, "error");
    }
  }
  let profTimer;
  function editProfile(key, v) {
    prof = { ...prof, [key]: v };
    clearTimeout(profTimer);
    profTimer = setTimeout(() => saveProfile({ identity: prof.identity, teach_start_year: Number(prof.teach_start_year) || null }).catch(() => {}), 600);
  }
  $effect(() => {
    app.refreshKey;
    load();
  });
  const job = $derived(app.server?.jobs?.active?.find((j) => ["classify", "classify_ai", "classify_review"].includes(j.kind)) || null);
  // AI 看完：重新讀一次（新的計畫卡、分好的資料夾）
  let wasRunning = false;
  $effect(() => {
    const running = !!job;
    if (wasRunning && !running) load();
    wasRunning = running;
  });

  async function toggle(key, v) {
    await set(key, v ? 1 : 0);
    if (key === "classify_rules_auto" || key === "classify_ai_auto") await set("classify_asked", 1);
    load();
  }
  async function saveEdit() {
    const e = editing;
    editing = null;
    try {
      await editCategory(e.add ? { action: "add", name: e.name } : { action: "rename", key: e.key, name: e.name });
      await loadCatalog();
      load();
    } catch (err) {
      toast(err.message, "error");
    }
  }
  async function remove() {
    const c = removing;
    removing = null;
    try {
      const out = await editCategory({ action: "delete", key: c.key });
      await loadCatalog();
      load();
      refresh();
      if (out.action) toast(t("cat.set.deleted", { name: categoryName(c, t) }), "info", 10000, {
        label: t("act.undo"), run: async () => { await undoAction(out.action.id); await loadCatalog(); load(); refresh(); toast(t("insight.undone")); },
      });
    } catch (err) {
      toast(err.message, "error");
    }
  }
  async function restoreDefaults() {
    try {
      const out = await editCategory({ action: "restore" });
      await loadCatalog();
      load();
      refresh();
      toast(out.restored ? t("cat.set.restored", { n: formatNumber(out.restored) }) : t("cat.set.nothingToRestore"));
    } catch (err) {
      toast(err.message, "error");
    }
  }
  // 讓 AI 重新看一遍：先說要看幾個資料夾、大約多久，確認才開始
  let reviewAsk = $state(null);
  async function askReview() {
    try {
      reviewAsk = await reviewEstimate();
    } catch (err) {
      toast(err.message, "error");
    }
  }
  async function startReview(onlyNew) {
    reviewAsk = null;
    try {
      await runReview(undefined, onlyNew);
      toast(t("cat.review.started"));
      refresh();
    } catch (err) {
      toast(err.message, "error");
    }
  }
  const minutes = (s) => Math.max(1, Math.round((s || 0) / 60));
  const missingDefaults = $derived(st ? ["school", "work", "travel", "life", "finance", "creative", "hobby", "software", "other"].filter((k) => !st.categories.some((c) => c.key === k)).length : 0);
</script>

{#if settings && st}
  <List header={t("cat.set.list")} footer={t("cat.set.listHint")}>
    {#each st.categories as c (c.key)}
      <ListRow title={categoryName(c, t)} icon={CATEGORY_ICONS[c.key] || "tag"} subtitle={c.description || t("cat.set.stats", { folders: formatNumber(c.folders), files: formatNumber(c.files) })}
        detail={c.description ? t("cat.set.folders", { n: formatNumber(c.folders) }) : ""}>
        {#snippet trailing()}<span class="acts">
          <Button size="small" variant="borderless" onclick={() => (editing = { key: c.key, name: categoryName(c, t) })}>{t("cat.set.rename")}</Button>
          <Button size="small" variant="borderless" role="destructive" onclick={() => (removing = c)}>{t("cat.set.delete")}</Button>
        </span>{/snippet}
      </ListRow>
    {/each}
    <ListRow title={t("cat.set.add")} icon="plus" onclick={() => (editing = { add: true, name: "" })} />
    {#if missingDefaults}<ListRow title={t("cat.set.restore")} subtitle={t("cat.set.restoreHint", { n: formatNumber(missingDefaults) })} icon="undo" onclick={restoreDefaults} />{/if}
  </List>

  {#if plans || st.review}
    <div class="waiting"><InboxLink text={plans && st.review ? t("inbox.linkCategory", { plans: formatNumber(plans), review: formatNumber(st.review) })
      : plans ? t("inbox.linkPlans", { n: formatNumber(plans) }) : t("inbox.linkReview", { n: formatNumber(st.review) })} /></div>
  {/if}

  <List header={t("cat.look.title")} footer={t("cat.look.footer")}>
    {#if job}
      <ListRow title={job.kind === "classify" ? t("cat.set.rulesRunning") : t("cat.look.running")} subtitle={job.message || ""} icon="sparkles"
        detail={job.total ? `${formatNumber(job.done)} / ${formatNumber(job.total)}` : ""} />
    {:else}
      <ListRow title={t("cat.look.run")} subtitle={st.unclassified ? t("cat.look.hintN", { n: formatNumber(st.unclassified) }) : t("cat.look.hint")} icon="sparkles">
        {#snippet trailing()}<Button size="small" variant="bordered" onclick={askReview}>{t("cat.review.aiButton")}</Button>{/snippet}
      </ListRow>
    {/if}
  </List>

  <List header={t("cat.set.title")} footer={t("cat.set.footer")}>
    <ListRow title={t("cat.choice.rules_auto")} subtitle={t("cat.choice.rules_auto.hint")}>
      {#snippet trailing()}<Toggle checked={!!settings.classify_rules_auto} onchange={(v) => toggle("classify_rules_auto", v)} aria-label={t("cat.choice.rules_auto")} />{/snippet}
    </ListRow>
    <ListRow title={t("cat.choice.ai_auto")} subtitle={t("cat.choice.ai_auto.hint2")}>
      {#snippet trailing()}<Toggle checked={!!settings.classify_ai_auto} onchange={(v) => toggle("classify_ai_auto", v)} aria-label={t("cat.choice.ai_auto")} />{/snippet}
    </ListRow>
    <ListRow title={t("cat.choice.read_text")} subtitle={t("cat.choice.read_text.hint")}>
      {#snippet trailing()}<Toggle checked={!!settings.classify_read_text} onchange={(v) => toggle("classify_read_text", v)} aria-label={t("cat.choice.read_text")} />{/snippet}
    </ListRow>
    {#if st.remote}
      <ListRow title={t("cat.set.cloud")} subtitle={t("cat.set.cloudHint")}>
        {#snippet trailing()}<Toggle checked={!!settings.classify_cloud} onchange={(v) => toggle("classify_cloud", v)} aria-label={t("cat.set.cloud")} />{/snippet}
      </ListRow>
    {/if}
  </List>

  <List header={t("rule.title")} footer={t("rule.footer")}>
    {#each ruleList as r (r.id)}
      <ListRow title={`「${r.pattern}」 → ${nameOfKey(r.category)}`} icon="tag"
        subtitle={[ruleYears(r), r.source === "user" ? t("rule.byYou") : t("rule.byAssistant"), t("rule.folders", { n: formatNumber(r.folders) })].filter(Boolean).join(" · ")}>
        {#snippet trailing()}<Button size="small" variant="borderless" role="destructive" onclick={() => (removingRule = r)}>{t("cat.set.delete")}</Button>{/snippet}
      </ListRow>
    {:else}
      <ListRow title={t("rule.none")} subtitle={t("rule.noneHint")} accessory="disclosure" onclick={() => navigate("/insights")} />
    {/each}
  </List>

  {#if prof}
    <List header={t("prof.title")} footer={t("prof.footer")}>
      <div class="pad">
        <TextField label={t("prof.identity")} value={prof.identity} placeholder={t("prof.identityPlaceholder")} onchange={(v) => editProfile("identity", v)} />
        <TextField label={t("prof.startYear")} type="number" value={prof.teach_start_year} placeholder={t("prof.startYearPlaceholder")}
          onchange={(v) => editProfile("teach_start_year", v)} />
      </div>
    </List>
  {/if}
{/if}

{#if editing}
  <div class="backdrop">
    <Alert title={editing.add ? t("cat.set.addTitle") : t("cat.set.renameTitle")} textField={{ value: editing.name, placeholder: t("cat.set.namePlaceholder"), onchange: (v) => (editing.name = v) }}
      message={editing.add ? "" : t("cat.set.renameHint")} actions={[
        { label: t("cat.set.save"), role: "default", onPress: saveEdit, disabled: editing.add && !editing.name.trim() },
        { label: t("common.cancel"), role: "cancel", onPress: () => (editing = null) },
      ]} />
  </div>
{/if}
{#if reviewAsk}
  <div class="backdrop">
    {#if reviewAsk.unclassified && reviewAsk.unclassified < reviewAsk.folders}
      <Alert title={t("cat.look.confirmTitle")}
        message={t("cat.look.confirmMessage", { u: formatNumber(reviewAsk.unclassified), um: formatNumber(minutes(reviewAsk.unclassified_seconds)),
          n: formatNumber(reviewAsk.folders), nm: formatNumber(minutes(reviewAsk.seconds)) })} actions={[
          { label: t("cat.look.onlyNew"), role: "default", onPress: () => startReview(true) },
          { label: t("cat.look.all"), role: "default", onPress: () => startReview(false) },
          { label: t("common.cancel"), role: "cancel", onPress: () => (reviewAsk = null) },
        ]} />
    {:else}
      <Alert title={t("cat.review.confirmTitle", { n: formatNumber(reviewAsk.folders) })}
        message={t("cat.review.confirmMessage", { min: formatNumber(minutes(reviewAsk.seconds)) })} actions={[
          { label: t("cat.review.aiButton"), role: "default", onPress: () => startReview(false), disabled: !reviewAsk.folders },
          { label: t("common.cancel"), role: "cancel", onPress: () => (reviewAsk = null) },
        ]} />
    {/if}
  </div>
{/if}
{#if removingRule}
  <div class="backdrop">
    <Alert title={t("rule.deleteTitle", { word: removingRule.pattern })} message={t("rule.deleteMessage")} actions={[
      { label: t("cat.set.delete"), role: "destructive", onPress: dropRule },
      { label: t("common.cancel"), role: "cancel", onPress: () => (removingRule = null) },
    ]} />
  </div>
{/if}
{#if removing}
  <div class="backdrop">
    <Alert title={t("cat.set.deleteTitle", { name: categoryName(removing, t) })} message={t("cat.set.deleteMessage")} actions={[
      { label: t("cat.set.delete"), role: "destructive", onPress: remove },
      { label: t("common.cancel"), role: "cancel", onPress: () => (removing = null) },
    ]} />
  </div>
{/if}

<style>
  .acts { display: inline-flex; align-items: center; gap: var(--space-1); }
  .waiting { margin: var(--space-2) 0 var(--space-4); }
  .pad { display: flex; flex-direction: column; gap: var(--space-3); padding: var(--space-3); }
  .backdrop { position: fixed; inset: 0; z-index: 320; display: flex; align-items: center; justify-content: center; background: var(--media-scrim-light); }
</style>
