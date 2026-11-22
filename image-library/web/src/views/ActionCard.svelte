<script>
  /**
   * 助理提出的一個動作：列出要做什麼（原本 → 之後），本人勾選、按「執行」才做；會動到硬碟的動作再跳一次確認。
   * 做完顯示每一項的結果，可以「復原」。核心原則一：助理只提案，動手的永遠是本人；沒有刪除這個動作。
   */
  import { Alert, Button, Checkbox, Icon } from "../ui/index.js";
  import { runAction, undoAction, dismissAction } from "../data/assistant.js";
  import { t, formatBytes, formatNumber } from "../i18n/index.svelte.js";
  import { toast, refresh } from "../lib/state.svelte.js";

  let { action = $bindable(), compact = false } = $props();

  import CategoryPlanPreview from "./CategoryPlanPreview.svelte";

  const ICON = { label: "star", smart_folder: "magnifyingglass", mark_delete: "trash", move: "folder", rename: "compose", to_pending: "trash",
    category_rule: "tag", category_plan: "tag" };
  // 分類的整理計畫：看不懂的那一步預設不勾
  const isPlan = $derived(action.kind === "category_plan" || action.kind === "category_rule");
  const SHOW = 6;
  let expanded = $state(false);
  // svelte-ignore state_referenced_locally（一開始全部勾選；項目數變了才重來）
  let checked = $state(action.items.map((it) => it.ok !== false));
  $effect(() => {
    if (checked.length !== action.items.length) checked = action.items.map((it) => it.ok !== false);
  });
  const chosen = $derived(checked.map((c, i) => (c ? i : -1)).filter((i) => i >= 0));
  const visible = $derived(expanded ? action.items : action.items.slice(0, SHOW));
  const proposed = $derived(action.state === "proposed");
  const canUndo = $derived(action.state === "done" || action.state === "partial");
  let busy = $state(false);
  let confirm = $state(null); // "run" | "undo"

  async function call(fn) {
    busy = true;
    confirm = null;
    try {
      action = await fn();
      if (action.message) toast(action.message, action.state === "failed" ? "error" : "info");
      refresh();
    } catch (e) {
      toast(e.message, "error");
    } finally {
      busy = false;
    }
  }
  const run = () => call(() => runAction(action.id, chosen.length === action.items.length ? undefined : chosen));
  const undo = () => call(() => undoAction(action.id));
  const dismiss = () => call(() => dismissAction(action.id));
  function pressRun() {
    if (action.file_op) confirm = "run";
    else run();
  }
  function pressUndo() {
    if (action.file_op) confirm = "undo";
    else undo();
  }
  const top = (p) => p || t("act.top");
  const parent = (p) => (p && p.includes("/") ? p.slice(0, p.lastIndexOf("/")) : "");
</script>

<section class="card" class:compact aria-label={action.summary}>
  <header>
    <Icon name={ICON[action.kind] || "sparkles"} size={15} />
    <div class="head">
      <b class="mac-body">{action.summary}</b>
      <span class="meta mac-caption-1">
        <span class="state s-{action.state}">{t(`act.state.${action.state}`)}</span>
        <span class:disk={action.file_op}>{action.file_op ? t("act.disk") : t("act.catalog")}</span>
      </span>
    </div>
  </header>

  {#if isPlan && action.preview}
    <CategoryPlanPreview preview={action.preview} done={!proposed} />
    {#if action.items.length}<h4 class="mac-caption-1 steps">{t("plan.steps")}</h4>{/if}
  {/if}
  {#if action.kind === "smart_folder"}
    <p class="mac-callout sub">{t("act.smart", { q: action.query?.q || "" })}</p>
  {:else if action.items.length}
    <ul class="items mac-callout">
      {#each visible as it, i (i)}
        <li>
          {#if proposed && action.items.length > 1}
            <Checkbox bind:checked={checked[i]} aria-label={it.name} />
          {/if}
          <div class="what">
            <span class="name">{it.name}</span>
            {#if action.file_op && it.to}
              <span class="path sub"><span>{top(parent(it.from))}</span><span class="arrow">→</span><span class="to">{action.kind === "rename" ? it.new_name : top(parent(it.to))}</span></span>
            {:else}
              <span class="path sub">{[it.drive, it.type === "folder" ? it.from : parent(it.from)].filter(Boolean).join(" › ")}{it.size ? ` · ${formatBytes(it.size)}` : ""}</span>
            {/if}
            {#if it.reason}<span class="reason">{it.reason}</span>{/if}
          </div>
          {#if it.status}<span class="st st-{it.status} mac-caption-1">{t(`act.item.${it.status}`)}</span>{/if}
        </li>
      {/each}
    </ul>
    {#if action.items.length > SHOW && !expanded}
      <button type="button" class="more mac-callout" onclick={() => (expanded = true)}>{t("act.more", { n: formatNumber(action.items.length - SHOW) })}</button>
    {/if}
  {/if}
  {#if action.kind === "label"}
    <p class="mac-caption-1 sub">{action.color ? t(`label.${action.color}`) : t("act.noLabel")}</p>
  {/if}

  {#if proposed}
    <div class="acts">
      <Button size="small" variant="borderedProminent" loading={busy} disabled={!chosen.length} onclick={pressRun}>{isPlan ? t("plan.apply") : t("act.run")}</Button>
      <Button size="small" variant="bordered" disabled={busy} onclick={dismiss}>{t("act.dismiss")}</Button>
    </div>
  {:else if canUndo}
    <div class="acts">
      <Button size="small" variant="bordered" icon="undo" loading={busy} onclick={pressUndo}>{t("act.undo")}</Button>
      {#if action.message}<span class="mac-caption-1 sub">{action.message}</span>{/if}
    </div>
  {/if}
</section>

{#if confirm}
  <div class="backdrop">
    <Alert title={confirm === "run" ? t(`act.confirm.${action.kind}`, { n: formatNumber(chosen.length) }) : t("act.undoTitle")}
      message={confirm === "run" ? t("act.confirmMessage") : t("act.undoMessage")} actions={[
        { label: confirm === "run" ? t("act.run") : t("act.undo"), role: "default", onPress: confirm === "run" ? run : undo },
        { label: t("common.cancel"), role: "cancel", onPress: () => (confirm = null) },
      ]} />
  </div>
{/if}

<style>
  .card { display: flex; flex-direction: column; gap: var(--space-2); margin-top: var(--space-2); padding: var(--space-2) var(--space-3);
    border-radius: var(--radius-md); background: var(--bg-primary); box-shadow: inset 0 0 0 1px var(--separator); }
  .card.compact { margin-top: 0; }
  header { display: flex; align-items: flex-start; gap: var(--space-2); }
  header > :global(svg) { flex: none; margin-top: 3px; color: var(--accent); }
  .head { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
  .meta { display: flex; flex-wrap: wrap; gap: var(--space-2); color: var(--label-secondary); }
  .disk { color: var(--system-orange); }
  .state { font-weight: 600; }
  .s-done, .s-undone { color: var(--system-green); }
  .s-failed { color: var(--system-red); }
  .sub { color: var(--label-secondary); margin: 0; }
  .items { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: var(--space-1); }
  .items li { display: flex; align-items: flex-start; gap: var(--space-2); }
  .what { display: flex; flex-direction: column; min-width: 0; flex: 1; }
  .name, .path { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .path { display: flex; gap: var(--space-1); min-width: 0; }
  .path > span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .arrow { flex: none; }
  .to { color: var(--label-primary); }
  .reason { color: var(--system-orange); }
  .st { flex: none; color: var(--label-secondary); }
  .st-done, .st-undone { color: var(--system-green); }
  .st-skipped { color: var(--system-orange); }
  .more { align-self: flex-start; border: 0; padding: 0; background: none; color: var(--accent); font: inherit; cursor: pointer; }
  .acts { display: flex; align-items: center; flex-wrap: wrap; gap: var(--space-2); }
  .steps { margin: var(--space-1) 0 0; color: var(--label-secondary); font-weight: 600; }
  .backdrop { position: fixed; inset: 0; z-index: 320; display: flex; align-items: center; justify-content: center; background: var(--media-scrim-light); }
</style>
