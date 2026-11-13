<script>
  /**
   * 警示視窗：需要立刻處理的關鍵資訊，最多三個按鈕。
   * 標題要具體（「要把 128 個項目移到垃圾桶嗎？」），取消一律叫「取消」；按鈕順序自動依規範排列，Escape 等同取消。
   * actions：{label, role: "default" | "cancel" | "destructive", onPress, disabled}
   */
  import Button from "./Button.svelte";
  import Checkbox from "./Checkbox.svelte";
  import TextField from "./TextField.svelte";
  import { t } from "../i18n/index.svelte.js";
  import { usePlatform, uid } from "./platform.js";

  let { title, message = "", actions = undefined, icon, textField = undefined, suppression = "", presented = false, platform: p = "", class: cls = "" } = $props();
  // svelte-ignore state_referenced_locally（平台在元件建立時決定，之後不變）
  const platform = usePlatform(p);
  const id = uid("alert");
  const list = $derived((actions || [{ label: t("common.ok"), role: "default" }]).slice(0, 3));
  const stacked = $derived(list.length > 2);
  const ordered = $derived.by(() => {
    const cancel = list.filter((a) => a.role === "cancel");
    const def = list.filter((a) => a.role === "default");
    const rest = list.filter((a) => a.role !== "cancel" && a.role !== "default");
    return stacked ? [...def, ...rest, ...cancel] : [...cancel, ...rest, ...def];
  });
  let card = $state();
  $effect(() => {
    if (presented && card) (card.querySelector("[data-default]") || card.querySelector("button"))?.focus();
  });
  function onkeydown(e) {
    if (e.key === "Escape") {
      const cancel = list.find((a) => a.role === "cancel");
      if (cancel && !cancel.disabled) { e.preventDefault(); cancel.onPress?.(); }
    }
  }
</script>

{#snippet body()}
  <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
  <div bind:this={card} role="alertdialog" tabindex="-1" aria-modal={presented || undefined} aria-labelledby="{id}-t" aria-describedby={message ? `${id}-m` : undefined}
    class="lg-alert lg-alert-{platform} lg-glass lg-glass-regular {cls}" {onkeydown}>
    {#if platform === "mac" && icon}<div class="lg-alert-icon">{@render icon()}</div>{/if}
    <div id="{id}-t" class="lg-alert-title {platform === 'ios' ? 'ios-headline' : 'mac-headline'}">{title}</div>
    {#if message}<div id="{id}-m" class="lg-alert-msg {platform === 'ios' ? 'ios-footnote' : 'mac-callout'}">{message}</div>{/if}
    {#if textField}<div class="lg-alert-field"><TextField placeholder={textField.placeholder} secure={textField.secure} clearButton={false} /></div>{/if}
    {#if suppression && platform === "mac"}<div class="lg-alert-suppress"><Checkbox label={suppression} /></div>{/if}
    <div class="lg-alert-actions {stacked ? 'lg-stacked' : 'lg-row'}">
      {#each ordered as a, i (i)}
        <Button {platform} size="large" variant={a.role === "default" ? "borderedProminent" : "bordered"}
          role={a.role === "destructive" ? "destructive" : a.role === "cancel" ? "cancel" : "normal"} disabled={a.disabled} onclick={a.onPress}
          class="lg-alert-btn" data-default={a.role === "default" ? "" : undefined}>{a.label}</Button>
      {/each}
    </div>
  </div>
{/snippet}

{#if presented}<div class="lg-scrim">{@render body()}</div>{:else}{@render body()}{/if}
