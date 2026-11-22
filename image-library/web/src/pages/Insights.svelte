<script>
  /**
   * 檔案分析：類型、年份分布、關鍵字雲（資料夾名稱與檔名裡最常出現的詞）。
   * 按一個詞：出現在哪些資料夾與檔案、現在分在哪些類；可以「分到某分類」，先看影響範圍、確認才套用，可以復原。
   * 只讀目錄資料庫，不讀硬碟、不上傳；規則只改目錄裡的分類。
   */
  import { Button, Icon, PopUpButton, ProgressIndicator, TextField } from "../ui/index.js";
  import CategoryPlanPreview from "../views/CategoryPlanPreview.svelte";
  import KindIcon from "../views/KindIcon.svelte";
  import { loadAnalysis, runAnalysis, loadWord, proposeRule } from "../data/analysis.js";
  import { runAction, undoAction, dismissAction } from "../data/assistant.js";
  import { catalog, loadCatalog } from "../data/catalog.svelte.js";
  import { categoryName } from "../data/category.svelte.js";
  import { setFrame } from "../shell/frame.svelte.js";
  import { navigate } from "../lib/router.svelte.js";
  import { t, formatNumber, formatBytes, formatDateTime } from "../i18n/index.svelte.js";
  import { app, toast, refresh } from "../lib/state.svelte.js";

  let data = $state(null);
  let error = $state("");
  let word = $state(null); // 選到的詞
  let detail = $state(null);
  let target = $state("");
  let yearFrom = $state("");
  let yearTo = $state("");
  let proposal = $state(null); // 還沒套用的規則（含預覽）
  let busy = $state("");

  function load() {
    loadAnalysis().then((d) => { data = d; error = ""; }).catch((e) => (error = e.message));
  }
  $effect(() => {
    app.refreshKey;
    load();
  });
  const job = $derived(app.server?.jobs?.active?.find((j) => j.kind === "keywords") || null);
  let wasRunning = false;
  $effect(() => {
    const running = !!job;
    if (wasRunning && !running) load();
    wasRunning = running;
  });
  // 第一次打開還沒有關鍵字：自動找一次（只讀目錄，很快）
  let started = false;
  $effect(() => {
    if (data && !data.words.length && !data.updated_at && !started && !job) {
      started = true;
      runAnalysis().then(refresh).catch(() => {});
    }
  });
  $effect(() => {
    setFrame({ crumbs: [], location: null, info: null, status: data ? t("insight.status", { files: formatNumber(data.total.files), size: formatBytes(data.total.bytes) }) : "" });
  });

  // ---- 類型與年份 ----
  const maxKind = $derived(Math.max(1, ...(data?.kinds || []).map((k) => k.bytes)));
  const years = $derived(data?.years || []);
  const maxYear = $derived(Math.max(1, ...years.map((y) => y.files)));
  const yearLabel = (i) => i === 0 || i === years.length - 1 || years[i].year % 5 === 0;

  // ---- 關鍵字雲 ----
  const PALETTE = ["--system-blue", "--system-orange", "--system-green", "--system-purple", "--system-pink", "--system-teal", "--system-indigo", "--system-brown", "--system-mint", "--system-red"];
  const colorOf = (key) => {
    const i = catalog.categories.findIndex((c) => c.key === key);
    return i >= 0 ? `var(${PALETTE[i % PALETTE.length]})` : "var(--label-secondary)";
  };
  const nameOf = (key) => (key ? categoryName(catalog.categories.find((c) => c.key === key) || { key }, t) : t("plan.uncategorized"));
  const SIZES = ["mac-caption-1", "mac-callout", "mac-body", "mac-title-3", "mac-title-2", "mac-title-1"];
  const scores = $derived((data?.words || []).map((w) => w.folders * 3 + w.files));
  const maxScore = $derived(Math.max(1, ...scores));
  const sizeOf = (w) => SIZES[Math.min(SIZES.length - 1, Math.floor((Math.log(1 + w.folders * 3 + w.files) / Math.log(1 + maxScore)) * (SIZES.length - 0.01)))];
  // 雲裡出現的分類（圖例：顏色不是唯一的線索，名稱也寫出來）
  const legend = $derived([...new Set((data?.words || []).map((w) => w.category))].map((k) => ({ key: k, name: nameOf(k), color: k ? colorOf(k) : "var(--label-secondary)" })));

  async function pick(w) {
    word = w;
    detail = null;
    proposal = null;
    target = w.category || catalog.categories[0]?.key || "";
    yearFrom = yearTo = "";
    try {
      detail = await loadWord(w.word);
    } catch (e) {
      toast(e.message, "error");
    }
  }
  async function preview() {
    busy = "preview";
    try {
      if (proposal) await dismissAction(proposal.id).catch(() => {});
      proposal = await proposeRule(word.word, target, Number(yearFrom) || null, Number(yearTo) || null);
    } catch (e) {
      toast(e.message, "error");
    } finally {
      busy = "";
    }
  }
  async function apply() {
    busy = "apply";
    try {
      const done = await runAction(proposal.id);
      proposal = null;
      await loadCatalog();
      refresh();
      detail = await loadWord(word.word);
      toast(t("insight.applied", { word: word.word, name: nameOf(target) }), "info", 10000, {
        label: t("act.undo"), run: async () => { await undoAction(done.id); await loadCatalog(); refresh(); toast(t("insight.undone")); },
      });
    } catch (e) {
      toast(e.message, "error");
    } finally {
      busy = "";
    }
  }
  async function cancel() {
    if (proposal) await dismissAction(proposal.id).catch(() => {});
    proposal = null;
  }
  const options = $derived(catalog.categories.map((c) => ({ value: c.key, label: categoryName(c, t) })));
  const href = (f) => `/folders/${f.root_id}?path=${encodeURIComponent(f.path)}`;
</script>

<div class="insights">
  <header class="top">
    <div>
      <h1 class="mac-title-2">{t("insight.title")}</h1>
      <p class="mac-callout sub">{t("insight.lead")}</p>
    </div>
    <span class="grow"></span>
    {#if job}<span class="mac-callout sub busy"><ProgressIndicator kind="spinner" size="small" label={t("insight.running")} />{t("insight.running")}</span>
    {:else}<Button size="small" variant="bordered" onclick={() => runAnalysis().then(refresh).catch((e) => toast(e.message, "error"))}>{t("insight.refresh")}</Button>{/if}
  </header>

  {#if error}
    <div class="state" role="alert"><p class="mac-body">{error}</p><Button onclick={load}>{t("view.retry")}</Button></div>
  {:else if !data}
    <div class="state"><ProgressIndicator kind="spinner" label={t("view.loading")} /></div>
  {:else if !data.total.files}
    <div class="state"><h2 class="mac-title-3">{t("insight.empty")}</h2><p class="mac-body sub">{t("insight.emptyHint")}</p>
      <Button variant="borderedProminent" onclick={() => navigate("/drives")}>{t("nav.addDrive")}</Button></div>
  {:else}
    <div class="row">
      <section class="card">
        <h2 class="mac-headline">{t("insight.kinds")}</h2>
        <ul class="bars">
          {#each data.kinds as k (k.kind)}
            <li>
              <KindIcon kind={k.kind} size={15} />
              <span class="bl">{t(`kind.${k.kind}`)}</span>
              <span class="track"><i style:width="{(k.bytes / maxKind) * 100}%" style:background="var(--kind-{k.kind === 'package' ? 'other' : k.kind})"></i></span>
              <span class="num sub">{formatNumber(k.files)}</span>
              <span class="num">{formatBytes(k.bytes)}</span>
            </li>
          {/each}
        </ul>
      </section>
      <section class="card">
        <h2 class="mac-headline">{t("insight.years")}</h2>
        {#if years.length}
          <div class="years" role="img" aria-label={t("insight.years")}>
            {#each years as y, i (y.year)}
              <div class="ycol" title={t("insight.yearTip", { year: y.year, files: formatNumber(y.files), size: formatBytes(y.bytes) })}>
                <span class="ybar" style:height="{Math.max(2, (y.files / maxYear) * 100)}%"></span>
                <span class="ylab mac-caption-2">{yearLabel(i) ? y.year : ""}</span>
              </div>
            {/each}
          </div>
          <p class="mac-caption-1 sub">{t("insight.yearsHint")}</p>
        {:else}<p class="mac-callout sub">{t("insight.noYears")}</p>{/if}
      </section>
    </div>

    <section class="card cloudcard">
      <div class="cloudhead">
        <h2 class="mac-headline">{t("insight.cloud")}</h2>
        <span class="mac-caption-1 sub">{data.updated_at ? t("insight.updated", { time: formatDateTime(new Date(data.updated_at)) }) : ""}</span>
      </div>
      <p class="mac-callout sub">{t("insight.cloudHint")}</p>
      {#if !data.words.length}
        <p class="mac-callout sub">{job ? t("insight.running") : t("insight.noWords")}</p>
      {:else}
        <div class="split">
          <div class="cloud" role="list">
            {#each data.words as w (w.word)}
              <button type="button" role="listitem" class="w {sizeOf(w)}" class:on={word?.word === w.word} style:color={colorOf(w.category)}
                title={t("insight.wordTip", { folders: formatNumber(w.folders), files: formatNumber(w.files), cat: nameOf(w.category) })}
                onclick={() => pick(w)}>{w.word}</button>
            {/each}
          </div>
          {#if word}
            <aside class="detail">
              <h3 class="mac-title-3">「{word.word}」</h3>
              {#if !detail}
                <ProgressIndicator kind="spinner" size="small" label={t("view.loading")} />
              {:else}
                <p class="mac-callout sub">{t("insight.wordCounts", { folders: formatNumber(detail.folders), files: formatNumber(detail.files) })}</p>
                {#if detail.categories.length}
                  <div class="chips">
                    {#each detail.categories as c (c.category || "none")}
                      <span class="chip mac-caption-1"><i style:background={c.category ? colorOf(c.category) : "var(--label-secondary)"}></i>{nameOf(c.category)} {formatNumber(c.count)}</span>
                    {/each}
                  </div>
                {/if}
                <div class="assign">
                  <span class="mac-callout">{t("insight.assign")}</span>
                  <PopUpButton value={target} {options} onchange={(v) => { target = v; proposal = null; }} />
                </div>
                <div class="yearsel">
                  <TextField type="number" value={yearFrom} placeholder={t("insight.yearFrom")} onchange={(v) => { yearFrom = v; proposal = null; }} />
                  <span class="sub">–</span>
                  <TextField type="number" value={yearTo} placeholder={t("insight.yearTo")} onchange={(v) => { yearTo = v; proposal = null; }} />
                </div>
                <p class="mac-caption-1 sub">{t("insight.yearHint")}</p>
                {#if proposal}
                  <CategoryPlanPreview preview={proposal.preview} compact />
                  <div class="acts">
                    <Button size="small" variant="borderedProminent" loading={busy === "apply"} disabled={!!busy || !proposal.preview.changed} onclick={apply}>{t("insight.apply")}</Button>
                    <Button size="small" variant="bordered" disabled={!!busy} onclick={cancel}>{t("common.cancel")}</Button>
                  </div>
                {:else}
                  <Button size="small" variant="bordered" loading={busy === "preview"} disabled={!!busy || !target} onclick={preview}>{t("insight.preview")}</Button>
                {/if}
                <h4 class="mac-subheadline">{t("insight.folders")}</h4>
                <ul class="list mac-callout">
                  {#each detail.folder_list as f (f.id)}
                    <li><Icon name="folder" size={14} />
                      <a href={href(f)} onclick={(e) => { e.preventDefault(); navigate(href(f)); }}>{f.name}</a>
                      <span class="sub">{[f.year, nameOf(f.category)].filter(Boolean).join(" · ")}</span></li>
                  {/each}
                </ul>
                {#if detail.file_list.length}
                  <h4 class="mac-subheadline">{t("insight.files")}</h4>
                  <ul class="list mac-callout">
                    {#each detail.file_list.slice(0, 12) as f (f.id)}
                      <li><KindIcon kind={f.kind} size={14} /><span class="fname">{f.name}</span></li>
                    {/each}
                  </ul>
                {/if}
              {/if}
            </aside>
          {/if}
        </div>
        <ul class="legend mac-caption-1" aria-label={t("insight.legend")}>
          {#each legend as l (l.key || "none")}<li><i style:background={l.color}></i>{l.name}</li>{/each}
        </ul>
      {/if}
    </section>
  {/if}
</div>

<style>
  .insights { padding: var(--space-4) var(--space-6) var(--space-8); display: flex; flex-direction: column; gap: var(--space-4); color: var(--label-primary); }
  h1, h2, h3, h4, p { margin: 0; }
  .top { display: flex; align-items: flex-start; gap: var(--space-3); }
  .grow { flex: 1; }
  .busy { display: inline-flex; align-items: center; gap: var(--space-2); }
  .sub { color: var(--label-secondary); }
  .state { display: flex; flex-direction: column; align-items: center; gap: var(--space-2); padding: var(--space-8) 0; text-align: center; }
  .row { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: var(--space-4); }
  .card { display: flex; flex-direction: column; gap: var(--space-3); padding: var(--space-4); border-radius: var(--radius-lg); background: var(--fill-quaternary); min-width: 0; }
  .bars { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: var(--space-2); }
  .bars li { display: grid; grid-template-columns: auto 64px 1fr auto 72px; align-items: center; gap: var(--space-2); }
  .bl { white-space: nowrap; }
  .track { height: 8px; border-radius: var(--radius-capsule); background: var(--fill-tertiary); overflow: hidden; }
  .track i { display: block; height: 100%; border-radius: inherit; }
  .num { text-align: right; font-feature-settings: "tnum"; white-space: nowrap; }
  .years { display: flex; align-items: flex-end; gap: 2px; height: 160px; padding-bottom: 18px; position: relative; }
  .ycol { flex: 1; min-width: 4px; height: 100%; display: flex; flex-direction: column; justify-content: flex-end; align-items: center; position: relative; }
  .ybar { width: 100%; border-radius: var(--radius-sm) var(--radius-sm) 0 0; background: var(--accent); }
  .ycol:hover .ybar { opacity: .75; }
  .ylab { position: absolute; bottom: -18px; color: var(--label-secondary); white-space: nowrap; }
  .cloudhead { display: flex; align-items: baseline; gap: var(--space-3); }
  .split { display: flex; gap: var(--space-4); align-items: flex-start; }
  .cloud { flex: 1; min-width: 0; display: flex; flex-wrap: wrap; align-items: baseline; gap: var(--space-1) var(--space-3); line-height: 1.2; }
  .w { border: 0; background: none; padding: 2px var(--space-1); border-radius: var(--radius-sm); cursor: pointer; font-weight: 600; }
  .w:hover { background: var(--fill-tertiary); }
  .w.on { background: var(--accent); color: var(--on-accent) !important; }
  .w:focus-visible { box-shadow: var(--focus-ring); outline: none; }
  .detail { flex: none; width: 340px; display: flex; flex-direction: column; gap: var(--space-2); padding: var(--space-3); border-radius: var(--radius-md); background: var(--bg-primary); box-shadow: inset 0 0 0 1px var(--separator); }
  .chips { display: flex; flex-wrap: wrap; gap: var(--space-1); }
  .chip { display: inline-flex; align-items: center; gap: var(--space-1); padding: 1px var(--space-2); border-radius: var(--radius-capsule); background: var(--fill-tertiary); }
  .chip i, .legend i { width: 8px; height: 8px; border-radius: var(--radius-capsule); display: inline-block; }
  .assign { display: flex; align-items: center; gap: var(--space-2); }
  .yearsel { display: flex; align-items: center; gap: var(--space-2); }
  .yearsel :global(.lg-field) { flex: 1; }
  .acts { display: flex; gap: var(--space-2); }
  .detail > :global(.lg-btn), .detail > :global(button) { align-self: flex-start; }
  h4 { margin-top: var(--space-2); color: var(--label-secondary); }
  .list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: var(--space-1); max-height: 260px; overflow-y: auto; }
  .list li { display: flex; align-items: center; gap: var(--space-2); min-width: 0; }
  .list a { color: var(--label-primary); text-decoration: none; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .list a:hover { text-decoration: underline; }
  .list .sub { flex: none; margin-left: auto; }
  .fname { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .legend { list-style: none; margin: 0; padding: 0; display: flex; flex-wrap: wrap; gap: var(--space-3); color: var(--label-secondary); }
  .legend li { display: inline-flex; align-items: center; gap: var(--space-1); }
  @media (max-width: 900px) { .split { flex-direction: column; } .detail { width: 100%; box-sizing: border-box; } }
</style>
