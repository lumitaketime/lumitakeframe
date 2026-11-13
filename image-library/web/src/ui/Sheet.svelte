<script>
  /** 表單：和目前情境相關的一件工作，有「取消」與「完成」。Mac 是附著在視窗上的面板，觸控裝置從底部滑出。 */
  import Button from "./Button.svelte";
  import { t } from "../i18n/index.svelte.js";
  import { usePlatform } from "./platform.js";

  let { title = "", detent = "large", grabber = undefined, cancelLabel = "", doneLabel = "", oncancel, ondone, doneDisabled = false, hideDone = false, symbols = true,
    height = undefined, platform: p = "", class: cls = "", children } = $props();
  // svelte-ignore state_referenced_locally（平台在元件建立時決定，之後不變）
  const platform = usePlatform(p);
  const cancel = $derived(cancelLabel || t("common.cancel"));
  const done = $derived(doneLabel || t("common.done"));
  const h = $derived(typeof height === "number" ? `${height}px` : height || null);
  const onkeydown = (e) => { if (e.key === "Escape") oncancel?.(); };
</script>

{#if platform === "mac"}
  <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
  <div role="dialog" tabindex="-1" aria-label={title || undefined} class="lg-sheet lg-sheet-mac {cls}" style:height={h} {onkeydown}>
    {#if title}<div class="lg-sheet-mac-title mac-title-3">{title}</div>{/if}
    <div class="lg-sheet-body">{@render children?.()}</div>
    <div class="lg-sheet-mac-actions">
      <Button platform="mac" variant="bordered" role="cancel" onclick={oncancel}>{cancel}</Button>
      {#if !hideDone}<Button platform="mac" variant="borderedProminent" disabled={doneDisabled} onclick={ondone}>{done}</Button>{/if}
    </div>
  </div>
{:else}
  <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
  <div role="dialog" tabindex="-1" aria-label={title || undefined} class="lg-sheet lg-sheet-ios lg-sheet-{detent} {cls}" style:height={h} {onkeydown}>
    {#if grabber !== undefined ? grabber : detent === "medium"}<div class="lg-grabber" aria-hidden="true"></div>{/if}
    <div class="lg-sheet-bar">
      {#if symbols}<Button platform="ios" variant="glass" iconOnly icon="xmark" aria-label={cancel} onclick={oncancel} />
      {:else}<Button platform="ios" variant="glass" onclick={oncancel}>{cancel}</Button>{/if}
      <div class="lg-sheet-title ios-headline">{title}</div>
      {#if hideDone}<span class="lg-sheet-spacer"></span>
      {:else if symbols}<Button platform="ios" variant="glassProminent" iconOnly icon="checkmark" aria-label={done} disabled={doneDisabled} onclick={ondone} />
      {:else}<Button platform="ios" variant="glassProminent" disabled={doneDisabled} onclick={ondone}>{done}</Button>{/if}
    </div>
    <div class="lg-sheet-body">{@render children?.()}</div>
  </div>
{/if}
