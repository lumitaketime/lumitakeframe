<script>
  /**
   * 工具列的搜尋欄（⌘F）：打字後 200 毫秒就到搜尋頁顯示結果。
   * 從資料夾開始搜尋時，範圍預設是「這個資料夾」；從類型頁開始則只找這個類型。結果頁上可以改成所有硬碟。
   * Esc：有字就清除，沒字就回到搜尋前的頁面。窄視窗時先顯示放大鏡按鈕，按了才展開。
   */
  import { untrack } from "svelte";
  import { Button, SearchField } from "../ui/index.js";
  import { t } from "../i18n/index.svelte.js";
  import { route, navigate, goBack } from "../lib/router.svelte.js";
  import { findParams, findHref } from "../data/find.svelte.js";

  let { narrow = false, expanded = $bindable(false) } = $props();

  const DELAY = 200;
  const page = $derived(route.path.split("/").filter(Boolean)[0] || "");
  const onFind = $derived(page === "find");
  let value = $state("");
  let input = $state();
  let timer = 0;

  // 搜尋頁的網址變了（上一頁、智慧資料夾）：搜尋欄跟著顯示；離開搜尋頁就清空
  $effect(() => {
    const q = onFind ? route.query.q || "" : "";
    untrack(() => {
      if (value.trim() === q) return; // 自己打的字（可能還在打空白）不要被改掉
      clearTimeout(timer);
      value = q;
    });
  });

  /** 開始搜尋時的範圍：目前所在的資料夾或類型 */
  function scopeHere() {
    const seg = route.path.split("/").filter(Boolean);
    if (seg[0] === "folders" && seg[1]) return { root: seg[1], path: route.query.path || "" };
    if (seg[0] === "kind" && seg[1]) return { kind: seg[1] };
    return {};
  }
  function go(text) {
    clearTimeout(timer);
    const q = text.trim();
    if (onFind) {
      const params = { ...findParams(route.query), q };
      navigate(findHref(params), { replace: true }); // 同一次搜尋只留一筆紀錄，按上一頁直接回到原來的資料夾
    } else if (q) {
      navigate(findHref({ ...scopeHere(), q }));
    }
  }
  // 中文輸入法正在組字（例如「ㄒㄧㄢˋ」）時不搜尋，選好字才搜尋；按 Enter 選字也不算送出
  let composing = false;
  function onchange(text) {
    clearTimeout(timer);
    if (composing) return;
    timer = setTimeout(() => go(text), DELAY);
  }
  function submit(text) {
    if (!composing) go(text);
  }
  function oncompositionstart() {
    composing = true;
    clearTimeout(timer);
  }
  function oncompositionend() {
    composing = false;
    onchange(value);
  }
  function onkeydown(e) {
    if (e.isComposing) return;
    if (e.key === "Escape") {
      e.preventDefault();
      if (value) {
        value = "";
        go("");
      } else {
        input?.blur();
        if (narrow) expanded = false;
        if (onFind) goBack("/folders");
      }
    }
  }
  function onfocusout(e) {
    if (narrow && !value && !e.currentTarget.contains(e.relatedTarget)) expanded = false;
  }
  async function expand() {
    expanded = true;
    await Promise.resolve();
    requestAnimationFrame(() => input?.focus());
  }
  $effect(() => {
    if (!narrow) expanded = false;
  });
</script>

{#if narrow && !expanded}
  <Button variant="glass" icon="magnifyingglass" iconOnly aria-label={t("find.field")} onclick={expand} />
{:else}
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div class="find" class:expanded={narrow && expanded} {onkeydown} {onfocusout} {oncompositionstart} {oncompositionend}>
    <SearchField glass bind:value bind:input placeholder={t("find.placeholder")} {onchange} onsubmit={submit} width="100%" />
  </div>
{/if}

<style>
  .find { width: 100%; min-width: 0; }
  /* 焦點框畫在整個搜尋欄外圍（.lg-search:focus-within），裡面的輸入框不要再畫一圈 */
  .find :global(.lg-search input:focus-visible) { box-shadow: none; }
  .find.expanded { position: absolute; left: var(--space-2); right: var(--space-2); top: calc(var(--space-2) + env(safe-area-inset-top)); z-index: 40; }
</style>
