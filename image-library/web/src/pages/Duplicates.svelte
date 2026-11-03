<script>
  import Icon from "../components/Icon.svelte";
  import { api, thumbUrl } from "../lib/api.js";
  import { app, openViewer, refresh, toast } from "../lib/state.svelte.js";
  import { confirm } from "../lib/actions.js";
  import { bytes } from "../lib/format.js";
  import { mdiContentDuplicate, mdiCheckCircle, mdiStar } from "../lib/icons.js";

  let data = $state(null);
  let tab = $state("similar");
  let keep = $state({}); // 每組選擇保留的 id
  const running = $derived((app.server?.jobs?.active || []).some((j) => j.kind === "dups"));

  $effect(() => {
    app.refreshKey;
    api("/api/duplicates").then((d) => {
      data = d;
      const k = {};
      for (const g of [...d.exact, ...d.similar]) k[key(g)] = new Set([g.keep]);
      keep = k;
    });
  });

  const key = (g) => g.items.map((i) => i.id).sort((a, b) => a - b).join(",");
  const groups = $derived(data ? data[tab] : []);

  async function start() {
    await api("/api/jobs", { body: { kind: "dups" } });
    toast("開始比對，完成後這一頁會自動更新");
    refresh();
  }

  function toggleKeep(g, id) {
    const set = new Set(keep[key(g)]);
    set.has(id) ? set.delete(id) : set.add(id);
    keep = { ...keep, [key(g)]: set };
  }

  async function cleanGroup(g) {
    const kept = keep[key(g)];
    if (!kept?.size) return toast("至少保留一張", "error");
    const ids = g.items.filter((i) => !kept.has(i.id)).map((i) => i.id);
    if (!ids.length) return;
    if (!(await confirm("移到垃圾桶？", `保留 ${kept.size} 張，其餘 ${ids.length} 張移到垃圾桶（可以還原）。`, { ok: "移到垃圾桶", danger: true }))) return;
    const res = await api("/api/assets/bulk", { body: { ids, action: "trash" } });
    toast(`已移到垃圾桶：${res.done} 張`);
    data[tab] = data[tab].filter((x) => x !== g);
    refresh();
  }

  async function ignore(g) {
    await api("/api/duplicates/ignore", { body: { ids: g.items.map((i) => i.id) } });
    data[tab] = data[tab].filter((x) => x !== g);
  }
</script>

<div class="page">
  <div class="page-head">
    <h1>重複與相似照片</h1>
    <button class="btn" disabled={running} onclick={start}>{running ? "比對中…" : data?.computed_at ? "重新比對" : "開始比對"}</button>
  </div>
  {#if data?.computed_at}
    <p class="muted small">上次比對：{data.computed_at.slice(0, 16).replace("T", " ")}。藍框是建議保留的（星等、最愛、RAW、解析度優先），點照片可切換保留；按右下角的放大鏡看大圖。</p>
    <div class="chips tabs">
      <button class="chip" class:on={tab === "similar"} onclick={() => (tab = "similar")}>幾乎一樣（{data.total_similar}）</button>
      <button class="chip" class:on={tab === "exact"} onclick={() => (tab = "exact")}>完全相同的檔案（{data.total_exact}）</button>
    </div>
    {#each groups as g (key(g))}
      <section class="group">
        <div class="items">
          {#each g.items as item (item.id)}
            {@const kept = keep[key(g)]?.has(item.id)}
            <div class="item" class:kept>
              <button class="pic" onclick={() => toggleKeep(g, item.id)}>
                <img src={thumbUrl(item)} alt="" loading="lazy" />
                {#if kept}<span class="keep"><Icon path={mdiCheckCircle} size={22} />保留</span>{/if}
              </button>
              <button class="zoom" title="看大圖" onclick={() => openViewer(g.items, g.items.indexOf(item))}>🔍</button>
              <div class="info">
                <b>{item.name}</b>
                <span>{item.width}×{item.height} · {bytes(item.size)}{item.raw ? " · RAW" : ""}</span>
                {#if item.rating > 0}<span class="stars"><Icon path={mdiStar} size={12} />{item.rating}</span>{/if}
                <span class="path" title={item.path}>{item.folder || "（根目錄）"}</span>
              </div>
            </div>
          {/each}
        </div>
        <div class="actions">
          <button class="btn small danger" onclick={() => cleanGroup(g)}>只保留選取的，其餘移到垃圾桶</button>
          <button class="btn small ghost" onclick={() => ignore(g)}>不是重複，忽略</button>
        </div>
      </section>
    {:else}
      <div class="empty"><h2>沒有找到</h2><p>{tab === "exact" ? "沒有完全相同的檔案。" : "沒有幾乎一樣的照片。"}</p></div>
    {/each}
  {:else if data}
    <div class="empty">
      <Icon path={mdiContentDuplicate} size={56} />
      <h2>找出重複與幾乎一樣的照片</h2>
      <p>完全相同的檔案（例如複製到不同資料夾）與幾乎一樣的照片（連拍、縮小或重新壓縮過的版本）。<br />十萬張大約需要幾分鐘，可以在背景執行。</p>
    </div>
  {/if}
</div>

<style>
  .tabs { margin: 8px 0 18px; }
  .group { background: var(--bg-2); border-radius: 16px; padding: 12px; margin-bottom: 14px; }
  .items { display: flex; gap: 10px; overflow-x: auto; padding-bottom: 4px; }
  .item { position: relative; width: 180px; flex-shrink: 0; }
  .pic { border: 3px solid transparent; border-radius: 12px; padding: 0; background: none; cursor: pointer; display: block; position: relative; width: 100%; }
  .item.kept .pic { border-color: var(--primary); }
  .pic img { width: 100%; aspect-ratio: 1; object-fit: cover; border-radius: 9px; display: block; }
  .keep { position: absolute; left: 6px; top: 6px; display: flex; align-items: center; gap: 2px; background: var(--primary); color: var(--on-primary); border-radius: 999px; padding: 1px 8px 1px 2px; font-size: 12px; font-weight: 600; }
  .zoom { position: absolute; right: 8px; top: 150px; border: 0; border-radius: 50%; width: 28px; height: 28px; background: rgba(0,0,0,.5); cursor: pointer; }
  .info { display: flex; flex-direction: column; font-size: 12px; margin-top: 4px; min-width: 0; }
  .info b { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .info span { color: var(--muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .stars { display: flex; align-items: center; gap: 2px; }
  .stars :global(svg) { color: #f5c518; }
  .actions { display: flex; gap: 8px; margin-top: 10px; flex-wrap: wrap; }
  .empty :global(svg) { color: var(--muted); margin: 0 auto; }
  @media (max-width: 760px) { .item { width: 140px; } .zoom { top: 110px; } }
</style>
