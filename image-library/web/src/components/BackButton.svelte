<script>
  /** 頁面左上角的返回鍵：回到剛才的頁面；直接打開連結時回到上一層。 */
  import Icon from "./Icon.svelte";
  import { goBack } from "../lib/router.svelte.js";
  import { mdiArrowLeft } from "../lib/icons.js";

  let { to = "/", label = "返回" } = $props();
</script>

<button class="icon-btn back-btn" onclick={() => goBack(to)} aria-label={label} title={label}><Icon path={mdiArrowLeft} /></button>

<style>
  .back-btn { color: var(--on-surface); margin-left: -8px; flex-shrink: 0; }
</style>
