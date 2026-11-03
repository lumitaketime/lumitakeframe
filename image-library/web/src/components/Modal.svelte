<script>
  /** Material 3 Dialog：surface-container-high、28px 圓角，由上方長出，關閉時先播離場動畫。 */
  import { popIn, popOut, scrim } from "../lib/motion.js";

  let { title = "", onclose, children, actions, wide = false } = $props();
</script>

<svelte:window onkeydown={(e) => e.key === "Escape" && onclose?.()} />

<div class="backdrop" role="presentation" onclick={(e) => e.target === e.currentTarget && onclose?.()} transition:scrim|global>
  <div class="modal" class:wide role="dialog" aria-modal="true" aria-label={title} in:popIn|global out:popOut|global>
    {#if title}<h2>{title}</h2>{/if}
    <div class="body">{@render children?.()}</div>
    {#if actions}<div class="actions">{@render actions()}</div>{/if}
  </div>
</div>

<style>
  .backdrop {
    position: fixed; inset: 0; background: var(--overlay); z-index: 200;
    display: flex; align-items: center; justify-content: center; padding: 16px;
  }
  .modal {
    background: var(--surface-container-high); color: var(--on-surface); border-radius: var(--corner-extra-large);
    box-shadow: var(--elevation-level3);
    width: min(440px, 100%); max-height: min(720px, 90vh); display: flex; flex-direction: column;
    padding: 24px; transform-origin: top center;
  }
  .modal.wide { width: min(620px, 100%); }
  h2 { margin: 0 0 16px; font-size: 24px; line-height: 32px; font-weight: 400; }
  .body { overflow-y: auto; min-height: 0; color: var(--on-surface-variant); }
  .actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 24px; flex-wrap: wrap; }
  /* Dialog 的動作按鈕用 Text button（主要動作保留 Filled） */
  .actions :global(.btn.ghost) { border: 0; padding: 0 12px; }
</style>
