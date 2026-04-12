// ═══════════════════════════════════════════════════════════════════════════
// FilterPanel.tsx — Sol filtre paneli
// Kategori checkbox, güven range slider, durum, tarih aralığı, bölge.
// ═══════════════════════════════════════════════════════════════════════════

"use client";

import { useCallback, useState } from "react";
import { cn } from "@/lib/utils";
import { CATEGORY_LABELS, CATEGORY_ICONS, CATEGORY_COLORS } from "@/lib/utils";
import { AnomalyCategory, AnomalyStatus } from "@/lib/types";
import {
  Filter,
  ChevronDown,
  RotateCcw,
} from "lucide-react";

// ── Filtre State Tipi ─────────────────────────────────────────────────────

export interface ExploreFilters {
  categories: Set<AnomalyCategory>;
  minConfidence: number;
  maxConfidence: number;
  statuses: Set<AnomalyStatus>;
  dateFrom: string;
  dateTo: string;
  region: string;
}

export const DEFAULT_FILTERS: ExploreFilters = {
  categories: new Set([
    AnomalyCategory.GHOST_BUILDING,
    AnomalyCategory.HIDDEN_STRUCTURE,
    AnomalyCategory.CENSORED_AREA,
    AnomalyCategory.IMAGE_DISCREPANCY,
  ]),
  minConfidence: 0,
  maxConfidence: 100,
  statuses: new Set([
    AnomalyStatus.PENDING,
    AnomalyStatus.VERIFIED,
    AnomalyStatus.UNDER_REVIEW,
  ]),
  dateFrom: "",
  dateTo: "",
  region: "",
};

// ── Durum Yapılandırması ──────────────────────────────────────────────────

const STATUS_CONFIG: Array<{
  value: AnomalyStatus;
  label: string;
  color: string;
  dotColor: string;
}> = [
  {
    value: AnomalyStatus.PENDING,
    label: "Beklemede",
    color: "text-yellow-400",
    dotColor: "bg-yellow-500",
  },
  {
    value: AnomalyStatus.VERIFIED,
    label: "Doğrulanmış",
    color: "text-emerald-400",
    dotColor: "bg-emerald-500",
  },
  {
    value: AnomalyStatus.REJECTED,
    label: "Reddedilmiş",
    color: "text-red-400",
    dotColor: "bg-red-500",
  },
  {
    value: AnomalyStatus.UNDER_REVIEW,
    label: "İnceleniyor",
    color: "text-blue-400",
    dotColor: "bg-blue-500",
  },
];

// ── Bölge Seçenekleri (GeoNames bazlı) ────────────────────────────────────

const REGION_OPTIONS = [
  { value: "", label: "Tümü" },
  { value: "TR", label: "🇹🇷 Türkiye" },
  { value: "RU", label: "🇷🇺 Rusya" },
  { value: "CN", label: "🇨🇳 Çin" },
  { value: "IR", label: "🇮🇷 İran" },
  { value: "KP", label: "🇰🇵 Kuzey Kore" },
  { value: "SA", label: "🇸🇦 Suudi Arabistan" },
  { value: "IL", label: "🇮🇱 İsrail" },
  { value: "EG", label: "🇪🇬 Mısır" },
  { value: "US", label: "🇺🇸 ABD" },
  { value: "IN", label: "🇮🇳 Hindistan" },
  { value: "OTHER", label: "🌍 Diğer" },
];

// ═══════════════════════════════════════════════════════════════════════════

interface FilterPanelProps {
  filters: ExploreFilters;
  onFiltersChange: (filters: ExploreFilters) => void;
  className?: string;
}

export default function FilterPanel({
  filters,
  onFiltersChange,
  className,
}: FilterPanelProps) {
  const [expandedSections, setExpandedSections] = useState<Set<string>>(
    new Set(["category", "confidence", "status"])
  );

  // ── Bölüm aç/kapat ───────────────────────────────────────────────

  const toggleSection = useCallback((section: string) => {
    setExpandedSections((prev) => {
      const next = new Set(prev);
      if (next.has(section)) next.delete(section);
      else next.add(section);
      return next;
    });
  }, []);

  // ── Filtre güncelleyiciler ────────────────────────────────────────

  const toggleCategory = useCallback(
    (cat: AnomalyCategory) => {
      const next = new Set(filters.categories);
      if (next.has(cat)) next.delete(cat);
      else next.add(cat);
      onFiltersChange({ ...filters, categories: next });
    },
    [filters, onFiltersChange]
  );

  const toggleStatus = useCallback(
    (status: AnomalyStatus) => {
      const next = new Set(filters.statuses);
      if (next.has(status)) next.delete(status);
      else next.add(status);
      onFiltersChange({ ...filters, statuses: next });
    },
    [filters, onFiltersChange]
  );

  const resetFilters = useCallback(() => {
    onFiltersChange({ ...DEFAULT_FILTERS });
  }, [onFiltersChange]);

  const hasActiveFilters =
    filters.categories.size < 4 ||
    filters.minConfidence > 0 ||
    filters.maxConfidence < 100 ||
    filters.statuses.size < 3 ||
    filters.dateFrom ||
    filters.dateTo ||
    filters.region;

  // ── Render ─────────────────────────────────────────────────────────

  return (
    <div
      className={cn(
        "glass-panel flex flex-col overflow-hidden",
        className
      )}
      id="filter-panel"
    >
      {/* Header */}
      <div className="p-4 pb-3 border-b border-white/[0.03] flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Filter className="w-4 h-4 text-secondary" />
          <h2 className="text-xs font-bold text-gray-300 uppercase tracking-wider">
            Filtreler
          </h2>
        </div>
        {hasActiveFilters && (
          <button
            onClick={resetFilters}
            className="flex items-center gap-1 text-[10px] text-secondary hover:text-secondary-300 transition-colors"
            id="reset-filters-btn"
          >
            <RotateCcw className="w-3 h-3" />
            Sıfırla
          </button>
        )}
      </div>

      {/* Bölümler */}
      <div className="flex-1 overflow-y-auto custom-scrollbar thin-scrollbar p-3 space-y-1">
        {/* ── Kategori ──────────────────────────────────────────── */}
        <FilterSection
          title="Kategori"
          expanded={expandedSections.has("category")}
          onToggle={() => toggleSection("category")}
        >
          <div className="space-y-1">
            {(
              Object.values(AnomalyCategory) as AnomalyCategory[]
            ).map((cat) => {
              const colors = CATEGORY_COLORS[cat];
              const isActive = filters.categories.has(cat);

              return (
                <label
                  key={cat}
                  className={cn(
                    "flex items-center gap-2.5 p-2 rounded-lg cursor-pointer",
                    "transition-all duration-200",
                    isActive
                      ? "bg-white/[0.03] hover:bg-white/[0.05]"
                      : "opacity-50 hover:opacity-75"
                  )}
                >
                  <div
                    className={cn(
                      "w-4 h-4 rounded border-2 flex items-center justify-center",
                      "transition-all duration-200",
                      isActive
                        ? "border-current bg-current"
                        : "border-gray-600 bg-transparent"
                    )}
                    style={{
                      borderColor: isActive ? colors.hex : undefined,
                      backgroundColor: isActive ? colors.hex : undefined,
                    }}
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
                  <input
                    type="checkbox"
                    checked={isActive}
                    onChange={() => toggleCategory(cat)}
                    className="sr-only"
                  />
                  <span className="text-xs text-gray-300">
                    {CATEGORY_ICONS[cat]} {CATEGORY_LABELS[cat]}
                  </span>
                </label>
              );
            })}
          </div>
        </FilterSection>

        {/* ── Güven Skoru ────────────────────────────────────────── */}
        <FilterSection
          title="Güven Skoru"
          expanded={expandedSections.has("confidence")}
          onToggle={() => toggleSection("confidence")}
          badge={
            filters.minConfidence > 0 || filters.maxConfidence < 100
              ? `${filters.minConfidence}–${filters.maxConfidence}`
              : undefined
          }
        >
          <div className="space-y-3 px-1">
            {/* Min slider */}
            <div>
              <div className="flex items-center justify-between mb-1">
                <span className="text-[10px] text-gray-500">Minimum</span>
                <span className="text-[10px] font-bold text-gray-300 tabular-nums">
                  {filters.minConfidence}%
                </span>
              </div>
              <input
                type="range"
                min={0}
                max={100}
                step={5}
                value={filters.minConfidence}
                onChange={(e) =>
                  onFiltersChange({
                    ...filters,
                    minConfidence: parseInt(e.target.value),
                  })
                }
                className="range-slider w-full"
                id="min-confidence-slider"
              />
            </div>

            {/* Max slider */}
            <div>
              <div className="flex items-center justify-between mb-1">
                <span className="text-[10px] text-gray-500">Maksimum</span>
                <span className="text-[10px] font-bold text-gray-300 tabular-nums">
                  {filters.maxConfidence}%
                </span>
              </div>
              <input
                type="range"
                min={0}
                max={100}
                step={5}
                value={filters.maxConfidence}
                onChange={(e) =>
                  onFiltersChange({
                    ...filters,
                    maxConfidence: parseInt(e.target.value),
                  })
                }
                className="range-slider w-full"
                id="max-confidence-slider"
              />
            </div>

            {/* Görsel bar */}
            <div className="h-1.5 rounded-full bg-white/[0.03] overflow-hidden">
              <div
                className="h-full bg-secondary/60 rounded-full transition-all duration-300"
                style={{
                  marginLeft: `${filters.minConfidence}%`,
                  width: `${filters.maxConfidence - filters.minConfidence}%`,
                }}
              />
            </div>
          </div>
        </FilterSection>

        {/* ── Durum ──────────────────────────────────────────────── */}
        <FilterSection
          title="Durum"
          expanded={expandedSections.has("status")}
          onToggle={() => toggleSection("status")}
        >
          <div className="space-y-1">
            {STATUS_CONFIG.map((status) => {
              const isActive = filters.statuses.has(status.value);

              return (
                <label
                  key={status.value}
                  className={cn(
                    "flex items-center gap-2.5 p-2 rounded-lg cursor-pointer",
                    "transition-all duration-200",
                    isActive
                      ? "bg-white/[0.03] hover:bg-white/[0.05]"
                      : "opacity-50 hover:opacity-75"
                  )}
                >
                  <div
                    className={cn(
                      "w-4 h-4 rounded border-2 flex items-center justify-center",
                      "transition-all duration-200",
                      isActive
                        ? cn("border-secondary bg-secondary")
                        : "border-gray-600 bg-transparent"
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
                  <input
                    type="checkbox"
                    checked={isActive}
                    onChange={() => toggleStatus(status.value)}
                    className="sr-only"
                  />
                  <span className="flex items-center gap-1.5 text-xs text-gray-300">
                    <span
                      className={cn("w-1.5 h-1.5 rounded-full", status.dotColor)}
                    />
                    {status.label}
                  </span>
                </label>
              );
            })}
          </div>
        </FilterSection>

        {/* ── Tarih Aralığı ──────────────────────────────────────── */}
        <FilterSection
          title="Tarih Aralığı"
          expanded={expandedSections.has("date")}
          onToggle={() => toggleSection("date")}
        >
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="block text-[9px] text-gray-600 uppercase tracking-wider mb-1 px-1">
                Başlangıç
              </label>
              <input
                type="date"
                value={filters.dateFrom}
                onChange={(e) =>
                  onFiltersChange({ ...filters, dateFrom: e.target.value })
                }
                className={cn(
                  "w-full px-2.5 py-1.5 rounded-lg text-[11px]",
                  "bg-white/[0.03] border border-white/8 text-gray-300",
                  "focus:outline-none focus:ring-1 focus:ring-secondary/40",
                  "transition-all duration-200",
                  "[color-scheme:dark]"
                )}
                id="filter-date-from"
              />
            </div>
            <div>
              <label className="block text-[9px] text-gray-600 uppercase tracking-wider mb-1 px-1">
                Bitiş
              </label>
              <input
                type="date"
                value={filters.dateTo}
                onChange={(e) =>
                  onFiltersChange({ ...filters, dateTo: e.target.value })
                }
                className={cn(
                  "w-full px-2.5 py-1.5 rounded-lg text-[11px]",
                  "bg-white/[0.03] border border-white/8 text-gray-300",
                  "focus:outline-none focus:ring-1 focus:ring-secondary/40",
                  "transition-all duration-200",
                  "[color-scheme:dark]"
                )}
                id="filter-date-to"
              />
            </div>
          </div>
        </FilterSection>

        {/* ── Bölge/Ülke ─────────────────────────────────────────── */}
        <FilterSection
          title="Bölge / Ülke"
          expanded={expandedSections.has("region")}
          onToggle={() => toggleSection("region")}
        >
          <div className="relative">
            <select
              value={filters.region}
              onChange={(e) =>
                onFiltersChange({ ...filters, region: e.target.value })
              }
              className={cn(
                "w-full appearance-none px-3 py-2 rounded-lg text-xs",
                "bg-white/[0.03] border border-white/8 text-gray-300",
                "focus:outline-none focus:ring-1 focus:ring-secondary/40",
                "transition-all duration-200 cursor-pointer"
              )}
              id="filter-region"
            >
              {REGION_OPTIONS.map((opt) => (
                <option
                  key={opt.value}
                  value={opt.value}
                  className="bg-surface text-gray-200"
                >
                  {opt.label}
                </option>
              ))}
            </select>
            <div className="absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none">
              <ChevronDown className="w-3.5 h-3.5 text-gray-500" />
            </div>
          </div>
        </FilterSection>
      </div>
    </div>
  );
}

// ── Açılır Kapanır Filtre Bölümü ─────────────────────────────────────────

function FilterSection({
  title,
  expanded,
  onToggle,
  badge,
  children,
}: {
  title: string;
  expanded: boolean;
  onToggle: () => void;
  badge?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-xl border border-white/[0.02] overflow-hidden">
      <button
        onClick={onToggle}
        className={cn(
          "w-full flex items-center justify-between px-3 py-2.5",
          "hover:bg-white/[0.02] transition-colors"
        )}
      >
        <span className="text-[11px] font-semibold text-gray-400 uppercase tracking-wider">
          {title}
        </span>
        <div className="flex items-center gap-2">
          {badge && (
            <span className="text-[9px] font-bold text-secondary bg-secondary/10 px-1.5 py-0.5 rounded">
              {badge}
            </span>
          )}
          <ChevronDown
            className={cn(
              "w-3.5 h-3.5 text-gray-500 transition-transform duration-200",
              expanded && "rotate-180"
            )}
          />
        </div>
      </button>
      {expanded && <div className="px-3 pb-3 animate-fade-in">{children}</div>}
    </div>
  );
}
