<script>
  /**
   * 第一次先問：目錄裡有資料夾了、本人還沒決定過要不要自動分類 → 問一次（不問就不自動跑）。
   * 「開始」＝依勾選的設定，並馬上用規則分一次；「先不要」＝記住已經問過，之後可以到「設定 → AI 助理」打開。
   */
  import { Button } from "../ui/index.js";
  import ClassifyChoices from "../views/ClassifyChoices.svelte";
  import { classifyConsent } from "../data/category.svelte.js";
  import { t } from "../i18n/index.svelte.js";
  import { toast, refresh } from "../lib/state.svelte.js";

  let { ondone } = $props();
  let value = $state({ rules_auto: true, ai_auto: true, read_text: true });
  let busy = $state(false);

  async function answer(start) {
    busy = true;
    try {
      await classifyConsent(start ? value : { rules_auto: false, ai_auto: false });
      if (start && value.rules_auto) toast(t("cat.consent.started"));
      refresh();
      ondone?.();
    } catch (e) {
      toast(e.message, "error");
    } finally {
      busy = false;
    }
  }
</script>

<div class="scrim" role="presentation">
  <div class="panel" role="dialog" aria-modal="true" aria-labelledby="cat-consent-title">
    <div class="body">
      <h1 id="cat-consent-title" class="mac-title-2">{t("cat.consent.title")}</h1>
      <p class="lead mac-body">{t("cat.consent.lead")}</p>
      <ClassifyChoices bind:value />
      <p class="mac-callout sub">{t("cat.consent.promise")}</p>
    </div>
    <footer>
      <span class="grow"></span>
      <Button variant="borderless" disabled={busy} onclick={() => answer(false)}>{t("cat.consent.no")}</Button>
      <Button variant="borderedProminent" loading={busy} onclick={() => answer(true)}>{t("cat.consent.yes")}</Button>
    </footer>
  </div>
</div>

<style>
  .scrim { position: fixed; inset: 0; z-index: 300; display: flex; align-items: center; justify-content: center; padding: var(--space-4); background: var(--media-scrim-light); }
  .panel { box-sizing: border-box; width: min(520px, 100%); max-height: calc(100vh - var(--space-8)); display: flex; flex-direction: column;
    border-radius: var(--radius-xl); background: var(--window-bg); box-shadow: var(--shadow-window); overflow: hidden; }
  .body { flex: 1; min-height: 0; overflow-y: auto; padding: var(--space-5) var(--space-6) var(--space-3); display: flex; flex-direction: column; gap: var(--space-3); }
  h1 { margin: 0; text-align: center; color: var(--label-primary); }
  .lead { margin: 0; text-align: center; color: var(--label-secondary); }
  .sub { margin: 0; color: var(--label-secondary); }
  footer { display: flex; align-items: center; gap: var(--space-2); padding: var(--space-3) var(--space-5) var(--space-4); border-top: 1px solid var(--separator); }
  .grow { flex: 1; }
</style>
