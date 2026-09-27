// ═══════════════════════════════════════════════════════════════════════════
// AnomalyCard.tsx — Keşfet listesindeki bulgu kartı
// Kanıt karosu, konum, kategori, anomali puanı (50 çizgisiyle) ve durum.
// ═══════════════════════════════════════════════════════════════════════════

"use client";

import Image from "next/image";
import Link from "next/link";
import { resolveMediaUrl } from "@/lib/api";
import {
  CATEGORY_COLORS,
  CATEGORY_LABELS,
  STATUS_COLORS,
  cn,
  formatCoordsCompact,
  formatRelativeTime,
  formatScore,
} from "@/lib/utils";
import type { AnomalyListItem } from "@/lib/types";
import { ScoreScale } from "@/components/anomaly/EvidenceView";

interface AnomalyCardProps {
  anomaly: AnomalyListItem;
  onClick?: () => void;
  className?: string;
}

export default function AnomalyCard({ anomaly, onClick, className }: AnomalyCardProps) {
  const colors = CATEGORY_COLORS[anomaly.category];
  const status = STATUS_COLORS[anomaly.status];
  const thumb = resolveMediaUrl(anomaly.thumbnail_url);
  const heading = anomaly.location_label ?? formatCoordsCompact(anomaly.lat, anomaly.lng);

  return (
    <Link
      href={`/explore/${anomaly.id}`}
      onClick={onClick}
      className={cn(
        "group block overflow-hidden rounded-2xl border border-border bg-surface/70",
        "transition-colors hover:border-white/15 hover:bg-card focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-secondary",
        className
      )}
      id={`anomaly-card-${anomaly.id}`}
    >
      <div className="relative h-40 overflow-hidden bg-black">
        {thumb ? (
          <Image
            src={thumb}
            alt={`${heading} için kanıt karosu`}
            fill
            unoptimized
            sizes="(max-width: 768px) 100vw, 50vw"
            className="object-cover [image-rendering:pixelated] opacity-90 transition-opacity group-hover:opacity-100"
          />
        ) : (
          <div className="flex h-full items-center justify-center text-xs text-muted">Görüntü yok</div>
        )}
        <span
          className="absolute left-2 top-2 inline-flex items-center gap-1.5 rounded-md bg-black/75 px-2 py-0.5 text-[11px] font-semibold"
          style={{ color: colors.hex }}
        >
          <span className={cn("size-1.5 rounded-full", colors.dot)} aria-hidden />
          {CATEGORY_LABELS[anomaly.category]}
        </span>
      </div>

      <div className="space-y-2.5 p-3.5">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h2 className="truncate text-sm font-semibold text-foreground">{heading}</h2>
            {anomaly.title && <p className="mt-0.5 truncate text-xs text-muted">{anomaly.title}</p>}
          </div>
          <span className="shrink-0 font-mono text-base font-bold tabular-nums text-foreground">
            {formatScore(anomaly.confidence_score)}
          </span>
        </div>
        <ScoreScale score={anomaly.confidence_score} hex={colors.hex} className="h-1.5" />
        <div className="flex items-center justify-between text-[11px]">
          <span className={cn("font-medium", status.text)}>{status.label}</span>
          <span className="text-muted">{formatRelativeTime(anomaly.detected_at)}</span>
        </div>
      </div>
    </Link>
  );
}
