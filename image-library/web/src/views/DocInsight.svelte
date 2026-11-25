<script>
  /**
   * 資訊欄裡的文件資訊：關鍵字、AI 摘要（按了才寫，記起來；檔案改過才重寫）、別顆硬碟上的副本（完整比對過的）。
   * 摘要預設用這台電腦上的模型；雲端服務要本人允許傳文件內容才送。
   */
  import { Button, Icon } from "../ui/index.js";
  import { api } from "../lib/api.js";
  import { t, i18n } from "../i18n/index.svelte.js";
  import { toast } from "../lib/state.svelte.js";
  import { link } from "../lib/router.svelte.js";

  let { fileId } = $props();
  let info = $state(null);
  let busy = $state(false);
  $effect(() => {
    const id = fileId;
    info = null;
    api(`/api/files/${id}/insight`, { quiet: true }).then((d) => { if (id === fileId) info = d; }).catch(() => {});
  });
  async function summarize() {
    busy = true;
    try {
      const d = await api(`/api/files/${fileId}/summary`, { body: { lang: i18n.locale } });
      info = { ...info, summary: d.summary };
    } catch (e) {
      toast(e.message, "error");
    } finally {
      busy = false;
    }
  }
</script>

{#if info && (info.has_text || info.copies.length)}
  <section class="doc">
    {#if info.has_text}
      <h3 class="mac-subheadline">{t("ins.summary")}</h3>
      {#if info.summary}
        <p class="mac-callout summary">{info.summary}</p>
      {:else}
        <Button size="small" variant="bordered" icon="sparkles" loading={busy} onclick={summarize}>{t("ins.summarize")}</Button>
        <p class="mac-caption-1 sub">{t("ins.summaryHint")}</p>
      {/if}
      {#if info.keywords.length}
        <h3 class="mac-subheadline">{t("ins.keywords")}</h3>
        <ul class="chips mac-caption-1">
          {#each info.keywords as k (k)}<li><a href={`/find?q=${encodeURIComponent(k)}`} use:link>{k}</a></li>{/each}
        </ul>
      {/if}
    {/if}
    <h3 class="mac-subheadline">{t("ins.copies")}</h3>
    {#if info.copies.length}
      <ul class="copies mac-callout">
        {#each info.copies as c, i (i)}<li><Icon name="external-drive" size={12} /><span class="path" title={c.path}>{c.drive}／{c.path}</span></li>{/each}
      </ul>
    {:else}
      <p class="mac-caption-1 sub">{info.hashed ? t("ins.noCopies") : t("ins.notCompared")}</p>
    {/if}
  </section>
{/if}

<style>
  .doc { margin-top: var(--space-4); padding-top: var(--space-3); border-top: 1px solid var(--separator); display: flex; flex-direction: column; gap: var(--space-2); }
  h3 { margin: var(--space-2) 0 0; color: var(--label-secondary); font-weight: 600; }
  p { margin: 0; }
  .summary { color: var(--label-primary); line-height: 1.5; }
  .sub { color: var(--label-secondary); }
  .chips { list-style: none; margin: 0; padding: 0; display: flex; flex-wrap: wrap; gap: var(--space-1); }
  .chips a { display: inline-block; padding: 1px var(--space-2); border-radius: var(--radius-capsule); background: var(--fill-tertiary); color: var(--label-primary); text-decoration: none; }
  .chips a:hover { background: var(--fill-secondary); }
  .copies { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: var(--space-1); }
  .copies li { display: flex; align-items: center; gap: var(--space-1); min-width: 0; }
  .copies li > :global(svg) { flex: none; color: var(--label-secondary); }
  .path { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; min-width: 0; }
</style>
