<script>
  let { title = "", onclose, children, actions, wide = false } = $props();
</script>

<svelte:window onkeydown={(e) => e.key === "Escape" && onclose?.()} />

<div class="backdrop" role="presentation" onclick={(e) => e.target === e.currentTarget && onclose?.()}>
  <div class="modal" class:wide role="dialog" aria-modal="true" aria-label={title}>
    {#if title}<h2>{title}</h2>{/if}
    <div class="body">{@render children?.()}</div>
    {#if actions}<div class="actions">{@render actions()}</div>{/if}
  </div>
</div>

<style>
  .backdrop {
    position: fixed; inset: 0; background: var(--overlay); z-index: 200;
    display: flex; align-items: center; justify-content: center; padding: 16px;
    animation: fade .15s ease-out;
  }
  .modal {
    background: var(--panel); color: var(--text); border-radius: 20px; box-shadow: var(--shadow);
    width: min(440px, 100%); max-height: min(720px, 90vh); display: flex; flex-direction: column;
    padding: 22px; animation: pop .18s ease-out;
  }
  .modal.wide { width: min(620px, 100%); }
  h2 { margin: 0 0 12px; font-size: 18px; font-weight: 600; }
  .body { overflow-y: auto; min-height: 0; }
  .actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 18px; flex-wrap: wrap; }
  @keyframes fade { from { opacity: 0; } }
  @keyframes pop { from { transform: scale(.96); opacity: 0; } }
</style>
