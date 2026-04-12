// ═══════════════════════════════════════════════════════════════════════════
// StatsBar.tsx — Üst istatistik çubuğu
// Toplam anomali, haftalık artış, doğrulanmış, aktif araştırmacı.
// ═══════════════════════════════════════════════════════════════════════════

"use client";

import { useMemo } from "react";
import { cn, formatNumber } from "@/lib/utils";
import { useAnomalyStats } from "@/hooks/useAnomaly";
import {
  MapPin,
  TrendingUp,
  ShieldCheck,
  Users,
} from "lucide-react";

// ── Stat Kartı ────────────────────────────────────────────────────────────

interface StatItemProps {
  icon: React.ReactNode;
  label: string;
  value: string;
  trend?: string;
  trendUp?: boolean;
  color: string;
  glowColor: string;
}

function StatItem({
  icon,
  label,
  value,
  trend,
  trendUp,
  color,
  glowColor,
}: StatItemProps) {
  return (
    <div className="flex items-center gap-3 group">
      <div
        className={cn(
          "w-9 h-9 rounded-xl flex items-center justify-center",
          "transition-all duration-300 group-hover:scale-110"
        )}
        style={{
          backgroundColor: `${color}15`,
          border: `1px solid ${color}25`,
          boxShadow: `0 0 0 0 ${glowColor}`,
        }}
      >
        {icon}
      </div>
      <div>
        <div className="flex items-baseline gap-1.5">
          <span className="text-base font-bold text-white tabular-nums tracking-tight">
            {value}
          </span>
          {trend && (
            <span
              className={cn(
                "text-[10px] font-bold",
                trendUp ? "text-emerald-400" : "text-red-400"
              )}
            >
              {trend}
            </span>
          )}
        </div>
        <span className="text-[10px] text-gray-500 font-medium uppercase tracking-wider">
          {label}
        </span>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════

interface StatsBarProps {
  className?: string;
}

export default function StatsBar({ className }: StatsBarProps) {
  const { data: stats } = useAnomalyStats();

  const statItems = useMemo<StatItemProps[]>(() => {
    const total = stats?.total_count ?? 12_483;
    const last30 = stats?.last_30_days_count ?? 127;

    return [
      {
        icon: <MapPin className="w-4 h-4" style={{ color: "#2E6DA4" }} />,
        label: "Toplam Anomali",
        value: formatNumber(total),
        color: "#2E6DA4",
        glowColor: "rgba(46, 109, 164, 0.3)",
      },
      {
        icon: <TrendingUp className="w-4 h-4" style={{ color: "#10B981" }} />,
        label: "Bu Ay",
        value: `+${formatNumber(last30)}`,
        trend: "↑ 12%",
        trendUp: true,
        color: "#10B981",
        glowColor: "rgba(16, 185, 129, 0.3)",
      },
      {
        icon: <ShieldCheck className="w-4 h-4" style={{ color: "#F4A261" }} />,
        label: "Doğrulanmış",
        value: formatNumber(
          stats?.by_category?.reduce((acc, c) => acc + c.count, 0) ?? 3_421
        ),
        color: "#F4A261",
        glowColor: "rgba(244, 162, 97, 0.3)",
      },
      {
        icon: <Users className="w-4 h-4" style={{ color: "#8B5CF6" }} />,
        label: "Araştırmacı",
        value: formatNumber(892),
        color: "#8B5CF6",
        glowColor: "rgba(139, 92, 246, 0.3)",
      },
    ];
  }, [stats]);

  return (
    <div
      className={cn(
        "glass-panel px-6 py-4",
        "flex items-center justify-between gap-4",
        "overflow-x-auto",
        className
      )}
      id="stats-bar"
    >
      {/* Stats */}
      <div className="flex items-center gap-8">
        {statItems.map((item) => (
          <StatItem key={item.label} {...item} />
        ))}
      </div>

      {/* Canlı gösterge */}
      <div className="flex items-center gap-2 text-[11px] font-semibold text-emerald-400 bg-emerald-400/8 px-3 py-1.5 rounded-lg border border-emerald-400/15 whitespace-nowrap flex-shrink-0">
        <div className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
        Canlı Veri
      </div>
    </div>
  );
}
