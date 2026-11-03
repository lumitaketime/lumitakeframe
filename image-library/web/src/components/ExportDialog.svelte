<script>
  /** 批次匯出交件：尺寸、品質、檔名、浮水印、GPS、輸出位置。設定會記住，下次直接沿用。 */
  import Modal from "./Modal.svelte";
  import Icon from "./Icon.svelte";
  import { api } from "../lib/api.js";
  import { app, refresh, toast } from "../lib/state.svelte.js";
  import { mdiFolderOutline } from "../lib/icons.js";

  let { ids = [], onclose } = $props();

  const DEFAULTS = {
    size: "2048", custom: 3000, quality: 90, rename: "{name}", customRename: "{date}_{seq}",
    wm: false, wmText: "© ", wmPos: "br", wmSize: 3, wmOpacity: 70, stripGps: true, keepExif: true,
  };
  let o = $state(read());
  let dest = $state("");
  let defaultDest = $state("");
  let sending = $state(false);

  function read() {
    try {
      return { ...DEFAULTS, ...JSON.parse(localStorage.getItem("exportOpts") || "{}") };
    } catch {
      return { ...DEFAULTS };
    }
  }

  $effect(() => {
    api("/api/export/defaults").then((d) => (defaultDest = d.dest)).catch(() => {});
  });

  const pattern = $derived(o.rename === "custom" ? o.customRename : o.rename);
  const longSide = $derived(o.size === "orig" ? 0 : o.size === "custom" ? Number(o.custom) || 0 : Number(o.size));
  const sample = $derived(
    (pattern || "{name}")
      .replaceAll("{name}", "DSC01234").replaceAll("{date}", "20240625").replaceAll("{time}", "180600")
      .replaceAll("{seq}", String(1).padStart(Math.max(3, String(ids.length).length), "0"))
      .replaceAll("{camera}", "ILCE-7M4").replaceAll("{folder}", "婚禮") + ".jpg",
  );

  async function pick() {
    try {
      const { path } = await api("/api/pick-folder", { body: {} });
      if (path) dest = path;
    } catch (e) {
      toast(e.message, "error");
    }
  }

  async function start() {
    sending = true;
    try {
      localStorage.setItem("exportOpts", JSON.stringify(o));
    } catch {
      /* 不影響匯出 */
    }
    try {
      await api("/api/jobs", {
        body: {
          kind: "export", ids,
          options: {
            long_side: longSide, quality: Number(o.quality), rename: pattern || "{name}",
            strip_gps: o.stripGps, keep_exif: o.keepExif,
            watermark: { enabled: o.wm, text: o.wmText, position: o.wmPos, size: Number(o.wmSize), opacity: Number(o.wmOpacity) },
            dest: dest || undefined,
          },
        },
      });
      toast(`開始匯出 ${ids.length} 張，完成後會通知你`);
      refresh();
      onclose?.(true);
    } catch (e) {
      toast(e.message, "error");
    } finally {
      sending = false;
    }
  }
</script>

<Modal title="匯出 {ids.length} 張照片" wide onclose={() => onclose?.(false)}>
  <div class="form">
    <div class="field">
      <span class="label">尺寸（長邊）</span>
      <div class="chips">
        {#each [["orig", "原尺寸"], ["3840", "3840"], ["2048", "2048"], ["1600", "1600"], ["1080", "1080"], ["custom", "自訂"]] as [v, label] (v)}
          <button class="chip" class:on={o.size === v} onclick={() => (o.size = v)}>{label}{v !== "orig" && v !== "custom" ? " px" : ""}</button>
        {/each}
      </div>
      {#if o.size === "custom"}
        <input class="input short" type="number" min="200" max="12000" step="10" bind:value={o.custom} aria-label="自訂長邊像素" />
      {/if}
      <span class="hint">2048 適合社群與客戶預覽；Instagram 建議 1080。原圖比指定尺寸小時維持原尺寸。</span>
    </div>

    <div class="field">
      <span class="label">品質</span>
      <div class="chips">
        {#each [[95, "最高"], [90, "高（建議）"], [82, "標準"], [72, "小檔"]] as [v, label] (v)}
          <button class="chip" class:on={Number(o.quality) === v} onclick={() => (o.quality = v)}>{label}</button>
        {/each}
      </div>
    </div>

    <div class="field">
      <span class="label">檔名</span>
      <div class="chips">
        {#each [["{name}", "原檔名"], ["{date}_{seq}", "日期_序號"], ["{folder}_{seq}", "資料夾_序號"], ["custom", "自訂"]] as [v, label] (v)}
          <button class="chip" class:on={o.rename === v} onclick={() => (o.rename = v)}>{label}</button>
        {/each}
      </div>
      {#if o.rename === "custom"}
        <input class="input" bind:value={o.customRename} placeholder="例如：客戶名_{date}_{seq}" aria-label="自訂檔名規則" />
        <span class="hint">可用：{"{name}"} 原檔名、{"{date}"} 拍攝日期、{"{time}"} 時間、{"{seq}"} 序號、{"{camera}"} 相機、{"{folder}"} 資料夾</span>
      {/if}
      <span class="hint">範例：<b>{sample}</b></span>
    </div>

    <div class="field">
      <label class="toggle"><input type="checkbox" bind:checked={o.wm} />加上文字浮水印</label>
      {#if o.wm}
        <div class="wm">
          <input class="input" bind:value={o.wmText} placeholder="© 你的名字" aria-label="浮水印文字" />
          <div class="row">
            <label class="mini">位置
              <select class="input" bind:value={o.wmPos}>
                <option value="br">右下</option><option value="bl">左下</option><option value="tr">右上</option>
                <option value="tl">左上</option><option value="center">中間</option>
              </select>
            </label>
            <label class="mini">大小 {o.wmSize}%
              <input type="range" min="1.5" max="8" step="0.5" bind:value={o.wmSize} />
            </label>
            <label class="mini">不透明度 {o.wmOpacity}%
              <input type="range" min="20" max="100" step="5" bind:value={o.wmOpacity} />
            </label>
          </div>
        </div>
      {/if}
    </div>

    <div class="field">
      <label class="toggle"><input type="checkbox" bind:checked={o.stripGps} />移除 GPS 位置（建議交件與上傳社群時開啟）</label>
      <label class="toggle"><input type="checkbox" bind:checked={o.keepExif} />保留拍攝資訊（相機、鏡頭、光圈、快門、時間）</label>
    </div>

    <div class="field">
      <span class="label">輸出位置</span>
      <div class="row">
        <span class="dest"><Icon path={mdiFolderOutline} size={18} />{dest || `${defaultDest || "圖片 / Lumitake 匯出"} / 今天的日期時間`}</span>
        {#if app.server?.local && app.server?.platform === "darwin"}<button class="btn ghost small" onclick={pick}>選擇資料夾…</button>{/if}
        {#if dest}<button class="btn text small" onclick={() => (dest = "")}>用預設位置</button>{/if}
      </div>
      <span class="hint">原始照片不會被修改。影片不會匯出。RAW 檔使用相機內嵌的預覽圖，部分機型尺寸較小。</span>
    </div>
  </div>

  {#snippet actions()}
    <button class="btn ghost" onclick={() => onclose?.(false)}>取消</button>
    <button class="btn" onclick={start} disabled={sending || !ids.length || (o.wm && !o.wmText.trim())}>
      {#if sending}<span class="spinner"></span>{/if}開始匯出
    </button>
  {/snippet}
</Modal>

<style>
  .form { display: flex; flex-direction: column; gap: 18px; color: var(--on-surface); }
  .field { display: flex; flex-direction: column; gap: 8px; }
  .label { font-size: 14px; font-weight: 500; color: var(--on-surface); }
  .hint { font-size: 12px; line-height: 16px; color: var(--on-surface-variant); }
  .hint b { color: var(--on-surface); font-weight: 500; }
  .short { max-width: 180px; }
  .row { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }
  .wm { display: flex; flex-direction: column; gap: 10px; }
  .mini { display: flex; flex-direction: column; gap: 4px; font-size: 12px; color: var(--on-surface-variant); flex: 1; min-width: 140px; }
  .toggle { display: flex; flex-direction: row-reverse; justify-content: space-between; align-items: center; gap: 16px; font-size: 14px; cursor: pointer; }
  .dest { display: inline-flex; align-items: center; gap: 6px; background: var(--surface-container-highest); border-radius: var(--corner-small); padding: 6px 10px; font-size: 13px; word-break: break-all; }
  .spinner { width: 14px; height: 14px; }
</style>
