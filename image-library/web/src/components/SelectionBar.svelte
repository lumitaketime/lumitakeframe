<script>
  import Icon from "./Icon.svelte";
  import ExportDialog from "./ExportDialog.svelte";
  import TagDialog from "./TagDialog.svelte";
  import { app, selection } from "../lib/state.svelte.js";
  import { addToAlbum, analyzeAssets, removeFromAlbum, setFavorite, trashAssets } from "../lib/actions.js";
  import { api } from "../lib/api.js";
  import { toast, refresh, showDialog } from "../lib/state.svelte.js";
  import { navigate } from "../lib/router.svelte.js";
  import { undoable } from "../lib/undo.svelte.js";
  import {
    mdiFileExportOutline, mdiPound, mdiClose, mdiHeartOutline, mdiImageAlbum, mdiCreation, mdiDeleteOutline, mdiImageRemoveOutline, mdiImageOutline, mdiAccountRemoveOutline, mdiAccountArrowRightOutline, mdiStarOutline, mdiStar, mdiFlagRemove, mdiLayers,
  } from "../lib/icons.js";
  import { LABEL_COLORS, LABEL_KEYS, LABEL_NAMES } from "../lib/format.js";

  let rateMenu = $state(false);
  let exporting = $state(false);
  let tagging = $state(false);

  async function bulk(action, value) {
    const res = await api("/api/assets/bulk", { body: { ids, action, value } });
    toast(res.errors?.length ? `已更新，但有 ${res.errors.length} 個項目無法更新：${res.errors[0]}` : `已更新 ${ids.length} 個項目`, res.errors?.length ? "error" : "info");
    refresh();
    rateMenu = false;
  }

  async function stackSelected() {
    await api("/api/assets/bulk", { body: { ids, action: "stack" } });
    toast(`已把 ${ids.length} 張疊放在一起`);
    refresh();
  }

  const ids = $derived([...selection]);
  const albumId = $derived(app.context?.album);
  const personId = $derived(app.context?.person);
  const folderCtx = $derived(app.context?.folder);

  async function setFolderCover() {
    await api("/api/folders/cover", { body: { root_id: folderCtx.root, path: folderCtx.path, image_id: ids[0] } });
    toast("已設為資料夾封面");
    refresh();
  }

  async function notThisPerson() {
    const res = await api(`/api/people/${personId}/remove`, { body: { ids } });
    toast(`已從這個人物移除 ${ids.length} 張，之後也不會自動歸回`);
    refresh();
    return res;
  }

  // 移到另一個人物，或拆成新人物（在選擇視窗輸入新名字）；可以復原
  async function moveToPerson() {
    const target = await showDialog("person", { exclude: personId, allowNew: true, title: `把 ${ids.length} 張照片中的這個人移到…` });
    if (!target) return "keep";
    const body = target.id ? { ids, to: target.id } : { ids, name: target.name };
    const res = await api(`/api/people/${personId}/move`, { body });
    const back = personId;
    undoable(target.id ? `已移到「${target.name || "未命名"}」（${res.moved} 張臉）` : `已拆成新人物「${target.name}」`, async () => {
      await api("/api/people/move/undo", { body: { undo: res.undo } });
      navigate(`/people/${back}`, { replace: true });
    });
    refresh();
  }

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
  <div class="rate-wrap">
    <button class="icon-btn" title="星等與顏色標籤" onclick={() => (rateMenu = !rateMenu)}><Icon path={mdiStarOutline} /></button>
    {#if rateMenu}
      <div class="rate-menu" role="menu">
        <div class="row">
          {#each [1, 2, 3, 4, 5] as n (n)}
            <button title="{n} 星" onclick={() => run(() => bulk("rating", n))}>{n}<Icon path={mdiStar} size={14} /></button>
          {/each}
        </div>
        <div class="row">
          <button onclick={() => run(() => bulk("rating", 0))}>清除星等</button>
          <button onclick={() => run(() => bulk("rating", -1))}><Icon path={mdiFlagRemove} size={16} />拒絕</button>
        </div>
        <div class="row">
          {#each LABEL_KEYS as key (key)}
            <button class="dot" title="{LABEL_NAMES[key]}" style:background={LABEL_COLORS[key]} aria-label={LABEL_NAMES[key]} onclick={() => run(() => bulk("label", key))}></button>
          {/each}
          <button onclick={() => run(() => bulk("label", ""))}>清除</button>
        </div>
      </div>
    {/if}
  </div>
  <button class="icon-btn" title="加上 #標籤" aria-label="加上標籤" onclick={() => (tagging = true)}><Icon path={mdiPound} /></button>
  <button class="icon-btn" title="加到我的最愛" onclick={() => run(() => setFavorite(ids, true))}><Icon path={mdiHeartOutline} /></button>
  <button class="icon-btn" title="加到相簿" onclick={() => run(() => addToAlbum(ids))}><Icon path={mdiImageAlbum} /></button>
  {#if albumId}
    <button class="icon-btn" title="從相簿移除" onclick={() => run(() => removeFromAlbum(albumId, ids))}><Icon path={mdiImageRemoveOutline} /></button>
    {#if ids.length === 1}
      <button class="icon-btn" title="設為相簿封面" aria-label="設為相簿封面" onclick={() => run(setCover)}><Icon path={mdiImageOutline} /></button>
    {/if}
  {/if}
  {#if folderCtx && ids.length === 1}
    <button class="icon-btn" title="設為資料夾封面" aria-label="設為資料夾封面" onclick={() => run(setFolderCover)}><Icon path={mdiImageOutline} /></button>
  {/if}
  {#if personId}
    <button class="icon-btn" title="移到其他人物，或拆成新人物" aria-label="移到其他人物" onclick={() => run(moveToPerson)}><Icon path={mdiAccountArrowRightOutline} /></button>
    <button class="icon-btn" title="不是這個人" onclick={() => run(notThisPerson)}><Icon path={mdiAccountRemoveOutline} /></button>
  {/if}
  <button class="btn soft small export" onclick={() => (exporting = true)} title="匯出交件（尺寸、浮水印、移除 GPS、重新命名）"><Icon path={mdiFileExportOutline} size={18} />匯出</button>
  {#if ids.length > 1}
    <button class="icon-btn" title="疊放在一起" onclick={() => run(stackSelected)}><Icon path={mdiLayers} /></button>
  {/if}
  <button class="icon-btn" title="AI 分析" onclick={() => run(() => analyzeAssets(ids))}><Icon path={mdiCreation} /></button>
  <button class="icon-btn" title="移到垃圾桶" onclick={() => run(async () => ((await trashAssets(ids)).length ? null : "keep"))}><Icon path={mdiDeleteOutline} /></button>
</div>

{#if tagging}
  <TagDialog {ids} onclose={() => (tagging = false)} />
{/if}
{#if exporting}
  <ExportDialog {ids} onclose={(done) => { exporting = false; if (done) selection.clear(); }} />
{/if}

<style>
  .export { margin: 0 4px; }
  @media (max-width: 760px) { .export { padding: 0 10px; } }
  .bar {
    position: fixed; top: 0; left: 0; right: 0; height: var(--topbar); z-index: 60;
    display: flex; align-items: center; gap: 4px; padding: 0 12px; padding-top: env(safe-area-inset-top);
    background: var(--surface-container); border-bottom: 1px solid var(--outline-variant); color: var(--primary);
    animation: down .15s ease-out;
  }
  b { color: var(--on-surface); font-weight: 500; margin-left: 4px; }
  .spacer { flex: 1; }
  .rate-wrap { position: relative; }
  .rate-menu {
    position: absolute; top: 46px; right: -40px; background: var(--surface-container); color: var(--on-surface); border-radius: var(--corner-large);
    border: 1px solid var(--outline-variant); padding: 8px; display: flex; flex-direction: column; gap: 6px; z-index: 5; min-width: 250px;
  }
  .rate-menu .row { display: flex; gap: 4px; align-items: center; }
  .rate-menu button {
    border: 0; background: var(--surface-container); color: var(--on-surface); border-radius: var(--corner-small); padding: 6px 8px; cursor: pointer;
    display: flex; align-items: center; gap: 2px; font-size: var(--text-body);
  }
  .rate-menu button:hover { background: var(--surface-container-highest); }
  .rate-menu button :global(svg) { color: var(--system-yellow); }
  .rate-menu .dot { width: 26px; height: 26px; border-radius: 50%; padding: 0; }
  @keyframes down { from { transform: translateY(-100%); } }
</style>
