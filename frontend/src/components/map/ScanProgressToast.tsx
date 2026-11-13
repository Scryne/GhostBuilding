// ═══════════════════════════════════════════════════════════════════════════
// ScanProgressToast.tsx — Tarama ilerleme bildirimi
// Polling ile task status takibi, progress bar, tamamlanma bildirimi.
// ═══════════════════════════════════════════════════════════════════════════

"use client";

import { useEffect, useRef } from "react";
import { useSWRConfig } from "swr";
import { Radar, CheckCircle2, XCircle, Loader2 } from "lucide-react";
import { useScanStatus } from "@/hooks/useAnomaly";
import { useMapContext } from "./MapState";
import { cn } from "@/lib/utils";
import { toast } from "@/components/ui/Toast";

// ═══════════════════════════════════════════════════════════════════════════
// Component
// ═══════════════════════════════════════════════════════════════════════════

interface ScanProgressToastProps {
  taskId: string;
}

export default function ScanProgressToast({ taskId }: ScanProgressToastProps) {
  const { setActiveScanTaskId, setSelectedAnomalyId } = useMapContext();
  const { mutate } = useSWRConfig();

  const {
    data,
    isRunning,
    isComplete,
    isFailed,
    progress,
  } = useScanStatus(taskId);

  // ── Tamamlanma bildirimi (bir kere göster) ──────────────────────────

  const notifiedRef = useRef(false);

  useEffect(() => {
    if (notifiedRef.current) return;

    if (isComplete && data) {
      notifiedRef.current = true;
      // Harita katmanı, son bulgular ve sayaçlar kendi aralıklarıyla (15–60 sn) yenilenir;
      // yeni bulgu tarama biter bitmez görünsün diye hepsi şimdi yeniden çekilir.
      void mutate(
        (key) =>
          key === "anomaly-stats" || (Array.isArray(key) && key[0] === "anomalies")
      );
      const firstId = data.anomaly_urls?.[0]?.split("/").pop();
      const count = data.anomaly_urls?.length ?? 0;
      if (firstId) {
        // İlk bulgunun kanıt paneli açılır: tarayan kişi sonucu aramak zorunda kalmaz.
        setSelectedAnomalyId(firstId);
        toast.success("Tarama tamamlandı", {
          description:
            count > 1
              ? `${count} bulgu kaydedildi. İlki sağdaki panelde açık.`
              : "Bir bulgu kaydedildi. Kanıtı sağdaki panelde açık.",
        });
      } else {
        toast.success("Tarama tamamlandı", {
          description:
            "Bu konumdaki fark sıradan konumların içinde kaldı; bulgu kaydedilmedi.",
        });
      }
      setTimeout(() => setActiveScanTaskId(null), 1500);
    }

    if (isFailed) {
      notifiedRef.current = true;
      toast.error("Tarama başarısız", {
        description: data?.current_step || "Bilinmeyen hata.",
      });
      setTimeout(() => setActiveScanTaskId(null), 3000);
    }
  }, [isComplete, isFailed, data, setActiveScanTaskId, setSelectedAnomalyId, mutate]);

  // ── Durum ikonu ─────────────────────────────────────────────────────

  const StatusIcon = isComplete
    ? CheckCircle2
    : isFailed
    ? XCircle
    : isRunning
    ? Loader2
    : Radar;

  const statusColor = isComplete
    ? "text-emerald-400"
    : isFailed
    ? "text-red-400"
    : "text-secondary";

  const statusLabel = isComplete
    ? "Tamamlandı"
    : isFailed
    ? "Başarısız"
    : data?.status === "pending"
    ? "Kuyrukta…"
    : "Taranıyor…";

  // ── Progress bar rengi ──────────────────────────────────────────────

  const barColor = isComplete
    ? "bg-emerald-500"
    : isFailed
    ? "bg-red-500"
    : "bg-secondary";

  return (
    <div
      role="status"
      aria-live="polite"
      className="absolute inset-x-3 top-20 z-30 pointer-events-auto animate-slide-in-right sm:inset-x-auto sm:right-4 sm:top-24 sm:w-[300px]"
    >
      <div className="glass-panel-strong p-4 space-y-3">
        {/* Header */}
        <div className="flex items-center gap-2.5">
          <StatusIcon
            className={cn(
              "w-4 h-4 flex-shrink-0",
              statusColor,
              isRunning && "animate-spin"
            )}
          />
          <div className="flex-1 min-w-0">
            <p className="text-xs font-semibold text-white">{statusLabel}</p>
            {data?.current_step && (
              <p className="text-[10px] text-gray-500 truncate mt-0.5">
                {data.current_step}
              </p>
            )}
          </div>

          {/* Kapat butonu */}
          <button
            onClick={() => setActiveScanTaskId(null)}
            className="-m-1 p-2 rounded-md text-gray-500 hover:text-gray-300 hover:bg-white/5 transition-colors"
            aria-label="Tarama bildirimini kapat"
            title="Kapat"
          >
            <svg
              className="w-3 h-3"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M6 18L18 6M6 6l12 12"
              />
            </svg>
          </button>
        </div>

        {/* Progress Bar */}
        <div className="space-y-1.5">
          <div className="w-full h-1.5 rounded-full bg-white/[0.06] overflow-hidden">
            <div
              className={cn(
                "h-full rounded-full transition-all duration-500 ease-out",
                barColor,
                isRunning && "relative overflow-hidden"
              )}
              style={{
                width: `${Math.min(100, Math.max(isComplete ? 100 : isFailed ? 100 : progress, 2))}%`,
              }}
            >
              {/* Shimmer efekti — çalışırken */}
              {isRunning && (
                <div
                  className="absolute inset-0 bg-gradient-to-r from-transparent via-white/20 to-transparent animate-shimmer"
                  style={{ backgroundSize: "200% 100%" }}
                />
              )}
            </div>
          </div>

          {/* Progress Detayları */}
          <div className="flex items-center justify-between">
            <span className="text-[9px] font-mono text-gray-600 tabular-nums">
              {isComplete
                ? `${data?.anomaly_urls?.length ?? 0} bulgu kaydedildi`
                : isFailed
                ? "Hata oluştu"
                : `%${progress}`}
            </span>
            <span className="text-[9px] font-mono text-gray-600 tabular-nums">
              {taskId.slice(0, 8)}…
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
