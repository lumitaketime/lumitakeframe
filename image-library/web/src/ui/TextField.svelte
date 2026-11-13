<script>
  /** 文字輸入框：單行、標籤一直看得到（不要只靠佔位文字）。error 會顯示在輸入框下方。 */
  import Icon from "./Icon.svelte";
  import { t } from "../i18n/index.svelte.js";
  import { usePlatform, TYPE, uid } from "./platform.js";

  let { label = "", placeholder = "", value = $bindable(""), onchange, secure = false, type = "text", clearButton = undefined, error = "", hint = "", disabled = false,
    leadingIcon = "", width = undefined, class: cls = "", ...rest } = $props();
  const platform = usePlatform();
  const id = uid("field");
  const showClear = $derived((clearButton !== undefined ? clearButton : platform === "ios") && value && !disabled);
  const w = $derived(typeof width === "number" ? `${width}px` : width || null);
</script>

<div class="lg-field lg-field-{platform} {cls}" class:lg-field-error={!!error} style:width={w}>
  {#if label}<label for={id} class="lg-field-label {platform === 'ios' ? 'ios-footnote' : 'mac-body'}">{label}</label>{/if}
  <div class="lg-field-box">
    {#if leadingIcon}<Icon name={leadingIcon} size={platform === "ios" ? 17 : 13} class="lg-field-lead" />{/if}
    <input {id} class={TYPE[platform].body} type={secure ? "password" : type} bind:value {placeholder} {disabled}
      aria-invalid={error ? true : undefined} aria-describedby={error || hint ? `${id}-msg` : undefined} oninput={() => onchange?.(value)} {...rest} />
    {#if showClear}
      <button type="button" class="lg-field-clear" aria-label={t("common.clearText")} onclick={() => { value = ""; onchange?.(""); }}>
        <span><Icon name="xmark" size={9} weight="bold" /></span>
      </button>
    {/if}
  </div>
  {#if error}
    <div id="{id}-msg" class="lg-field-msg lg-field-msg-error {TYPE[platform].footnote}"><Icon name="exclamation-triangle" size={platform === "ios" ? 14 : 11} weight="medium" />{error}</div>
  {:else if hint}
    <div id="{id}-msg" class="lg-field-msg {TYPE[platform].footnote}">{hint}</div>
  {/if}
</div>
