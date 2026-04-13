// ═══════════════════════════════════════════════════════════════════════════
// GhostMap.tsx — Ana harita bileşeni
// MapLibre GL JS tabanlı, dark tema, Nominatim geocoding, tam ekran.
// ═══════════════════════════════════════════════════════════════════════════

"use client";

import {
  useRef,
  useCallback,
  useState,
  createContext,
  useContext,
  type ReactNode,
} from "react";
import Map, {
  NavigationControl,
  type MapRef,
  type ViewStateChangeEvent,
} from "react-map-gl/maplibre";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";

import AnomalyLayer from "./AnomalyLayer";
import LayerControls from "./LayerControls";
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

const INITIAL_VIEWPORT: MapViewport = {
  latitude: 39.0,
  longitude: 35.0,
  zoom: 5,
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

  const [viewport, setViewport] = useState<MapViewport>(INITIAL_VIEWPORT);

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
    (evt: maplibregl.MapMouseEvent & { target: maplibregl.Map }) => {
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

  const [minConfidence, setMinConfidence] = useState(40);
  const [showNearby, setShowNearby] = useState(false);
  const [activeScanTaskId, setActiveScanTaskId] = useState<string | null>(null);
  const [selectedAnomalyId, setSelectedAnomalyId] = useState<string | null>(
    null
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
  };

  return (
    <MapContext.Provider value={contextValue}>
      <div className="w-full h-full relative">
        <Map
          ref={mapRef}
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          mapLib={maplibregl as any}
          initialViewState={INITIAL_VIEWPORT}
          onMove={handleMove}
          onLoad={handleMapLoad}
          mapStyle={MAP_STYLES.dark}
          attributionControl={false}
          maxZoom={19}
          minZoom={2}
          maxTileCacheSize={500}
          style={{ width: "100%", height: "100%" }}
        >
          {/* Zoom Kontrolleri — sağ üst */}
          <NavigationControl position="top-right" showCompass={false} />

          {/* Anomali Katmanı */}
          <AnomalyLayer />
        </Map>

        {/* Harita Üstü Kontroller — map dışında render
            (pointer-events: auto ile tıklanabilir) */}
        <LayerControls />
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
