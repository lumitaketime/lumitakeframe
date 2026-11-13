<script>
  /**
   * 工具列：標題、導覽與最常用的動作，分成前、中、後三區；每個內層陣列是一組玻璃膠囊。
   * 項目：{icon, label, onClick, prominent, text, disabled}。純圖示的項目用 label 當作 aria-label 與提示。
   * 要放其他元件（分段控制、搜尋欄）用 centerExtra、trailingExtra。內容從工具列底下捲過，工具列不墊實心色塊。
   */
  import Button from "./Button.svelte";
  import Icon from "./Icon.svelte";
  import { usePlatform, TYPE } from "./platform.js";

  let { title = "", subtitle = "", leading = [], center = [], trailing = [], largeTitle = false, edgeEffect = true, platform: p = "", class: cls = "",
    centerExtra, trailingExtra } = $props();
  // svelte-ignore state_referenced_locally（平台在元件建立時決定，之後不變）
  const platform = usePlatform(p);
  const arr = (g) => (Array.isArray(g) ? g : [g]);
</script>

{#snippet group(g)}
  {@const plain = arr(g).filter((it) => !it.prominent)}
  {#if plain.length}
    <div class="lg-tool-group lg-glass lg-glass-regular lg-shape-capsule" role="group">
      {#each plain as it, i (i)}
        <button type="button" title={it.label} aria-label={it.text ? undefined : it.label} disabled={it.disabled} onclick={it.onClick}
          class="lg-tool-btn {it.text ? `lg-tool-text ${TYPE[platform].body}` : ''}">
          {#if it.text}{it.label}{:else}<Icon name={it.icon} size={platform === "ios" ? 19 : 15} weight="medium" />{/if}
        </button>
      {/each}
    </div>
  {/if}
  {#each arr(g).filter((it) => it.prominent) as it, i (i)}
    <Button {platform} variant="glassProminent" size={platform === "ios" ? "large" : "regular"} icon={it.text ? "" : it.icon} iconOnly={!it.text}
      aria-label={it.text ? undefined : it.label} title={it.label} disabled={it.disabled} onclick={it.onClick} class="lg-tool-prominent">{#if it.text}{it.label}{/if}</Button>
  {/each}
{/snippet}

<header class="lg-toolbar lg-toolbar-{platform} {cls}" class:lg-toolbar-edge={edgeEffect}>
  <div class="lg-toolbar-row">
    <div class="lg-toolbar-zone lg-zone-leading">
      {#each leading as g, i (i)}{@render group(g)}{/each}
      {#if platform === "mac" && title}
        <div class="lg-toolbar-titles">
          <div class="mac-headline lg-toolbar-title">{title}</div>
          {#if subtitle}<div class="mac-callout lg-toolbar-sub">{subtitle}</div>{/if}
        </div>
      {/if}
    </div>
    {#if platform === "ios" && !largeTitle && title}<div class="lg-toolbar-center-title ios-headline">{title}</div>{/if}
    {#if center.length || centerExtra}
      <div class="lg-toolbar-zone lg-zone-center">{#each center as g, i (i)}{@render group(g)}{/each}{@render centerExtra?.()}</div>
    {/if}
    <div class="lg-toolbar-zone lg-zone-trailing">{@render trailingExtra?.()}{#each trailing as g, i (i)}{@render group(g)}{/each}</div>
  </div>
  {#if platform === "ios" && largeTitle && title}<h1 class="lg-large-title ios-large-title-em">{title}</h1>{/if}
</header>
