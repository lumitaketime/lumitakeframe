<script>
  /** Material 3 Snackbar：inverse-surface 底色，由下往上彈入，先播離場動畫再移除。 */
  import Icon from "./Icon.svelte";
  import { app, dismissToast, holdToast, releaseToast } from "../lib/state.svelte.js";
  import { riseIn, popOut } from "../lib/motion.js";
  import { mdiAlertCircleOutline, mdiClose } from "../lib/icons.js";
  import { flip } from "svelte/animate";
</script>

<div class="toasts" aria-live="polite">
  {#each app.toasts as t (t.id)}
    <!-- svelte-ignore a11y_no_static_element_interactions -->
    <div class="toast" class:error={t.kind === "error"} role={t.kind === "error" ? "alert" : "status"}
      onpointerenter={() => holdToast(t.id)} onpointerleave={() => releaseToast(t.id)}
      in:riseIn out:popOut={{ y: 8, scale: 0.98 }} animate:flip={{ duration: 250 }}>
      {#if t.kind === "error"}<span class="lead"><Icon path={mdiAlertCircleOutline} size={20} /></span>{/if}
      <span class="msg">{t.message}</span>
      {#if t.action}
        <button class="act" onclick={() => { t.action.run(); dismissToast(t.id); }}>{t.action.label}</button>
      {/if}
      {#if t.kind === "error" || t.action}
        <button class="x" onclick={() => dismissToast(t.id)} aria-label="關閉"><Icon path={mdiClose} size={18} /></button>
      {/if}
    </div>
  {/each}
</div>

<style>
  .toasts {
    position: fixed; left: 50%; bottom: calc(24px + env(safe-area-inset-bottom)); transform: translateX(-50%);
    z-index: 300; display: flex; flex-direction: column; gap: 8px; align-items: center; pointer-events: none;
    width: min(600px, calc(100% - 32px));
  }
  .toast {
    pointer-events: auto; display: flex; align-items: center; gap: 12px; min-height: 48px; max-width: 100%;
    padding: 6px 8px 6px 16px; border-radius: var(--corner-extra-small);
    background: var(--inverse-surface); color: var(--inverse-on-surface); box-shadow: var(--elevation-level3);
    font-size: var(--text-body); line-height: 20px;
  }
  .msg { padding: 8px 0; word-break: break-word; flex: 1; }
  .lead { display: flex; color: var(--inverse-primary); }
  .toast.error .lead { color: var(--system-red); }
  .act {
    border: 0; background: none; color: var(--inverse-primary); font-weight: 500;
    padding: 10px 12px; border-radius: var(--corner-full); cursor: pointer; white-space: nowrap;
  }
  .act:hover { background: color-mix(in srgb, var(--inverse-primary) 8%, transparent); }
  .x { border: 0; background: none; color: var(--inverse-on-surface); width: 36px; height: 36px; border-radius: 50%; display: flex; align-items: center; justify-content: center; cursor: pointer; flex-shrink: 0; }
  .x:hover { background: color-mix(in srgb, var(--inverse-on-surface) 8%, transparent); }
  @media (max-width: 840px) { .toasts { bottom: calc(100px + env(safe-area-inset-bottom)); } }
</style>
