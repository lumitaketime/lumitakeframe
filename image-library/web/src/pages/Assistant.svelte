<script>
  /**
   * 檔案管理助理：上方是「我可以幫忙什麼」的建議卡片（直接從目錄算出來），下方是對話。
   * 助理預設在這台電腦上執行（Ollama＋Gemma 4），先查目錄再回答，並附上來源。
   * 權限允許時，助理會提出整理動作（動作卡片）；本人勾選、按「執行」才會做，都可以復原。助理自己不會刪除、搬移或修改任何檔案。
   * 問題與回答只存在這個畫面（關掉就沒了）；用雲端服務時才會送到那個服務。
   */
  import { tick } from "svelte";
  import { Alert, Button, Icon, ProgressIndicator } from "../ui/index.js";
  import KindIcon from "../views/KindIcon.svelte";
  import ActionCard from "../views/ActionCard.svelte";
  import { loadAssistantStatus, loadSuggestions, downloadModel, startOllama, ask, loadChats, loadChat, deleteChats } from "../data/assistant.js";
  import { Checkbox } from "../ui/index.js";
  import { setFrame } from "../shell/frame.svelte.js";
  import { t, i18n, formatBytes, formatNumber } from "../i18n/index.svelte.js";
  import { app, toast, refresh } from "../lib/state.svelte.js";
  import { route, navigate } from "../lib/router.svelte.js";

  let st = $state(null);
  // ---- 對話紀錄：每段對話存在這台電腦，換頁、重開 App 都看得到；可以多選刪除 ----
  let chats = $state([]);
  let chatId = $state(null);
  let selecting = $state(false);
  let picked = $state(new Set());
  let confirmDelete = $state(false);
  let showHistory = $state(false); // 窄的視窗：對話紀錄收起來，按按鈕才打開
  let pageWidth = $state(1200);
  const reloadChats = () => loadChats().then((d) => (chats = d)).catch(() => {});
  $effect(() => {
    reloadChats();
  });
  async function openChat(id) {
    if (asking) return;
    try {
      const d = await loadChat(id);
      chatId = d.id;
      messages = d.messages.map((m) => ({ ...m, busy: false }));
      await scroll();
    } catch (e) {
      toast(e.message, "error");
    }
  }
  function newChat() {
    if (asking) return;
    chatId = null;
    messages = [];
    input?.focus();
  }
  function togglePick(id, on) {
    const next = new Set(picked);
    if (on) next.add(id);
    else next.delete(id);
    picked = next;
  }
  const allPicked = $derived(chats.length > 0 && chats.every((c) => picked.has(c.id)));
  async function removePicked() {
    confirmDelete = false;
    const ids = [...picked];
    try {
      await deleteChats(ids);
      if (ids.includes(chatId)) newChat();
      picked = new Set();
      selecting = false;
      toast(t("ai.history.deleted", { n: formatNumber(ids.length) }));
      reloadChats();
    } catch (e) {
      toast(e.message, "error");
    }
  }
  const dayOf = (iso) => (iso || "").slice(0, 10);
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
    const reply = { role: "assistant", content: "", steps: [], sources: [], actions: [], error: "", busy: true };
    messages.push(reply);
    const at = messages.length - 1;
    asking = true;
    await scroll();
    stopAsk = ask({ question: q, history, context, lang: i18n.locale, chatId }, (ev) => {
      const m = messages[at];
      if (ev.type === "chat") { if (chatId !== ev.id) { chatId = ev.id; reloadChats(); } }
      else if (ev.type === "step") m.steps.push(ev);
      else if (ev.type === "action") m.actions.push(ev.action);
      else if (ev.type === "token") m.content += ev.text;
      else if (ev.type === "done") { m.sources = ev.sources || []; m.busy = false; asking = false; reloadChats(); }
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
  const hostOf = (u) => { try { return new URL(u).host; } catch { return u || ""; } };
  const STEP = { propose_label: "ai.step.propose", propose_smart_folder: "ai.step.propose", propose_mark_delete: "ai.step.propose",
    propose_move: "ai.step.propose", propose_rename: "ai.step.propose", propose_to_pending: "ai.step.propose", search_files: "ai.step.search", largest_folders: "ai.step.folders", drives_overview: "ai.step.drives", duplicates: "ai.step.dupes", read_document: "ai.step.read" };
</script>

<div class="page" bind:clientWidth={pageWidth}>
{#if showHistory || pageWidth >= 900}
<aside class="history" class:overlay={pageWidth < 900} aria-label={t("ai.history.title")}>
  <div class="hhead">
    <b class="mac-headline">{t("ai.history.title")}</b>
    <span class="grow"></span>
    {#if chats.length}
      <Button size="small" variant="borderless" onclick={() => { selecting = !selecting; picked = new Set(); }}>{selecting ? t("common.done") : t("ai.history.select")}</Button>
    {/if}
    <Button size="small" variant="bordered" icon="compose" iconOnly aria-label={t("ai.history.new")} onclick={newChat} />
  </div>
  {#if selecting}
    <div class="hbar mac-callout">
      <Checkbox checked={allPicked} onchange={(on) => (picked = on ? new Set(chats.map((c) => c.id)) : new Set())} label={t("ai.history.all")} />
      <span class="grow"></span>
      <Button size="small" variant="borderless" role="destructive" disabled={!picked.size} onclick={() => (confirmDelete = true)}>
        {t("ai.history.delete", { n: formatNumber(picked.size) })}</Button>
    </div>
  {/if}
  {#if chats.length}
    <ul class="hlist">
      {#each chats as c (c.id)}
        <li>
          {#if selecting}
            <label class="hrow mac-body" class:on={picked.has(c.id)}>
              <Checkbox checked={picked.has(c.id)} onchange={(on) => togglePick(c.id, on)} aria-label={c.title} />
              <span class="htext"><span class="ht">{c.title}</span><span class="hd mac-caption-1">{dayOf(c.updated_at)}</span></span>
            </label>
          {:else}
            <button type="button" class="hrow mac-body" class:on={c.id === chatId} onclick={() => { openChat(c.id); if (pageWidth < 900) showHistory = false; }}>
              <span class="htext"><span class="ht">{c.title}</span><span class="hd mac-caption-1">{dayOf(c.updated_at)}</span></span>
            </button>
          {/if}
        </li>
      {/each}
    </ul>
  {:else}
    <p class="mac-callout hempty">{t("ai.history.empty")}</p>
  {/if}
  <p class="mac-caption-1 hnote">{t("ai.history.note")}</p>
</aside>
{/if}
<div class="assistant">
  <div class="log" bind:this={log}>
    {#if pageWidth < 900}
      <Button size="small" variant="bordered" icon="list" onclick={() => (showHistory = !showHistory)}>{t("ai.history.title")}</Button>
    {/if}
    <header class="intro">
      <span class="badge"><Icon name="sparkles" size={20} weight="medium" /></span>
      <div>
        <h1 class="mac-title-2">{t("ai.title")}</h1>
        <p class="mac-callout sub">{t("ai.lead")} {#if st}<a class="model" href="/settings/assistant" onclick={(e) => { e.preventDefault(); navigate("/settings/assistant"); }}>{st.service ? `${st.service} · ` : ""}{st.model}</a>
          · <a class="model" href="/settings/assistant" onclick={(e) => { e.preventDefault(); navigate("/settings/assistant"); }}>{t("ai.permChip", { level: t(`set.ai.perm.${st.permission}`) })}</a>{/if}</p>
      </div>
    </header>

    {#if st?.remote}
      <p class="remote mac-callout"><Icon name="exclamation-triangle" size={13} />{t("ai.remoteBanner", { host: hostOf(st.url), content: st.cloud_content && st.permission >= 2 ? t("ai.remoteContent") : t("ai.remoteNoContent") })}
        <a href="/settings/assistant" onclick={(e) => { e.preventDefault(); navigate("/settings/assistant"); }}>{t("ai.changeModel")}</a></p>
    {/if}
    {#if st && !ready}
      <section class="setup mac-body" aria-live="polite">
        {#if st.provider !== "ollama"}
          <p><b>{st.message}</b></p>
          <div class="acts"><Button variant="borderedProminent" onclick={() => navigate("/settings/assistant")}>{t("ai.changeModel")}</Button></div>
        {:else if !st.ollama}
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
            <p class="step mac-callout"><Icon name={s.tool.startsWith("propose_") ? "sparkles" : "magnifyingglass"} size={11} />{t(STEP[s.tool] || "ai.step.other", { q: s.args?.query || "" })}</p>
          {/each}
          {#if m.content}
            <p class="answer">{#each parts(m.content) as p, j (j)}{#if p.ref}<button type="button" class="ref mac-caption-1" onclick={() => openSource(m.sources[p.ref - 1])}
              disabled={!m.sources[p.ref - 1]}>{p.ref}</button>{:else}{p.text}{/if}{/each}</p>
          {:else if m.busy}
            <p class="thinking mac-callout"><ProgressIndicator kind="spinner" size="small" label={t("ai.thinking")} />{t("ai.thinking")}</p>
          {/if}
          {#if m.error}<p class="err mac-callout">{m.error}</p>{/if}
          {#each m.actions as _, j (m.actions[j].id)}
            <ActionCard bind:action={m.actions[j]} />
          {/each}
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
  <p class="privacy mac-caption-1">{st?.remote ? t("ai.privacyRemote", { service: st.service || hostOf(st.url) }) : t("ai.privacy")}</p>
</div>

</div>

{#if confirmDelete}
  <div class="backdrop">
    <Alert title={t("ai.history.confirmTitle", { n: formatNumber(picked.size) })} message={t("ai.history.confirmMessage")} actions={[
      { label: t("ai.history.deleteShort"), role: "destructive", onPress: removePicked },
      { label: t("common.cancel"), role: "cancel", onPress: () => (confirmDelete = false) },
    ]} />
  </div>
{/if}
{#if confirmDownload}
  <div class="backdrop">
    <Alert title={t("ai.setup.confirmTitle", { model: st.model })} message={t("ai.setup.confirmMessage")} actions={[
      { label: t("ai.setup.download"), role: "default", onPress: download },
      { label: t("common.cancel"), role: "cancel", onPress: () => (confirmDownload = false) },
    ]} />
  </div>
{/if}

<style>
  .page { height: 100%; min-height: 0; display: flex; position: relative; }
  .history { flex: none; width: 250px; min-height: 0; display: flex; flex-direction: column; gap: var(--space-2); padding: var(--space-4) var(--space-3);
    border-right: 1px solid var(--separator); box-sizing: border-box; }
  .history.overlay { position: absolute; z-index: 30; inset: 0 auto 0 0; background: var(--bg-primary); box-shadow: var(--shadow-popover); }
  .hhead, .hbar { display: flex; align-items: center; gap: var(--space-1); color: var(--label-primary); }
  .grow { flex: 1; }
  .hlist { flex: 1; min-height: 0; overflow-y: auto; list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 2px; }
  .hrow { width: 100%; display: flex; align-items: center; gap: var(--space-2); padding: var(--space-1) var(--space-2); border: 0; border-radius: var(--radius-sm);
    background: none; color: var(--label-primary); font: inherit; text-align: left; cursor: pointer; box-sizing: border-box; }
  .hrow:hover { background: var(--fill-quaternary); }
  .hrow.on { background: var(--fill-tertiary); }
  .htext { display: flex; flex-direction: column; min-width: 0; }
  .ht { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .hd, .hempty, .hnote { color: var(--label-secondary); }
  .hempty, .hnote { margin: 0; }
  .assistant { flex: 1; min-width: 0;
    height: 100%; min-height: 0; display: flex; flex-direction: column; max-width: 860px; margin: 0 auto; padding: 0 var(--space-5); box-sizing: border-box; }
  .log { flex: 1; min-height: 0; overflow-y: auto; padding: var(--space-5) 0 var(--space-3); display: flex; flex-direction: column; gap: var(--space-3); }
  .intro { display: flex; align-items: center; gap: var(--space-3); }
  .badge { flex: none; display: inline-flex; align-items: center; justify-content: center; width: 40px; height: 40px; border-radius: var(--radius-md);
    background: var(--accent); color: var(--on-accent); }
  h1, h2 { margin: 0; color: var(--label-primary); }
  .sub { color: var(--label-secondary); }
  .intro p { margin: var(--space-1) 0 0; }
  .intro .model { color: var(--accent); white-space: nowrap; }
  .remote { display: flex; align-items: center; gap: var(--space-2); flex-wrap: wrap; margin: 0; padding: var(--space-2) var(--space-3); border-radius: var(--radius-md);
    background: color-mix(in srgb, var(--system-orange) 14%, transparent); color: var(--label-primary); }
  .remote a { color: var(--accent); }
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
