<script>
  /**
   * 選擇相簿或資料夾的封面：
   * 上方是封面預覽（和相簿、資料夾列表的卡片同樣的圓角方形），可選「自動（最新的照片）」或「自己選一張」；
   * 下方列出這個相簿／資料夾（含子資料夾）裡的照片，點一張就換成那張。
   */
  import Modal from "./Modal.svelte";
  import Loading from "./Loading.svelte";
  import Icon from "./Icon.svelte";
  import { api, thumbUrl } from "../lib/api.js";
  import { slider } from "../lib/slider.js";
  import { mdiCheckCircle, mdiImageOutline } from "../lib/icons.js";

  /** scope：搜尋範圍字串（album:3、folder:1:旅行/京都）；current：目前自訂的封面（null＝自動）；auto：自動時會用的照片 */
  let { title = "", scope, current = null, auto = null, onsave, onclose } = $props();

  // svelte-ignore state_referenced_locally
  let picked = $state(current);
  // svelte-ignore state_referenced_locally
  let mode = $state(current ? "custom" : "auto");
  let items = $state(null);
  let total = $state(0);
  let saving = $state(false);
  const PAGE = 300;

  async function load(more = false) {
    const data = await api("/api/search", { params: { q: "", scope, smart: 0, limit: PAGE, offset: more ? items.length : 0 } });
    items = more ? [...items, ...data.results] : data.results;
    total = data.total;
  }
  load().catch(() => (items = []));

  const preview = $derived(mode === "custom" ? picked : auto ?? items?.[0]?.id ?? null);

  function pick(id) {
    picked = id;
    mode = "custom";
  }

  async function save() {
    saving = true;
    try {
      await onsave?.(mode === "custom" ? picked : null);
      onclose?.(true);
    } finally {
      saving = false;
    }
  }
</script>

<Modal title="選擇封面" wide onclose={() => onclose?.(false)}>
  <div class="head">
    <div class="preview">
      {#key preview}
        {#if preview}<img src={thumbUrl({ id: preview })} alt="封面預覽" />{:else}<Icon path={mdiImageOutline} size={40} />{/if}
      {/key}
    </div>
    <div class="info">
      <b>{title}</b>
      <div class="seg" role="radiogroup" aria-label="封面" use:slider>
        <button role="radio" aria-checked={mode === "auto"} class:on={mode === "auto"} onclick={() => (mode = "auto")}>自動</button>
        <button role="radio" aria-checked={mode === "custom"} class:on={mode === "custom"} disabled={!picked} onclick={() => (mode = "custom")}>自選</button>
      </div>
      <span class="hint">{mode === "auto" ? "使用最新的一張照片，加入新照片時會跟著換。" : "固定使用這一張。"}</span>
    </div>
  </div>

  {#if !items}
    <Loading kind="grid" count={12} />
  {:else if !items.length}
    <p class="empty-note">這裡還沒有照片。</p>
  {:else}
    <div class="grid" role="listbox" aria-label="選擇封面照片">
      {#each items as a (a.id)}
        <button class="cell" class:sel={mode === "custom" && picked === a.id} role="option" aria-selected={mode === "custom" && picked === a.id}
          title={a.name} onclick={() => pick(a.id)}>
          <img src={thumbUrl(a)} alt="" loading="lazy" decoding="async" />
          {#if mode === "custom" && picked === a.id}<span class="mark"><Icon path={mdiCheckCircle} size={22} /></span>{/if}
        </button>
      {/each}
    </div>
    {#if items.length < total}
      <p class="more"><button class="btn text small" onclick={() => load(true)}>再顯示 {Math.min(PAGE, total - items.length)} 張（共 {total.toLocaleString()} 張）</button></p>
    {/if}
  {/if}

  {#snippet actions()}
    <button class="btn ghost" onclick={() => onclose?.(false)}>取消</button>
    <button class="btn" onclick={save} disabled={saving || (mode === "custom" && !picked)}>{#if saving}<span class="spinner"></span>{/if}儲存</button>
  {/snippet}
</Modal>

<style>
  .head { display: flex; gap: 20px; align-items: center; margin-bottom: 20px; }
  .preview {
    width: 112px; height: 112px; flex-shrink: 0; border-radius: var(--corner-large); overflow: hidden;
    background: var(--surface-container-highest); color: var(--on-surface-variant); display: flex; align-items: center; justify-content: center;
  }
  .preview img { width: 100%; height: 100%; object-fit: cover; animation: m3-fade var(--duration-medium2) var(--easing-standard); }
  .info { display: flex; flex-direction: column; gap: 10px; min-width: 0; }
  .info b { color: var(--on-surface); font-weight: 500; font-size: var(--text-title-3); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .hint { font-size: var(--text-callout); line-height: 16px; }
  .seg { display: inline-flex; align-self: flex-start; border: 1px solid var(--outline); border-radius: var(--corner-full); overflow: hidden; }
  .seg button { border: 0; background: none; color: var(--on-surface); height: 36px; padding: 0 20px; font-size: var(--text-body); font-weight: 500; cursor: pointer; }
  .seg button + button { border-left: 1px solid var(--outline); }
  .seg button.on { color: var(--on-secondary-container); }
  .seg button:disabled { color: color-mix(in srgb, var(--on-surface) 38%, transparent); cursor: default; }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(84px, 1fr)); gap: 4px; }
  .cell {
    position: relative; aspect-ratio: 1; padding: 0; border: 0; cursor: pointer; overflow: hidden; border-radius: var(--corner-small);
    background: var(--surface-container-highest);
    transition: border-radius var(--spring-expressive-fast-spatial-duration) var(--spring-expressive-fast-spatial);
  }
  .cell img {
    width: 100%; height: 100%; object-fit: cover; display: block;
    transition: transform var(--spring-expressive-fast-spatial-duration) var(--spring-expressive-fast-spatial);
  }
  .cell:hover { border-radius: var(--corner-medium); }
  .cell.sel { border-radius: var(--corner-large); outline: 3px solid var(--primary); outline-offset: -3px; }
  .cell.sel img { transform: scale(.88); border-radius: var(--corner-medium); }
  .mark { position: absolute; top: 4px; left: 4px; color: var(--primary); background: var(--surface-container-high); border-radius: 50%; display: flex; }
  .cell:focus-visible { outline: 3px solid var(--primary); outline-offset: -3px; }
  .more { text-align: center; margin: 12px 0 0; }
  .empty-note { text-align: center; padding: 24px; }
  @media (max-width: 520px) { .head { gap: 14px; } .preview { width: 88px; height: 88px; } }
</style>
