<script>
  /**
   * 設定 → AI 助理 → 自動分類：要不要自動跑、立即分類、管理分類清單（改名、新增、刪除自己加的）。
   * 分類只記在目錄裡，不改硬碟上的檔案；本人設定的永遠優先。
   */
  import { Alert, Button, List, ListRow, Toggle, TextField } from "../ui/index.js";
  import { loadCategories, runClassify, editCategory, categoryName, CATEGORY_ICONS } from "../data/category.svelte.js";
  import { loadCatalog } from "../data/catalog.svelte.js";
  import { navigate } from "../lib/router.svelte.js";
  import { t, formatNumber } from "../i18n/index.svelte.js";
  import { app, toast, refresh } from "../lib/state.svelte.js";

  let { settings, set } = $props();
  let st = $state(null);
  let busy = $state("");
  let editing = $state(null); // {key, name} 或 {add: true, name}
  let removing = $state(null);
  function load() {
    loadCategories().then((d) => (st = d)).catch(() => {});
  }
  $effect(() => {
    app.refreshKey;
    load();
  });
  const job = $derived(app.server?.jobs?.active?.find((j) => j.kind === "classify" || j.kind === "classify_ai") || null);

  async function toggle(key, v) {
    await set(key, v ? 1 : 0);
    if (key === "classify_rules_auto" || key === "classify_ai_auto") await set("classify_asked", 1);
    load();
  }
  async function run(ai) {
    busy = ai ? "ai" : "rules";
    try {
      await runClassify(ai);
      toast(ai ? t("cat.set.aiStarted") : t("cat.set.rulesStarted"));
      refresh();
    } catch (e) {
      toast(e.message, "error");
    } finally {
      busy = "";
    }
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
      await editCategory({ action: "delete", key: c.key });
      await loadCatalog();
      load();
    } catch (err) {
      toast(err.message, "error");
    }
  }
</script>

{#if settings && st}
  <List header={t("cat.set.title")} footer={t("cat.set.footer")}>
    <ListRow title={t("cat.choice.rules_auto")} subtitle={t("cat.choice.rules_auto.hint")}>
      {#snippet trailing()}<Toggle checked={!!settings.classify_rules_auto} onchange={(v) => toggle("classify_rules_auto", v)} aria-label={t("cat.choice.rules_auto")} />{/snippet}
    </ListRow>
    <ListRow title={t("cat.choice.ai_auto")} subtitle={t("cat.choice.ai_auto.hint")}>
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
    {#if job}
      <ListRow title={job.kind === "classify_ai" ? t("cat.set.aiRunning") : t("cat.set.rulesRunning")} subtitle={job.message || ""}
        detail={job.total ? `${formatNumber(job.done)} / ${formatNumber(job.total)}` : ""} />
    {:else}
      <ListRow title={t("cat.set.run")} subtitle={t("cat.set.runHint", { n: formatNumber(st.ai_todo) })}>
        {#snippet trailing()}<span class="acts">
          <Button size="small" variant="bordered" loading={busy === "rules"} disabled={!!busy} onclick={() => run(false)}>{t("cat.set.runRules")}</Button>
          <Button size="small" variant="bordered" loading={busy === "ai"} disabled={!!busy || !st.ai_todo} onclick={() => run(true)}>{t("cat.set.runAi")}</Button>
        </span>{/snippet}
      </ListRow>
    {/if}
    {#if st.review}
      <ListRow title={t("cat.review.title")} subtitle={t("cat.review.count", { n: formatNumber(st.review) })} icon="exclamation-triangle" iconTint="orange"
        accessory="disclosure" onclick={() => navigate("/category/review")} />
    {/if}
  </List>

  <List header={t("cat.set.list")} footer={t("cat.set.listHint")}>
    {#each st.categories as c (c.key)}
      <ListRow title={categoryName(c, t)} icon={CATEGORY_ICONS[c.key] || "tag"} subtitle={t("cat.set.stats", { folders: formatNumber(c.folders), files: formatNumber(c.files) })}>
        {#snippet trailing()}<span class="acts">
          <Button size="small" variant="borderless" onclick={() => (editing = { key: c.key, name: categoryName(c, t) })}>{t("cat.set.rename")}</Button>
          {#if !c.builtin}<Button size="small" variant="borderless" role="destructive" onclick={() => (removing = c)}>{t("cat.set.delete")}</Button>{/if}
        </span>{/snippet}
      </ListRow>
    {/each}
    <ListRow title={t("cat.set.add")} icon="plus" onclick={() => (editing = { add: true, name: "" })} />
  </List>
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
  .backdrop { position: fixed; inset: 0; z-index: 320; display: flex; align-items: center; justify-content: center; background: var(--media-scrim-light); }
</style>
