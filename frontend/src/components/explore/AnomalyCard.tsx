// ═══════════════════════════════════════════════════════════════════════════
// AnomalyCard.tsx — Anomali liste kartı
// Thumbnail, başlık, koordinat, kategori badge, güven skoru, doğrulama.
// ═══════════════════════════════════════════════════════════════════════════

"use client";

import { cn } from "@/lib/utils";
import {
  CATEGORY_LABELS,
  CATEGORY_ICONS,
  CATEGORY_COLORS,
  STATUS_COLORS,
  formatCoordsCompact,
  formatRelativeTime,
  getConfidenceColor,
} from "@/lib/utils";
import type { AnomalyListItem } from "@/lib/types";
import { MapPin, CheckCircle2, Clock } from "lucide-react";
import Image from "next/image";

// ═══════════════════════════════════════════════════════════════════════════

interface AnomalyCardProps {
  anomaly: AnomalyListItem;
  onClick?: () => void;
  className?: string;
}

export default function AnomalyCard({
  anomaly,
  onClick,
  className,
}: AnomalyCardProps) {
  const colors = CATEGORY_COLORS[anomaly.category];
  const statusConfig = STATUS_COLORS[anomaly.status];

  return (
    <button
      onClick={onClick}
      className={cn(
        "w-full text-left group relative overflow-hidden",
        "rounded-2xl border border-white/[0.04]",
        "bg-surface/60 backdrop-blur-sm",
        "hover:border-white/[0.1] hover:bg-surface/80",
        "hover:shadow-panel hover:-translate-y-0.5",
        "active:scale-[0.99]",
        "transition-all duration-300 cursor-pointer",
        className
      )}
      id={`anomaly-card-${anomaly.id}`}
    >
      {/* ── Glow efekti ──────────────────────────────────────────── */}
      <div
        className="absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity duration-500 pointer-events-none"
        style={{
          background: `radial-gradient(ellipse at 50% 0%, ${colors?.hex || "#2E6DA4"}08 0%, transparent 70%)`,
        }}
      />

      {/* ── Thumbnail ────────────────────────────────────────────── */}
      <div className="relative h-32 overflow-hidden rounded-t-2xl bg-surface-50">
        {anomaly.thumbnail_url ? (
          <Image
            src={anomaly.thumbnail_url}
            alt={anomaly.title || "Anomali"}
            fill
            sizes="(max-width: 768px) 100vw, (max-width: 1200px) 50vw, 33vw"
            className="object-cover group-hover:scale-105 transition-transform duration-500"
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center bg-gradient-to-br from-surface via-surface-50 to-surface">
            <span className="text-3xl opacity-20">
              {CATEGORY_ICONS[anomaly.category]}
            </span>
          </div>
        )}

        {/* Üst sağ: güven skoru */}
        <div className="absolute top-2 right-2">
          <div
            className={cn(
              "px-2 py-0.5 rounded-lg text-[11px] font-bold tabular-nums",
              "backdrop-blur-md bg-black/50 border border-white/10"
            )}
          >
            <span className={getConfidenceColor(anomaly.confidence_score)}>
              {anomaly.confidence_score.toFixed(0)}%
            </span>
          </div>
        </div>

        {/* Üst sol: kategori badge */}
        <div className="absolute top-2 left-2">
          <span
            className={cn(
              "inline-flex items-center gap-1 px-2 py-0.5 rounded-lg text-[9px] font-bold uppercase tracking-wider",
              "backdrop-blur-md bg-black/50 border border-white/10"
            )}
            style={{ color: colors?.hex || "#2E6DA4" }}
          >
            {CATEGORY_ICONS[anomaly.category]}{" "}
            {CATEGORY_LABELS[anomaly.category]}
          </span>
        </div>

        {/* Alt gradient overlay */}
        <div className="absolute bottom-0 left-0 right-0 h-12 bg-gradient-to-t from-surface/90 to-transparent" />
      </div>

      {/* ── İçerik ───────────────────────────────────────────────── */}
      <div className="relative p-3.5 space-y-2">
        {/* Başlık */}
        <h3 className="text-sm font-bold text-gray-200 leading-snug group-hover:text-white transition-colors line-clamp-2">
          {anomaly.title || "İsimsiz Anomali"}
        </h3>

        {/* Koordinat */}
        <div className="flex items-center gap-1.5 text-[10px] text-gray-500">
          <MapPin className="w-3 h-3 flex-shrink-0" />
          <span className="font-mono">
            {formatCoordsCompact(anomaly.lat, anomaly.lng)}
          </span>
        </div>

        {/* Alt bar: durum + tarih */}
        <div className="flex items-center justify-between pt-1 border-t border-white/[0.03]">
          {/* Durum */}
          <span
            className={cn(
              "inline-flex items-center gap-1 text-[9px] font-bold uppercase tracking-wider",
              statusConfig?.text || "text-gray-500"
            )}
          >
            <CheckCircle2 className="w-3 h-3" />
            {statusConfig?.label || anomaly.status}
          </span>

          {/* Tarih */}
          {anomaly.detected_at && (
            <span className="flex items-center gap-1 text-[9px] text-gray-600">
              <Clock className="w-3 h-3" />
              {formatRelativeTime(anomaly.detected_at)}
            </span>
          )}
        </div>
      </div>
    </button>
  );
}
