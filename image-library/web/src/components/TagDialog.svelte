<script>
  import { slider } from "../lib/slider.js";
  /**
   * 批次加上（或移除）我的標籤，例如 #嘉義車站。
   * 標籤和 AI 關鍵字一起被搜尋，也會出現在關鍵字雲；RAW 會寫入 .xmp，Lightroom 看得到。
   */
  import Modal from "./Modal.svelte";
  import Icon from "./Icon.svelte";
  import { api } from "../lib/api.js";
  import { refresh, toast } from "../lib/state.svelte.js";
  import { mdiClose, mdiPound } from "../lib/icons.js";

  let { ids = [], onclose } = $props();

  let mode = $state("add");
  let tags = $state([]);
  let text = $state("");
  let known = $state([]);
  let sending = $state(false);
  let input = $state();

  $effect(() => {
    api("/api/keywords", { params: { source: "mine", limit: 400 } }).then((r) => (known = r.keywords)).catch(() => {});
    setTimeout(() => input?.focus(), 250);
  });

  const query = $derived(text.trim().replace(/^#/, "").toLowerCase());
  const suggestions = $derived(
    known.filter((k) => !tags.some((t) => t.toLowerCase() === k.tag.toLowerCase()) && (!query || k.tag.toLowerCase().includes(query))).slice(0, 12),
  );

  function add(raw) {
    for (const part of String(raw).split(/[,，、\n]/)) {
      const t = part.trim().replace(/^#+/, "").trim();
      if (t && !tags.some((x) => x.toLowerCase() === t.toLowerCase())) tags = [...tags, t];
    }
    text = "";
  }

  function onkey(e) {
    if ((e.key === "Enter" || e.key === "," || e.key === "，") && !e.isComposing) {
      e.preventDefault();
      if (text.trim()) add(text);
      else if (e.key === "Enter" && tags.length) submit();
    } else if (e.key === "Backspace" && !text && tags.length) {
      tags = tags.slice(0, -1);
    }
  }

  async function submit() {
    if (text.trim()) add(text);
    if (!tags.length) return;
    sending = true;
    try {
      const r = await api("/api/assets/bulk", { body: { ids, action: mode === "add" ? "add_tags" : "remove_tags", tags } });
      const label = tags.map((t) => `#${t}`).join(" ");
      if (r.errors?.length) toast(`已更新 ${r.done} 張，但有 ${r.errors.length} 個檔案無法寫回：${r.errors[0]}`, "error");
      else toast(mode === "add" ? `已為 ${r.done} 張加上 ${label}` : `已從 ${r.done} 張移除 ${label}`, "info", 6000,
        mode === "add" ? { label: "復原", run: () => undo(label) } : null);
      refresh();
      onclose?.(true);
    } catch (e) {
      toast(e.message, "error");
    } finally {
      sending = false;
    }
  }

  async function undo(label) {
    await api("/api/assets/bulk", { body: { ids, action: "remove_tags", tags } });
    toast(`已移除 ${label}`);
    refresh();
  }
</script>

<Modal title="{mode === 'add' ? '加上標籤' : '移除標籤'}（{ids.length} 張）" onclose={() => onclose?.(false)}>
  <div class="form">
    <div class="seg" role="tablist" use:slider>
      <button class:on={mode === "add"} onclick={() => (mode = "add")}>加上</button>
      <button class:on={mode === "remove"} onclick={() => (mode = "remove")}>移除</button>
    </div>
    <label class="field">
      <Icon path={mdiPound} size={20} />
      {#each tags as t (t)}
        <span class="tag">{t}<button onclick={() => (tags = tags.filter((x) => x !== t))} aria-label="移除 {t}"><Icon path={mdiClose} size={14} /></button></span>
      {/each}
      <input bind:this={input} bind:value={text} onkeydown={onkey} placeholder={tags.length ? "" : "輸入標籤，例如 嘉義車站，按 Enter"} aria-label="標籤" />
    </label>
    {#if suggestions.length}
      <div class="sugg">
        <span class="hint">{query ? "符合的標籤" : "常用的標籤"}</span>
        <div class="chips">
          {#each suggestions as k (k.tag)}<button class="chip" onclick={() => add(k.tag)}>#{k.tag}<span class="n">{k.count}</span></button>{/each}
        </div>
      </div>
    {/if}
    <p class="hint">標籤會和 AI 關鍵字一起被搜尋，也會出現在關鍵字雲。RAW 檔會寫入 .xmp，Lightroom 讀取中繼資料後就看得到。</p>
  </div>
  {#snippet actions()}
    <button class="btn ghost" onclick={() => onclose?.(false)}>取消</button>
    <button class="btn" class:danger={mode === "remove"} onclick={submit} disabled={sending || (!tags.length && !text.trim())}>
      {#if sending}<span class="spinner"></span>{/if}{mode === "add" ? "加上標籤" : "移除標籤"}
    </button>
  {/snippet}
</Modal>

<style>
  .form { display: flex; flex-direction: column; gap: 14px; color: var(--on-surface); }
  .seg { display: inline-flex; align-self: flex-start; border: 1px solid var(--outline); border-radius: var(--corner-full); overflow: hidden; }
  .seg button { border: 0; background: none; color: var(--on-surface); padding: 0 18px; height: 36px; font-weight: 500; cursor: pointer; }
  .seg button + button { border-left: 1px solid var(--outline); }
  .seg button.on { background: var(--secondary-container); color: var(--on-secondary-container); }
  .field {
    display: flex; flex-wrap: wrap; align-items: center; gap: 6px; min-height: 56px; padding: 8px 12px; cursor: text;
    border: 1px solid var(--outline); border-radius: var(--corner-extra-small); color: var(--on-surface-variant);
  }
  .field:focus-within { border-color: var(--primary); box-shadow: inset 0 0 0 1px var(--primary); }
  .field input { flex: 1; min-width: 160px; border: 0; outline: none; background: none; font-size: 16px; color: var(--on-surface); }
  .tag {
    display: inline-flex; align-items: center; gap: 2px; height: 32px; padding: 0 4px 0 12px; border-radius: var(--corner-small);
    background: var(--secondary-container); color: var(--on-secondary-container); font-weight: 500;
    animation: m3-pop var(--spring-expressive-fast-spatial-duration) var(--spring-expressive-fast-spatial);
  }
  .tag button { border: 0; background: none; color: inherit; display: flex; padding: 4px; border-radius: 50%; cursor: pointer; }
  .tag button:hover { background: color-mix(in srgb, currentColor 12%, transparent); }
  .sugg { display: flex; flex-direction: column; gap: 6px; }
  .n { font-size: 11px; color: var(--on-surface-variant); }
  .hint { font-size: 12px; line-height: 16px; color: var(--on-surface-variant); margin: 0; }
  .spinner { width: 14px; height: 14px; }
</style>
