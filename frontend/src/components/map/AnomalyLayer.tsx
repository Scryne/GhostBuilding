// ═══════════════════════════════════════════════════════════════════════════
// AnomalyLayer.tsx — Anomali işaretleri katmanı
// GeoJSON source, kategoriye göre renk/ikon, cluster, hover tooltip, click.
// ═══════════════════════════════════════════════════════════════════════════

"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Source, Layer, Popup, useMap, type MapLayerMouseEvent } from "react-map-gl/maplibre";
import type { CircleLayerSpecification, SymbolLayerSpecification } from "maplibre-gl";
import { useMapContext } from "./GhostMap";
import { useMapAnomalies } from "@/hooks/useAnomaly";
import { CATEGORY_LABELS, formatCoordsCompact } from "@/lib/utils";
import type { AnomalyCategory } from "@/lib/types";

// ── Kategori Renk Haritası (hex) ──────────────────────────────────────────

const CATEGORY_HEX: Record<string, string> = {
  GHOST_BUILDING: "#F4A261",
  HIDDEN_STRUCTURE: "#E63946",
  CENSORED_AREA: "#9B2226",
  IMAGE_DISCREPANCY: "#457B9D",
};

// ── Cluster renk skalası ──────────────────────────────────────────────────

const CLUSTER_COLORS = [
  { count: 100, color: "#E63946" },
  { count: 50, color: "#F4A261" },
  { count: 20, color: "#457B9D" },
  { count: 0, color: "#2E6DA4" },
];

// ═══════════════════════════════════════════════════════════════════════════
// Component
// ═══════════════════════════════════════════════════════════════════════════

export default function AnomalyLayer() {
  const { current: map } = useMap();
  const {
    viewport,
    activeCategories,
    minConfidence,
    setSelectedAnomalyId,
  } = useMapContext();

  // ── SWR ile anomali verisi çek ──────────────────────────────────────

  const { data: anomalyData } = useMapAnomalies(
    viewport
      ? {
          latitude: viewport.latitude,
          longitude: viewport.longitude,
          zoom: viewport.zoom,
        }
      : null,
    { min_confidence: minConfidence }
  );

  // ── GeoJSON Source ──────────────────────────────────────────────────

  const geojson = useMemo(() => {
    const anomaliesList = anomalyData?.data ?? [];
    const filteredAnomalies = anomaliesList.filter((a) =>
      activeCategories.has(a.category)
    );

    return {
      type: "FeatureCollection" as const,
      features: filteredAnomalies.map((anomaly) => ({
        type: "Feature" as const,
        id: anomaly.id,
        geometry: {
          type: "Point" as const,
          coordinates: [anomaly.lng, anomaly.lat],
        },
        properties: {
          id: anomaly.id,
          category: anomaly.category,
          confidence_score: anomaly.confidence_score,
          title: anomaly.title || "Anomali",
          status: anomaly.status,
          color: CATEGORY_HEX[anomaly.category] || "#2E6DA4",
        },
      })),
    };
  }, [anomalyData?.data, activeCategories]);

  // ── Hover / Tooltip State ───────────────────────────────────────────

  const [hoveredAnomaly, setHoveredAnomaly] = useState<{
    longitude: number;
    latitude: number;
    title: string;
    category: string;
    confidence: number;
  } | null>(null);

  // ── Map Event Handlers ──────────────────────────────────────────────

  // Hover — unclustered-point
  const onMouseEnter = useCallback(
    (e: MapLayerMouseEvent) => {
      if (!map) return;
      map.getCanvas().style.cursor = "pointer";

      const feature = e.features?.[0];
      if (!feature || feature.geometry.type !== "Point") return;

      const coords = feature.geometry.coordinates as [number, number];
      const props = feature.properties;

      setHoveredAnomaly({
        longitude: coords[0],
        latitude: coords[1],
        title: props?.title || "Anomali",
        category: props?.category || "",
        confidence: props?.confidence_score || 0,
      });
    },
    [map]
  );

  const onMouseLeave = useCallback(() => {
    if (!map) return;
    map.getCanvas().style.cursor = "crosshair";
    setHoveredAnomaly(null);
  }, [map]);

  // Click — anomali seç
  const onClick = useCallback(
    (e: MapLayerMouseEvent) => {
      const feature = e.features?.[0];
      if (!feature) return;

      const props = feature.properties;

      // Cluster tıklaması — zoom in
      if (props?.cluster) {
        const clusterId = props.cluster_id;
        const source = map?.getSource("anomalies") as maplibregl.GeoJSONSource | undefined;
        if (source && feature.geometry.type === "Point") {
          const coords = feature.geometry.coordinates as [number, number];
          source.getClusterExpansionZoom(clusterId).then((zoom) => {
            map?.flyTo({
              center: coords,
              zoom: zoom ?? 14,
              duration: 800,
            });
          }).catch(() => {});
        }
        return;
      }

      // Tek anomali tıklaması
      const anomalyId = props?.id;
      if (anomalyId) {
        setSelectedAnomalyId(anomalyId);
        setHoveredAnomaly(null);
      }
    },
    [map, setSelectedAnomalyId]
  );

  // Event listener'ları bağla
  useEffect(() => {
    if (!map) return;

    const mapInstance = map;

    mapInstance.on("mouseenter", "unclustered-point", onMouseEnter as unknown as (e: maplibregl.MapMouseEvent) => void);
    mapInstance.on("mouseleave", "unclustered-point", onMouseLeave);
    mapInstance.on("click", "unclustered-point", onClick as unknown as (e: maplibregl.MapMouseEvent) => void);
    mapInstance.on("click", "cluster-circles", onClick as unknown as (e: maplibregl.MapMouseEvent) => void);

    return () => {
      mapInstance.off("mouseenter", "unclustered-point", onMouseEnter as unknown as (e: maplibregl.MapMouseEvent) => void);
      mapInstance.off("mouseleave", "unclustered-point", onMouseLeave);
      mapInstance.off("click", "unclustered-point", onClick as unknown as (e: maplibregl.MapMouseEvent) => void);
      mapInstance.off("click", "cluster-circles", onClick as unknown as (e: maplibregl.MapMouseEvent) => void);
    };
  }, [map, onMouseEnter, onMouseLeave, onClick]);

  // ── Layer Style Definitions ─────────────────────────────────────────

  // Cluster circle layer
  const clusterLayer: CircleLayerSpecification = {
    id: "cluster-circles",
    type: "circle",
    source: "anomalies",
    filter: ["has", "point_count"],
    paint: {
      "circle-color": [
        "step",
        ["get", "point_count"],
        CLUSTER_COLORS[3].color,
        CLUSTER_COLORS[2].count,
        CLUSTER_COLORS[2].color,
        CLUSTER_COLORS[1].count,
        CLUSTER_COLORS[1].color,
        CLUSTER_COLORS[0].count,
        CLUSTER_COLORS[0].color,
      ],
      "circle-radius": [
        "step",
        ["get", "point_count"],
        18,
        20,
        24,
        50,
        30,
        100,
        36,
      ],
      "circle-opacity": 0.85,
      "circle-stroke-width": 2,
      "circle-stroke-color": "rgba(255,255,255,0.15)",
    },
  };

  // Cluster count label
  const clusterCountLayer: SymbolLayerSpecification = {
    id: "cluster-count",
    type: "symbol",
    source: "anomalies",
    filter: ["has", "point_count"],
    layout: {
      "text-field": "{point_count_abbreviated}",
      "text-font": ["Open Sans Bold"],
      "text-size": 12,
    },
    paint: {
      "text-color": "#ffffff",
    },
  };

  // Individual anomaly points
  const unclusteredPointLayer: CircleLayerSpecification = {
    id: "unclustered-point",
    type: "circle",
    source: "anomalies",
    filter: ["!", ["has", "point_count"]],
    paint: {
      // Renk — kategoriye göre
      "circle-color": ["get", "color"],
      // Boyut — güven skoruna göre (40-100 arası → 6-14px)
      "circle-radius": [
        "interpolate",
        ["linear"],
        ["get", "confidence_score"],
        40,
        6,
        60,
        8,
        80,
        10,
        100,
        14,
      ],
      "circle-opacity": 0.9,
      "circle-stroke-width": 2,
      "circle-stroke-color": "rgba(255,255,255,0.25)",
      // Glow efekti
      "circle-blur": 0.15,
    },
  };

  // Glow halo layer (altında)
  const glowLayer: CircleLayerSpecification = {
    id: "unclustered-glow",
    type: "circle",
    source: "anomalies",
    filter: ["!", ["has", "point_count"]],
    paint: {
      "circle-color": ["get", "color"],
      "circle-radius": [
        "interpolate",
        ["linear"],
        ["get", "confidence_score"],
        40,
        14,
        60,
        18,
        80,
        22,
        100,
        28,
      ],
      "circle-opacity": 0.15,
      "circle-blur": 1,
    },
  };

  // ── Render ──────────────────────────────────────────────────────────

  const categoryLabel =
    hoveredAnomaly?.category
      ? CATEGORY_LABELS[hoveredAnomaly.category as AnomalyCategory] ||
        hoveredAnomaly.category
      : "";

  return (
    <>
      <Source
        id="anomalies"
        type="geojson"
        data={geojson}
        cluster={true}
        clusterMaxZoom={14}
        clusterRadius={50}
      >
        <Layer {...glowLayer} />
        <Layer {...clusterLayer} />
        <Layer {...clusterCountLayer} />
        <Layer {...unclusteredPointLayer} />
      </Source>

      {/* Hover Tooltip */}
      {hoveredAnomaly && (
        <Popup
          longitude={hoveredAnomaly.longitude}
          latitude={hoveredAnomaly.latitude}
          closeButton={false}
          closeOnClick={false}
          anchor="bottom"
          offset={16}
          className="anomaly-tooltip"
        >
          <div className="bg-surface border border-border rounded-xl p-3 shadow-panel min-w-[180px]">
            <div className="flex items-center gap-2 mb-1.5">
              <div
                className="w-2 h-2 rounded-full flex-shrink-0"
                style={{
                  backgroundColor:
                    CATEGORY_HEX[hoveredAnomaly.category] || "#2E6DA4",
                }}
              />
              <span className="text-[10px] font-bold uppercase tracking-wider text-gray-400">
                {categoryLabel}
              </span>
            </div>
            <p className="text-xs font-semibold text-white leading-snug mb-1">
              {hoveredAnomaly.title}
            </p>
            <div className="flex items-center justify-between">
              <span className="text-[10px] text-gray-500">
                {formatCoordsCompact(
                  hoveredAnomaly.latitude,
                  hoveredAnomaly.longitude
                )}
              </span>
              <span className="text-[10px] font-bold text-secondary">
                %{hoveredAnomaly.confidence.toFixed(0)}
              </span>
            </div>
          </div>
        </Popup>
      )}
    </>
  );
}
