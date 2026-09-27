// ═══════════════════════════════════════════════════════════════════════════
// FilterPanel.tsx — Keşfet filtreleri
// Yalnız API'nin gerçekten uyguladığı filtreler: kategori, en düşük puan, durum.
// (Eskiden tarih aralığı, bölge ve üst puan sınırı da vardı; hiçbiri API'ye gitmiyordu.)
// ═══════════════════════════════════════════════════════════════════════════

"use client";

import { RotateCcw, SlidersHorizontal } from "lucide-react";
import { BASELINE_P99_SCORE, CATEGORY_COLORS, CATEGORY_LABELS, STATUS_COLORS, cn } from "@/lib/utils";
import { AnomalyCategory, AnomalyStatus } from "@/lib/types";

export interface ExploreFilters {
  categories: Set<AnomalyCategory>;
  minConfidence: number;
  statuses: Set<AnomalyStatus>;
}

const ALL_CATEGORIES: AnomalyCategory[] = [
  AnomalyCategory.CENSORED_AREA,
  AnomalyCategory.IMAGE_DISCREPANCY,
  AnomalyCategory.GHOST_BUILDING,
  AnomalyCategory.HIDDEN_STRUCTURE,
];

const ALL_STATUSES: AnomalyStatus[] = [
  AnomalyStatus.PENDING,
  AnomalyStatus.UNDER_REVIEW,
  AnomalyStatus.VERIFIED,
  AnomalyStatus.REJECTED,
];

export const DEFAULT_FILTERS: ExploreFilters = {
  categories: new Set(ALL_CATEGORIES),
  minConfidence: 0,
  // Reddedilen bulgular varsayılan olarak gizli
  statuses: new Set([AnomalyStatus.PENDING, AnomalyStatus.UNDER_REVIEW, AnomalyStatus.VERIFIED]),
};

interface FilterPanelProps {
  filters: ExploreFilters;
  onFiltersChange: (filters: ExploreFilters) => void;
  className?: string;
}

function toggle<T>(set: Set<T>, value: T): Set<T> {
  const next = new Set(set);
  if (next.has(value)) next.delete(value);
  else next.add(value);
  return next;
}

export default function FilterPanel({ filters, onFiltersChange, className }: FilterPanelProps) {
  const isDefault =
    filters.minConfidence === 0 &&
    filters.categories.size === ALL_CATEGORIES.length &&
    filters.statuses.size === DEFAULT_FILTERS.statuses.size &&
    !filters.statuses.has(AnomalyStatus.REJECTED);

  return (
    <div className={cn("rounded-2xl border border-border bg-surface/70 p-4", className)} id="filter-panel">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="flex items-center gap-2 text-sm font-semibold text-foreground">
          <SlidersHorizontal className="size-4 text-secondary" aria-hidden /> Filtreler
        </h2>
        {!isDefault && (
          <button
            type="button"
            onClick={() => onFiltersChange({ ...DEFAULT_FILTERS, categories: new Set(DEFAULT_FILTERS.categories), statuses: new Set(DEFAULT_FILTERS.statuses) })}
            className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs text-muted hover:bg-white/[0.05] hover:text-foreground"
          >
            <RotateCcw className="size-3.5" aria-hidden /> Sıfırla
          </button>
        )}
      </div>

      <fieldset className="space-y-1">
        <legend className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-muted">Kategori</legend>
        {ALL_CATEGORIES.map((cat) => (
          <label key={cat} className="flex cursor-pointer items-center gap-2.5 rounded-lg px-2 py-1.5 text-sm hover:bg-white/[0.04]">
            <input
              type="checkbox"
              checked={filters.categories.has(cat)}
              onChange={() => onFiltersChange({ ...filters, categories: toggle(filters.categories, cat) })}
              className="size-4 accent-secondary"
            />
            <span className={cn("size-2 rounded-full", CATEGORY_COLORS[cat].dot)} aria-hidden />
            <span className="text-foreground">{CATEGORY_LABELS[cat]}</span>
          </label>
        ))}
      </fieldset>

      <div className="mt-5">
        <div className="mb-1.5 flex items-baseline justify-between">
          <label htmlFor="explore-min-score" className="text-[11px] font-semibold uppercase tracking-wider text-muted">
            En düşük puan
          </label>
          <span className="font-mono text-sm tabular-nums text-foreground">{filters.minConfidence}</span>
        </div>
        <input
          id="explore-min-score"
          type="range"
          min={0}
          max={100}
          step={5}
          value={filters.minConfidence}
          onChange={(e) => onFiltersChange({ ...filters, minConfidence: Number(e.target.value) })}
          className="w-full accent-secondary"
        />
        <p className="mt-1 text-[11px] leading-relaxed text-muted-foreground">
          {BASELINE_P99_SCORE} = sıradan konumların %99&apos;u. Kayıtlı bulguların hepsi bu çizginin üstünde.
        </p>
      </div>

      <fieldset className="mt-5 space-y-1">
        <legend className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-muted">Durum</legend>
        {ALL_STATUSES.map((st) => (
          <label key={st} className="flex cursor-pointer items-center gap-2.5 rounded-lg px-2 py-1.5 text-sm hover:bg-white/[0.04]">
            <input
              type="checkbox"
              checked={filters.statuses.has(st)}
              onChange={() => onFiltersChange({ ...filters, statuses: toggle(filters.statuses, st) })}
              className="size-4 accent-secondary"
            />
            <span className={STATUS_COLORS[st].text}>{STATUS_COLORS[st].label}</span>
          </label>
        ))}
      </fieldset>
    </div>
  );
}
