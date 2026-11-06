<script>
  import { slider } from "../lib/slider.js";
  /**
   * EXIF 編輯器：一張或多張照片的檔名、拍攝時間、相機、鏡頭、地點、標題說明、作者版權。
   * 選取的照片值不同時顯示「多個值」，只寫入有改的欄位；套用前先預覽「從什麼改成什麼」，之後可以復原。
   * RAW 寫進 .xmp 附屬檔，JPEG／HEIC 直接寫進檔案，檔名直接改硬碟上的檔案。
   */
  import { onDestroy, tick } from "svelte";
  import { slide } from "svelte/transition";
  import L from "leaflet";
  import "leaflet/dist/leaflet.css";
  import Modal from "./Modal.svelte";
  import Icon from "./Icon.svelte";
  import { api } from "../lib/api.js";
  import { refresh, toast } from "../lib/state.svelte.js";
  import { count } from "../lib/format.js";
  import { mdiMagnify, mdiMapMarkerOutline, mdiClose, mdiArrowRight } from "../lib/icons.js";

  let { ids = [], onclose } = $props();

  let info = $state(null);
  let step = $state("edit"); // edit → preview
  let previewData = $state(null);
  let busy = $state(false);

  // 欄位：value 是輸入框裡的值，orig 是原本的值（多個值時為 null）
  const TEXT = [
    ["make", "相機品牌", "例如 FUJIFILM、SONY"],
    ["model", "相機型號", "例如 X-T5"],
    ["lens", "鏡頭", "例如 XF33mmF1.4 R LM WR"],
    ["title", "標題", ""],
    ["caption", "說明", ""],
    ["artist", "作者", "攝影師名字"],
    ["copyright", "版權", "例如 © 2026 你的名字"],
  ];
  let text = $state({});
  let renameMode = $state("");
  let customRename = $state("{date}_{seq}");
  let timeMode = $state("keep");
  let timeValue = $state("");
  let shift = $state({ sign: 1, d: 0, h: 0, m: 0, s: 0 });
  let tzMode = $state("keep");
  let tzValue = $state("+08:00");
  let gpsMode = $state("keep");
  let lat = $state("");
  let lon = $state("");
  let placeQ = $state("");
  let places = $state([]);
  let searching = $state(false);
  let mapEl = $state();
  let map;
  let marker;

  $effect(() => {
    api("/api/exif/inspect", { body: { ids } })
      .then((d) => {
        info = d;
        const t = {};
        for (const [k] of TEXT) {
          const f = d.fields[k];
          t[k] = { value: f.mixed ? "" : f.value || "", orig: f.mixed ? null : f.value || "", mixed: f.mixed };
        }
        text = t;
        const tf = d.fields.taken_at;
        if (!tf.mixed && tf.value) timeValue = tf.value.slice(0, 19);
        const g = d.fields.gps;
        if (!g.mixed && g.value) {
          lat = String(g.value[0]);
          lon = String(g.value[1]);
        }
      })
      .catch((e) => toast(e.message, "error"));
  });

  const RENAMES = [
    ["", "不改檔名"], ["{date}_{seq}", "日期_序號"], ["{date}_{time}", "日期_時間"], ["{folder}_{seq}", "資料夾_序號"],
    ["{camera}_{date}_{seq}", "相機_日期_序號"], ["custom", "自訂規則"],
  ];
  const renamePattern = $derived(renameMode === "custom" ? customRename.trim() : renameMode);
  const shiftSeconds = $derived(shift.sign * ((+shift.d || 0) * 86400 + (+shift.h || 0) * 3600 + (+shift.m || 0) * 60 + (+shift.s || 0)));

  const changes = $derived.by(() => {
    const c = {};
    if (renamePattern) c.rename = renamePattern;
    if (timeMode === "set" && timeValue) c.time = { mode: "set", value: timeValue.length === 16 ? `${timeValue}:00` : timeValue };
    if (timeMode === "shift" && shiftSeconds) c.time = { mode: "shift", seconds: shiftSeconds };
    if (tzMode === "set") c.tz = tzValue;
    for (const [k] of TEXT) {
      const f = text[k];
      if (!f) continue;
      if (f.mixed ? f.value.trim() !== "" || f.clear : f.value.trim() !== (f.orig || "").trim()) c[k] = f.clear ? "" : f.value.trim();
    }
    if (gpsMode === "remove") c.gps = { remove: true };
    if (gpsMode === "set" && lat !== "" && lon !== "") c.gps = { lat: Number(lat), lon: Number(lon) };
    return c;
  });
  const changeCount = $derived(Object.keys(changes).length);

  function setText(k, v) {
    text[k] = { ...text[k], value: v, clear: false };
  }
  function clearText(k) {
    text[k] = { ...text[k], value: "", clear: true };
  }
  function resetText(k) {
    text[k] = { ...text[k], value: text[k].orig ?? "", clear: false };
  }
  const isChanged = (k) => k in changes;

  // ---- 地圖 ----
  async function showMap() {
    await tick();
    if (!mapEl || map) return;
    const start = lat !== "" && lon !== "" ? [Number(lat), Number(lon)] : [23.7, 121];
    map = L.map(mapEl, { zoomControl: true, attributionControl: true }).setView(start, lat !== "" ? 14 : 7);
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19, attribution: "© OpenStreetMap" }).addTo(map);
    if (lat !== "") placeMarker(Number(lat), Number(lon));
    map.on("click", (e) => setPoint(e.latlng.lat, e.latlng.lng));
  }
  function placeMarker(a, b) {
    if (!map) return;
    if (!marker) {
      marker = L.circleMarker([a, b], { radius: 9, color: "#fff", weight: 3, fillColor: "#1B3A6B", fillOpacity: 1 }).addTo(map);
    } else marker.setLatLng([a, b]);
  }
  function setPoint(a, b, zoom = null) {
    lat = a.toFixed(6);
    lon = b.toFixed(6);
    placeMarker(a, b);
    if (zoom && map) map.setView([a, b], zoom);
  }
  $effect(() => {
    if (gpsMode === "set") showMap();
  });
  onDestroy(() => map?.remove());

  let searchTimer;
  function searchPlace() {
    clearTimeout(searchTimer);
    const q = placeQ.trim();
    if (!q) {
      places = [];
      return;
    }
    searchTimer = setTimeout(async () => {
      searching = true;
      try {
        places = await api("/api/places/search", { params: { q } });
      } catch {
        places = [];
      } finally {
        searching = false;
      }
    }, 300);
  }
  function pickPlace(p) {
    setPoint(p.lat, p.lon, 15);
    placeQ = p.name;
    places = [];
  }

  // ---- 預覽與套用 ----
  async function goPreview() {
    busy = true;
    try {
      previewData = await api("/api/exif/preview", { body: { ids, changes } });
      step = "preview";
    } catch (e) {
      toast(e.message, "error");
    } finally {
      busy = false;
    }
  }

  async function applyNow() {
    busy = true;
    try {
      await api("/api/jobs", { body: { kind: "exif", ids, changes } });
      toast(`正在修改 ${count(previewData.changed)} 張的資訊…`);
      refresh();
      onclose?.(true);
    } catch (e) {
      toast(e.message, "error");
    } finally {
      busy = false;
    }
  }

  const LABELS = { taken_at: "拍攝時間", tz: "時區", make: "相機品牌", model: "相機型號", lens: "鏡頭", gps: "地點", title: "標題",
    caption: "說明", artist: "作者", copyright: "版權", name: "檔名" };
  function show(k, v) {
    if (v === null || v === undefined || v === "") return "（無）";
    if (k === "gps") return `${Number(v[0]).toFixed(5)}, ${Number(v[1]).toFixed(5)}`;
    if (k === "taken_at") return v.replace("T", " ");
    return String(v);
  }
  const TZS = ["+08:00", "+09:00", "+07:00", "+00:00", "+01:00", "+02:00", "-05:00", "-08:00", "+05:30", "+10:00"];
</script>

<Modal title={step === "edit" ? `編輯 ${count(ids.length)} 個項目的資訊` : "確認修改"} wide onclose={() => onclose?.(false)}>
  {#if !info}
    <div class="loading"><span class="spinner"></span>正在讀取照片資訊…</div>
  {:else if step === "edit"}
    <p class="where">
      {[info.embedded ? `${count(info.embedded)} 張直接寫入檔案` : "", info.raw ? `${count(info.raw)} 張 RAW 寫進 .xmp 附屬檔（RAW 本身不動）` : "",
        info.video ? `${count(info.video)} 部影片只能改檔名` : "", info.missing ? `${count(info.missing)} 個檔案目前找不到` : ""].filter(Boolean).join("　·　")}
    </p>
    <div class="form">
      <section>
        <h3>檔名</h3>
        <div class="row">
          <select class="input auto" bind:value={renameMode} aria-label="檔名規則">
            {#each RENAMES as [v, label] (v)}<option value={v}>{label}</option>{/each}
          </select>
          {#if renameMode === "custom"}
            <input class="input grow" bind:value={customRename} placeholder="例如 婚禮_{'{date}'}_{'{seq}'}" aria-label="自訂檔名規則" />
          {/if}
          {#if isChanged("rename")}<span class="chg">會改</span>{/if}
        </div>
        {#if renameMode}<p class="hint">直接改硬碟上的檔名，同名的 .xmp 一起改；RAW+JPEG 雙檔取相同序號。已匯入 Lightroom 的照片，改名後要在 Lightroom 重新連結。可用：{"{name}"} 原檔名、{"{date}"} 日期、{"{time}"} 時間、{"{seq}"} 序號、{"{camera}"} 相機、{"{folder}"} 資料夾</p>{/if}
      </section>

      <section>
        <h3>拍攝時間</h3>
        <div class="seg" role="radiogroup" aria-label="拍攝時間" use:slider>
          {#each [["keep", "不改"], ["set", "設定為"], ["shift", "整批平移"]] as [v, label] (v)}
            <button role="radio" aria-checked={timeMode === v} class:on={timeMode === v} onclick={() => (timeMode = v)}>{label}</button>
          {/each}
        </div>
        {#if timeMode === "set"}
          <div class="row" transition:slide={{ duration: 160 }}>
            <input class="input auto" type="datetime-local" step="1" bind:value={timeValue} aria-label="拍攝時間" />
            {#if info.fields.taken_at.mixed}<span class="hint">目前每張不同，會全部改成同一個時間</span>{/if}
          </div>
        {:else if timeMode === "shift"}
          <div class="row" transition:slide={{ duration: 160 }}>
            <select class="input auto" bind:value={shift.sign} aria-label="往前或往後">
              <option value={1}>往後（加）</option><option value={-1}>往前（減）</option>
            </select>
            <label class="num"><input class="input" type="number" min="0" bind:value={shift.d} />天</label>
            <label class="num"><input class="input" type="number" min="0" max="23" bind:value={shift.h} />時</label>
            <label class="num"><input class="input" type="number" min="0" max="59" bind:value={shift.m} />分</label>
            <label class="num"><input class="input" type="number" min="0" max="59" bind:value={shift.s} />秒</label>
          </div>
          <p class="hint">相機時鐘設錯（例如出國忘了改時區）時用：每張照片各自加減同樣的時間。</p>
        {/if}
        <div class="row tz">
          <span class="sub">時區</span>
          <select class="input auto" bind:value={tzMode} aria-label="時區">
            <option value="keep">不改{info.fields.tz.mixed ? "（多個值）" : info.fields.tz.value ? `（目前 ${info.fields.tz.value}）` : ""}</option>
            <option value="set">設定為</option>
          </select>
          {#if tzMode === "set"}
            <select class="input auto" bind:value={tzValue} aria-label="時區">
              {#each TZS as z (z)}<option value={z}>UTC{z}{z === "+08:00" ? "（台灣）" : z === "+09:00" ? "（日本、韓國）" : ""}</option>{/each}
            </select>
          {/if}
        </div>
      </section>

      <section>
        <h3>相機與鏡頭</h3>
        <div class="grid">
          {#each TEXT.slice(0, 3) as [k, label, ph] (k)}
            {@const f = text[k]}
            <label class="field">
              <span class="lbl">{label}{#if isChanged(k)}<span class="chg">已修改</span>{/if}</span>
              <span class="inwrap">
                <input class="input" value={f?.value ?? ""} oninput={(e) => setText(k, e.currentTarget.value)}
                  placeholder={f?.mixed ? "多個值（不改）" : f?.clear ? "（會清除）" : ph} />
                {#if isChanged(k)}<button class="icon-btn mini" onclick={() => resetText(k)} aria-label="還原 {label}" title="還原"><Icon path={mdiClose} size={18} /></button>{/if}
              </span>
            </label>
          {/each}
        </div>
      </section>

      <section>
        <h3>地點</h3>
        <div class="seg" role="radiogroup" aria-label="地點" use:slider>
          {#each [["keep", "不改"], ["set", "指定位置"], ["remove", "移除 GPS"]] as [v, label] (v)}
            <button role="radio" aria-checked={gpsMode === v} class:on={gpsMode === v} onclick={() => (gpsMode = v)}>{label}</button>
          {/each}
          {#if gpsMode === "keep"}<span class="hint inline">{info.fields.gps.mixed ? "目前每張不同" : info.fields.gps.value ? `目前 ${show("gps", info.fields.gps.value)}` : "目前沒有 GPS"}</span>{/if}
        </div>
        {#if gpsMode === "set"}
          <div class="gps" transition:slide={{ duration: 180 }}>
            <div class="psearch">
              <span class="lead"><Icon path={mdiMagnify} size={20} /></span>
              <input class="input" bind:value={placeQ} oninput={searchPlace} placeholder="搜尋地點，例如 嘉義車站、京都、九份" aria-label="搜尋地點" />
              {#if searching}<span class="spinner sm"></span>{/if}
              {#if places.length}
                <div class="presults" role="listbox">
                  {#each places as p, i (i)}
                    <button role="option" aria-selected="false" onclick={() => pickPlace(p)}>
                      <Icon path={mdiMapMarkerOutline} size={18} />
                      <span class="pn">{p.name}</span>
                      <span class="pc">{p.photos ? `你有 ${p.photos} 張在這裡` : p.country}</span>
                    </button>
                  {/each}
                </div>
              {/if}
            </div>
            <div class="map" bind:this={mapEl}></div>
            <div class="row">
              <label class="num wide">緯度<input class="input" type="number" step="0.000001" min="-90" max="90" bind:value={lat}
                onchange={() => lat !== "" && lon !== "" && setPoint(Number(lat), Number(lon), 15)} /></label>
              <label class="num wide">經度<input class="input" type="number" step="0.000001" min="-180" max="180" bind:value={lon}
                onchange={() => lat !== "" && lon !== "" && setPoint(Number(lat), Number(lon), 15)} /></label>
              <span class="hint">在地圖上點一下就能放置位置</span>
            </div>
          </div>
        {:else if gpsMode === "remove"}
          <p class="hint">會刪除選取照片的 GPS 位置（交件或上傳前保護隱私）。</p>
        {/if}
      </section>

      <section>
        <h3>標題、說明與版權</h3>
        <div class="grid">
          {#each TEXT.slice(3) as [k, label, ph] (k)}
            {@const f = text[k]}
            <label class="field" class:span={k === "caption"}>
              <span class="lbl">{label}{#if isChanged(k)}<span class="chg">已修改</span>{/if}</span>
              <span class="inwrap">
                {#if k === "caption"}
                  <textarea class="input" rows="2" value={f?.value ?? ""} oninput={(e) => setText(k, e.currentTarget.value)}
                    placeholder={f?.mixed ? "多個值（不改）" : f?.clear ? "（會清除）" : ph}></textarea>
                {:else}
                  <input class="input" value={f?.value ?? ""} oninput={(e) => setText(k, e.currentTarget.value)}
                    placeholder={f?.mixed ? "多個值（不改）" : f?.clear ? "（會清除）" : ph} />
                {/if}
                {#if isChanged(k)}<button class="icon-btn mini" onclick={() => resetText(k)} aria-label="還原 {label}" title="還原"><Icon path={mdiClose} size={18} /></button>
                {:else if f?.orig}<button class="btn text small clr" onclick={() => clearText(k)}>清除</button>{/if}
              </span>
            </label>
          {/each}
        </div>
      </section>
    </div>
  {:else}
    <div class="pv">
      <p class="sum">
        <b>{count(previewData.changed)} 個項目會被修改</b>
        {#if previewData.count > previewData.changed}<span class="muted">，{count(previewData.count - previewData.changed)} 個不用改</span>{/if}
      </p>
      {#if previewData.sample.length}
        <ul class="diffs">
          {#each previewData.sample as s (s.id)}
            <li>
              <b class="fname">{s.name}</b>
              {#each Object.entries(s.diff) as [k, d] (k)}
                <div class="d"><span class="k">{LABELS[k]}</span><span class="from">{show(k, d.from)}</span><Icon path={mdiArrowRight} size={16} /><span class="to">{show(k, d.to)}</span></div>
              {/each}
            </li>
          {/each}
        </ul>
        {#if previewData.changed > previewData.sample.length}<p class="hint">另外還有 {count(previewData.changed - previewData.sample.length)} 個項目，改法相同。</p>{/if}
      {:else}
        <p class="muted">選取的照片已經是這些值，不需要修改。</p>
      {/if}
      <p class="hint">JPEG／HEIC 直接寫進檔案；RAW 寫進 .xmp。套用後跳出的通知可以「復原」，也可以按 ⌘Z。</p>
    </div>
  {/if}

  {#snippet actions()}
    {#if step === "edit"}
      <span class="foot muted small">{changeCount ? `已修改 ${changeCount} 個欄位` : "還沒有修改"}</span>
      <button class="btn ghost" onclick={() => onclose?.(false)}>取消</button>
      <button class="btn" onclick={goPreview} disabled={!changeCount || busy}>{#if busy}<span class="spinner"></span>{/if}預覽變更</button>
    {:else}
      <button class="btn ghost" onclick={() => (step = "edit")}>返回修改</button>
      <button class="btn" onclick={applyNow} disabled={busy || !previewData.changed}>{#if busy}<span class="spinner"></span>{/if}套用到 {count(previewData.changed)} 個項目</button>
    {/if}
  {/snippet}
</Modal>

<style>
  .loading { display: flex; align-items: center; gap: 10px; color: var(--on-surface-variant); padding: 24px 0; }
  .where { margin: 0 0 12px; font-size: 14px; color: var(--on-surface-variant); }
  .form { display: flex; flex-direction: column; gap: 4px; color: var(--on-surface); }
  section { display: flex; flex-direction: column; gap: 10px; padding: 14px 0; border-top: 1px solid var(--outline-variant); }
  section:first-child { border-top: 0; padding-top: 0; }
  h3 { margin: 0; font-size: 14px; font-weight: 500; }
  .row { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
  .input.auto { width: auto; }
  .grow { flex: 1; min-width: 200px; }
  .hint { margin: 0; font-size: 12px; line-height: 16px; color: var(--on-surface-variant); }
  .hint.inline { margin-left: 8px; align-self: center; }
  .chg { margin-left: 8px; font-size: 11px; font-weight: 500; padding: 1px 8px; border-radius: var(--corner-full); background: var(--secondary-container); color: var(--on-secondary-container); }
  .seg { display: flex; flex-wrap: wrap; align-items: center; }
  .seg button { border: 1px solid var(--outline); background: none; color: var(--on-surface); height: 36px; padding: 0 16px; font-size: 14px; font-weight: 500; cursor: pointer; margin-left: -1px; }
  .seg button:first-child { border-radius: var(--corner-full) 0 0 var(--corner-full); margin-left: 0; }
  .seg button:nth-child(3) { border-radius: 0 var(--corner-full) var(--corner-full) 0; }
  .seg button.on { background: var(--secondary-container); color: var(--on-secondary-container); }
  .num { display: inline-flex; align-items: center; gap: 6px; font-size: 14px; color: var(--on-surface-variant); }
  .num .input { width: 72px; min-height: 40px; padding: 8px 10px; }
  .num.wide .input { width: 140px; }
  .tz .sub { font-size: 14px; color: var(--on-surface-variant); }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; }
  .field { display: flex; flex-direction: column; gap: 4px; min-width: 0; }
  .field.span { grid-column: 1 / -1; }
  .lbl { font-size: 12px; color: var(--on-surface-variant); display: flex; align-items: center; }
  .inwrap { position: relative; display: flex; align-items: center; }
  .inwrap .input { padding-right: 44px; }
  .inwrap .mini { position: absolute; right: 4px; width: 32px; height: 32px; color: var(--on-surface-variant); }
  .inwrap .clr { position: absolute; right: 4px; }
  .gps { display: flex; flex-direction: column; gap: 10px; }
  .psearch { position: relative; display: flex; align-items: center; }
  .psearch .lead { position: absolute; left: 12px; color: var(--on-surface-variant); display: flex; pointer-events: none; }
  .psearch .input { padding-left: 42px; }
  .psearch .sm { position: absolute; right: 12px; width: 16px; height: 16px; }
  .psearch { flex-wrap: wrap; }
  .presults {
    flex-basis: 100%; margin-top: 4px; padding: 4px 0;
    background: var(--surface-container-high); border: 1px solid var(--outline-variant); border-radius: var(--corner-medium);
  }
  .presults button { display: flex; align-items: center; gap: 10px; width: 100%; padding: 10px 14px; border: 0; background: none; color: var(--on-surface); cursor: pointer; text-align: left; font-size: 14px; }
  .presults button:hover { background: color-mix(in srgb, var(--on-surface) 8%, transparent); }
  .pn { font-weight: 500; }
  .pc { color: var(--on-surface-variant); font-size: 12px; margin-left: auto; text-align: right; }
  .map { height: 260px; border-radius: var(--corner-medium); overflow: hidden; z-index: 0; cursor: crosshair; }
  .pv .sum { margin: 0 0 12px; }
  .pv .sum b { font-weight: 500; font-size: 16px; }
  .diffs { list-style: none; margin: 0 0 12px; padding: 0; display: flex; flex-direction: column; background: var(--surface-container-high); border-radius: var(--corner-large); overflow: hidden; }
  .diffs li { padding: 10px 16px; display: flex; flex-direction: column; gap: 4px; }
  .diffs li + li { border-top: 1px solid var(--outline-variant); }
  .fname { font-weight: 500; font-size: 14px; }
  .d { display: grid; grid-template-columns: 72px minmax(0, 1fr) 16px minmax(0, 1fr); gap: 8px; align-items: center; font-size: 14px; color: var(--on-surface-variant); }
  .d .from { text-decoration: line-through; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .d .to { color: var(--on-surface); font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .foot { margin-right: auto; }
  .spinner { width: 14px; height: 14px; }
</style>
