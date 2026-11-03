// ═══════════════════════════════════════════════════════════════════════════
// MapState.tsx — Harita bağlamı (filtreler, seçim, görünüm, tarama) ve altlık listesi.
// MapLibre'ye bağlı DEĞİL: kabuk (MapChrome, MapControls, bulgu paneli) bu bağlamla sunucuda
// render edilir; harita tuvali (GhostMap) MapLibre yüklendikten sonra aynı bağlama bağlanır.
// Buraya maplibre-gl / react-map-gl'den değer import edilmez (yalnız tip).
// ═══════════════════════════════════════════════════════════════════════════

"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
  type ReactNode,
} from "react";
import type { MapRef } from "react-map-gl/maplibre";
import type { AnomalyCategory, MapViewport } from "@/lib/types";

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

// ── Başlangıç Viewport ───────────────────────────────────────────────────

// Referans taramasının bulguları Batı Avrupa'da; ilk açılış onları gösterir.
const INITIAL_VIEWPORT: MapViewport = {
  latitude: 48.8,
  longitude: 2.5,
  zoom: 4.6,
};

export interface UrlState {
  viewport: MapViewport;
  anomalyId: string | null;
}

/** Paylaşılan bağlantı: /?a=<anomali>&lat=..&lng=..&z=.. haritayı o bulguda açar. */
function parseUrlState(search: string): UrlState {
  const params = new URLSearchParams(search);
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

// Sayfa statik ön-render edilir; sunucuda URL yoktur. Sunucu anlık görüntüsü null'dır,
// istemci hidrasyondan hemen sonra gerçek sorgu dizesiyle yeniden render eder.
const noopSubscribe = () => () => {};
const getSearch = () => window.location.search;
const getServerSearch = () => null;

// ── Map Context — Alt bileşenlerin map instance'a erişimi ─────────────────

interface MapContextValue {
  mapRef: React.RefObject<MapRef>;
  /** URL'den okunan başlangıç durumu; sunucuda ve hidrasyonda null. */
  urlState: UrlState | null;
  viewport: MapViewport;
  setViewport: (viewport: MapViewport) => void;
  cursorPosition: { lat: number; lng: number } | null;
  setCursorPosition: (pos: { lat: number; lng: number } | null) => void;
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
  if (!ctx) throw new Error("useMapContext must be used within MapStateProvider");
  return ctx;
}

// ═══════════════════════════════════════════════════════════════════════════
// MapStateProvider
// ═══════════════════════════════════════════════════════════════════════════

export function MapStateProvider({ children }: { children?: ReactNode }) {
  // Harita tuvali yüklendiğinde GhostMap bu ref'i <Map>'e bağlar; öncesinde null'dır.
  const mapRef = useRef<MapRef>(null!);

  // ── URL durumu ──────────────────────────────────────────────────────

  const search = useSyncExternalStore(noopSubscribe, getSearch, getServerSearch);
  const urlState = useMemo(() => (search === null ? null : parseUrlState(search)), [search]);

  // ── Viewport State ──────────────────────────────────────────────────
  // Harita hareket edene kadar URL'deki (yoksa başlangıç) görünüm geçerlidir.

  const [movedViewport, setViewport] = useState<MapViewport | null>(null);
  const viewport = movedViewport ?? urlState?.viewport ?? INITIAL_VIEWPORT;

  // ── Cursor Position ─────────────────────────────────────────────────

  const [cursorPosition, setCursorPosition] = useState<{
    lat: number;
    lng: number;
  } | null>(null);

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

  // Seçim kullanıcı değiştirene kadar URL'deki ?a= değeridir.
  const [pickedAnomalyId, setSelectedAnomalyId] = useState<string | null | undefined>(undefined);
  const selectedAnomalyId =
    pickedAnomalyId !== undefined ? pickedAnomalyId : (urlState?.anomalyId ?? null);

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

  // ── Context Value ───────────────────────────────────────────────────

  const contextValue: MapContextValue = {
    mapRef,
    urlState,
    viewport,
    setViewport,
    cursorPosition,
    setCursorPosition,
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

  return <MapContext.Provider value={contextValue}>{children}</MapContext.Provider>;
}
