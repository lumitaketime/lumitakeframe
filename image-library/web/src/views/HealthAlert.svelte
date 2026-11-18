<script>
  /**
   * 硬碟可能有狀況：說明看到了什麼、Re'memor 現在先不碰它，請本人選擇怎麼處理。
   * 不會自己繼續；選「照常進行」而且狀況嚴重時，再確認一次。
   */
  import { Alert, Button, Icon } from "../ui/index.js";
  import { decideHealth, recheckHealth } from "../data/health.js";
  import { t } from "../i18n/index.svelte.js";
  import { toast, refresh } from "../lib/state.svelte.js";

  let { health, onchange } = $props();

  let busy = $state("");
  let confirmGo = $state(false);
  async function decide(decision) {
    confirmGo = false;
    busy = decision;
    try {
      const out = await decideHealth(health.key, decision);
      toast(t(`health.decided.${decision}`, { name: health.name }));
      onchange?.(out);
      refresh();
    } catch (e) {
      toast(e.message, "error");
    } finally {
      busy = "";
    }
  }
  async function recheck() {
    busy = "check";
    try {
      onchange?.(await recheckHealth(health.root_id));
      refresh();
    } catch (e) {
      toast(e.message, "error");
    } finally {
      busy = "";
    }
  }
</script>

<section class="alert" class:fail={health.status === "fail"} aria-live="polite">
  <header>
    <Icon name="exclamation-triangle" size={18} />
    <div>
      <b class="mac-headline">{t(`health.title.${health.status}`, { name: health.name })}</b>
      <p class="mac-callout">{t("health.paused")}</p>
    </div>
  </header>
  {#if health.findings?.length}
    <ul class="mac-callout">
      {#each health.findings as f, k (k)}<li class="lv-{f.level}">{f.text}</li>{/each}
    </ul>
  {/if}
  <p class="mac-callout advice">{t("health.advice")}</p>
  <div class="choices">
    <Button variant="borderedProminent" loading={busy === "pause"} disabled={!!busy} onclick={() => decide("pause")}>{t("health.pause")}</Button>
    <Button variant="bordered" loading={busy === "light"} disabled={!!busy} onclick={() => decide("light")}>{t("health.light")}</Button>
    <Button variant="bordered" loading={busy === "continue"} disabled={!!busy}
      onclick={() => (health.status === "fail" ? (confirmGo = true) : decide("continue"))}>{t("health.continue")}</Button>
    <span class="grow"></span>
    {#if health.online !== false && health.root_id}
      <Button variant="borderless" loading={busy === "check"} disabled={!!busy} onclick={recheck}>{t("health.recheck")}</Button>
    {/if}
  </div>
  <p class="mac-caption-1 hint">{t("health.choiceHint")}</p>
</section>

{#if confirmGo}
  <div class="backdrop">
    <Alert title={t("health.goTitle", { name: health.name })} message={t("health.goMessage")} actions={[
      { label: t("health.continue"), role: "destructive", onPress: () => decide("continue") },
      { label: t("common.cancel"), role: "cancel", onPress: () => (confirmGo = false) },
    ]} />
  </div>
{/if}

<style>
  .alert { display: flex; flex-direction: column; gap: var(--space-2); padding: var(--space-3) var(--space-4); border-radius: var(--radius-lg);
    background: color-mix(in srgb, var(--system-orange) 12%, transparent); box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--system-orange) 40%, transparent);
    color: var(--label-primary); }
  .alert.fail { background: color-mix(in srgb, var(--system-red) 10%, transparent); box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--system-red) 40%, transparent); }
  header { display: flex; gap: var(--space-2); align-items: flex-start; }
  header > :global(svg) { flex: none; margin-top: 2px; color: var(--system-orange); }
  .fail header > :global(svg) { color: var(--system-red); }
  p, ul { margin: 0; }
  header p, .advice, .hint { color: var(--label-secondary); }
  ul { padding-left: var(--space-5); display: flex; flex-direction: column; gap: 2px; }
  .lv-fail { color: var(--system-red); }
  .lv-info { color: var(--label-secondary); }
  .choices { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-2); }
  .grow { flex: 1; }
  .backdrop { position: fixed; inset: 0; z-index: 320; display: flex; align-items: center; justify-content: center; background: var(--media-scrim-light); }
</style>
