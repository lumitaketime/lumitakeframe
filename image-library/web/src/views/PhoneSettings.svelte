<script>
  /**
   * 設定 → 連線與系統 → 手機與平板：同一個 Wi-Fi 下用瀏覽器打開 Re'memor（要設密碼）。
   * 只在這台 Mac 上可以改；連線設定改了要重新啟動服務才生效。
   */
  import { Button, List, ListRow, TextField, Toggle } from "../ui/index.js";
  import { api } from "../lib/api.js";
  import { t } from "../i18n/index.svelte.js";
  import { toast } from "../lib/state.svelte.js";

  let lan = $state(null);
  let password = $state("");
  let restarting = $state(false);
  const load = () => api("/api/lan", { quiet: true }).then((d) => (lan = d)).catch(() => {});
  $effect(() => {
    load();
  });
  async function savePassword() {
    try {
      await api("/api/lan", { body: { password } });
      password = "";
      await load();
      toast(t("phone.passwordSet"));
    } catch (e) {
      toast(e.message, "error");
    }
  }
  async function setLan(enabled) {
    try {
      await api("/api/lan", { body: { enabled } });
      await load();
    } catch (e) {
      toast(e.message, "error");
    }
  }
  async function restart() {
    restarting = true;
    await api("/api/restart", { body: {} }).catch(() => {});
    for (let i = 0; i < 40; i++) {
      await new Promise((r) => setTimeout(r, 750));
      try {
        await fetch("/api/auth/status");
        location.reload();
        return;
      } catch {
        /* 還在重新啟動 */
      }
    }
    restarting = false;
    toast(t("phone.restartTimeout"), "error");
  }
</script>

{#if lan}
  <List header={t("phone.title")} footer={lan.local ? t("phone.footer") : t("phone.remoteOnly")}>
    {#if lan.local}
      <div class="pad">
        <TextField label={lan.has_password ? t("phone.changePassword") : t("phone.setPassword")} secure bind:value={password}
          placeholder={t("phone.passwordHint")} />
        <Button size="small" variant="bordered" disabled={password.length < 6} onclick={savePassword}>{lan.has_password ? t("phone.change") : t("phone.set")}</Button>
      </div>
      <ListRow title={t("phone.allow")} subtitle={lan.has_password ? "" : t("phone.needPassword")}>
        {#snippet trailing()}<Toggle checked={!!lan.enabled} disabled={!lan.has_password} onchange={setLan} aria-label={t("phone.allow")} />{/snippet}
      </ListRow>
      {#if lan.needs_restart}
        <ListRow title={t("phone.needsRestart")} subtitle={t("phone.needsRestartHint")} icon="exclamation-triangle" iconTint="orange">
          {#snippet trailing()}<Button size="small" variant="borderedProminent" loading={restarting} onclick={restart}>{t("phone.restart")}</Button>{/snippet}
        </ListRow>
      {/if}
    {/if}
    {#if lan.active && lan.urls.length}
      <div class="qr-row">
        <!-- QR code 是引擎產生的 SVG（只有方塊，沒有外部內容） -->
        {#if lan.qr}<div class="qr">{@html lan.qr}</div>{/if}
        <div class="mac-callout">
          <p>{t("phone.scan")}</p>
          {#each lan.urls as u (u)}<p><code>{u}</code></p>{/each}
          <p class="sub mac-caption-1">{t("phone.homeScreen")}</p>
        </div>
      </div>
    {/if}
  </List>
{/if}

<style>
  .pad { display: flex; align-items: flex-end; gap: var(--space-2); padding: var(--space-3); flex-wrap: wrap; }
  .pad :global(.lg-textfield), .pad :global(label) { flex: 1; min-width: 200px; }
  .qr-row { display: flex; gap: var(--space-4); align-items: center; padding: var(--space-3); flex-wrap: wrap; }
  .qr { width: 140px; flex: none; background: white; padding: var(--space-2); border-radius: var(--radius-sm); }
  .qr :global(svg) { display: block; width: 100%; height: auto; }
  p { margin: 0 0 var(--space-1); }
  .sub { color: var(--label-secondary); }
  code { user-select: all; }
</style>
