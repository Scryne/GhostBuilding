// ═══════════════════════════════════════════════════════════════════════════
// GhostMap.tsx — Ana harita bileşeni
// MapLibre GL JS tabanlı, dark tema, Nominatim geocoding, tam ekran.
// ═══════════════════════════════════════════════════════════════════════════

"use client";

import {
  useRef,
  useCallback,
  useState,
  useEffect,
  createContext,
  useContext,
  type ReactNode,
} from "react";
import Map, {
  AttributionControl,
  Layer,
  Source,
  type MapRef,
  type ViewStateChangeEvent,
} from "react-map-gl/maplibre";
import { setWorkerUrl, type MapMouseEvent } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";

import AnomalyLayer from "./AnomalyLayer";
import MapControls from "./MapControls";
import ScanProgressToast from "./ScanProgressToast";
import { AnomalyDetailPanel } from "@/components/anomaly";
import type { AnomalyCategory, MapViewport } from "@/lib/types";

// ── Harita Stili ──────────────────────────────────────────────────────────

const MAP_STYLES = {
  dark: "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
  darkNoLabels:
    "https://basemaps.cartocdn.com/gl/dark-matter-nolabels-gl-style/style.json",
} as const;

// ── Başlangıç Viewport ───────────────────────────────────────────────────

// MapLibre 6 worker'ı: paketleyici import.meta.url'li worker dosyalarını yayımlamadığı için
// public/maplibre/ altına kopyalanır (scripts/copy-maplibre-worker.mjs).
setWorkerUrl("/maplibre/maplibre-gl-worker.mjs");

// ── Altlıklar ─────────────────────────────────────────────────────────────
// Vektör karanlık harita + karşılaştırmada kullanılan uydu kaynaklarının kendileri.
// Kullanıcı bir bulguyu, motorun baktığı görüntünün aynısıyla haritada görebilir.

export type BasemapId = "dark" | "esri" | "maptiler" | "ign";

const MAPTILER_KEY = process.env.NEXT_PUBLIC_MAPLIBRE_TOKEN;

export const BASEMAPS: Record<
  BasemapId,
  { label: string; hint?: string; tiles?: string[]; attribution?: string; maxzoom?: number }
> = {
  dark: { label: "Harita" },
  esri: {
    label: "Esri uydu",
    tiles: [
      "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    ],
    attribution: "Esri, Maxar, Earthstar Geographics, and the GIS User Community",
    maxzoom: 19,
  },
  maptiler: {
    label: "MapTiler uydu",
    tiles: MAPTILER_KEY
      ? [`https://api.maptiler.com/tiles/satellite-v2/{z}/{x}/{y}.jpg?key=${MAPTILER_KEY}`]
      : undefined,
    attribution: "© MapTiler © OpenStreetMap contributors",
    maxzoom: 20,
  },
  ign: {
    label: "IGN ortofoto",
    hint: "Yalnız Fransa",
    tiles: [
      "https://data.geopf.fr/wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER=ORTHOIMAGERY.ORTHOPHOTOS&STYLE=normal&TILEMATRIXSET=PM&TILEMATRIX={z}&TILEROW={y}&TILECOL={x}&FORMAT=image/jpeg",
    ],
    attribution: "© IGN – Géoplateforme",
    maxzoom: 19,
  },
};

/** Paylaşılan bağlantı: /?a=<anomali>&lat=..&lng=..&z=.. haritayı o bulguda açar. */
function readUrlState(): { viewport: MapViewport; anomalyId: string | null } {
  const params = new URLSearchParams(window.location.search);
  const lat = Number(params.get("lat"));
  const lng = Number(params.get("lng"));
  const zoom = Number(params.get("z"));
  const valid = params.has("lat") && params.has("lng") && Number.isFinite(lat) && Number.isFinite(lng);
  return {
    viewport: valid
      ? { latitude: lat, longitude: lng, zoom: Number.isFinite(zoom) && zoom > 0 ? zoom : 15 }
      : INITIAL_VIEWPORT,
    anomalyId: params.get("a"),
  };
}

// Referans taramasının bulguları Batı Avrupa'da; ilk açılış onları gösterir.
const INITIAL_VIEWPORT: MapViewport = {
  latitude: 48.8,
  longitude: 2.5,
  zoom: 4.6,
};

// ── Map Context — Alt bileşenlerin map instance'a erişimi ─────────────────

interface MapContextValue {
  mapRef: React.RefObject<MapRef>;
  viewport: MapViewport;
  cursorPosition: { lat: number; lng: number } | null;
  flyTo: (lat: number, lng: number, zoom?: number) => void;
  // Katman filtre state'i
  activeCategories: Set<AnomalyCategory>;
  toggleCategory: (category: AnomalyCategory) => void;
  minConfidence: number;
  setMinConfidence: (value: number) => void;
  showNearby: boolean;
  setShowNearby: (value: boolean) => void;
  // Tarama state'i
  activeScanTaskId: string | null;
  setActiveScanTaskId: (id: string | null) => void;
  // Seçili anomali
  selectedAnomalyId: string | null;
  setSelectedAnomalyId: (id: string | null) => void;
  basemap: BasemapId;
  setBasemap: (id: BasemapId) => void;
}

const MapContext = createContext<MapContextValue | null>(null);

export function useMapContext() {
  const ctx = useContext(MapContext);
  if (!ctx) throw new Error("useMapContext must be used within GhostMap");
  return ctx;
}

// ═══════════════════════════════════════════════════════════════════════════
// GhostMap Component
// ═══════════════════════════════════════════════════════════════════════════

interface GhostMapProps {
  children?: ReactNode;
}

export default function GhostMap({ children }: GhostMapProps) {
  const mapRef = useRef<MapRef>(null!);

  // ── Viewport State ──────────────────────────────────────────────────

  // Bileşen yalnız istemcide yüklenir (Map.tsx, ssr: false); URL okunabilir.
  const [urlState] = useState(readUrlState);
  const [viewport, setViewport] = useState<MapViewport>(urlState.viewport);

  const handleMove = useCallback((evt: ViewStateChangeEvent) => {
    setViewport({
      latitude: evt.viewState.latitude,
      longitude: evt.viewState.longitude,
      zoom: evt.viewState.zoom,
    });
  }, []);

  // ── Cursor Position ─────────────────────────────────────────────────

  const [cursorPosition, setCursorPosition] = useState<{
    lat: number;
    lng: number;
  } | null>(null);

  const handleMouseMove = useCallback(
    (evt: MapMouseEvent) => {
      setCursorPosition({
        lat: evt.lngLat.lat,
        lng: evt.lngLat.lng,
      });
    },
    []
  );

  // ── Fly To ──────────────────────────────────────────────────────────

  const flyTo = useCallback((lat: number, lng: number, zoom?: number) => {
    mapRef.current?.flyTo({
      center: [lng, lat],
      zoom: zoom ?? 14,
      duration: 1500,
      essential: true,
    });
  }, []);

  // ── Layer Filter State ──────────────────────────────────────────────

  const [activeCategories, setActiveCategories] = useState<
    Set<AnomalyCategory>
  >(
    new Set([
      "GHOST_BUILDING" as AnomalyCategory,
      "HIDDEN_STRUCTURE" as AnomalyCategory,
      "CENSORED_AREA" as AnomalyCategory,
      "IMAGE_DISCREPANCY" as AnomalyCategory,
    ])
  );

  const toggleCategory = useCallback((category: AnomalyCategory) => {
    setActiveCategories((prev) => {
      const next = new Set(prev);
      if (next.has(category)) {
        next.delete(category);
      } else {
        next.add(category);
      }
      return next;
    });
  }, []);

  // Kayıtlı her anomali zaten tabanın üstünde (>50); varsayılan filtre hiçbirini gizlemez.
  const [minConfidence, setMinConfidence] = useState(0);
  const [basemap, setBasemap] = useState<BasemapId>("dark");
  const [showNearby, setShowNearby] = useState(false);
  const [activeScanTaskId, setActiveScanTaskId] = useState<string | null>(null);
  const [selectedAnomalyId, setSelectedAnomalyId] = useState<string | null>(
    urlState.anomalyId
  );

  // ── Map Event Handlers ──────────────────────────────────────────────

  const handleMapLoad = useCallback(() => {
    const map = mapRef.current?.getMap();
    if (!map) return;

    // Fare imlecini default crosshair yap
    map.getCanvas().style.cursor = "crosshair";

    map.on("mousemove", handleMouseMove);
  }, [handleMouseMove]);

  // ── Context Value ───────────────────────────────────────────────────

  // ── Custom Event Listeners ──────────────────────────────────────────

  useEffect(() => {
    const handleFlyTo = (e: CustomEvent<{ lat: number; lng: number; zoom?: number }>) => {
      flyTo(e.detail.lat, e.detail.lng, e.detail.zoom);
    };

    window.addEventListener("ghostbuilding:flyto", handleFlyTo as EventListener);
    return () => {
      window.removeEventListener("ghostbuilding:flyto", handleFlyTo as EventListener);
    };
  }, [flyTo]);


  const contextValue: MapContextValue = {
    mapRef,
    viewport,
    cursorPosition,
    flyTo,
    activeCategories,
    toggleCategory,
    minConfidence,
    setMinConfidence,
    showNearby,
    setShowNearby,
    activeScanTaskId,
    setActiveScanTaskId,
    selectedAnomalyId,
    setSelectedAnomalyId,
    basemap,
    setBasemap,
  };

  const raster = BASEMAPS[basemap];

  return (
    <MapContext.Provider value={contextValue}>
      <div className="w-full h-full relative">
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

        {/* Harita üstü kontroller (zoom, konum, tarama) */}
        <MapControls />

        {/* Tarama İlerleme */}
        {activeScanTaskId && (
          <ScanProgressToast taskId={activeScanTaskId} />
        )}

        {/* Anomali Detay Paneli — sağ kenar */}
        {selectedAnomalyId && (
          <AnomalyDetailPanel
            anomalyId={selectedAnomalyId}
            onClose={() => setSelectedAnomalyId(null)}
          />
        )}

        {/* Ek overlay bileşenleri */}
        {children}
      </div>
    </MapContext.Provider>
  );
}
