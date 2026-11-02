<script>
  import Icon from "./Icon.svelte";
  import { app, selection } from "../lib/state.svelte.js";
  import { addToAlbum, analyzeAssets, moveAssets, removeFromAlbum, setFavorite, trashAssets } from "../lib/actions.js";
  import { api } from "../lib/api.js";
  import { toast, refresh } from "../lib/state.svelte.js";
  import {
    mdiClose, mdiHeartOutline, mdiImageAlbum, mdiFolderMoveOutline, mdiCreation, mdiDeleteOutline, mdiImageRemoveOutline, mdiImageOutline,
  } from "../lib/icons.js";

  const ids = $derived([...selection]);
  const albumId = $derived(app.context?.album);

  async function run(fn) {
    try {
      const keep = await fn();
      if (keep !== "keep") selection.clear();
    } catch (e) {
      toast(e.message, "error");
    }
  }

  async function setCover() {
    await api(`/api/albums/${albumId}`, { body: { cover_id: ids[0] } });
    toast("已設為相簿封面");
    refresh();
  }
</script>

<div class="bar">
  <button class="icon-btn" onclick={() => selection.clear()} aria-label="取消選取"><Icon path={mdiClose} /></button>
  <b>已選取 {selection.size} 個</b>
  <span class="spacer"></span>
  <button class="icon-btn" title="加到我的最愛" onclick={() => run(() => setFavorite(ids, true))}><Icon path={mdiHeartOutline} /></button>
  <button class="icon-btn" title="加到相簿" onclick={() => run(() => addToAlbum(ids))}><Icon path={mdiImageAlbum} /></button>
  {#if albumId}
    <button class="icon-btn" title="從相簿移除" onclick={() => run(() => removeFromAlbum(albumId, ids))}><Icon path={mdiImageRemoveOutline} /></button>
    {#if ids.length === 1}
      <button class="icon-btn" title="設為封面" onclick={() => run(setCover)}><Icon path={mdiImageOutline} /></button>
    {/if}
  {/if}
  <button class="icon-btn" title="搬移到資料夾" onclick={() => run(() => moveAssets(ids))}><Icon path={mdiFolderMoveOutline} /></button>
  <button class="icon-btn" title="AI 分析" onclick={() => run(() => analyzeAssets(ids))}><Icon path={mdiCreation} /></button>
  <button class="icon-btn" title="移到垃圾桶" onclick={() => run(async () => ((await trashAssets(ids)).length ? null : "keep"))}><Icon path={mdiDeleteOutline} /></button>
</div>

<style>
  .bar {
    position: fixed; top: 0; left: 0; right: 0; height: var(--topbar); z-index: 60;
    display: flex; align-items: center; gap: 4px; padding: 0 12px; padding-top: env(safe-area-inset-top);
    background: var(--panel); box-shadow: 0 2px 12px rgba(0,0,0,.12); color: var(--primary);
    animation: down .15s ease-out;
  }
  b { color: var(--text); font-weight: 600; margin-left: 4px; }
  .spacer { flex: 1; }
  @keyframes down { from { transform: translateY(-100%); } }
</style>
