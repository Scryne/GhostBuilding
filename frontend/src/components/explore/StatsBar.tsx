// ═══════════════════════════════════════════════════════════════════════════
// StatsBar.tsx — Keşfet üst istatistikleri
// Yalnız API'nin döndürdüğü sayılar. Veri gelmezse "—" (eskiden 12.483 anomali,
// "↑ %12" ve 892 araştırmacı gibi sabit sayılar gösteriliyordu).
// ═══════════════════════════════════════════════════════════════════════════

"use client";

import { cn } from "@/lib/utils";
import { useAnomalyStats } from "@/hooks/useAnomaly";
import { AnomalyStatus } from "@/lib/types";

interface StatsBarProps {
  className?: string;
}

export default function StatsBar({ className }: StatsBarProps) {
  const { data: stats, error } = useAnomalyStats();
  const byStatus = new Map((stats?.by_status ?? []).map((s) => [s.status, s.count]));
  const pending =
    (byStatus.get(AnomalyStatus.PENDING) ?? 0) + (byStatus.get(AnomalyStatus.UNDER_REVIEW) ?? 0);

  const items = [
    { label: "Bulgu", value: stats?.total_count },
    { label: "Son 30 gün", value: stats?.last_30_days_count },
    { label: "İnceleme bekliyor", value: stats ? pending : undefined },
    { label: "Toplulukça doğrulandı", value: stats ? (byStatus.get(AnomalyStatus.VERIFIED) ?? 0) : undefined },
  ];

  return (
    <section
      className={cn("rounded-2xl border border-border bg-surface/70 px-5 py-4", className)}
      aria-label="Bulgu istatistikleri"
      id="stats-bar"
    >
      <dl className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        {items.map((item) => (
          <div key={item.label}>
            <dt className="text-[11px] font-medium uppercase tracking-wider text-muted">{item.label}</dt>
            <dd className="mt-0.5 font-mono text-xl font-bold tabular-nums text-foreground">
              {item.value?.toLocaleString("tr-TR") ?? "—"}
            </dd>
          </div>
        ))}
      </dl>
      {error && (
        <p className="mt-2 text-xs text-red-400" role="alert">
          İstatistikler alınamadı; sayılar bağlantı gelince görünecek.
        </p>
      )}
    </section>
  );
}
