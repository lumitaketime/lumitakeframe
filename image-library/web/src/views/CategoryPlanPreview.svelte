<script>
  /**
   * 分類整理計畫的預覽（計畫卡、關鍵字雲共用）：
   * - 每一類套用後有幾個資料夾（和現在比），新的分類標「新」，拆掉或合併掉的分類列在下面；
   * - 哪些資料夾會換分類（原本 → 之後、幾個、舉例）；
   * - 有幾個資料夾要你確認（例如看不出年份、你原本手動設的那一類被拆開）。
   * 預覽是在目錄裡試做一次再全部取消，不會改到任何東西。
   */
  import { navigate } from "../lib/router.svelte.js";
  import { t, formatNumber } from "../i18n/index.svelte.js";
  import { prettyName } from "../lib/names.js";

  let { preview, done = false, compact = false } = $props();
  const none = (n) => n || t("plan.uncategorized");
  const href = (e) => `/folders/${e.root_id}?path=${encodeURIComponent(e.path)}`;
  const open = (e, ev) => { ev.preventDefault(); navigate(href(e)); };
  // 表格只列出會變動的分類（新的、數量變了的）；其他的收起來，要看再展開
  let all = $state(false);
  const changedCats = $derived((preview.categories || []).filter((c) => c.new || c.folders !== c.before));
  const rows = $derived(all || !changedCats.length ? preview.categories || [] : changedCats);
  const hidden = $derived((preview.categories?.length || 0) - changedCats.length);
</script>

<div class="pv mac-callout">
  {#if !done}
    <p class="lead">{preview.changed ? t("plan.changed", { n: formatNumber(preview.changed) }) : t("plan.noChange")}
      {#if preview.review}<span class="warn">{t("plan.review", { n: formatNumber(preview.review) })}</span>{/if}</p>
  {/if}
  {#if !compact && preview.categories?.length}
    <table class="cats">
      <thead><tr><th>{t("plan.category")}</th><th class="num">{t("plan.before")}</th><th class="num">{t("plan.after")}</th></tr></thead>
      <tbody>
        {#each rows as c (c.key)}
          <tr>
            <td><span class="cname">{c.name}</span>{#if c.new}<span class="tag new">{t("plan.new")}</span>{/if}
              {#if c.description}<span class="desc">{c.description}</span>{/if}</td>
            <td class="num sub">{formatNumber(c.before)}</td>
            <td class="num" class:up={c.folders > c.before} class:down={c.folders < c.before}>{formatNumber(c.folders)}</td>
          </tr>
        {/each}
        {#each preview.removed || [] as c (c.key)}
          <tr class="gone"><td><span class="cname">{c.name}</span><span class="tag">{t("plan.removed")}</span></td>
            <td class="num sub">{formatNumber(c.folders)}</td><td class="num">0</td></tr>
        {/each}
      </tbody>
    </table>
    {#if changedCats.length && hidden > 0}
      <button type="button" class="all mac-caption-1" onclick={() => (all = !all)}>{all ? t("plan.onlyChanged") : t("plan.showAll", { n: formatNumber(hidden) })}</button>
    {/if}
  {/if}
  {#if preview.changes?.length}
    <ul class="changes">
      {#each preview.changes.slice(0, compact ? 4 : 8) as ch, i (i)}
        <li>
          <span class="move"><span class="sub">{none(ch.from_name)}</span><span class="arrow">→</span><b>{none(ch.to_name)}</b>
            <span class="sub">{t("plan.folders", { n: formatNumber(ch.count) })}</span></span>
          <span class="ex sub">{t("plan.example")}{#each ch.examples as e, j (e.id)}{j ? "、" : ""}<a href={href(e)} onclick={(ev) => open(e, ev)} title={e.path}>{prettyName(e.name)}</a>{/each}</span>
        </li>
      {/each}
    </ul>
  {/if}
</div>

<style>
  .pv { display: flex; flex-direction: column; gap: var(--space-2); }
  .lead { margin: 0; color: var(--label-primary); }
  .warn { margin-left: var(--space-2); color: var(--system-orange); }
  .sub { color: var(--label-secondary); }
  .cats { width: 100%; border-collapse: collapse; }
  .cats th { text-align: left; font-weight: 600; color: var(--label-secondary); padding: 2px var(--space-2) 2px 0; border-bottom: 1px solid var(--separator); }
  .cats td { padding: 3px var(--space-2) 3px 0; vertical-align: top; border-bottom: 1px solid var(--separator); }
  .num { text-align: right; white-space: nowrap; font-feature-settings: "tnum"; }
  .up { color: var(--system-green); font-weight: 600; }
  .down { color: var(--system-orange); }
  .cname { font-weight: 600; color: var(--label-primary); }
  .desc { display: block; color: var(--label-secondary); }
  .tag { margin-left: var(--space-1); padding: 0 var(--space-1); border-radius: var(--radius-sm); background: var(--fill-tertiary); color: var(--label-secondary); }
  .tag.new { background: var(--accent); color: var(--on-accent); }
  .gone .cname { color: var(--label-secondary); text-decoration: line-through; }
  .changes { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: var(--space-1); }
  .changes li { display: flex; flex-direction: column; min-width: 0; }
  .move { display: flex; align-items: baseline; gap: var(--space-1); flex-wrap: wrap; }
  .arrow { color: var(--label-secondary); }
  .ex { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .ex a { color: var(--accent); text-decoration: none; }
  .all { align-self: flex-start; border: 0; padding: 0; background: none; color: var(--accent); font: inherit; cursor: pointer; }
  .ex a:hover { text-decoration: underline; }
</style>
