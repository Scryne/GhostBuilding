// ═══════════════════════════════════════════════════════════════════════════
// AnomalyDetailPanel.tsx — Sağ kenar paneli (harita üstünde float)
// Glassmorphism overlay ile anomali detay bilgisini gösterir.
// ═══════════════════════════════════════════════════════════════════════════

"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { cn } from "@/lib/utils";
import {
  formatCoordsDMS,
  formatCoordsDecimal,
  formatDate,
  formatRelativeTime,
  CATEGORY_LABELS,
  CATEGORY_ICONS,
  CATEGORY_COLORS,
  STATUS_COLORS,
} from "@/lib/utils";
import { VerificationVote } from "@/lib/types";
import type {
  AnomalyDetail,
  VerificationSummary,
  TimeSeriesEntry,
} from "@/lib/types";
import { useAnomalyDetail } from "@/hooks/useAnomaly";
import { verificationApi } from "@/lib/api";

import ProviderComparison from "./ProviderComparison";
import TimelineChart from "./TimelineChart";
import VerificationPanel from "./VerificationPanel";

// ── Güven Skoru Bileşenleri ───────────────────────────────────────────────

interface ConfidenceComponent {
  label: string;
  value: number;
  color: string;
  icon: string;
}

function getConfidenceBreakdown(
  detail: AnomalyDetail
): ConfidenceComponent[] {
  const meta = detail.meta_data || {};
  const components: ConfidenceComponent[] = [];

  // Pixel diff
  const pixelDiff =
    typeof meta.pixel_diff_score === "number"
      ? meta.pixel_diff_score
      : null;
  if (pixelDiff !== null) {
    components.push({
      label: "Piksel Farkı",
      value: pixelDiff,
      color: pixelDiff >= 60 ? "#E63946" : pixelDiff >= 30 ? "#F4A261" : "#2E6DA4",
      icon: "🔲",
    });
  }

  // Blur detection
  const blurScore =
    typeof meta.blur_score === "number" ? meta.blur_score : null;
  if (blurScore !== null) {
    components.push({
      label: "Blur Tespiti",
      value: blurScore,
      color: blurScore >= 60 ? "#E63946" : blurScore >= 30 ? "#F4A261" : "#2E6DA4",
      icon: "🌫️",
    });
  }

  // Geospatial
  const geoScore =
    typeof meta.geospatial_score === "number"
      ? meta.geospatial_score
      : null;
  if (geoScore !== null) {
    components.push({
      label: "Mekansal Analiz",
      value: geoScore,
      color: geoScore >= 60 ? "#E63946" : geoScore >= 30 ? "#F4A261" : "#2E6DA4",
      icon: "📍",
    });
  }

  // Time series
  const tsScore =
    typeof meta.time_series_score === "number"
      ? meta.time_series_score
      : null;
  if (tsScore !== null) {
    components.push({
      label: "Zaman Serisi",
      value: tsScore,
      color: tsScore >= 60 ? "#E63946" : tsScore >= 30 ? "#F4A261" : "#2E6DA4",
      icon: "📈",
    });
  }

  // Eğer meta'da bileşen yoksa, genel skoru göster
  if (components.length === 0) {
    components.push({
      label: "Genel Güven",
      value: detail.confidence_score,
      color:
        detail.confidence_score >= 60
          ? "#E63946"
          : detail.confidence_score >= 30
          ? "#F4A261"
          : "#2E6DA4",
      icon: "📊",
    });
  }

  return components;
}

// ═══════════════════════════════════════════════════════════════════════════

interface AnomalyDetailPanelProps {
  anomalyId: string | null;
  isLoggedIn?: boolean;
  onClose?: () => void;
  className?: string;
}

export default function AnomalyDetailPanel({
  anomalyId,
  isLoggedIn = false,
  onClose,
  className,
}: AnomalyDetailPanelProps) {
  const { data: detail, error, isLoading, mutate } = useAnomalyDetail(anomalyId);
  const [verificationSummary, setVerificationSummary] =
    useState<VerificationSummary | null>(null);
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const [loadingVerification, setLoadingVerification] = useState(false);

  // ── Verification verisini çek ─────────────────────────────────────

  useEffect(() => {
    if (!anomalyId) return;

    setLoadingVerification(true);
    verificationApi
      .getSummary(anomalyId)
      .then(setVerificationSummary)
      .catch(() => setVerificationSummary(null))
      .finally(() => setLoadingVerification(false));
  }, [anomalyId]);

  // ── Oy gönder ─────────────────────────────────────────────────────

  const handleVote = useCallback(
    async (vote: VerificationVote, comment?: string) => {
      if (!anomalyId) return;

      await verificationApi.verify(anomalyId, { vote, comment });

      // Yeniden çek
      const updated = await verificationApi.getSummary(anomalyId);
      setVerificationSummary(updated);
      mutate(); // Anomali detayını da güncelle
    },
    [anomalyId, mutate]
  );

  // ── Timeline tıklaması ────────────────────────────────────────────

  const handleTimelineClick = useCallback((entry: TimeSeriesEntry) => {
    // TODO: İlgili yılın görüntüsünü göster
    console.log("Timeline point clicked:", entry);
  }, []);

  // ── Güven bileşenleri ─────────────────────────────────────────────

  const confidenceBreakdown = useMemo(
    () => (detail ? getConfidenceBreakdown(detail) : []),
    [detail]
  );

  // ── Kapalıysa render etme ─────────────────────────────────────────

  if (!anomalyId) return null;

  // ── Kategori renkleri ─────────────────────────────────────────────

  const categoryColors = detail
    ? CATEGORY_COLORS[detail.category]
    : null;

  const statusConfig = detail
    ? STATUS_COLORS[detail.status]
    : null;

  // ── Skor daire gradyanı ───────────────────────────────────────────

  const scorePercent = detail ? detail.confidence_score : 0;
  const scoreColor = detail
    ? scorePercent >= 80
      ? "#10B981"
      : scorePercent >= 60
      ? "#F59E0B"
      : scorePercent >= 40
      ? "#F97316"
      : "#EF4444"
    : "#6B7280";

  return (
    <div
      className={cn(
        "map-overlay map-overlay-right glass-panel-strong",
        "flex flex-col overflow-hidden",
        "animate-slide-in-right",
        className
      )}
      id="anomaly-detail-panel"
    >
      {/* ── İç kaplama — scroll edilebilir ─────────────────────────── */}
      <div className="flex-1 overflow-y-auto custom-scrollbar thin-scrollbar">
        {/* Yükleme durumu */}
        {isLoading && (
          <div className="flex items-center justify-center h-full p-8">
            <div className="text-center space-y-3">
              <div className="w-10 h-10 rounded-full border-2 border-secondary/30 border-t-secondary animate-spin mx-auto" />
              <p className="text-xs text-gray-500">Anomali yükleniyor...</p>
            </div>
          </div>
        )}

        {/* Hata durumu */}
        {error && !isLoading && (
          <div className="flex items-center justify-center h-full p-8">
            <div className="text-center space-y-2">
              <div className="text-2xl opacity-40">⚠️</div>
              <p className="text-xs text-red-400">
                Veri alınamadı. Lütfen tekrar deneyin.
              </p>
            </div>
          </div>
        )}

        {/* Detail yüklendiyse */}
        {detail && !isLoading && (
          <div className="p-4 space-y-5">
            {/* ════════════════════════════════════════════════════════
               1. HEADER
            ════════════════════════════════════════════════════════ */}
            <section className="space-y-3">
              {/* Üst bar: Kapat + Durum */}
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  {/* Kategori badge */}
                  <span
                    className={cn(
                      "inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider border",
                      categoryColors?.bg,
                      categoryColors?.text,
                      categoryColors?.border
                    )}
                  >
                    <span>{CATEGORY_ICONS[detail.category]}</span>
                    {CATEGORY_LABELS[detail.category]}
                  </span>

                  {/* Status badge */}
                  {statusConfig && (
                    <span
                      className={cn(
                        "px-2 py-0.5 rounded-full text-[9px] font-bold uppercase tracking-wider border",
                        statusConfig.bg,
                        statusConfig.text,
                        statusConfig.border
                      )}
                    >
                      {statusConfig.label}
                    </span>
                  )}
                </div>

                {/* Kapat butonu */}
                <button
                  onClick={onClose}
                  className={cn(
                    "w-7 h-7 rounded-lg flex items-center justify-center",
                    "bg-white/[0.03] hover:bg-white/[0.08] text-gray-500 hover:text-white",
                    "transition-all duration-200"
                  )}
                  id="anomaly-detail-close-btn"
                  aria-label="Paneli kapat"
                >
                  <svg
                    width="14"
                    height="14"
                    viewBox="0 0 14 14"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                  >
                    <path d="M2 2L12 12M12 2L2 12" />
                  </svg>
                </button>
              </div>

              {/* Güven skoru dairesi + Başlık */}
              <div className="flex items-start gap-3">
                {/* Skor dairesi */}
                <div className="relative flex-shrink-0">
                  <svg width="52" height="52" viewBox="0 0 52 52">
                    {/* Arka plan halkası */}
                    <circle
                      cx="26"
                      cy="26"
                      r="22"
                      stroke="rgba(255,255,255,0.05)"
                      strokeWidth="4"
                      fill="none"
                    />
                    {/* Skor halkası */}
                    <circle
                      cx="26"
                      cy="26"
                      r="22"
                      stroke={scoreColor}
                      strokeWidth="4"
                      fill="none"
                      strokeLinecap="round"
                      strokeDasharray={`${(scorePercent / 100) * 138.23} 138.23`}
                      transform="rotate(-90 26 26)"
                      className="transition-all duration-1000 ease-out"
                      style={{
                        filter: `drop-shadow(0 0 4px ${scoreColor}66)`,
                      }}
                    />
                  </svg>
                  <span
                    className="absolute inset-0 flex items-center justify-center text-xs font-bold tabular-nums"
                    style={{ color: scoreColor }}
                  >
                    {scorePercent.toFixed(0)}
                  </span>
                </div>

                {/* Başlık + Koordinatlar */}
                <div className="flex-1 min-w-0">
                  <h2 className="text-sm font-bold text-white leading-snug mb-1">
                    {detail.title || "İsimsiz Anomali"}
                  </h2>
                  {detail.description && (
                    <p className="text-[11px] text-gray-400 leading-relaxed mb-1.5 line-clamp-2">
                      {detail.description}
                    </p>
                  )}
                  <button
                    onClick={() => {
                      navigator.clipboard.writeText(
                        `${detail.lat}, ${detail.lng}`
                      );
                    }}
                    className="text-[10px] text-gray-500 hover:text-secondary font-mono transition-colors"
                    title="Koordinatları kopyala"
                    id="copy-coords-btn"
                  >
                    📍 {formatCoordsDecimal(detail.lat, detail.lng)}
                  </button>
                </div>
              </div>
            </section>

            {/* ════════════════════════════════════════════════════════
               2. GÜVEN SKORU BREAKDOWN
            ════════════════════════════════════════════════════════ */}
            <section className="space-y-2">
              <h4 className="text-[10px] font-semibold uppercase tracking-wider text-gray-500 px-1">
                Analiz Bileşenleri
              </h4>
              <div className="space-y-1.5">
                {confidenceBreakdown.map((comp) => (
                  <div key={comp.label} className="group">
                    <div className="flex items-center justify-between mb-0.5 px-1">
                      <span className="flex items-center gap-1.5 text-[10px] text-gray-400">
                        <span className="text-xs">{comp.icon}</span>
                        {comp.label}
                      </span>
                      <span
                        className="text-[10px] font-bold tabular-nums"
                        style={{ color: comp.color }}
                      >
                        {comp.value.toFixed(1)}%
                      </span>
                    </div>
                    <div className="h-1.5 rounded-full bg-white/[0.03] overflow-hidden">
                      <div
                        className="h-full rounded-full transition-all duration-700 ease-out"
                        style={{
                          width: `${Math.min(100, comp.value)}%`,
                          backgroundColor: comp.color,
                          boxShadow: `0 0 8px ${comp.color}44`,
                        }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            </section>

            {/* ════════════════════════════════════════════════════════
               3. SAĞLAYICI KARŞILAŞTIRMASI
            ════════════════════════════════════════════════════════ */}
            {detail.images.length > 0 && (
              <section>
                <div className="flex items-center justify-between px-1 mb-2">
                  <h4 className="text-[10px] font-semibold uppercase tracking-wider text-gray-500">
                    Sağlayıcı Karşılaştırması
                  </h4>
                  <span className="text-[10px] text-gray-600">
                    {detail.images.length} görüntü
                  </span>
                </div>
                <ProviderComparison images={detail.images} />
              </section>
            )}

            {/* ════════════════════════════════════════════════════════
               4. TARİHSEL ZAMAN SERİSİ
            ════════════════════════════════════════════════════════ */}
            {detail.time_series.length > 0 && (
              <section>
                <TimelineChart
                  data={detail.time_series}
                  onPointClick={handleTimelineClick}
                />
              </section>
            )}

            {/* ════════════════════════════════════════════════════════
               5. TOPLULUK DOĞRULAMA
            ════════════════════════════════════════════════════════ */}
            <section>
              <VerificationPanel
                anomalyId={anomalyId!}
                summary={verificationSummary}
                isLoggedIn={isLoggedIn}
                onVote={handleVote}
              />
            </section>

            {/* ════════════════════════════════════════════════════════
               6. METADATA
            ════════════════════════════════════════════════════════ */}
            <section className="space-y-2">
              <h4 className="text-[10px] font-semibold uppercase tracking-wider text-gray-500 px-1">
                Metadata
              </h4>
              <div className="rounded-xl bg-white/[0.015] border border-white/5 divide-y divide-white/[0.03]">
                {/* Keşfedilme tarihi */}
                <MetaRow
                  label="Keşfedilme"
                  value={formatDate(detail.detected_at)}
                  subValue={
                    detail.detected_at
                      ? formatRelativeTime(detail.detected_at)
                      : undefined
                  }
                />

                {/* Doğrulanma tarihi */}
                {detail.verified_at && (
                  <MetaRow
                    label="Doğrulanma"
                    value={formatDate(detail.verified_at)}
                  />
                )}

                {/* Tespit yöntemleri */}
                {detail.detection_methods &&
                  detail.detection_methods.length > 0 && (
                    <MetaRow
                      label="Yöntemler"
                      value={
                        <div className="flex flex-wrap gap-1">
                          {detail.detection_methods.map((m) => (
                            <span
                              key={m}
                              className="px-1.5 py-0.5 rounded text-[9px] bg-secondary/8 text-secondary/80 border border-secondary/15 font-medium"
                            >
                              {m}
                            </span>
                          ))}
                        </div>
                      }
                    />
                  )}

                {/* Kaynak sağlayıcılar */}
                {detail.source_providers &&
                  detail.source_providers.length > 0 && (
                    <MetaRow
                      label="Kaynaklar"
                      value={
                        <div className="flex flex-wrap gap-1">
                          {detail.source_providers.map((p) => (
                            <span
                              key={p}
                              className="px-1.5 py-0.5 rounded text-[9px] bg-white/[0.04] text-gray-400 border border-white/5 font-medium"
                            >
                              {p}
                            </span>
                          ))}
                        </div>
                      }
                    />
                  )}

                {/* Koordinatlar (DMS) */}
                <MetaRow
                  label="Koordinat"
                  value={
                    <span className="font-mono text-[10px]">
                      {formatCoordsDMS(detail.lat, detail.lng)}
                    </span>
                  }
                />

                {/* ID */}
                <MetaRow
                  label="ID"
                  value={
                    <span className="font-mono text-[10px] text-gray-500 select-all">
                      {detail.id.slice(0, 8)}…
                    </span>
                  }
                />
              </div>
            </section>

            {/* Alt boşluk */}
            <div className="h-4" />
          </div>
        )}
      </div>
    </div>
  );
}

// ── Meta Satır Bileşeni ──────────────────────────────────────────────────

function MetaRow({
  label,
  value,
  subValue,
}: {
  label: string;
  value: React.ReactNode;
  subValue?: string;
}) {
  return (
    <div className="flex items-start justify-between px-3 py-2.5">
      <span className="text-[10px] text-gray-500 font-medium flex-shrink-0 mt-0.5">
        {label}
      </span>
      <div className="text-right">
        <div className="text-[11px] text-gray-300 font-medium">{value}</div>
        {subValue && (
          <div className="text-[9px] text-gray-600 mt-0.5">{subValue}</div>
        )}
      </div>
    </div>
  );
}
