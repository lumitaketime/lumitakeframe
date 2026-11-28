<script>
  /**
   * 安裝（或更新）Ollama 前的確認視窗：畫面正中央、背景變暗。
   * 一眼看懂會發生什麼：從哪裡下載、怎麼檢查、放到哪裡、之後會怎樣；並清楚說明不會送出任何檔案。
   * Escape 或「取消」關閉；Enter 等同「安裝」。
   */
  import { Button, Icon } from "../ui/index.js";
  import { t } from "../i18n/index.svelte.js";

  let { update = false, onconfirm, oncancel } = $props();

  const steps = $derived(update
    ? ["oll.dlg.uDownload", "oll.dlg.check", "oll.dlg.uReplace", "oll.dlg.uOpen"]
    : ["oll.dlg.download", "oll.dlg.check", "oll.dlg.place", "oll.dlg.open"]);
  let card = $state();
  $effect(() => {
    card?.querySelector("[data-default]")?.focus();
  });
  function onkeydown(e) {
    if (e.key === "Escape") { e.preventDefault(); oncancel?.(); }
  }
</script>

<div class="scrim" role="presentation">
  <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
  <div bind:this={card} class="panel" role="alertdialog" aria-modal="true" aria-labelledby="oll-dlg-t" aria-describedby="oll-dlg-d" tabindex="-1" {onkeydown}>
    <div class="head">
      <span class="tile" aria-hidden="true"><Icon name={update ? "arrow-up" : "arrow-down"} size={26} weight="semibold" /></span>
      <h2 id="oll-dlg-t" class="mac-title-3">{t(update ? "oll.confirmUpdate" : "oll.confirmInstall")}</h2>
      <p id="oll-dlg-d" class="mac-callout sub">{t("oll.dlg.lead")}</p>
    </div>
    <ol class="steps">
      {#each steps as key, i (key)}
        <li>
          <span class="num mac-caption-1">{i + 1}</span>
          <span class="mac-body">{t(key)}</span>
        </li>
      {/each}
    </ol>
    <p class="note mac-callout"><Icon name="lock" size={14} />{t("oll.dlg.private")}</p>
    <footer>
      <Button variant="bordered" role="cancel" onclick={oncancel}>{t("common.cancel")}</Button>
      <Button variant="borderedProminent" data-default="" onclick={onconfirm}>{t(update ? "oll.updateShort" : "oll.installShort")}</Button>
    </footer>
  </div>
</div>

<style>
  .scrim { position: fixed; inset: 0; z-index: 320; display: flex; align-items: center; justify-content: center; padding: var(--space-4); background: var(--media-scrim-light); }
  .panel { box-sizing: border-box; width: min(440px, 100%); max-height: calc(100vh - var(--space-8)); overflow-y: auto; display: flex; flex-direction: column; gap: var(--space-4);
    padding: var(--space-6) var(--space-6) var(--space-5); border-radius: var(--radius-xl); background: var(--window-bg); box-shadow: var(--shadow-window); color: var(--label-primary); outline: none; }
  .head { display: flex; flex-direction: column; align-items: center; gap: var(--space-2); text-align: center; }
  .tile { width: 56px; height: 56px; display: inline-flex; align-items: center; justify-content: center; border-radius: var(--radius-lg);
    background: var(--system-blue); color: var(--on-accent); box-shadow: var(--shadow-rim); }
  h2, p { margin: 0; }
  .sub { color: var(--label-secondary); }
  .steps { list-style: none; margin: 0; padding: var(--space-1) 0; display: flex; flex-direction: column; border-radius: var(--radius-lg); background: var(--fill-quaternary); }
  .steps li { display: flex; align-items: center; gap: var(--space-3); padding: var(--space-2) var(--space-4); }
  .steps li + li { border-top: 1px solid var(--separator); }
  .num { flex: none; width: 20px; height: 20px; display: inline-flex; align-items: center; justify-content: center; border-radius: var(--radius-capsule);
    background: var(--accent); color: var(--on-accent); font-weight: 600; font-feature-settings: "tnum"; }
  .note { display: flex; align-items: flex-start; gap: var(--space-2); color: var(--label-secondary); }
  .note > :global(svg) { flex: none; margin-top: 2px; color: var(--system-green); }
  footer { display: flex; justify-content: flex-end; gap: var(--space-2); margin-top: var(--space-1); }
  @media (max-width: 480px) { .panel { padding: var(--space-5) var(--space-4) var(--space-4); } footer { flex-direction: column-reverse; } footer > :global(*) { width: 100%; } }
</style>
