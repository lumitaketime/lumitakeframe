<script>
  import { api } from "../lib/api.js";
  import { app } from "../lib/state.svelte.js";

  let password = $state("");
  let error = $state("");
  let busy = $state(false);

  async function submit(e) {
    e.preventDefault();
    busy = true;
    error = "";
    try {
      await api("/api/auth/login", { body: { password } });
      app.needLogin = false;
    } catch (err) {
      error = err.message;
    } finally {
      busy = false;
    }
  }
</script>

<div class="wrap">
  <form class="card" onsubmit={submit}>
    <img src="/icon.svg" alt="" width="64" height="64" />
    <h1>Lumitake Library</h1>
    <p class="muted small">請輸入在 Mac 上設定的連線密碼</p>
    <!-- svelte-ignore a11y_autofocus -->
    <input class="input" type="password" bind:value={password} placeholder="密碼" autocomplete="current-password" autofocus />
    {#if error}<p class="danger-text small">{error}</p>{/if}
    <button class="btn" disabled={busy || !password}>登入</button>
  </form>
</div>

<style>
  .wrap { min-height: 100vh; display: flex; align-items: center; justify-content: center; padding: 20px; background: var(--bg-2); }
  .card { background: var(--panel); border-radius: 24px; padding: 32px; width: min(360px, 100%); display: flex; flex-direction: column; gap: 12px; align-items: center; box-shadow: var(--shadow); }
  h1 { margin: 0; font-size: 22px; }
  .card .btn, .card .input { width: 100%; }
</style>
