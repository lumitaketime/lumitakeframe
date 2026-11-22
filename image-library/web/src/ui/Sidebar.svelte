<script>
  /**
   * 側邊欄：App 的主要導覽，浮在內容上的玻璃面板；最多兩層。
   * sections：[{id, title, items, href, collapsible, open}]（有 href 的群組標題可以按）；bottom：固定在底部的項目（例如「掃描進度」「設定」）。
 * - collapsible：標題旁有收合按鈕（像 Finder）；收起來的群組記在 collapsed（{id: true}），按下時呼叫 ontogglesection(id)。
 * - open：暫時一定要展開（例如正在把東西拖進「喜好項目」）。
 * - droppable：可以把東西放進這一組（放在空白處＝放在最後），呼叫 onsectiondrop(e, section)。
   * 項目：{value, label, icon, href, badge, trailing, muted, sub, meter, progress, children}
   * - href：有網址的項目畫成連結（可以用 ⌘ 加按開新視窗）；按下時一樣呼叫 onchange。
   * - muted：次要文字色（例如未連線的硬碟）；trailing：列尾的文字（例如「未連線」）。狀態不能只靠顏色表示。
   * - dot：用顏色圓點代替圖示（CSS 顏色）；draggable／droppable：可以拖曳、可以把東西放在這一項上。
   * - sub：第二行的說明（給陣列就是多行）；meter：0–1 的容量條；progress：true 是轉圈、0–1 是進度環。
   */
  import Icon from "./Icon.svelte";
  import ProgressIndicator from "./ProgressIndicator.svelte";
  import { t } from "../i18n/index.svelte.js";
  import { usePlatform, TYPE } from "./platform.js";

  let { sections = [], bottom = [], value = $bindable(), onchange, floating = true, width = 220, class: cls = "", label = "", header, footer,
    onitemdragstart, onitemdrop, onitemcontext, collapsed = {}, ontogglesection, onsectiondrop } = $props();
  let over = $state(null);
  const platform = usePlatform();
  let closed = $state({});
  function pick(e, it) {
    if (it.href && (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0)) return; // 交給瀏覽器開新視窗
    if (it.href) e.preventDefault();
    value = it.value;
    onchange?.(it.value, it);
  }
</script>

{#snippet row(it, depth)}
  {@const sel = it.value === value}
  {@const kids = depth === 0 && it.children?.length > 0}
  {@const open = !closed[it.value]}
  {@const tall = !!it.sub || it.meter != null}
  <li>
    <svelte:element this={it.href ? "a" : "button"} href={it.href} type={it.href ? undefined : "button"} role={it.href ? undefined : "button"}
      aria-current={sel ? "page" : undefined} aria-expanded={kids ? open : undefined}
      class="lg-side-item {TYPE[platform].body}" class:lg-on={sel} class:lg-side-sub={depth > 0} class:rm-tall={tall} class:rm-over={over === it.value} onclick={(e) => pick(e, it)}
      draggable={it.draggable ? "true" : undefined} ondragstart={it.draggable ? (e) => onitemdragstart?.(e, it) : undefined}
      ondragover={it.droppable ? (e) => { e.preventDefault(); over = it.value; } : undefined}
      ondragleave={it.droppable ? () => { if (over === it.value) over = null; } : undefined}
      ondrop={it.droppable ? (e) => { e.preventDefault(); e.stopPropagation(); over = null; onitemdrop?.(e, it); } : undefined}
      oncontextmenu={onitemcontext && it.context ? (e) => { e.preventDefault(); onitemcontext(e, it); } : undefined}>
      {#if kids}
        <!-- svelte-ignore a11y_click_events_have_key_events -->
        <span class="lg-side-disc" class:lg-open={open} role="presentation" onclick={(e) => { e.stopPropagation(); e.preventDefault(); closed[it.value] = open; }}>
          <Icon name="chevron-right" size={10} weight="bold" />
        </span>
      {:else if depth === 0}<span class="lg-side-disc-space"></span>{/if}
      {#if it.dot}<i class="rm-dot" style:background={it.dot}></i>{:else if it.icon}<Icon name={it.icon} size={platform === "ios" ? 20 : 15} weight="medium" class="lg-side-icon {it.muted ? 'rm-muted' : ''}" />{/if}
      <span class="rm-text">
        <span class="rm-line">
          <span class="lg-side-label" class:rm-muted={it.muted}>{it.label}</span>
          {#if it.progress != null && it.progress !== false}
            <ProgressIndicator kind="circular" size="small" value={it.progress === true ? undefined : it.progress} label={it.trailing || ""} />
          {/if}
          {#if it.trailing}<span class="lg-side-badge {TYPE[platform].callout}">{it.trailing}</span>{/if}
          {#if it.badge != null}<span class="lg-side-badge {TYPE[platform].callout}">{it.badge}</span>{/if}
        </span>
        {#if it.meter != null}<span class="rm-meter" class:rm-muted={it.muted} aria-hidden="true"><i style:width="{Math.max(0, Math.min(1, it.meter)) * 100}%"></i></span>{/if}
        {#each [it.sub].flat().filter(Boolean) as line, i (i)}<span class="rm-sub {TYPE[platform].caption}">{line}</span>{/each}
      </span>
    </svelte:element>
    {#if kids && open}<ul class="lg-side-list">{#each it.children as k (k.value)}{@render row(k, 1)}{/each}</ul>{/if}
  </li>
{/snippet}

<nav aria-label={label || t("common.sidebar")} class="lg-sidebar lg-sidebar-{platform} {floating ? 'lg-glass lg-glass-regular lg-sidebar-floating' : 'lg-sidebar-inline'} {cls}" style:width="{width}px">
  {#if header}<div class="lg-side-top">{@render header()}</div>{/if}
  <div class="rm-scroll">
    {#each sections as s, i (s.id || i)}
      {@const shut = s.collapsible && !s.open && !!collapsed[s.id]}
      {@const listId = s.id ? `side-${s.id}` : undefined}
      <!-- svelte-ignore a11y_no_static_element_interactions -->
      <div class="lg-side-section" class:rm-shut={shut} class:rm-drop-zone={s.droppable}
        ondragover={s.droppable ? (e) => e.preventDefault() : undefined}
        ondrop={s.droppable ? (e) => { e.preventDefault(); e.stopPropagation(); over = null; onsectiondrop?.(e, s); } : undefined}>
        {#if s.title}
          <div class="rm-heading-row">
            {#if s.href}
              <a class="lg-side-heading rm-heading-link {platform === 'ios' ? 'ios-title-3' : 'mac-subheadline'}" href={s.href} aria-current={s.current ? "page" : undefined}
                onclick={(e) => pick(e, { href: s.href, value: undefined })}>{s.title}<Icon name="chevron-right" size={9} weight="bold" /></a>
            {:else if s.collapsible}
              <!-- 整個標題都可以按：收起或展開這一組 -->
              <button type="button" class="lg-side-heading rm-heading-button {platform === 'ios' ? 'ios-title-3' : 'mac-subheadline'}"
                aria-expanded={!shut} aria-controls={listId} onclick={() => ontogglesection?.(s.id)}>{s.title}</button>
            {:else}<div class="lg-side-heading {platform === 'ios' ? 'ios-title-3' : 'mac-subheadline'}">{s.title}</div>{/if}
            {#if s.collapsible}
              <button type="button" class="rm-collapse" class:rm-collapse-shut={shut} aria-expanded={!shut} aria-controls={listId}
                aria-label={shut ? t("common.showSection", { name: s.title }) : t("common.hideSection", { name: s.title })}
                tabindex={s.href ? 0 : -1} onclick={() => ontogglesection?.(s.id)}>
                <Icon name="chevron-right" size={9} weight="bold" />
              </button>
            {/if}
          </div>
        {/if}
        {#if !shut}
          <ul class="lg-side-list" id={listId}>{#each s.items as it (it.value)}{@render row(it, 0)}{/each}</ul>
          {#if s.note}<p class="rm-note {TYPE[platform].callout}">{s.note}</p>{/if}
        {/if}
      </div>
    {/each}
  </div>
  {#if bottom.length}<ul class="lg-side-list rm-bottom">{#each bottom as it (it.value)}{@render row(it, 0)}{/each}</ul>{/if}
  {#if footer}<div class="lg-side-top">{@render footer()}</div>{/if}
</nav>

<style>
  /* 中間可捲動，標誌與底部的項目固定 */
  .lg-sidebar { overflow: hidden; }
  .rm-scroll { flex: 1; min-height: 0; overflow-y: auto; overflow-x: hidden; display: flex; flex-direction: column; gap: var(--space-3); overscroll-behavior: contain; }
  .rm-bottom { flex: none; padding-top: var(--space-2); border-top: 1px solid var(--separator); }
  .lg-side-item { text-decoration: none; }
  .rm-text { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 3px; }
  .rm-line { display: flex; align-items: center; gap: 6px; min-width: 0; }
  .rm-muted, :global(.lg-side-icon.rm-muted) { color: var(--label-glass-secondary); }
  /* 兩行的項目（硬碟）：容量條與說明 */
  .lg-side-item.rm-tall { height: auto; padding-top: 6px; padding-bottom: 6px; align-items: flex-start; }
  .rm-tall :global(.lg-side-icon), .rm-tall .lg-side-disc, .rm-tall .lg-side-disc-space { margin-top: 2px; }
  .rm-meter { display: block; height: 3px; border-radius: var(--radius-capsule); background: var(--fill-secondary); overflow: hidden; }
  .rm-meter i { display: block; height: 100%; border-radius: inherit; background: var(--accent); }
  .rm-meter.rm-muted i { background: var(--label-glass-secondary); }
  .rm-sub { color: var(--label-glass-secondary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; font-weight: 400; }
  /* 可以按的群組標題（例如「硬碟」→ 硬碟總覽） */
  .rm-heading-link { display: flex; align-items: center; gap: var(--space-1); text-decoration: none; border-radius: var(--radius-sm); margin-bottom: var(--space-1); padding-top: 2px; padding-bottom: 2px; }
  .rm-heading-link:hover, .rm-heading-link[aria-current="page"] { color: var(--label-primary); background: var(--fill-quaternary); }
  /* 收合：標題列右邊的小箭頭，滑鼠移到這一組或用鍵盤選到時才明顯（像 Finder） */
  .rm-heading-row { display: flex; align-items: center; gap: var(--space-1); }
  .rm-heading-row > :first-child { flex: 1; min-width: 0; }
  .rm-heading-button { display: block; width: 100%; text-align: start; border: 0; background: none; cursor: default; border-radius: var(--radius-sm); }
  .rm-collapse { flex: none; display: inline-flex; align-items: center; justify-content: center; width: 20px; height: 20px; padding: 0; border: 0; border-radius: var(--radius-sm);
    background: none; color: var(--label-glass-secondary); opacity: 0; transform: rotate(90deg); transition: opacity var(--dur-fast) var(--ease), transform var(--dur-quick) var(--ease-out); }
  .rm-collapse.rm-collapse-shut { transform: rotate(0deg); }
  .lg-side-section:hover .rm-collapse, .rm-collapse:focus-visible, .rm-shut .rm-collapse { opacity: 1; }
  .rm-collapse:hover { background: var(--fill-quaternary); color: var(--label-primary); }
  .rm-shut .lg-side-heading { margin-bottom: 0; }
  .rm-dot { flex: none; width: 11px; height: 11px; margin: 0 2px; border-radius: var(--radius-capsule); box-shadow: inset 0 0 0 1px var(--separator); }
  .lg-side-item.rm-over { box-shadow: inset 0 2px 0 var(--accent); }
  .rm-note { margin: 0; padding: var(--space-1) var(--space-2); color: var(--label-glass-secondary); }
</style>
