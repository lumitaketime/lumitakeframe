<script>
  /**
   * 自動分類的三個選擇（第一次詢問、首次使用的教學、設定頁共用）：
   * 掃描完用規則分類、規則分不出來的在夜間交給 AI、AI 可以讀文件開頭一小段（只在這台電腦上的模型）。
   */
  import { Checkbox } from "../ui/index.js";
  import { t } from "../i18n/index.svelte.js";

  let { value = $bindable({ rules_auto: true, ai_auto: true, read_text: true }) } = $props();
  const ITEMS = [
    { key: "rules_auto", icon: "tag" },
    { key: "ai_auto", icon: "sparkles" },
    { key: "read_text", icon: "document" },
  ];
</script>

<ul class="choices">
  {#each ITEMS as it (it.key)}
    <li class:off={it.key === "read_text" && !value.ai_auto}>
      <Checkbox checked={value[it.key]} disabled={it.key === "read_text" && !value.ai_auto}
        onchange={(v) => (value = { ...value, [it.key]: v })} label={t(`cat.choice.${it.key}`)} />
      <p class="mac-callout sub">{t(`cat.choice.${it.key}.hint`)}</p>
    </li>
  {/each}
</ul>

<style>
  .choices { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: var(--space-2); }
  li { display: flex; flex-direction: column; gap: var(--space-1); padding: var(--space-3); border-radius: var(--radius-md); background: var(--fill-quaternary); }
  li.off { opacity: .6; }
  .sub { margin: 0; padding-left: calc(var(--space-5) + var(--space-1)); color: var(--label-secondary); }
</style>
