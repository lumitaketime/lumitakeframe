<script>
  import { onMount } from "svelte";
  import L from "leaflet";
  import "leaflet/dist/leaflet.css";

  let { lat, lon, height = 180 } = $props();
  let el;
  let map;
  let marker;

  onMount(() => {
    map = L.map(el, { zoomControl: false, attributionControl: true, scrollWheelZoom: false }).setView([lat, lon], 13);
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: "© OpenStreetMap",
    }).addTo(map);
    marker = L.circleMarker([lat, lon], { radius: 8, color: "#fff", weight: 2, fillColor: "#4250af", fillOpacity: 1 }).addTo(map);
    return () => map.remove();
  });

  $effect(() => {
    if (map) {
      map.setView([lat, lon], map.getZoom());
      marker.setLatLng([lat, lon]);
    }
  });
</script>

<div class="map" bind:this={el} style:height="{height}px"></div>

<style>
  .map { width: 100%; border-radius: 12px; overflow: hidden; z-index: 0; }
</style>
