<script>
  /**
   * 檔案管理助理：上方是「我可以幫忙什麼」的建議卡片（直接從目錄算出來），下方是對話。
   * 助理在這台電腦上執行（Ollama＋Gemma 4），先查目錄再回答，並附上來源；它不會刪除、搬移或修改任何檔案。
   * 問題與回答只存在這個畫面（關掉就沒了），不會上傳。
   */
  import { tick } from "svelte";
  import { Alert, Button, Icon, ProgressIndicator } from "../ui/index.js";
  import KindIcon from "../views/KindIcon.svelte";
  import { loadAssistantStatus, loadSuggestions, downloadModel, startOllama, ask } from "../data/assistant.js";
  import { setFrame } from "../shell/frame.svelte.js";
  import { t, i18n, formatBytes, formatNumber } from "../i18n/index.svelte.js";
  import { app, toast, refresh } from "../lib/state.svelte.js";
  import { route, navigate } from "../lib/router.svelte.js";

  let st = $state(null);
  let cards = $state([]);
  let messages = $state([]); // {role, content, steps, sources, error, busy}
  let question = $state("");
  let stopAsk = null;
  let asking = $state(false);
  let confirmDownload = $state(false);
  let log = $state();
  let input = $state();

  $effect(() => {
    setFrame({ crumbs: [], status: "", location: null, info: null });
  });
  function loadAll() {
    loadAssistantStatus().then((d) => (st = d)).catch(() => {});
    loadSuggestions().then((d) => (cards = d)).catch(() => {});
  }
  $effect(() => {
    app.refreshKey;
    loadAll();
  });
  const pull = $derived(app.server?.jobs?.active?.find((j) => j.kind === "pull" && j.model === st?.model) || null);
  const ready = $derived(!!st?.model_ready);
  // 下載進行中：每 5 秒看一次好了沒
  $effect(() => {
    if (!pull) return;
    const timer = setInterval(() => loadAssistantStatus().then((d) => (st = d)).catch(() => {}), 5000);
    return () => clearInterval(timer);
  });

  // 從某個資料夾打開助理時（網址帶 at=），告訴助理使用者目前在哪裡
  const context = $derived(route.query.at || "");

  async function send(text) {
    const q = (text ?? question).trim();
    if (!q || asking) return;
    question = "";
    const history = messages.filter((m) => !m.error).map((m) => ({ role: m.role, content: m.content }));
    messages.push({ role: "user", content: q });
    const reply = { role: "assistant", content: "", steps: [], sources: [], error: "", busy: true };
    messages.push(reply);
    const at = messages.length - 1;
    asking = true;
    await scroll();
    stopAsk = ask({ question: q, history, context, lang: i18n.locale }, (ev) => {
      const m = messages[at];
      if (ev.type === "step") m.steps.push(ev);
      else if (ev.type === "token") m.content += ev.text;
      else if (ev.type === "done") { m.sources = ev.sources || []; m.busy = false; asking = false; }
      else if (ev.type === "error") { m.error = ev.message; m.busy = false; asking = false; }
      scroll();
    });
  }
  function stop() {
    stopAsk?.();
    const m = messages[messages.length - 1];
    if (m?.busy) { m.busy = false; m.content += m.content ? "…" : ""; }
    asking = false;
  }
  async function scroll() {
    await tick();
    if (log) log.scrollTop = log.scrollHeight;
  }
  function onkeydown(e) {
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
      e.preventDefault();
      send();
    }
  }

  async function download() {
    confirmDownload = false;
    try {
      await downloadModel(st.model);
      toast(t("ai.downloading", { model: st.model }));
      refresh();
    } catch (e) {
      toast(e.message, "error");
    }
  }
  async function openOllama() {
    try {
      await startOllama();
      setTimeout(loadAll, 2500);
    } catch (e) {
      toast(e.message, "error");
    }
  }

  // 建議卡片：文字依語言組成；有連結的直接前往，有 ask 的幫你問助理
  function cardText(c) {
    const p = { ...c, bytes: formatBytes(c.bytes || 0), files: formatNumber(c.files || 0), count: formatNumber(c.count || 0), groups: formatNumber(c.groups || 0) };
    return { title: t(`ai.card.${c.key}`, p), hint: t(`ai.card.${c.key}.hint`, p) };
  }
  function useCard(c) {
    if (c.ask) return ready ? send(t(`ai.ask.${c.ask}`)) : input?.focus();
    if (c.href) navigate(c.href);
  }
  const CARD_ICONS = { dupes: "duplicate", compare: "duplicate", pending: "trash", unread: "document", failed: "document", incomplete: "external-drive-fill",
    stale: "clock", big: "treemap", ask_find: "magnifyingglass" };

  // 回答裡的 [1]、[2]：換成可以點的來源
  function parts(text) {
    const out = [];
    let last = 0;
    for (const m of text.matchAll(/\[(\d{1,2})\]/g)) {
      if (m.index > last) out.push({ text: text.slice(last, m.index) });
      out.push({ ref: Number(m[1]) });
      last = m.index + m[0].length;
    }
    if (last < text.length) out.push({ text: text.slice(last) });
    return out;
  }
  // 回答裡真的有引用的來源（沒有引用任何一個時全部列出）
  const cited = (m) => new Set([...m.content.matchAll(/\[(\d{1,2})\]/g)].map((x) => Number(x[1])));
  function openSource(s) {
    if (!s) return;
    if (s.type === "folder") return navigate(`/folders/${s.root_id}${s.path ? `?path=${encodeURIComponent(s.path)}` : ""}`);
    navigate(`/folders/${s.root_id}${s.folder ? `?path=${encodeURIComponent(s.folder)}` : ""}`);
  }
  const STEP = { search_files: "ai.step.search", largest_folders: "ai.step.folders", drives_overview: "ai.step.drives", duplicates: "ai.step.dupes", read_document: "ai.step.read" };
</script>

<div class="assistant">
  <div class="log" bind:this={log}>
    <header class="intro">
      <span class="badge"><Icon name="sparkles" size={20} weight="medium" /></span>
      <div>
        <h1 class="mac-title-2">{t("ai.title")}</h1>
        <p class="mac-callout sub">{t("ai.lead")}</p>
      </div>
    </header>

    {#if st && !ready}
      <section class="setup mac-body" aria-live="polite">
        {#if !st.ollama}
          <p><b>{st.installed ? t("ai.setup.ollamaOff") : t("ai.setup.noOllama")}</b></p>
          <p class="sub mac-callout">{t("ai.setup.ollamaHint")}</p>
          <div class="acts">
            {#if st.installed}<Button variant="borderedProminent" onclick={openOllama}>{t("ai.setup.openOllama")}</Button>
            {:else}<Button variant="borderedProminent" onclick={() => navigate("/welcome?step=ollama")}>{t("ai.setup.installOllama")}</Button>{/if}
            <Button variant="bordered" onclick={loadAll}>{t("view.retry")}</Button>
          </div>
        {:else if pull}
          <p><b>{t("ai.setup.downloading", { model: st.model })}</b></p>
          <ProgressIndicator value={pull.total ? pull.done / pull.total : undefined} label={t("ai.setup.downloading", { model: st.model })} />
          <p class="sub mac-callout">{pull.total ? `${formatBytes(pull.done)}／${formatBytes(pull.total)}` : t("dupes.waiting")}</p>
        {:else}
          <p><b>{t("ai.setup.noModel", { model: st.model })}</b></p>
          <p class="sub mac-callout">{t("ai.setup.modelHint")}</p>
          <div class="acts"><Button variant="borderedProminent" icon="arrow-down" onclick={() => (confirmDownload = true)}>{t("ai.setup.download")}</Button></div>
        {/if}
      </section>
    {/if}

    {#if cards.length && !messages.length}
      <h2 class="mac-headline">{t("ai.cards")}</h2>
      <div class="cards">
        {#each cards as c, k (k)}
          {@const txt = cardText(c)}
          <button type="button" class="card" onclick={() => useCard(c)}>
            <Icon name={CARD_ICONS[c.key] || "sparkles"} size={16} />
            <span><b class="mac-body">{txt.title}</b><span class="sub mac-callout">{txt.hint}</span></span>
          </button>
        {/each}
      </div>
    {/if}

    {#each messages as m, k (k)}
      {#if m.role === "user"}
        <div class="msg user mac-body">{m.content}</div>
      {:else}
        <div class="msg bot mac-body">
          {#each m.steps as s, j (j)}
            <p class="step mac-callout"><Icon name="magnifyingglass" size={11} />{t(STEP[s.tool] || "ai.step.other", { q: s.args?.query || "" })}</p>
          {/each}
          {#if m.content}
            <p class="answer">{#each parts(m.content) as p, j (j)}{#if p.ref}<button type="button" class="ref mac-caption-1" onclick={() => openSource(m.sources[p.ref - 1])}
              disabled={!m.sources[p.ref - 1]}>{p.ref}</button>{:else}{p.text}{/if}{/each}</p>
          {:else if m.busy}
            <p class="thinking mac-callout"><ProgressIndicator kind="spinner" size="small" label={t("ai.thinking")} />{t("ai.thinking")}</p>
          {/if}
          {#if m.error}<p class="err mac-callout">{m.error}</p>{/if}
          {#if m.sources.length && !m.busy}
            <ol class="sources mac-callout">
              {#each m.sources as s, j (j)}
                {#if cited(m).size === 0 || cited(m).has(j + 1)}
                <li><button type="button" onclick={() => openSource(s)}>
                  <span class="num">{j + 1}</span><KindIcon kind={s.type === "folder" ? "folder" : "document"} size={13} />
                  <span class="name">{s.name}</span><span class="sub where">{[s.drive, s.type === "folder" ? s.path : s.folder].filter(Boolean).join(" › ")}{s.size ? ` · ${formatBytes(s.size)}` : ""}</span>
                </button></li>
                {/if}
              {/each}
            </ol>
          {/if}
        </div>
      {/if}
    {/each}
  </div>

  <footer class="composer">
    <!-- svelte-ignore a11y_autofocus -->
    <textarea bind:this={input} class="mac-body" rows="1" bind:value={question} {onkeydown} disabled={!ready} aria-label={t("ai.placeholder")}
      placeholder={ready ? t("ai.placeholder") : t("ai.placeholderOff")}></textarea>
    {#if asking}
      <Button variant="bordered" onclick={stop}>{t("drives.stop")}</Button>
    {:else}
      <Button variant="borderedProminent" icon="arrow-up" iconOnly aria-label={t("ai.send")} disabled={!ready || !question.trim()} onclick={() => send()} />
    {/if}
  </footer>
  <p class="privacy mac-caption-1">{t("ai.privacy")}</p>
</div>

{#if confirmDownload}
  <div class="backdrop">
    <Alert title={t("ai.setup.confirmTitle", { model: st.model })} message={t("ai.setup.confirmMessage")} actions={[
      { label: t("ai.setup.download"), role: "default", onPress: download },
      { label: t("common.cancel"), role: "cancel", onPress: () => (confirmDownload = false) },
    ]} />
  </div>
{/if}

<style>
  .assistant { height: 100%; min-height: 0; display: flex; flex-direction: column; max-width: 860px; margin: 0 auto; padding: 0 var(--space-5); box-sizing: border-box; }
  .log { flex: 1; min-height: 0; overflow-y: auto; padding: var(--space-5) 0 var(--space-3); display: flex; flex-direction: column; gap: var(--space-3); }
  .intro { display: flex; align-items: center; gap: var(--space-3); }
  .badge { flex: none; display: inline-flex; align-items: center; justify-content: center; width: 40px; height: 40px; border-radius: var(--radius-md);
    background: var(--accent); color: var(--on-accent); }
  h1, h2 { margin: 0; color: var(--label-primary); }
  .sub { color: var(--label-secondary); }
  .intro p { margin: var(--space-1) 0 0; }
  .setup { display: flex; flex-direction: column; gap: var(--space-2); padding: var(--space-3) var(--space-4); border-radius: var(--radius-md); background: var(--fill-quaternary); }
  .setup p { margin: 0; }
  .acts { display: flex; gap: var(--space-2); flex-wrap: wrap; }
  .cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: var(--space-2); }
  .card { display: flex; align-items: flex-start; gap: var(--space-2); padding: var(--space-3); border: 0; border-radius: var(--radius-md); background: var(--fill-quaternary);
    color: var(--label-primary); font: inherit; text-align: left; cursor: pointer; }
  .card:hover { background: var(--fill-tertiary); }
  .card :global(svg) { flex: none; margin-top: 2px; color: var(--accent); }
  .card > span { display: flex; flex-direction: column; gap: 2px; }
  .msg { max-width: 92%; padding: var(--space-2) var(--space-3); border-radius: var(--radius-lg); line-height: 1.55; }
  .msg.user { align-self: flex-end; background: var(--accent); color: var(--on-accent); white-space: pre-wrap; }
  .msg.bot { align-self: flex-start; background: var(--fill-quaternary); color: var(--label-primary); }
  .msg p { margin: 0; }
  .answer { white-space: pre-wrap; }
  .step { display: flex; align-items: center; gap: var(--space-1); color: var(--label-secondary); }
  .thinking { display: flex; align-items: center; gap: var(--space-2); color: var(--label-secondary); }
  .err { color: var(--system-red); }
  .ref { display: inline-flex; align-items: center; justify-content: center; min-width: 1.5em; height: 1.4em; margin: 0 1px; padding: 0 4px; border: 0;
    border-radius: var(--radius-capsule); background: var(--accent); color: var(--on-accent); font: inherit; cursor: pointer; vertical-align: 0.1em; }
  .sources { list-style: none; margin: var(--space-2) 0 0; padding: var(--space-2) 0 0; border-top: 1px solid var(--separator); display: flex; flex-direction: column; gap: 2px; }
  .sources button { width: 100%; display: flex; align-items: center; gap: var(--space-2); padding: 2px var(--space-1); border: 0; border-radius: var(--radius-sm);
    background: none; color: inherit; font: inherit; text-align: left; cursor: pointer; }
  .sources button:hover { background: var(--fill-tertiary); }
  .num { flex: none; min-width: 1.4em; text-align: center; color: var(--label-secondary); }
  .sources .name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; min-width: 0; flex: none; max-width: 50%; }
  .sources .where { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; min-width: 0; }
  .composer { flex: none; display: flex; align-items: flex-end; gap: var(--space-2); padding: var(--space-2); border-radius: var(--radius-lg);
    background: var(--fill-quaternary); box-shadow: inset 0 0 0 1px var(--separator); }
  textarea { flex: 1; min-height: var(--control-regular); max-height: 160px; resize: none; border: 0; padding: var(--space-1) var(--space-2); background: transparent;
    color: var(--label-primary); font: inherit; field-sizing: content; outline: none; }
  textarea::placeholder { color: var(--label-placeholder); }
  textarea:focus-visible { box-shadow: none; } /* 焦點框畫在外面整個輸入區 */
  .composer:focus-within { box-shadow: var(--focus-ring); }
  .privacy { margin: var(--space-1) 0 var(--space-3); text-align: center; color: var(--label-secondary); }
  .backdrop { position: fixed; inset: 0; z-index: 320; display: flex; align-items: center; justify-content: center; background: var(--media-scrim-light); }
</style>
