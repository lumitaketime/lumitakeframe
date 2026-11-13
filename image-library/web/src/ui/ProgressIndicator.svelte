<script>
  /** 進度：有 value（0–1）是進度條或進度環；沒有 value 是轉圈或來回跑的進度條。 */
  import { t } from "../i18n/index.svelte.js";
  import { usePlatform } from "./platform.js";

  let { kind = "bar", value = undefined, label = "", size = "regular", class: cls = "" } = $props();
  const platform = usePlatform();
  const determinate = $derived(typeof value === "number");
  const pct = $derived(determinate ? Math.max(0, Math.min(1, value)) : 0);
  const aria = $derived({
    role: "progressbar", "aria-label": label || t("common.progress"),
    ...(determinate ? { "aria-valuemin": 0, "aria-valuemax": 100, "aria-valuenow": Math.round(pct * 100) } : {}),
  });
  const R = 9;
  const LEN = 2 * Math.PI * R;
  const spinPx = $derived(size === "small" ? 16 : size === "large" ? 32 : 20);
  const ringPx = $derived(size === "small" ? 16 : size === "large" ? 32 : 22);
</script>

{#if kind === "spinner" || (kind === "circular" && !determinate)}
  <span class="lg-spinner {cls}" style:width="{spinPx}px" style:height="{spinPx}px" {...aria}>
    {#each Array(8) as _, i (i)}<i style:transform="rotate({i * 45}deg)" style:animation-delay="{(i - 8) * 0.125}s"></i>{/each}
  </span>
{:else if kind === "circular"}
  <svg class="lg-ring {cls}" width={ringPx} height={ringPx} viewBox="0 0 24 24" {...aria}>
    <circle cx="12" cy="12" r={R} class="lg-ring-track" />
    <circle cx="12" cy="12" r={R} class="lg-ring-fill" stroke-dasharray={LEN} stroke-dashoffset={LEN * (1 - pct)} transform="rotate(-90 12 12)" />
  </svg>
{:else}
  <div class="lg-bar lg-bar-{platform} {cls}" class:lg-bar-indeterminate={!determinate} {...aria}>
    <span style:width={determinate ? `${pct * 100}%` : null}></span>
  </div>
{/if}
