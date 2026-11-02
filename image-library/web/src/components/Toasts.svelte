<script>
  import { app } from "../lib/state.svelte.js";
</script>

<div class="toasts" aria-live="polite">
  {#each app.toasts as t (t.id)}
    <div class="toast" class:error={t.kind === "error"}>{t.message}</div>
  {/each}
</div>

<style>
  .toasts {
    position: fixed; left: 50%; bottom: calc(24px + env(safe-area-inset-bottom)); transform: translateX(-50%);
    z-index: 300; display: flex; flex-direction: column; gap: 8px; align-items: center; pointer-events: none;
    width: min(560px, calc(100% - 24px));
  }
  .toast {
    background: #26282f; color: #fff; padding: 10px 18px; border-radius: 12px; box-shadow: var(--shadow);
    font-size: 14px; animation: up .2s ease-out; max-width: 100%; word-break: break-word;
  }
  .toast.error { background: #8f1d29; }
  @keyframes up { from { transform: translateY(10px); opacity: 0; } }
  @media (max-width: 760px) { .toasts { bottom: calc(76px + env(safe-area-inset-bottom)); } }
</style>
