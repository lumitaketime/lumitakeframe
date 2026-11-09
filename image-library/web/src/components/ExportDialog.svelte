<script>
  /**
   * 匯出交件：先自動看選了什麼（RAW、JPEG、影片），只顯示用得到的設定。
   * RAW 直接交原檔（連同 .xmp）；JPEG 選一個用途就好，細節收在「更多選項」。
   * 設定會記在這台裝置，下次直接沿用。
   */
  import { slide } from "svelte/transition";
  import Modal from "./Modal.svelte";
  import Icon from "./Icon.svelte";
  import { api } from "../lib/api.js";
  import { app, refresh, toast } from "../lib/state.svelte.js";
  import { count } from "../lib/format.js";
  import { mdiFolderOutline, mdiChevronDown, mdiCameraOutline, mdiImageOutline, mdiVideoOutline } from "../lib/icons.js";

  let { ids = [], onclose } = $props();

  // 用途：決定長邊與品質
  const PURPOSES = [
    { key: "full", label: "原尺寸交件", hint: "完整解析度、最高品質，給客戶留存或輸出", size: 0, quality: 95 },
    { key: "web", label: "社群與預覽", hint: "長邊 2048 px，適合 Facebook、Line、客戶線上挑片", size: 2048, quality: 90 },
    { key: "ig", label: "Instagram", hint: "長邊 1080 px", size: 1080, quality: 90 },
    { key: "custom", label: "自訂", hint: "", size: null, quality: null },
  ];
  const NAMES = [
    ["{name}", "原檔名"], ["{date}_{seq}", "日期_序號"], ["{folder}_{seq}", "資料夾_序號"], ["custom", "自訂規則"],
  ];
  const DEFAULTS = {
    purpose: "web", custom: 3000, quality: 90, rename: "{name}", customRename: "{date}_{seq}",
    wm: false, wmText: "© ", wmPos: "br", wmSize: 3, wmOpacity: 70, stripGps: true, keepExif: true, rawToJpeg: false,
  };
  let o = $state(read());
  let info = $state(null);
  let dest = $state("");
  let defaultDest = $state("");
  let sending = $state(false);
  let more = $state(false);

  function read() {
    try {
      const saved = JSON.parse(localStorage.getItem("exportOpts2") || "{}");
      return { ...DEFAULTS, ...saved };
    } catch {
      return { ...DEFAULTS };
    }
  }

  $effect(() => {
    api("/api/export/defaults").then((d) => (defaultDest = d.dest)).catch(() => {});
    api("/api/export/inspect", { body: { ids } }).then((d) => (info = d)).catch(() => (info = { total: ids.length, raw: 0, photo: ids.length, video: 0 }));
  });

  const raw = $derived(info?.raw || 0);
  const photo = $derived(info?.photo || 0);
  const video = $derived(info?.video || 0);
  // 會輸出成 JPEG 的張數（一般照片＋選擇轉檔的 RAW）
  const jpegCount = $derived(photo + (o.rawToJpeg ? raw : 0));
  const rawCopies = $derived(o.rawToJpeg ? 0 : raw);
  const exportable = $derived(photo + raw);
  const purpose = $derived(PURPOSES.find((p) => p.key === o.purpose) || PURPOSES[1]);
  const longSide = $derived(o.purpose === "custom" ? Number(o.custom) || 0 : purpose.size);
  const quality = $derived(o.purpose === "custom" ? Number(o.quality) : purpose.quality);
  const pattern = $derived(o.rename === "custom" ? o.customRename : o.rename);
  const sample = $derived(
    (pattern || "{name}")
      .replaceAll("{name}", "DSC01234").replaceAll("{date}", "20240625").replaceAll("{time}", "180600")
      .replaceAll("{seq}", String(1).padStart(Math.max(3, String(exportable).length), "0"))
      .replaceAll("{camera}", "ILCE-7M4").replaceAll("{folder}", "婚禮"),
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
      localStorage.setItem("exportOpts2", JSON.stringify(o));
    } catch {
      /* 不影響匯出 */
    }
    try {
      await api("/api/jobs", {
        body: {
          kind: "export", ids,
          options: {
            long_side: longSide, quality, rename: pattern || "{name}",
            strip_gps: o.stripGps, keep_exif: o.keepExif, raw_mode: o.rawToJpeg ? "jpeg" : "original",
            watermark: { enabled: o.wm && jpegCount > 0, text: o.wmText, position: o.wmPos, size: Number(o.wmSize), opacity: Number(o.wmOpacity) },
            dest: dest || undefined,
          },
        },
      });
      toast(`開始匯出 ${count(exportable)} 張，完成後會通知你`);
      refresh();
      onclose?.(true);
    } catch (e) {
      toast(e.message, "error");
    } finally {
      sending = false;
    }
  }
</script>

<Modal title="匯出 {count(ids.length)} 個項目" wide onclose={() => onclose?.(false)}>
  {#if !info}
    <div class="loading"><span class="spinner"></span>正在檢查選取的檔案…</div>
  {:else}
    <div class="form">
      <!-- 自動判斷的結果 -->
      <ul class="plan">
        {#if raw}
          <li>
            <span class="ic raw"><Icon path={mdiCameraOutline} size={20} /></span>
            <div class="grow">
              <b>{count(raw)} 張 RAW</b>
              <span>{o.rawToJpeg ? "轉成 JPEG，依下方設定輸出" : "交付原始檔，不轉檔、不縮圖（同名的 .xmp 附屬檔會一起附上）"}</span>
            </div>
            <button class="btn text small" onclick={() => (o.rawToJpeg = !o.rawToJpeg)}>{o.rawToJpeg ? "改回交原檔" : "改成轉 JPEG"}</button>
          </li>
        {/if}
        {#if photo}
          <li>
            <span class="ic jpg"><Icon path={mdiImageOutline} size={20} /></span>
            <div class="grow">
              <b>{count(photo)} 張 JPEG 與其他照片</b>
              <span>依下方用途輸出成 JPEG</span>
            </div>
          </li>
        {/if}
        {#if video}
          <li class="off">
            <span class="ic"><Icon path={mdiVideoOutline} size={20} /></span>
            <div class="grow"><b>{count(video)} 部影片</b><span>影片不會匯出</span></div>
          </li>
        {/if}
      </ul>

      {#if jpegCount}
        <div class="field" transition:slide={{ duration: 200 }}>
          <span class="label">用途</span>
          <div class="purposes">
            {#each PURPOSES as p (p.key)}
              <button class="purpose m3-state" class:on={o.purpose === p.key} onclick={() => (o.purpose = p.key)} aria-pressed={o.purpose === p.key}>
                <b>{p.label}</b>
                {#if p.hint}<span>{p.hint}</span>{:else}<span>自己指定長邊與品質</span>{/if}
              </button>
            {/each}
          </div>
          {#if o.purpose === "custom"}
            <div class="row" transition:slide={{ duration: 180 }}>
              <label class="mini">長邊（px，0＝原尺寸）
                <input class="input short" type="number" min="0" max="12000" step="10" bind:value={o.custom} />
              </label>
              <label class="mini">品質 {o.quality}
                <input type="range" min="60" max="100" step="1" bind:value={o.quality} />
              </label>
            </div>
          {/if}
        </div>
      {/if}

      <div class="field">
        <span class="label">檔名</span>
        <div class="row">
          <select class="input name-pick" bind:value={o.rename} aria-label="檔名規則">
            {#each NAMES as [v, label] (v)}<option value={v}>{label}</option>{/each}
          </select>
          {#if o.rename === "custom"}
            <input class="input grow-in" bind:value={o.customRename} placeholder="例如：客戶名_{'{date}'}_{'{seq}'}" aria-label="自訂檔名規則" />
          {/if}
          <span class="hint">例如 <b>{sample}</b></span>
        </div>
        {#if o.rename === "custom"}
          <span class="hint">可用：{"{name}"} 原檔名、{"{date}"} 拍攝日期、{"{time}"} 時間、{"{seq}"} 序號、{"{camera}"} 相機、{"{folder}"} 資料夾</span>
        {/if}
      </div>

      <div class="field">
        <span class="label">儲存到</span>
        <div class="row">
          <span class="dest"><Icon path={mdiFolderOutline} size={18} /><span>{dest || `${defaultDest || "圖片 / Lumitake 匯出"} / 今天的日期時間`}</span></span>
          {#if app.server?.local && app.server?.platform === "darwin"}<button class="btn ghost small" onclick={pick}>更改…</button>{/if}
          {#if dest}<button class="btn text small" onclick={() => (dest = "")}>用預設位置</button>{/if}
        </div>
      </div>

      <button class="more m3-state" onclick={() => (more = !more)} aria-expanded={more}>
        <span>更多選項</span>
        <span class="summary">{[o.stripGps ? "移除 GPS" : "保留 GPS", o.keepExif ? "保留拍攝資訊" : "不含拍攝資訊", o.wm && jpegCount ? "浮水印" : ""].filter(Boolean).join(" · ")}</span>
        <span class="chev" class:up={more}><Icon path={mdiChevronDown} size={20} /></span>
      </button>
      {#if more}
        <div class="more-body" transition:slide={{ duration: 220 }}>
          <label class="toggle"><input type="checkbox" bind:checked={o.stripGps} />移除 GPS 位置（建議交件與上傳社群時開啟）</label>
          <label class="toggle"><input type="checkbox" bind:checked={o.keepExif} />保留拍攝資訊（相機、鏡頭、光圈、快門、時間）</label>
          {#if jpegCount}
            <label class="toggle"><input type="checkbox" bind:checked={o.wm} />JPEG 加上文字浮水印{raw && !o.rawToJpeg ? "（RAW 原檔不會加）" : ""}</label>
            {#if o.wm}
              <div class="wm" transition:slide={{ duration: 180 }}>
                <input class="input" bind:value={o.wmText} placeholder="© 你的名字" aria-label="浮水印文字" />
                <div class="row">
                  <label class="mini">位置
                    <select class="input" bind:value={o.wmPos}>
                      <option value="br">右下</option><option value="bl">左下</option><option value="tr">右上</option>
                      <option value="tl">左上</option><option value="center">中間</option>
                    </select>
                  </label>
                  <label class="mini">大小 {o.wmSize}%<input type="range" min="1.5" max="8" step="0.5" bind:value={o.wmSize} /></label>
                  <label class="mini">不透明度 {o.wmOpacity}%<input type="range" min="20" max="100" step="5" bind:value={o.wmOpacity} /></label>
                </div>
              </div>
            {/if}
          {/if}
        </div>
      {/if}
    </div>
  {/if}

  {#snippet actions()}
    <span class="foot muted small">{info ? [rawCopies ? `${count(rawCopies)} 個 RAW 原檔` : "", jpegCount ? `${count(jpegCount)} 張 JPEG` : ""].filter(Boolean).join("＋") : ""}</span>
    <button class="btn ghost" onclick={() => onclose?.(false)}>取消</button>
    <button class="btn" onclick={start} disabled={sending || !info || !exportable || (o.wm && jpegCount && !o.wmText.trim())}>
      {#if sending}<span class="spinner"></span>{/if}匯出
    </button>
  {/snippet}
</Modal>

<style>
  .loading { display: flex; align-items: center; gap: 10px; color: var(--on-surface-variant); padding: 24px 0; }
  .form { display: flex; flex-direction: column; gap: 20px; color: var(--on-surface); }
  .plan { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; background: var(--surface-container-high); border-radius: var(--corner-large); overflow: hidden; }
  .plan li { display: flex; align-items: center; gap: 12px; padding: 12px 16px; }
  .plan li + li { border-top: 1px solid var(--outline-variant); }
  .plan li.off { color: var(--on-surface-variant); }
  .plan .grow { flex: 1; min-width: 0; display: flex; flex-direction: column; }
  .plan b { font-weight: 500; font-size: 16px; }
  .plan .grow span { font-size: 14px; color: var(--on-surface-variant); }
  .ic { width: 40px; height: 40px; border-radius: 50%; display: flex; align-items: center; justify-content: center; background: var(--surface-container-highest); flex-shrink: 0; }
  .ic.raw { background: var(--tertiary-container); color: var(--on-tertiary-container); }
  .ic.jpg { background: var(--secondary-container); color: var(--on-secondary-container); }
  .field { display: flex; flex-direction: column; gap: 8px; }
  .label { font-size: 14px; font-weight: 500; }
  .hint { font-size: 12px; line-height: 16px; color: var(--on-surface-variant); }
  .hint b { color: var(--on-surface); font-weight: 500; }
  .purposes { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 8px; }
  .purpose {
    display: flex; flex-direction: column; gap: 2px; text-align: left; padding: 12px 14px; cursor: pointer; color: var(--on-surface);
    border: 1px solid var(--outline-variant); background: none; border-radius: var(--corner-medium);
    transition: border-color var(--spring-effects-fast-duration) var(--spring-effects-fast), background-color var(--spring-effects-fast-duration) var(--spring-effects-fast);
  }
  .purpose b { font-size: 14px; font-weight: 500; }
  .purpose span { font-size: 12px; line-height: 16px; color: var(--on-surface-variant); }
  .purpose.on { border: 2px solid var(--primary); padding: 11px 13px; background: color-mix(in srgb, var(--primary) 8%, transparent); }
  .row { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }
  .name-pick { width: auto; min-width: 160px; }
  .grow-in { flex: 1; min-width: 200px; }
  .short { max-width: 160px; }
  .mini { display: flex; flex-direction: column; gap: 4px; font-size: 12px; color: var(--on-surface-variant); flex: 1; min-width: 140px; }
  .dest { display: inline-flex; align-items: center; gap: 6px; background: var(--surface-container-highest); border-radius: var(--corner-small); padding: 6px 10px; font-size: 14px; min-width: 0; flex: 1; }
  .dest span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .more {
    display: flex; align-items: center; gap: 12px; border: 0; background: none; color: var(--on-surface); cursor: pointer;
    padding: 10px 4px; border-top: 1px solid var(--outline-variant); text-align: left; border-radius: 0;
  }
  .more > span:first-child { font-size: 14px; font-weight: 500; }
  .summary { flex: 1; font-size: 12px; color: var(--on-surface-variant); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .chev { display: flex; transition: transform var(--spring-standard-fast-spatial-duration) var(--spring-standard-fast-spatial); }
  .chev.up { transform: rotate(180deg); }
  .more-body { display: flex; flex-direction: column; gap: 14px; margin-top: -8px; }
  .wm { display: flex; flex-direction: column; gap: 10px; padding-left: 4px; }
  .toggle { display: flex; flex-direction: row-reverse; justify-content: space-between; align-items: center; gap: 16px; font-size: 14px; cursor: pointer; }
  .foot { margin-right: auto; }
  .spinner { width: 14px; height: 14px; }
</style>
