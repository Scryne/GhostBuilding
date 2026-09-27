// ═══════════════════════════════════════════════════════════════════════════
// AnomalyDetailPanel.tsx — Harita üstünde sağ kenar paneli
// İçerik EvidenceView ile /explore/[id] sayfasıyla aynıdır.
// ═══════════════════════════════════════════════════════════════════════════

"use client";

import Link from "next/link";
import { ArrowUpRight, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { useAnomalyDetail } from "@/hooks/useAnomaly";
import EvidenceView from "./EvidenceView";

interface AnomalyDetailPanelProps {
  anomalyId: string | null;
  onClose?: () => void;
  className?: string;
}

export default function AnomalyDetailPanel({ anomalyId, onClose, className }: AnomalyDetailPanelProps) {
  const { data: detail, error, isLoading, mutate } = useAnomalyDetail(anomalyId);

  if (!anomalyId) return null;

  return (
    <aside
      className={cn(
        "map-overlay map-overlay-right glass-panel-strong flex flex-col overflow-hidden animate-slide-in-right",
        className
      )}
      id="anomaly-detail-panel"
      aria-label="Anomali ayrıntısı"
    >
      <div className="flex items-center justify-between gap-2 border-b border-white/[0.06] px-4 py-2.5">
        <Link
          href={`/explore/${anomalyId}`}
          className="inline-flex items-center gap-1 text-xs font-medium text-secondary hover:text-secondary-300"
        >
          Tam sayfada aç <ArrowUpRight className="size-3.5" aria-hidden />
        </Link>
        <button
          type="button"
          onClick={onClose}
          className="flex size-8 items-center justify-center rounded-lg text-muted hover:bg-white/[0.06] hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-secondary"
          aria-label="Paneli kapat"
        >
          <X className="size-4" aria-hidden />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto thin-scrollbar p-4">
        {isLoading && (
          <div className="flex h-40 items-center justify-center" role="status">
            <div className="size-8 animate-spin rounded-full border-2 border-secondary/30 border-t-secondary" />
            <span className="sr-only">Anomali yükleniyor</span>
          </div>
        )}
        {error && !isLoading && (
          <p className="text-sm text-red-400" role="alert">
            Anomali yüklenemedi. Bağlantınızı kontrol edip paneli yeniden açın.
          </p>
        )}
        {detail && !isLoading && <EvidenceView detail={detail} variant="panel" onUpdated={() => mutate()} />}
      </div>
    </aside>
  );
}
