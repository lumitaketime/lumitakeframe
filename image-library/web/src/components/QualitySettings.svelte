<script>
  /** 整理工具的判定標準：拖動就即時更新清單，不用每次請人改程式。 */
  import { api } from "../lib/api.js";
  import { refresh, toast } from "../lib/state.svelte.js";

  let { only = null } = $props();  // "blur" | "exposure" | null（全部）

  const DEFAULTS = { blur_threshold: 45, under_luma: 25, over_percent: 45 };
  let v = $state(null);
  let timer;

  $effect(() => {
    api("/api/settings").then((s) => (v = { blur_threshold: s.blur_threshold, under_luma: s.under_luma, over_percent: s.over_percent }));
  });

  function save(key, value) {
    v[key] = Number(value);
    clearTimeout(timer);
    timer = setTimeout(async () => {
      try {
        await api("/api/settings", { body: { [key]: Number(value) } });
        refresh();
      } catch (e) {
        toast(e.message, "error");
      }
    }, 350);
  }

  async function reset() {
    v = { ...DEFAULTS };
    await api("/api/settings", { body: DEFAULTS });
    toast("已恢復預設標準");
    refresh();
  }

  const blurLabel = (t) => (t <= 25 ? "只列很糊的" : t <= 55 ? "標準" : t <= 85 ? "嚴格" : "非常嚴格");
</script>

{#if v}
  <div class="qs">
    {#if only !== "exposure"}
      <label class="row">
        <span class="name">模糊判定<b>{blurLabel(v.blur_threshold)}</b></span>
        <input type="range" min="10" max="120" step="5" value={v.blur_threshold} oninput={(e) => save("blur_threshold", e.currentTarget.value)} />
        <span class="hint">往右越嚴格，稍微柔焦的照片也會列入；往左只列明顯失焦或手震的。目前門檻 {v.blur_threshold}。</span>
      </label>
    {/if}
    {#if only !== "blur"}
      <label class="row">
        <span class="name">欠曝判定<b>平均亮度低於 {v.under_luma}</b></span>
        <input type="range" min="8" max="60" step="1" value={v.under_luma} oninput={(e) => save("under_luma", e.currentTarget.value)} />
        <span class="hint">0 是全黑、255 是全白。往右會列入更多偏暗的照片；有燈光或亮部的夜景不會被列入。</span>
      </label>
      <label class="row">
        <span class="name">過曝判定<b>過亮像素超過 {v.over_percent}%</b></span>
        <input type="range" min="15" max="85" step="5" value={v.over_percent} oninput={(e) => save("over_percent", e.currentTarget.value)} />
        <span class="hint">往左會列入更多偏亮的照片（高調作品也可能被列入）。</span>
      </label>
    {/if}
    <button class="btn text small" onclick={reset}>恢復預設</button>
  </div>
{/if}

<style>
  .qs { display: flex; flex-direction: column; gap: 14px; align-items: flex-start; }
  .row { display: flex; flex-direction: column; gap: 4px; width: 100%; max-width: 560px; }
  .name { display: flex; justify-content: space-between; gap: 12px; font-size: 14px; font-weight: 500; }
  .name b { font-weight: 500; color: var(--primary); }
  input[type="range"] { width: 100%; }
  .hint { font-size: 12px; line-height: 16px; color: var(--on-surface-variant); }
</style>
