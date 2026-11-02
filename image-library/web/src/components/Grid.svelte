<script>
  import Thumb from "./Thumb.svelte";
  import { justify, squares } from "../lib/layout.js";
  import { selection, openViewer } from "../lib/state.svelte.js";

  /** list：開啟檢視器時可左右切換的完整清單（預設等於 assets） */
  let { assets = [], list = null, offset = 0, target = 0, layoutWidth = 0 } = $props();
  let width = $state(0);

  const narrow = $derived((layoutWidth || width) > 0 && (layoutWidth || width) < 640);
  const rowTarget = $derived(target || (width > 1600 ? 260 : width > 1000 ? 230 : 190));
  const rows = $derived(
    narrow
      ? squares(assets, layoutWidth || width, (layoutWidth || width) < 420 ? 3 : 4, 2)
      : justify(assets, width, rowTarget, 4)
  );
  const gap = $derived(narrow ? 2 : 4);
  const selecting = $derived(selection.size > 0);

  let anchor = null;

  function open(index) {
    const full = list || assets;
    openViewer(full, offset + index);
  }

  function select(index, e) {
    const id = assets[index].id;
    if (e?.shiftKey && anchor !== null) {
      const [a, b] = [Math.min(anchor, index), Math.max(anchor, index)];
      for (let i = a; i <= b; i++) selection.add(assets[i].id);
    } else if (selection.has(id)) {
      selection.delete(id);
    } else {
      selection.add(id);
    }
    anchor = index;
  }
</script>

<div class="grid" bind:clientWidth={width} style:gap="{gap}px">
  {#each rows as row, r (r)}
    <div class="row" style:height="{row.height}px" style:gap="{gap}px">
      {#each row.items as item (item.asset.id)}
        <Thumb
          asset={item.asset}
          width={item.width}
          height={row.height}
          selected={selection.has(item.asset.id)}
          {selecting}
          onopen={() => open(item.index)}
          onselect={(e) => select(item.index, e)}
        />
      {/each}
    </div>
  {/each}
</div>

<style>
  .grid { display: flex; flex-direction: column; width: 100%; }
  .row { display: flex; overflow: hidden; content-visibility: auto; }
</style>
