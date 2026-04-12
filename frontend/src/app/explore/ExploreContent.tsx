// ═══════════════════════════════════════════════════════════════════════════
// ExploreContent.tsx — Client Component
// Sol filtre paneli, sağ kart grid, üst arama + istatistik + sıralama.
// ═══════════════════════════════════════════════════════════════════════════

"use client";

import { useCallback, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { cn } from "@/lib/utils";
import { useAnomalyList } from "@/hooks/useAnomaly";
import type { AnomalyListParams } from "@/lib/api";

import {
  StatsBar,
  SearchBar,
  FilterPanel,
  AnomalyCard,
  FeaturedAnomalies,
  DEFAULT_FILTERS,
  type ExploreFilters,
} from "@/components/explore";

import { Skeleton } from "@/components/ui/Spinner";

import {
  ShieldAlert,
  ArrowUpDown,
  ChevronLeft,
  Loader2,
  SlidersHorizontal,
  X,
} from "lucide-react";

// ── Sıralama Seçenekleri ──────────────────────────────────────────────────

type SortOption = "confidence" | "newest" | "verified";

const SORT_OPTIONS: Array<{ value: SortOption; label: string }> = [
  { value: "confidence", label: "En Yüksek Güven" },
  { value: "newest", label: "En Yeni" },
  { value: "verified", label: "En Çok Doğrulanan" },
];

// ═══════════════════════════════════════════════════════════════════════════

export default function ExploreContent() {
  const router = useRouter();

  // ── State ──────────────────────────────────────────────────────────
  const [filters, setFilters] = useState<ExploreFilters>(DEFAULT_FILTERS);
  const [sortBy, setSortBy] = useState<SortOption>("confidence");
  const [page, setPage] = useState(1);
  const [mobileFiltersOpen, setMobileFiltersOpen] = useState(false);
  const limit = 20;

  // ── API parametreleri oluştur ──────────────────────────────────────

  const apiParams = useMemo<AnomalyListParams>(() => {
    const params: AnomalyListParams = {
      page,
      limit,
      min_confidence: filters.minConfidence,
    };

    // Kategori filtresi (hepsi seçiliyse gönderme)
    if (filters.categories.size < 4 && filters.categories.size > 0) {
      params.category = Array.from(filters.categories).join(",");
    }

    // Durum filtresi
    if (filters.statuses.size < 4 && filters.statuses.size > 0) {
      params.status = Array.from(filters.statuses).join(",");
    }

    return params;
  }, [filters, page]);

  // ── SWR ile veri çek ──────────────────────────────────────────────

  const { data, error, isLoading, isValidating } = useAnomalyList(apiParams);
  const anomalies = data?.data ?? [];
  const pagination = data?.pagination;
  const totalPages = pagination?.total_pages ?? 1;

  // ── Arama callback'leri ───────────────────────────────────────────

  const handleLocationSelect = useCallback(
    // eslint-disable-next-line @typescript-eslint/no-unused-vars
    (lat: number, lng: number, _label?: string) => {
      router.push(`/?lat=${lat}&lng=${lng}&zoom=14`);
    },
    [router]
  );

  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const handleTextSearch = useCallback((_query: string) => {
    // TODO: Metin tabanlı anomali arama — backend desteği eklenince aktifleşecek
    setPage(1);
  }, []);

  // ── Anomali tıklaması ────────────────────────────────────────────

  const handleAnomalyClick = useCallback(
    (id: string, lat: number, lng: number) => {
      router.push(`/?lat=${lat}&lng=${lng}&zoom=16&anomaly=${id}`);
    },
    [router]
  );

  // ── Featured tıklaması ───────────────────────────────────────────

  const handleFeaturedClick = useCallback(
    (id: string, lat: number, lng: number) => {
      router.push(`/?lat=${lat}&lng=${lng}&zoom=16&anomaly=${id}`);
    },
    [router]
  );

  // ── Sayfalama ─────────────────────────────────────────────────────

  const handlePrevPage = useCallback(() => {
    setPage((p) => Math.max(1, p - 1));
    window.scrollTo({ top: 0, behavior: "smooth" });
  }, []);

  const handleNextPage = useCallback(() => {
    setPage((p) => Math.min(totalPages, p + 1));
    window.scrollTo({ top: 0, behavior: "smooth" });
  }, [totalPages]);

  // ── Aktif filtre sayısı ───────────────────────────────────────────

  const activeFilterCount = useMemo(() => {
    let count = 0;
    if (filters.categories.size < 4) count++;
    if (filters.minConfidence > 0 || filters.maxConfidence < 100) count++;
    if (filters.statuses.size < 3) count++;
    if (filters.dateFrom || filters.dateTo) count++;
    if (filters.region) count++;
    return count;
  }, [filters]);

  // ── Render ─────────────────────────────────────────────────────────

  return (
    <div className="min-h-screen bg-background">
      {/* ── Üst Navbar ───────────────────────────────────────────── */}
      <header className="sticky top-0 z-40 border-b border-white/[0.04]">
        <div className="glass-panel-strong rounded-none border-0 border-b border-white/[0.04]">
          <div className="max-w-[1600px] mx-auto px-4 sm:px-6 py-3 flex items-center gap-3 sm:gap-4">
            {/* Logo + Geri */}
            <button
              onClick={() => router.push("/")}
              className="flex items-center gap-2.5 group flex-shrink-0"
              id="nav-logo-btn"
            >
              <div className="p-1.5 bg-secondary/10 rounded-lg border border-secondary/20 group-hover:bg-secondary/15 transition-colors">
                <ShieldAlert className="w-5 h-5 text-secondary" />
              </div>
              <h1 className="text-base font-bold text-gradient-brand tracking-tight whitespace-nowrap hidden sm:block">
                GhostBuilding
              </h1>
            </button>

            {/* Ayırıcı */}
            <div className="w-px h-6 bg-white/[0.06] hidden sm:block" />

            {/* Sayfa başlığı */}
            <span className="text-sm font-semibold text-gray-400 hidden sm:block">
              Keşfet
            </span>

            {/* Arama */}
            <SearchBar
              onLocationSelect={handleLocationSelect}
              onTextSearch={handleTextSearch}
              className="flex-1 max-w-xl"
            />

            {/* Mobil filtre butonu */}
            <button
              onClick={() => setMobileFiltersOpen(true)}
              className={cn(
                "lg:hidden flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium",
                "bg-white/[0.04] text-gray-300 border border-white/[0.06]",
                "hover:bg-white/[0.06] transition-colors relative"
              )}
              id="mobile-filter-btn"
            >
              <SlidersHorizontal className="w-3.5 h-3.5" />
              Filtre
              {activeFilterCount > 0 && (
                <span className="absolute -top-1.5 -right-1.5 w-4 h-4 bg-secondary text-white text-[9px] font-bold rounded-full flex items-center justify-center">
                  {activeFilterCount}
                </span>
              )}
            </button>

            {/* Haritaya dön */}
            <button
              onClick={() => router.push("/")}
              className={cn(
                "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium",
                "bg-secondary/10 text-secondary border border-secondary/20",
                "hover:bg-secondary/15 transition-colors flex-shrink-0"
              )}
              id="back-to-map-btn"
            >
              <ChevronLeft className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">Harita</span>
            </button>
          </div>
        </div>
      </header>

      {/* ── İstatistik Çubuğu ────────────────────────────────────── */}
      <div className="max-w-[1600px] mx-auto px-4 sm:px-6 mt-4">
        <StatsBar className="rounded-2xl" />
      </div>

      {/* ── Ana İçerik ───────────────────────────────────────────── */}
      <div className="max-w-[1600px] mx-auto px-4 sm:px-6 py-6 flex gap-6">
        {/* ── Sol: Filtre Paneli (Desktop) ──────────────────────── */}
        <aside className="w-[280px] flex-shrink-0 hidden lg:flex flex-col gap-4 sticky top-[72px] max-h-[calc(100vh-88px)] overflow-y-auto custom-scrollbar thin-scrollbar">
          <FilterPanel
            filters={filters}
            onFiltersChange={(f) => {
              setFilters(f);
              setPage(1);
            }}
            className="flex-1"
          />

          {/* Öne Çıkanlar */}
          <div className="glass-panel p-4">
            <FeaturedAnomalies onAnomalyClick={handleFeaturedClick} />
          </div>
        </aside>

        {/* ── Mobil Filtre Overlay ──────────────────────────────── */}
        {mobileFiltersOpen && (
          <div className="fixed inset-0 z-50 lg:hidden">
            {/* Backdrop */}
            <div
              className="absolute inset-0 bg-black/60 backdrop-blur-sm animate-fade-in"
              onClick={() => setMobileFiltersOpen(false)}
            />
            {/* Panel */}
            <div className="absolute left-0 top-0 bottom-0 w-[320px] max-w-[85vw] glass-panel-strong rounded-none rounded-r-2xl animate-slide-in-right overflow-y-auto custom-scrollbar">
              <div className="p-4 border-b border-white/[0.04] flex items-center justify-between sticky top-0 bg-surface/95 backdrop-blur-sm z-10">
                <span className="text-sm font-bold text-gray-200">
                  Filtreler
                </span>
                <button
                  onClick={() => setMobileFiltersOpen(false)}
                  className="p-1.5 rounded-lg hover:bg-white/[0.04] text-gray-400 transition-colors"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
              <div className="p-4 space-y-4">
                <FilterPanel
                  filters={filters}
                  onFiltersChange={(f) => {
                    setFilters(f);
                    setPage(1);
                  }}
                />
                <div className="glass-panel p-4">
                  <FeaturedAnomalies onAnomalyClick={(id, lat, lng) => {
                    setMobileFiltersOpen(false);
                    handleFeaturedClick(id, lat, lng);
                  }} />
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ── Sağ: Anomali Kartları ────────────────────────────── */}
        <main className="flex-1 min-w-0 space-y-4">
          {/* Üst bar: sıralama + sonuç sayısı */}
          <div className="flex items-center justify-between flex-wrap gap-3">
            <div className="flex items-center gap-3">
              <span className="text-sm text-gray-400">
                {pagination ? (
                  <>
                    <span className="font-bold text-white">
                      {pagination.total.toLocaleString("tr-TR")}
                    </span>{" "}
                    anomali bulundu
                  </>
                ) : isLoading ? (
                  "Yükleniyor..."
                ) : (
                  "Anomali bulunamadı"
                )}
              </span>
              {isValidating && !isLoading && (
                <Loader2 className="w-3.5 h-3.5 text-secondary animate-spin" />
              )}
            </div>

            {/* Sıralama */}
            <div className="flex items-center gap-2">
              <ArrowUpDown className="w-3.5 h-3.5 text-gray-500" />
              <div className="flex items-center rounded-lg border border-white/5 overflow-hidden">
                {SORT_OPTIONS.map((opt) => (
                  <button
                    key={opt.value}
                    onClick={() => {
                      setSortBy(opt.value);
                      setPage(1);
                    }}
                    className={cn(
                      "px-3 py-1.5 text-[10px] font-semibold uppercase tracking-wider",
                      "transition-all duration-200",
                      sortBy === opt.value
                        ? "bg-secondary/15 text-secondary"
                        : "text-gray-500 hover:text-gray-300 hover:bg-white/[0.02]"
                    )}
                    id={`sort-${opt.value}`}
                  >
                    {opt.label}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* ── Kart Grid ──────────────────────────────────────── */}
          {isLoading ? (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {Array.from({ length: 6 }).map((_, i) => (
                <div key={i} className="space-y-3">
                  <Skeleton className="h-32 w-full rounded-2xl" />
                  <Skeleton className="h-4 w-3/4 rounded" />
                  <Skeleton className="h-3 w-1/2 rounded" />
                </div>
              ))}
            </div>
          ) : error ? (
            <div className="flex flex-col items-center justify-center py-20">
              <div className="w-16 h-16 rounded-2xl bg-red-500/10 border border-red-500/20 flex items-center justify-center mb-4">
                <span className="text-2xl">⚠️</span>
              </div>
              <p className="text-sm text-red-400 mb-2 font-medium">
                Veri yüklenirken bir hata oluştu
              </p>
              <p className="text-xs text-gray-600 mb-4">
                Sunucu bağlantısını kontrol edip tekrar deneyin
              </p>
              <button
                onClick={() => window.location.reload()}
                className={cn(
                  "px-4 py-2 rounded-xl text-xs font-semibold",
                  "bg-secondary/10 text-secondary border border-secondary/20",
                  "hover:bg-secondary/15 transition-colors"
                )}
              >
                Tekrar Dene
              </button>
            </div>
          ) : anomalies.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-20">
              <div className="w-16 h-16 rounded-2xl bg-white/[0.03] border border-white/[0.06] flex items-center justify-center mb-4">
                <span className="text-2xl opacity-40">🔍</span>
              </div>
              <p className="text-sm text-gray-400 mb-1 font-medium">
                Filtrelere uygun anomali bulunamadı
              </p>
              <p className="text-xs text-gray-600">
                Filtre kriterlerini genişletmeyi deneyin
              </p>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {anomalies.map((anomaly) => (
                <AnomalyCard
                  key={anomaly.id}
                  anomaly={anomaly}
                  onClick={() =>
                    handleAnomalyClick(
                      anomaly.id,
                      anomaly.lat,
                      anomaly.lng
                    )
                  }
                />
              ))}
            </div>
          )}

          {/* ── Pagination ───────────────────────────────────────── */}
          {pagination && totalPages > 1 && (
            <div className="flex items-center justify-center gap-3 pt-6 pb-8">
              <button
                onClick={handlePrevPage}
                disabled={page <= 1}
                className={cn(
                  "px-4 py-2 rounded-xl text-xs font-semibold",
                  "border border-white/5 transition-all duration-200",
                  page <= 1
                    ? "opacity-30 cursor-not-allowed text-gray-600"
                    : "bg-white/[0.03] text-gray-300 hover:bg-white/[0.06] hover:border-white/10"
                )}
                id="pagination-prev"
              >
                ← Önceki
              </button>

              {/* Sayfa numaraları */}
              <div className="flex items-center gap-1">
                {generatePageNumbers(page, totalPages).map((p, i) =>
                  p === "..." ? (
                    <span
                      key={`dots-${i}`}
                      className="px-2 text-gray-600 text-xs"
                    >
                      …
                    </span>
                  ) : (
                    <button
                      key={p}
                      onClick={() => {
                        setPage(p as number);
                        window.scrollTo({ top: 0, behavior: "smooth" });
                      }}
                      className={cn(
                        "w-8 h-8 rounded-lg text-xs font-semibold",
                        "transition-all duration-200",
                        page === p
                          ? "bg-secondary text-white shadow-glow-sm"
                          : "text-gray-400 hover:bg-white/[0.04]"
                      )}
                    >
                      {p}
                    </button>
                  )
                )}
              </div>

              <button
                onClick={handleNextPage}
                disabled={page >= totalPages}
                className={cn(
                  "px-4 py-2 rounded-xl text-xs font-semibold",
                  "border border-white/5 transition-all duration-200",
                  page >= totalPages
                    ? "opacity-30 cursor-not-allowed text-gray-600"
                    : "bg-white/[0.03] text-gray-300 hover:bg-white/[0.06] hover:border-white/10"
                )}
                id="pagination-next"
              >
                Sonraki →
              </button>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}

// ── Sayfa numarası oluşturucu ─────────────────────────────────────────────

function generatePageNumbers(
  current: number,
  total: number
): Array<number | "..."> {
  if (total <= 7) {
    return Array.from({ length: total }, (_, i) => i + 1);
  }

  const pages: Array<number | "..."> = [];

  // Her zaman ilk sayfa
  pages.push(1);

  if (current > 3) {
    pages.push("...");
  }

  // Mevcut sayfanın etrafı
  const start = Math.max(2, current - 1);
  const end = Math.min(total - 1, current + 1);

  for (let i = start; i <= end; i++) {
    pages.push(i);
  }

  if (current < total - 2) {
    pages.push("...");
  }

  // Her zaman son sayfa
  if (total > 1) {
    pages.push(total);
  }

  return pages;
}
