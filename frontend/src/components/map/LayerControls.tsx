// ═══════════════════════════════════════════════════════════════════════════
// LayerControls.tsx — Katman toggle paneli
// Kategori filtresi, güven skoru slider'ı, "Yakınımdakiler" toggle.
// ═══════════════════════════════════════════════════════════════════════════

"use client";

import { useCallback, useState } from "react";
import {
  Ghost,
  Lock,
  Ban,
  Search,
  SlidersHorizontal,
  MapPin,
} from "lucide-react";
import { useMapContext } from "./GhostMap";
import { AnomalyCategory } from "@/lib/types";
import { CATEGORY_LABELS, cn } from "@/lib/utils";

// ── Kategori Ayarları ─────────────────────────────────────────────────────

const CATEGORY_CONFIG = [
  {
    key: AnomalyCategory.GHOST_BUILDING,
    label: CATEGORY_LABELS[AnomalyCategory.GHOST_BUILDING],
    icon: Ghost,
    color: "text-ghost",
    bgActive: "bg-ghost/15 border-ghost/30",
    dot: "bg-ghost",
  },
  {
    key: AnomalyCategory.HIDDEN_STRUCTURE,
    label: CATEGORY_LABELS[AnomalyCategory.HIDDEN_STRUCTURE],
    icon: Lock,
    color: "text-accent",
    bgActive: "bg-accent/15 border-accent/30",
    dot: "bg-accent",
  },
  {
    key: AnomalyCategory.CENSORED_AREA,
    label: CATEGORY_LABELS[AnomalyCategory.CENSORED_AREA],
    icon: Ban,
    color: "text-censored",
    bgActive: "bg-censored/15 border-censored/30",
    dot: "bg-censored",
  },
  {
    key: AnomalyCategory.IMAGE_DISCREPANCY,
    label: CATEGORY_LABELS[AnomalyCategory.IMAGE_DISCREPANCY],
    icon: Search,
    color: "text-discrepancy",
    bgActive: "bg-discrepancy/15 border-discrepancy/30",
    dot: "bg-discrepancy",
  },
] as const;

// ═══════════════════════════════════════════════════════════════════════════
// Component
// ═══════════════════════════════════════════════════════════════════════════

export default function LayerControls() {
  const {
    activeCategories,
    toggleCategory,
    minConfidence,
    setMinConfidence,
    showNearby,
    setShowNearby,
    flyTo,
  } = useMapContext();

  const [isExpanded, setIsExpanded] = useState(true);

  // ── Konumuma Git (Yakınımdakiler) ──────────────────────────────────

  const handleNearbyToggle = useCallback(() => {
    if (!showNearby) {
      // Geolocation API ile konum al
      if ("geolocation" in navigator) {
        navigator.geolocation.getCurrentPosition(
          (pos) => {
            flyTo(pos.coords.latitude, pos.coords.longitude, 12);
            setShowNearby(true);
          },
          () => {
            // Hata — sessizce geç
            setShowNearby(false);
          },
          { enableHighAccuracy: true, timeout: 10_000 }
        );
      }
    } else {
      setShowNearby(false);
    }
  }, [showNearby, setShowNearby, flyTo]);

  return (
    <div className="absolute left-4 top-20 z-20 pointer-events-auto w-[240px]">
      {/* Header — toggle */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className={cn(
          "w-full flex items-center justify-between px-4 py-2.5",
          "glass-panel-strong rounded-xl",
          "hover:bg-white/[0.03] transition-colors",
          !isExpanded && "rounded-xl",
          isExpanded && "rounded-b-none border-b-0"
        )}
      >
        <div className="flex items-center gap-2">
          <SlidersHorizontal className="w-3.5 h-3.5 text-secondary" />
          <span className="text-[11px] font-bold tracking-widest uppercase text-gray-400">
            Filtreler
          </span>
        </div>
        <svg
          className={cn(
            "w-3.5 h-3.5 text-gray-500 transition-transform duration-200",
            isExpanded && "rotate-180"
          )}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M19 9l-7 7-7-7"
          />
        </svg>
      </button>

      {/* Panel Body */}
      {isExpanded && (
        <div className="glass-panel-strong rounded-t-none rounded-b-xl border-t-0 p-3 animate-slide-down space-y-4">
          {/* ── Kategori Toggleları ─────────────────────────────────── */}
          <div>
            <p className="text-[9px] font-bold uppercase tracking-widest text-gray-600 mb-2">
              Kategoriler
            </p>
            <div className="space-y-1.5">
              {CATEGORY_CONFIG.map((cat) => {
                const isActive = activeCategories.has(cat.key);
                const Icon = cat.icon;
                return (
                  <button
                    key={cat.key}
                    onClick={() => toggleCategory(cat.key)}
                    className={cn(
                      "w-full flex items-center gap-2.5 px-3 py-2 rounded-lg",
                      "border transition-all duration-200 text-left",
                      isActive
                        ? cat.bgActive
                        : "bg-transparent border-transparent hover:bg-white/[0.03]"
                    )}
                  >
                    <div
                      className={cn(
                        "w-3.5 h-3.5 rounded flex items-center justify-center transition-colors",
                        isActive
                          ? `${cat.dot} border-0`
                          : "border border-gray-600"
                      )}
                    >
                      {isActive && (
                        <svg
                          className="w-2.5 h-2.5 text-white"
                          fill="none"
                          viewBox="0 0 24 24"
                          stroke="currentColor"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={3}
                            d="M5 13l4 4L19 7"
                          />
                        </svg>
                      )}
                    </div>
                    <Icon
                      className={cn(
                        "w-3.5 h-3.5 transition-colors",
                        isActive ? cat.color : "text-gray-600"
                      )}
                    />
                    <span
                      className={cn(
                        "text-xs font-medium transition-colors",
                        isActive ? "text-gray-200" : "text-gray-500"
                      )}
                    >
                      {cat.label}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>

          {/* ── Güven Skoru Slider ──────────────────────────────────── */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <p className="text-[9px] font-bold uppercase tracking-widest text-gray-600">
                Min. Güven Skoru
              </p>
              <span className="text-[11px] font-bold text-secondary tabular-nums">
                %{minConfidence}
              </span>
            </div>
            <input
              type="range"
              min={0}
              max={100}
              step={5}
              value={minConfidence}
              onChange={(e) => setMinConfidence(Number(e.target.value))}
              className="w-full h-1 appearance-none rounded-full bg-white/10 cursor-pointer
                [&::-webkit-slider-thumb]:appearance-none
                [&::-webkit-slider-thumb]:w-3.5
                [&::-webkit-slider-thumb]:h-3.5
                [&::-webkit-slider-thumb]:rounded-full
                [&::-webkit-slider-thumb]:bg-secondary
                [&::-webkit-slider-thumb]:border-2
                [&::-webkit-slider-thumb]:border-white/20
                [&::-webkit-slider-thumb]:shadow-glow-sm
                [&::-webkit-slider-thumb]:cursor-pointer
                [&::-webkit-slider-thumb]:transition-transform
                [&::-webkit-slider-thumb]:hover:scale-110
                [&::-moz-range-thumb]:w-3.5
                [&::-moz-range-thumb]:h-3.5
                [&::-moz-range-thumb]:rounded-full
                [&::-moz-range-thumb]:bg-secondary
                [&::-moz-range-thumb]:border-2
                [&::-moz-range-thumb]:border-white/20
                [&::-moz-range-thumb]:cursor-pointer"
            />
            <div className="flex justify-between mt-1">
              <span className="text-[9px] text-gray-600">0</span>
              <span className="text-[9px] text-gray-600">100</span>
            </div>
          </div>

          {/* ── Yakınımdakiler Toggle ──────────────────────────────── */}
          <button
            onClick={handleNearbyToggle}
            className={cn(
              "w-full flex items-center gap-2.5 px-3 py-2.5 rounded-lg",
              "border transition-all duration-200",
              showNearby
                ? "bg-secondary/15 border-secondary/30"
                : "bg-transparent border-white/[0.06] hover:bg-white/[0.03]"
            )}
          >
            <MapPin
              className={cn(
                "w-3.5 h-3.5 transition-colors",
                showNearby ? "text-secondary" : "text-gray-500"
              )}
            />
            <span
              className={cn(
                "text-xs font-medium transition-colors",
                showNearby ? "text-gray-200" : "text-gray-500"
              )}
            >
              Yakınımdakiler
            </span>
            {showNearby && (
              <div className="ml-auto w-1.5 h-1.5 rounded-full bg-secondary animate-pulse" />
            )}
          </button>
        </div>
      )}
    </div>
  );
}
