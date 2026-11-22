<script>
  /** 設定了一個資料夾的分類後：還有名稱相近的資料夾，先問「要一起分嗎？」，同意了才照這樣分（只改還沒被你設定過的）。 */
  import { Alert } from "../ui/index.js";
  import { categoryPrompt, learnCategory, categoryName } from "../data/category.svelte.js";
  import { catalog } from "../data/catalog.svelte.js";
  import { t, formatNumber } from "../i18n/index.svelte.js";
  import { toast, refresh } from "../lib/state.svelte.js";

  const ask = $derived(categoryPrompt.ask);
  const name = $derived(ask ? categoryName(catalog.categories.find((c) => c.key === ask.category) || { key: ask.category }, t) : "");
  async function yes() {
    const a = ask;
    categoryPrompt.ask = null;
    try {
      await learnCategory(a.folder, a.category);
      toast(t("cat.learned", { name }));
      refresh();
    } catch (e) {
      toast(e.message, "error");
    }
  }
</script>

{#if ask}
  <div class="backdrop">
    <Alert title={t("cat.similarTitle", { n: formatNumber(ask.similar), name })}
      message={t("cat.similarMessage", { sample: ask.sample.map((s) => `「${s}」`).join("") })} actions={[
        { label: t("cat.similarYes"), role: "default", onPress: yes },
        { label: t("cat.similarNo"), role: "cancel", onPress: () => (categoryPrompt.ask = null) },
      ]} />
  </div>
{/if}

<style>
  .backdrop { position: fixed; inset: 0; z-index: 330; display: flex; align-items: center; justify-content: center; background: var(--media-scrim-light); }
</style>
