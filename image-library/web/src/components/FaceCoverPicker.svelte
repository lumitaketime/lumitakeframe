<script>
  /**
   * 人物的封面：列出偵測到的每一張臉（清楚的排前面），點一張當作封面。
   */
  import Modal from "./Modal.svelte";
  import Loading from "./Loading.svelte";
  import Icon from "./Icon.svelte";
  import { api } from "../lib/api.js";
  import { mdiCheckCircle } from "../lib/icons.js";

  let { kind = "person", id, name = "", current = null, onsave, onclose } = $props();

  // svelte-ignore state_referenced_locally
  let picked = $state(current);
  let faces = $state(null);
  let saving = $state(false);

  const thumb = (faceId) => `/api/faces/${faceId}/thumb`;
  // svelte-ignore state_referenced_locally
  api(`/api/people/${id}/faces`).then((f) => (faces = f)).catch(() => (faces = []));

  async function save() {
    saving = true;
    try {
      await onsave?.(picked);
      onclose?.(true);
    } finally {
      saving = false;
    }
  }
</script>

<Modal title="選擇封面" wide onclose={() => onclose?.(false)}>
  <div class="head">
    <div class="preview">
      {#key picked}{#if picked}<img src={thumb(picked)} alt="" />{/if}{/key}
    </div>
    <div class="info">
      <b>{name || "這個人物"}</b>
      <span>點下面任何一張臉，當作這個人在人物、搜尋建議和探索裡的頭像。</span>
    </div>
  </div>
  {#if !faces}
    <Loading kind="cards" round count={12} />
  {:else if !faces.length}
    <p class="empty-note">沒有可以選的臉。</p>
  {:else}
    <div class="grid" role="listbox" aria-label="選擇封面">
      {#each faces as f (f.id)}
        <button class="face" class:sel={picked === f.id} role="option" aria-selected={picked === f.id} onclick={() => (picked = f.id)}>
          <img src={thumb(f.id)} alt="" loading="lazy" decoding="async" />
          {#if picked === f.id}<span class="mark"><Icon path={mdiCheckCircle} size={20} /></span>{/if}
        </button>
      {/each}
    </div>
  {/if}

  {#snippet actions()}
    <button class="btn ghost" onclick={() => onclose?.(false)}>取消</button>
    <button class="btn" onclick={save} disabled={saving || !picked || picked === current}>{#if saving}<span class="spinner"></span>{/if}儲存</button>
  {/snippet}
</Modal>

<style>
  .head { display: flex; gap: 20px; align-items: center; margin-bottom: 20px; }
  .preview { width: 96px; height: 96px; border-radius: 50%; overflow: hidden; flex-shrink: 0; background: var(--surface-container-highest); }
  .preview img { width: 100%; height: 100%; object-fit: cover; animation: m3-fade var(--duration-medium2) var(--easing-standard); }
  .info { display: flex; flex-direction: column; gap: 6px; min-width: 0; font-size: 14px; line-height: 20px; }
  .info b { color: var(--on-surface); font-weight: 500; font-size: 16px; }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(72px, 1fr)); gap: 12px; }
  .face {
    position: relative; aspect-ratio: 1; border-radius: 50%; padding: 0; border: 0; cursor: pointer; background: var(--surface-container-highest);
    transition: transform var(--spring-expressive-fast-spatial-duration) var(--spring-expressive-fast-spatial);
  }
  .face img { width: 100%; height: 100%; object-fit: cover; border-radius: 50%; display: block; }
  .face:hover { transform: scale(1.05); }
  .face.sel { outline: 3px solid var(--primary); outline-offset: 3px; transform: scale(.94); }
  .face:focus-visible { outline: 3px solid var(--primary); outline-offset: 3px; }
  .mark { position: absolute; right: -4px; bottom: -4px; color: var(--primary); background: var(--surface-container-high); border-radius: 50%; display: flex; }
  .empty-note { text-align: center; padding: 24px; }
</style>
