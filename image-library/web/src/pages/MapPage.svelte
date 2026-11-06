<script>
  import { onMount } from "svelte";
  import L from "leaflet";
  import "leaflet/dist/leaflet.css";
  import "leaflet.markercluster/dist/MarkerCluster.css";
  import { api, thumbUrl } from "../lib/api.js";
  import { openViewer } from "../lib/state.svelte.js";

  let el;
  let count = $state(null);
  let error = $state("");

  onMount(() => {
    let map;
    let cancelled = false;
    (async () => {
      window.L = L; // markercluster 外掛需要全域 L
      await import("leaflet.markercluster");
      if (cancelled) return;
      map = L.map(el, { zoomControl: true, worldCopyJump: true }).setView([23.7, 121], 7);
      L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 19,
        attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
      }).addTo(map);
      let points;
      try {
        points = await api("/api/map");
      } catch (e) {
        error = e.message;
        return;
      }
      count = points.length;
      if (!points.length || cancelled) return;
      const list = points.map(([id]) => ({ id }));
      const cluster = L.markerClusterGroup({
        chunkedLoading: true,
        showCoverageOnHover: false,
        maxClusterRadius: 60,
        iconCreateFunction(c) {
          const first = c.getAllChildMarkers()[0];
          const n = c.getChildCount();
          return L.divIcon({
            html: `<div class="pin cluster"><img src="${thumbUrl({ id: first.options.assetId })}" loading="lazy" alt=""><b>${n > 999 ? Math.round(n / 100) / 10 + "k" : n}</b></div>`,
            className: "",
            iconSize: [52, 52],
          });
        },
      });
      const markers = points.map(([id, lat, lon], i) => {
        const m = L.marker([lat, lon], {
          assetId: id,
          icon: L.divIcon({ html: `<div class="pin"><img src="${thumbUrl({ id })}" loading="lazy" alt=""></div>`, className: "", iconSize: [44, 44] }),
        });
        m.on("click", () => openViewer(list, i));
        return m;
      });
      cluster.addLayers(markers);
      map.addLayer(cluster);
      map.fitBounds(cluster.getBounds(), { padding: [40, 40], maxZoom: 14 });
    })();
    return () => {
      cancelled = true;
      map?.remove();
    };
  });
</script>

<div class="wrap">
  <div class="map" bind:this={el}></div>
  {#if count === 0}
    <div class="note">沒有含 GPS 資訊的照片。相機或手機開啟定位後拍攝的照片會顯示在地圖上。</div>
  {:else if count}
    <div class="note small">{count.toLocaleString()} 個有位置的項目</div>
  {/if}
  {#if error}<div class="note danger-text">{error}</div>{/if}
</div>

<style>
  .wrap { position: absolute; inset: 0; }
  .map { width: 100%; height: 100%; z-index: 0; }
  .note {
    position: absolute; top: 12px; left: 50%; transform: translateX(-50%); z-index: 500; background: var(--surface-container-low);
    color: var(--on-surface); padding: 8px 16px; border-radius: var(--corner-full); border: 1px solid var(--outline-variant); font-size: 14px; max-width: 90%;
  }
  :global(.pin) {
    width: 44px; height: 44px; border-radius: var(--corner-medium); overflow: hidden; border: 3px solid #fff; background: #ccc;
    position: relative;
  }
  :global(.pin img) { width: 100%; height: 100%; object-fit: cover; display: block; }
  :global(.pin.cluster) { width: 52px; height: 52px; }
  :global(.pin b) {
    position: absolute; right: -2px; bottom: -2px; background: #4250af; color: #fff; font-size: 11px;
    padding: 1px 6px; border-radius: var(--corner-full) 0 var(--corner-small) 0; font-weight: 700;
  }
</style>
