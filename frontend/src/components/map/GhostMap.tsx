// ═══════════════════════════════════════════════════════════════════════════
// GhostMap.tsx — Harita tuvali (MapLibre GL JS, dark tema, tam ekran)
// Yalnız istemcide, kabuk çizildikten SONRA yüklenir (MapPage → next/dynamic, ssr: false).
// Durum MapState.tsx'teki bağlamdadır; burası yalnız MapLibre'ye bağlanan kısımdır.
// ═══════════════════════════════════════════════════════════════════════════

"use client";

import { useCallback } from "react";
import Map, {
  AttributionControl,
  Layer,
  Source,
  type ViewStateChangeEvent,
} from "react-map-gl/maplibre";
import { setWorkerUrl, type MapMouseEvent } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";

import AnomalyLayer from "./AnomalyLayer";
import { BASEMAPS, useMapContext } from "./MapState";

// ── Harita Stili ──────────────────────────────────────────────────────────

const MAP_STYLES = {
  dark: "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
  darkNoLabels:
    "https://basemaps.cartocdn.com/gl/dark-matter-nolabels-gl-style/style.json",
} as const;

// MapLibre 6 worker'ı: paketleyici import.meta.url'li worker dosyalarını yayımlamadığı için
// public/maplibre/ altına kopyalanır (scripts/copy-maplibre-worker.mjs). Bu modül yalnız
// tarayıcıda yüklendiği için çağrı, ilk Map örneğinden önce bir kez yapılır.
setWorkerUrl("/maplibre/maplibre-gl-worker.mjs");

// ═══════════════════════════════════════════════════════════════════════════
// GhostMap Component
// ═══════════════════════════════════════════════════════════════════════════

export default function GhostMap() {
  const { mapRef, urlState, setViewport, setCursorPosition, basemap } = useMapContext();

  const handleMove = useCallback(
    (evt: ViewStateChangeEvent) => {
      setViewport({
        latitude: evt.viewState.latitude,
        longitude: evt.viewState.longitude,
        zoom: evt.viewState.zoom,
      });
    },
    [setViewport]
  );

  const handleMouseMove = useCallback(
    (evt: MapMouseEvent) => {
      setCursorPosition({
        lat: evt.lngLat.lat,
        lng: evt.lngLat.lng,
      });
    },
    [setCursorPosition]
  );

  // ── Map Event Handlers ──────────────────────────────────────────────

  const handleMapLoad = useCallback(() => {
    const map = mapRef.current?.getMap();
    if (!map) return;

    // Fare imlecini default crosshair yap
    map.getCanvas().style.cursor = "crosshair";

    map.on("mousemove", handleMouseMove);
  }, [mapRef, handleMouseMove]);

  // Başlangıç görünümü URL'den gelir; tuval yalnız istemcide (hidrasyondan sonra) render
  // edildiği için burada urlState hep doludur. Yine de boşsa bekle.
  if (!urlState) return null;

  const raster = BASEMAPS[basemap];

  return (
    <Map
      ref={mapRef}
      initialViewState={urlState.viewport}
      onMove={handleMove}
      onLoad={handleMapLoad}
      mapStyle={MAP_STYLES.dark}
      attributionControl={false}
      maxZoom={19}
      minZoom={2}
      maxTileCacheSize={500}
      style={{ width: "100%", height: "100%" }}
    >
      {/* Kaynak atıfları kullanım koşulu gereği her altlıkta görünür */}
      <AttributionControl compact position="bottom-right" />

      {/* Uydu altlığı — anomali katmanlarının altında */}
      {raster.tiles && (
        <Source
          key={basemap}
          id={`basemap-${basemap}`}
          type="raster"
          tiles={raster.tiles}
          tileSize={256}
          maxzoom={raster.maxzoom}
          attribution={raster.attribution}
        >
          <Layer id={`basemap-${basemap}-layer`} type="raster" beforeId="cluster-circles" />
        </Source>
      )}

      {/* Anomali Katmanı */}
      <AnomalyLayer />
    </Map>
  );
}
