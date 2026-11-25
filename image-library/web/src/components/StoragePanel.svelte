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
  import { t } from "../i18n/index.svelte.js";
  import { mdiDatabaseOutline, mdiDeleteOutline, mdiFolderOpenOutline, mdiBroom, mdiHarddisk, mdiRefresh } from "../lib/icons.js";

  let data = $state(null);
  let loading = $state(false);
  let busy = $state("");

  const KIND = $derived({ ollama: t("stor.kind.ollama"), face: t("stor.kind.face"), clip: t("stor.kind.clip") });

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
    { key: "models", label: t("stor.models"), bytes: modelBytes, color: "var(--primary)" },
    { key: "thumbs", label: t("stor.thumbs"), bytes: data.thumbs.bytes, color: "var(--tertiary)" },
    { key: "faces", label: t("stor.faces"), bytes: data.face_thumbs.bytes, color: "var(--secondary)" },
    { key: "db", label: t("stor.db"), bytes: data.database.bytes, color: "var(--outline)" },
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
    const inUse = m.roles.length ? t("stor.inUseWarn", { roles: m.roles.join("、") }) : "";
    if (!(await confirm(t("stor.deleteModelTitle", { name: m.name }), inUse + t("stor.deleteModelMsg", { size: bytes(m.bytes) }), { ok: t("stor.delete"), danger: true }))) return;
    await run(`m:${m.kind}:${m.name}`, async () => {
      await api("/api/storage/models/delete", { body: { kind: m.kind, name: m.name } });
      toast(t("stor.deletedModel", { name: m.name, size: bytes(m.bytes) }));
    });
  }

  async function removeRoot(r) {
    const ok = await confirm(
      t("stor.removeTitle", { name: r.name }),
      t("stor.removeMsg", { n: count(r.items), size: bytes(r.thumb_bytes) || "0 KB" }),
      { ok: t("stor.removeOk"), danger: true },
    );
    if (!ok) return;
    await run(`r:${r.id}`, async () => {
      const res = await api(`/api/roots/${r.id}`, { method: "DELETE" });
      toast(t("stor.removed", { name: r.name, size: bytes(res.freed) || "0 KB" }));
    });
  }

  async function clearAnalysis(r) {
    const ok = await confirm(
      t("stor.clearTitle", { name: r.name }),
      t("stor.clearMsg", { n: count(r.analyzed) }),
      { ok: t("stor.clearOk"), danger: true },
    );
    if (!ok) return;
    await run(`c:${r.id}`, async () => {
      const res = await api("/api/storage/clear-analysis", { body: { root_id: r.id } });
      toast(t("stor.cleared", { n: count(res.cleared) }));
    });
  }

  const EMPTY = { bytes: 0, files: 0, thumbs: { files: 0, bytes: 0 }, face_thumbs: { files: 0, bytes: 0 }, database: { bytes: 0 } };
  const o = $derived(data?.orphans ?? EMPTY);

  async function clean() {
    await run("clean", async () => {
      const res = await api("/api/storage/clean", { body: {} });
      toast(res.freed ? t("stor.cleaned", { n: count(res.files), size: bytes(res.freed) }) : t("stor.nothingToClean"));
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
  <h2><Icon path={mdiDatabaseOutline} />{t("stor.title")}
    <button class="icon-btn small-btn" onclick={load} disabled={loading} title={t("stor.recalc")} aria-label={t("stor.recalc")}><Icon path={mdiRefresh} size={20} /></button>
  </h2>
  <p class="muted small">{t("stor.lead")}</p>

  {#if !data}
    <Loading kind="spinner" inline size={28} label={t("stor.calculating")} />
  {:else}
    <div class="total"><b>{bytes(total) || "0 KB"}</b><span class="muted small">{t("stor.used")}</span></div>
    <div class="bar" role="img" aria-label={t("stor.ratio")}>
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
      <span class="muted small">{t("stor.where")}<code>{data.home}</code></span>
      {#if app.server?.local}<button class="btn ghost small" onclick={reveal}><Icon path={mdiFolderOpenOutline} size={18} />{t("stor.reveal")}</button>{/if}
    </div>
  {/if}
</section>

{#if data}
  <section class="card">
    <h2>{t("stor.models")}</h2>
    <p class="muted small">{t("stor.modelsLead")}{#if !data.ollama_ok}{t("stor.ollamaOff")}{/if}</p>
    {#if !data.models.length}
      <p class="empty-row muted">{t("stor.noModels")}</p>
    {:else}
      <ul class="rows">
        {#each [...data.models].sort((a, b) => b.bytes - a.bytes) as m (m.kind + m.name)}
          <li>
            <div class="grow">
              <b>{m.name}</b>
              <span class="muted tiny">{KIND[m.kind]}{m.detail ? ` · ${m.detail}` : ""}</span>
            </div>
            {#if m.roles.length}
              <span class="tag on">{t("stor.inUse", { roles: m.roles.join("、") })}</span>
            {:else}
              <span class="tag">{t("stor.unused")}</span>
            {/if}
            <span class="size">{bytes(m.bytes)}</span>
            <button class="icon-btn" onclick={() => deleteModel(m)} disabled={busy === `m:${m.kind}:${m.name}`} title={t("stor.deleteModel")} aria-label={t("stor.deleteModelTitle", { name: m.name })}>
              {#if busy === `m:${m.kind}:${m.name}`}<span class="spinner"></span>{:else}<Icon path={mdiDeleteOutline} size={20} />{/if}
            </button>
          </li>
        {/each}
      </ul>
    {/if}
  </section>

  <section class="card">
    <h2>{t("stor.folders")}</h2>
    <p class="muted small">{t("stor.foldersLead")}</p>
    {#if !data.roots.length}
      <p class="empty-row muted">{t("stor.noFolders")}</p>
    {:else}
      <ul class="rows">
        {#each data.roots as r (r.id)}
          <li class="root">
            <Icon path={mdiHarddisk} />
            <div class="grow">
              <b>{r.name}</b>{#if !r.online}<span class="off">{t("drive.offline")}</span>{/if}
              <span class="muted tiny path">{r.path}</span>
              <span class="muted tiny">{t("stor.rootStats", { n: count(r.items), analyzed: count(r.analyzed), faces: count(r.faces), size: bytes(r.thumb_bytes) || "0 KB" })}</span>
            </div>
            <div class="acts">
              <button class="btn ghost small" onclick={() => clearAnalysis(r)} disabled={!r.analyzed || !!busy}>
                {#if busy === `c:${r.id}`}<span class="spinner"></span>{/if}{t("stor.clear")}
              </button>
              <button class="btn ghost small danger-text" onclick={() => removeRoot(r)} disabled={!!busy}>
                {#if busy === `r:${r.id}`}<span class="spinner"></span>{/if}{t("stor.remove")}
              </button>
            </div>
          </li>
        {/each}
      </ul>
    {/if}
  </section>

  <section class="card">
    <h2><Icon path={mdiBroom} />{t("stor.cleanTitle")}</h2>
    {#if o.bytes >= 1024 * 1024}
      <div class="reclaim">
        <span class="muted small">{t("stor.canFree")}</span>
        <b>{bytes(o.bytes)}</b>
      </div>
      <ul class="reclaim-list">
        {#if o.thumbs.files}<li><span>{t("stor.orphanThumbs")}</span><span>{t("stor.filesSize", { n: count(o.thumbs.files), size: bytes(o.thumbs.bytes) })}</span></li>{/if}
        {#if o.face_thumbs.files}<li><span>{t("stor.orphanFaces")}</span><span>{t("stor.filesSize", { n: count(o.face_thumbs.files), size: bytes(o.face_thumbs.bytes) })}</span></li>{/if}
        {#if o.database.bytes >= 1024 * 1024}<li><span>{t("stor.dbSlack")}</span><span>{bytes(o.database.bytes)}</span></li>{/if}
      </ul>
      <p class="muted small">{t("stor.cleanSafe")}</p>
    {:else}
      <p class="muted small">{o.bytes ? t("stor.nothingSmall", { size: bytes(o.bytes) }) : t("stor.nothing")}</p>
    {/if}
    <button class="btn" class:soft={o.bytes < 1024 * 1024} onclick={clean} disabled={busy === "clean"}>
      {#if busy === "clean"}<span class="spinner"></span>{t("stor.cleaning")}{:else if o.bytes >= 1024 * 1024}{t("stor.cleanFree", { size: bytes(o.bytes) })}{:else}{t("stor.compact")}{/if}
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
  .bar span { display: block; height: 100%; min-width: 3px; transition: width var(--dur-slow); }
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
