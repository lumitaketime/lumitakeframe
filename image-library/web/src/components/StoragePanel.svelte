<script>
  import Loading from "./Loading.svelte";
  /**
   * 儲存空間與模型：每一類資料與每個模型佔多少空間，以及清理、刪除。
   * 照片檔案本身永遠不會在這裡被刪除。
   */
  import Icon from "./Icon.svelte";
  import { api } from "../lib/api.js";
  import { app, refresh, toast } from "../lib/state.svelte.js";
  import { confirm } from "../lib/actions.js";
  import { bytes, count } from "../lib/format.js";
  import { mdiDatabaseOutline, mdiDeleteOutline, mdiFolderOpenOutline, mdiBroom, mdiHarddisk, mdiRefresh } from "../lib/icons.js";

  let data = $state(null);
  let loading = $state(false);
  let busy = $state("");

  const KIND = { ollama: "AI 模型（Ollama）", face: "人臉辨識模型", clip: "圖像搜尋模型" };

  async function load() {
    loading = true;
    try {
      data = await api("/api/storage");
    } catch (e) {
      toast(e.message, "error");
    } finally {
      loading = false;
    }
  }

  $effect(() => {
    app.refreshKey;
    load();
  });

  const modelBytes = $derived((data?.models || []).reduce((s, m) => s + m.bytes, 0));
  const parts = $derived(data ? [
    { key: "models", label: "模型", bytes: modelBytes, color: "var(--primary)" },
    { key: "thumbs", label: "縮圖快取", bytes: data.thumbs.bytes, color: "var(--tertiary)" },
    { key: "faces", label: "人臉縮圖", bytes: data.face_thumbs.bytes, color: "var(--secondary)" },
    { key: "db", label: "資料庫（分析結果）", bytes: data.database.bytes, color: "var(--outline)" },
  ] : []);
  const total = $derived(parts.reduce((s, p) => s + p.bytes, 0));

  async function run(key, fn) {
    busy = key;
    try {
      await fn();
    } catch (e) {
      toast(e.message, "error", 6000);
    } finally {
      busy = "";
      await load();
      refresh();
    }
  }

  async function deleteModel(m) {
    const inUse = m.roles.length ? `目前用於「${m.roles.join("、")}」，刪除後這個功能要重新下載模型才能使用。` : "";
    if (!(await confirm(`刪除 ${m.name}？`, `${inUse}會釋放約 ${bytes(m.bytes)}。已完成的分析結果不受影響。`, { ok: "刪除", danger: true }))) return;
    await run(`m:${m.kind}:${m.name}`, async () => {
      await api("/api/storage/models/delete", { body: { kind: m.kind, name: m.name } });
      toast(`已刪除 ${m.name}，釋放約 ${bytes(m.bytes)}`);
    });
  }

  async function removeRoot(r) {
    const ok = await confirm(
      `從圖庫移除「${r.name}」？`,
      `會刪除這個資料夾在圖庫裡的所有資料：${count(r.items)} 張照片的縮圖（約 ${bytes(r.thumb_bytes) || "0 KB"}）、AI 分析結果與人臉資料。硬碟上的照片完全不受影響，之後重新加入需要重新分析。`,
      { ok: "移除並清除資料", danger: true },
    );
    if (!ok) return;
    await run(`r:${r.id}`, async () => {
      const res = await api(`/api/roots/${r.id}`, { method: "DELETE" });
      toast(`已移除「${r.name}」，釋放約 ${bytes(res.freed) || "0 KB"}`);
    });
  }

  async function clearAnalysis(r) {
    const ok = await confirm(
      `清除「${r.name}」的 AI 分析？`,
      `${count(r.analyzed)} 張照片的描述、關鍵字與圖中文字會被清除並回到「待分析」。照片、星等、標籤、相簿與人臉不受影響。`,
      { ok: "清除分析結果", danger: true },
    );
    if (!ok) return;
    await run(`c:${r.id}`, async () => {
      const res = await api("/api/storage/clear-analysis", { body: { root_id: r.id } });
      toast(`已清除 ${count(res.cleared)} 張照片的分析結果`);
    });
  }

  const EMPTY = { bytes: 0, files: 0, thumbs: { files: 0, bytes: 0 }, face_thumbs: { files: 0, bytes: 0 }, database: { bytes: 0 } };
  const o = $derived(data?.orphans ?? EMPTY);

  async function clean() {
    await run("clean", async () => {
      const res = await api("/api/storage/clean", { body: {} });
      toast(res.freed ? `已清理 ${count(res.files)} 個檔案，釋放約 ${bytes(res.freed)}` : "沒有需要清理的檔案");
    });
  }

  async function reveal() {
    try {
      await api("/api/storage/reveal", { body: {} });
    } catch (e) {
      toast(e.message, "error");
    }
  }
</script>

<section class="card">
  <h2><Icon path={mdiDatabaseOutline} />儲存空間與模型
    <button class="icon-btn small-btn" onclick={load} disabled={loading} title="重新計算" aria-label="重新計算"><Icon path={mdiRefresh} size={20} /></button>
  </h2>
  <p class="muted small">這裡只管理圖庫自己產生的資料與下載的模型。照片檔案本身永遠不會在這裡被刪除。</p>

  {#if !data}
    <Loading kind="spinner" inline size={28} label="正在計算各項目佔用的空間…" />
  {:else}
    <div class="total"><b>{bytes(total) || "0 KB"}</b><span class="muted small">共使用</span></div>
    <div class="bar" role="img" aria-label="空間使用比例">
      {#each parts as p (p.key)}
        {#if p.bytes}<span style:width="{(p.bytes / total) * 100}%" style:background={p.color} title="{p.label} {bytes(p.bytes)}"></span>{/if}
      {/each}
    </div>
    <ul class="legend">
      {#each parts as p (p.key)}
        <li><i style:background={p.color}></i>{p.label}<b>{bytes(p.bytes) || "0 KB"}</b></li>
      {/each}
    </ul>
    <div class="where">
      <span class="muted small">圖庫資料位置：<code>{data.home}</code></span>
      {#if app.server?.local}<button class="btn ghost small" onclick={reveal}><Icon path={mdiFolderOpenOutline} size={18} />在 Finder 中打開</button>{/if}
    </div>
  {/if}
</section>

{#if data}
  <section class="card">
    <h2>模型</h2>
    <p class="muted small">已下載的所有模型。不用的可以刪除釋放空間，需要時再到對應的設定頁下載。{#if !data.ollama_ok}Ollama 目前沒有在執行，所以看不到它的模型。{/if}</p>
    {#if !data.models.length}
      <p class="empty-row muted">還沒有下載任何模型。</p>
    {:else}
      <ul class="rows">
        {#each [...data.models].sort((a, b) => b.bytes - a.bytes) as m (m.kind + m.name)}
          <li>
            <div class="grow">
              <b>{m.name}</b>
              <span class="muted tiny">{KIND[m.kind]}{m.detail ? ` · ${m.detail}` : ""}</span>
            </div>
            {#if m.roles.length}
              <span class="tag on">使用中：{m.roles.join("、")}</span>
            {:else}
              <span class="tag">未使用</span>
            {/if}
            <span class="size">{bytes(m.bytes)}</span>
            <button class="icon-btn" onclick={() => deleteModel(m)} disabled={busy === `m:${m.kind}:${m.name}`} title="刪除模型" aria-label="刪除 {m.name}">
              {#if busy === `m:${m.kind}:${m.name}`}<span class="spinner"></span>{:else}<Icon path={mdiDeleteOutline} size={20} />{/if}
            </button>
          </li>
        {/each}
      </ul>
    {/if}
  </section>

  <section class="card">
    <h2>各資料夾的資料</h2>
    <p class="muted small">掃描過、但不再使用的資料夾，可以在這裡移除，連同縮圖、分析結果與人臉資料一起清掉。</p>
    {#if !data.roots.length}
      <p class="empty-row muted">還沒有加入任何資料夾。</p>
    {:else}
      <ul class="rows">
        {#each data.roots as r (r.id)}
          <li class="root">
            <Icon path={mdiHarddisk} />
            <div class="grow">
              <b>{r.name}</b>{#if !r.online}<span class="off">未連接</span>{/if}
              <span class="muted tiny path">{r.path}</span>
              <span class="muted tiny">{count(r.items)} 張 · 已分析 {count(r.analyzed)} · 人臉 {count(r.faces)} · 縮圖 {bytes(r.thumb_bytes) || "0 KB"}</span>
            </div>
            <div class="acts">
              <button class="btn ghost small" onclick={() => clearAnalysis(r)} disabled={!r.analyzed || !!busy}>
                {#if busy === `c:${r.id}`}<span class="spinner"></span>{/if}清除分析
              </button>
              <button class="btn ghost small danger-text" onclick={() => removeRoot(r)} disabled={!!busy}>
                {#if busy === `r:${r.id}`}<span class="spinner"></span>{/if}移除資料夾
              </button>
            </div>
          </li>
        {/each}
      </ul>
    {/if}
  </section>

  <section class="card">
    <h2><Icon path={mdiBroom} />清理快取</h2>
    {#if o.bytes >= 1024 * 1024}
      <div class="reclaim">
        <span class="muted small">可以釋放</span>
        <b>{bytes(o.bytes)}</b>
      </div>
      <ul class="reclaim-list">
        {#if o.thumbs.files}<li><span>沒有照片使用的縮圖（照片已刪除或搬走）</span><span>{count(o.thumbs.files)} 個 · {bytes(o.thumbs.bytes)}</span></li>{/if}
        {#if o.face_thumbs.files}<li><span>不再使用的人臉縮圖（重新辨識後留下的）</span><span>{count(o.face_thumbs.files)} 個 · {bytes(o.face_thumbs.bytes)}</span></li>{/if}
        {#if o.database.bytes >= 1024 * 1024}<li><span>資料庫裡刪除資料後的空白</span><span>{bytes(o.database.bytes)}</span></li>{/if}
      </ul>
      <p class="muted small">只刪除本程式產生的快取，照片、分析結果與人物都不受影響。</p>
    {:else}
      <p class="muted small">目前沒有需要清理的快取{o.bytes ? `（只有約 ${bytes(o.bytes)}）` : ""}，不用清理。</p>
    {/if}
    <button class="btn" class:soft={o.bytes < 1024 * 1024} onclick={clean} disabled={busy === "clean"}>
      {#if busy === "clean"}<span class="spinner"></span>清理中…{:else if o.bytes >= 1024 * 1024}清理，釋放 {bytes(o.bytes)}{:else}仍要壓縮資料庫{/if}
    </button>
  </section>
{/if}

<style>
  h2 { display: flex; align-items: center; gap: 10px; }
  .reclaim { display: flex; align-items: baseline; gap: 8px; margin: 4px 0 6px; }
  .reclaim b { font-size: var(--text-large-title); font-weight: 500; font-variant-numeric: tabular-nums; }
  .reclaim-list { list-style: none; margin: 0 0 8px; padding: 0; display: flex; flex-direction: column; gap: 4px; font-size: var(--text-body); }
  .reclaim-list li { display: flex; justify-content: space-between; gap: 12px; flex-wrap: wrap; padding: 6px 0; border-bottom: 1px solid var(--outline-variant); }
  .reclaim-list li span:last-child { color: var(--on-surface-variant); font-variant-numeric: tabular-nums; }
  .small-btn { margin-left: auto; width: 36px; height: 36px; }
  .skeleton { height: 90px; border-radius: var(--corner-medium); background: var(--surface); animation: pulse 1.2s ease-in-out infinite; }
  @keyframes pulse { 50% { opacity: .5; } }
  .total { display: flex; align-items: baseline; gap: 8px; margin: 10px 0 8px; }
  .total b { font-size: var(--text-large-title); font-weight: 500; font-variant-numeric: tabular-nums; }
  .bar { display: flex; height: 12px; border-radius: var(--corner-full); overflow: hidden; background: var(--surface); gap: 2px; }
  .bar span { display: block; height: 100%; min-width: 3px; transition: width .4s; }
  .legend { list-style: none; padding: 0; margin: 12px 0; display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 6px 16px; }
  .legend li { display: flex; align-items: center; gap: 8px; font-size: var(--text-body); }
  .legend i { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }
  .legend b { margin-left: auto; font-weight: 500; font-variant-numeric: tabular-nums; }
  .where { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
  code { background: var(--surface); padding: 2px 8px; border-radius: var(--corner-small); font-size: var(--text-callout); word-break: break-all; }
  .rows { list-style: none; padding: 0; margin: 10px 0 0; display: flex; flex-direction: column; background: var(--surface); border-radius: var(--corner-medium); }
  .rows li { display: flex; align-items: center; gap: 12px; padding: 10px 14px; flex-wrap: wrap; }
  .rows li + li { border-top: 1px solid var(--outline-variant); }
  .grow { flex: 1; min-width: 180px; display: flex; flex-direction: column; gap: 2px; }
  .path { font-family: var(--font-mono); word-break: break-all; }
  .tag { font-size: var(--text-callout); padding: 2px 10px; border-radius: var(--corner-full); background: var(--surface-container); color: var(--on-surface-variant); white-space: nowrap; }
  .tag.on { background: var(--secondary-container); color: var(--primary); font-weight: 500; }
  .size { min-width: 72px; text-align: right; font-variant-numeric: tabular-nums; font-weight: 500; }
  .off { margin-left: 8px; font-size: var(--text-sub); color: var(--error); }
  .acts { display: flex; gap: 6px; flex-wrap: wrap; }
  .empty-row { padding: 10px 0; }
  .spinner { width: 14px; height: 14px; margin-right: 6px; }
</style>
