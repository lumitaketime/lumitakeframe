<script>
  /** 右鍵選單：出現在滑鼠的位置，超出視窗時往內收；按外面或 Escape 關閉。 */
  import { Menu } from "../ui/index.js";
  import { dismiss } from "../ui/platform.js";
  import { popIn, popOut } from "../lib/motion.js";

  let { x = 0, y = 0, items = [], onclose } = $props();
  let el = $state();
  let pos = $state({ left: 0, top: 0 });
  $effect(() => {
    if (!el) return;
    const r = el.getBoundingClientRect();
    pos = { left: Math.max(8, Math.min(x, innerWidth - r.width - 8)), top: Math.max(8, Math.min(y, innerHeight - r.height - 8)) };
  });
</script>

<div class="ctx" bind:this={el} style:left="{pos.left}px" style:top="{pos.top}px" use:dismiss={onclose} in:popIn={{ y: 0, scale: 0.96 }} out:popOut={{ y: 0, scale: 1 }}>
  <Menu {items} autofocus onselect={onclose} {onclose} />
</div>

<style>
  .ctx { position: fixed; z-index: 300; transform-origin: top left; }
</style>
