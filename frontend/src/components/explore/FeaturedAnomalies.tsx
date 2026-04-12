// ═══════════════════════════════════════════════════════════════════════════
// FeaturedAnomalies.tsx — Editoryal seçimler
// "Haftanın Keşfi" ve dikkat çekici anomaliler.
// ═══════════════════════════════════════════════════════════════════════════

"use client";

import { useMemo } from "react";
import { cn } from "@/lib/utils";
import {
  CATEGORY_LABELS,
  CATEGORY_ICONS,
  CATEGORY_COLORS,
  formatCoordsCompact,
} from "@/lib/utils";
import { useAnomalyStats } from "@/hooks/useAnomaly";
import type { TopAnomaly } from "@/lib/types";
import { Star, ChevronRight, Sparkles } from "lucide-react";

// ═══════════════════════════════════════════════════════════════════════════

interface FeaturedAnomaliesProps {
  onAnomalyClick?: (id: string, lat: number, lng: number) => void;
  className?: string;
}

export default function FeaturedAnomalies({
  onAnomalyClick,
  className,
}: FeaturedAnomaliesProps) {
  const { data: stats } = useAnomalyStats();

  const featured = useMemo(() => {
    if (!stats?.top_10?.length) return [];
    return stats.top_10.slice(0, 5);
  }, [stats]);

  const weeklyPick = featured[0] || null;
  const otherFeatured = featured.slice(1);

  if (!featured.length) {
    return null;
  }

  return (
    <div className={cn("space-y-4", className)}>
      {/* ── Haftanın Keşfi ──────────────────────────────────────────── */}
      {weeklyPick && (
        <div className="space-y-2">
          <div className="flex items-center gap-2 px-1">
            <Sparkles className="w-3.5 h-3.5 text-ghost" />
            <h3 className="text-[10px] font-bold uppercase tracking-widest text-ghost">
              Haftanın Keşfi
            </h3>
          </div>

          <button
            onClick={() =>
              onAnomalyClick?.(weeklyPick.id, weeklyPick.lat, weeklyPick.lng)
            }
            className={cn(
              "w-full text-left group relative overflow-hidden",
              "rounded-xl border border-ghost/15",
              "bg-gradient-to-br from-ghost/[0.06] via-transparent to-secondary/[0.04]",
              "hover:border-ghost/30 hover:shadow-glow-ghost",
              "transition-all duration-300 cursor-pointer"
            )}
            id="featured-weekly-pick"
          >
            {/* Glow arka plan */}
            <div className="absolute inset-0 bg-gradient-to-br from-ghost/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500" />

            <div className="relative p-4 space-y-2.5">
              {/* Kategori + Skor */}
              <div className="flex items-center justify-between">
                <span
                  className={cn(
                    "inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[9px] font-bold uppercase tracking-wider border",
                    CATEGORY_COLORS[weeklyPick.category]?.bg,
                    CATEGORY_COLORS[weeklyPick.category]?.text,
                    CATEGORY_COLORS[weeklyPick.category]?.border
                  )}
                >
                  {CATEGORY_ICONS[weeklyPick.category]}{" "}
                  {CATEGORY_LABELS[weeklyPick.category]}
                </span>
                <div className="flex items-center gap-1.5">
                  <Star className="w-3 h-3 text-ghost fill-ghost/40" />
                  <span className="text-xs font-bold text-ghost tabular-nums">
                    {weeklyPick.confidence_score.toFixed(0)}%
                  </span>
                </div>
              </div>

              {/* Başlık */}
              <h4 className="text-sm font-bold text-white leading-snug group-hover:text-ghost transition-colors">
                {weeklyPick.title || "İsimsiz Anomali"}
              </h4>

              {/* Koordinat + Ok */}
              <div className="flex items-center justify-between">
                <span className="text-[10px] text-gray-500 font-mono">
                  📍 {formatCoordsCompact(weeklyPick.lat, weeklyPick.lng)}
                </span>
                <div className="flex items-center gap-1 text-[10px] text-ghost/60 group-hover:text-ghost transition-colors">
                  <span>Keşfet</span>
                  <ChevronRight className="w-3 h-3 group-hover:translate-x-0.5 transition-transform" />
                </div>
              </div>
            </div>
          </button>
        </div>
      )}

      {/* ── Diğer Öne Çıkanlar ──────────────────────────────────────── */}
      {otherFeatured.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-[10px] font-bold uppercase tracking-widest text-gray-500 px-1">
            Öne Çıkanlar
          </h3>
          <div className="space-y-1.5">
            {otherFeatured.map((anomaly) => (
              <FeaturedCard
                key={anomaly.id}
                anomaly={anomaly}
                onClick={() =>
                  onAnomalyClick?.(anomaly.id, anomaly.lat, anomaly.lng)
                }
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Küçük öne çıkan kartı ────────────────────────────────────────────────

function FeaturedCard({
  anomaly,
  onClick,
}: {
  anomaly: TopAnomaly;
  onClick?: () => void;
}) {
  const colors = CATEGORY_COLORS[anomaly.category];

  return (
    <button
      onClick={onClick}
      className={cn(
        "w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-left",
        "bg-white/[0.015] border border-white/[0.04]",
        "hover:bg-white/[0.04] hover:border-white/[0.08]",
        "transition-all duration-200 group cursor-pointer"
      )}
    >
      {/* Renk göstergesi */}
      <div
        className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 text-sm"
        style={{
          backgroundColor: `${colors?.hex || "#2E6DA4"}12`,
          border: `1px solid ${colors?.hex || "#2E6DA4"}25`,
        }}
      >
        {CATEGORY_ICONS[anomaly.category]}
      </div>

      {/* İçerik */}
      <div className="flex-1 min-w-0">
        <p className="text-[11px] font-semibold text-gray-200 truncate group-hover:text-white transition-colors">
          {anomaly.title || "İsimsiz Anomali"}
        </p>
        <p className="text-[9px] text-gray-500 font-mono">
          {formatCoordsCompact(anomaly.lat, anomaly.lng)}
        </p>
      </div>

      {/* Skor */}
      <span
        className="text-[10px] font-bold tabular-nums flex-shrink-0"
        style={{ color: colors?.hex || "#2E6DA4" }}
      >
        {anomaly.confidence_score.toFixed(0)}%
      </span>
    </button>
  );
}
