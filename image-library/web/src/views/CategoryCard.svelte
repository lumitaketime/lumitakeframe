<script>
  /**
   * 資訊欄的「分類」：這個資料夾或檔案目前算哪一類、是誰分的（規則、AI 建議、你設定的）、為什麼；不對就直接改。
   * 只記在目錄裡，不改硬碟上的檔案。本人設定的永遠優先，重新分析也不會覆蓋。
   */
  import { PopUpButton } from "../ui/index.js";
  import { categoryOf, setCategory, categoryName } from "../data/category.svelte.js";
  import { catalog } from "../data/catalog.svelte.js";
  import { t } from "../i18n/index.svelte.js";
  import { app, toast, refresh } from "../lib/state.svelte.js";

  let { target } = $props(); // {folder} 或 {file}

  let cur = $state(null);
  let busy = $state(false);
  const key = $derived(target ? JSON.stringify(target) : "");
  $effect(() => {
    key;
    app.refreshKey;
    cur = null;
    if (!target) return;
    const want = key;
    categoryOf(target).then((d) => { if (want === key) cur = d; }).catch(() => {});
  });
  const nameOf = (k) => categoryName(catalog.categories.find((c) => c.key === k) || { key: k }, t);
  const value = $derived(!cur ? "auto" : cur.user ? (cur.category || "none") : "auto");
  const options = $derived([
    { value: "auto", label: cur && !cur.user && cur.category ? t("cat.autoIs", { name: nameOf(cur.category) }) : t("cat.auto") },
    ...catalog.categories.map((c) => ({ value: c.key, label: categoryName(c, t) })),
    { value: "none", label: t("cat.none") },
  ]);
  const SOURCE = { user: "cat.src.user", rule: "cat.src.rule", learned: "cat.src.learned", ai: "cat.src.ai", inherit: "cat.src.inherit",
    my_rule: "cat.src.myRule", pending: "cat.src.pending" };
  const note = $derived(!cur ? "" : cur.from_folder && !cur.user ? t("cat.fromFolder")
    : cur.source ? [t(SOURCE[cur.source] || "cat.src.rule"), cur.source === "user" ? "" : cur.reason].filter(Boolean).join(" · ") : t("cat.undecided"));

  async function change(v) {
    busy = true;
    try {
      await setCategory(target, v === "none" ? null : v);
      cur = await categoryOf(target);
      refresh();
    } catch (e) {
      toast(e.message, "error");
    } finally {
      busy = false;
    }
  }
</script>

{#if target}
  <section class="cat">
    <h3 class="mac-subheadline">{t("cat.title")}</h3>
    <PopUpButton {value} {options} disabled={busy || !cur} onchange={change} />
    {#if cur}<p class="mac-callout note" class:review={cur.review}>{cur.review ? t("cat.reviewNote") + " · " : ""}{note}</p>{/if}
  </section>
{/if}

<style>
  .cat { display: flex; flex-direction: column; gap: var(--space-2); }
  h3 { margin: 0; color: var(--label-secondary); }
  .note { margin: 0; color: var(--label-secondary); }
  .note.review { color: var(--system-orange); }
</style>
