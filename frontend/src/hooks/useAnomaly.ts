// ═══════════════════════════════════════════════════════════════════════════
// GhostBuilding — Anomali Veri Hook'ları (SWR)
// ═══════════════════════════════════════════════════════════════════════════

"use client";

import useSWR, { SWRConfiguration } from "swr";
import { anomalyApi, type AnomalyListParams } from "@/lib/api";
import type {
  PaginatedResponse,
  AnomalyListItem,
  AnomalyDetail,
  StatsResponse,
  ScanStatusResponse,
} from "@/lib/types";

// ── SWR Varsayılan Ayarlar ────────────────────────────────────────────────

const DEFAULT_SWR_CONFIG: SWRConfiguration = {
  revalidateOnFocus: false,
  revalidateOnReconnect: true,
  errorRetryCount: 3,
  dedupingInterval: 5_000,
};

// ── Anomali Listesi ───────────────────────────────────────────────────────

/**
 * Anomali listesini SWR ile çeker.
 * Mekansal filtre, kategori, güven skoru, durum ve sayfalama destekler.
 */
export function useAnomalyList(
  params?: AnomalyListParams,
  config?: SWRConfiguration
) {
  // params'ı SWR key olarak serialize et
  const key = params
    ? ["anomalies", JSON.stringify(params)]
    : ["anomalies"];

  return useSWR<PaginatedResponse<AnomalyListItem>>(
    key,
    () => anomalyApi.list(params),
    {
      ...DEFAULT_SWR_CONFIG,
      refreshInterval: 30_000, // 30 saniyede bir yenile
      ...config,
    }
  );
}

// ── Anomali Detay ─────────────────────────────────────────────────────────

/**
 * Tek bir anomalinin detay bilgisini çeker.
 */
export function useAnomalyDetail(
  id: string | null | undefined,
  config?: SWRConfiguration
) {
  return useSWR<AnomalyDetail>(
    id ? `anomaly-detail-${id}` : null,
    () => anomalyApi.getById(id!),
    {
      ...DEFAULT_SWR_CONFIG,
      ...config,
    }
  );
}

// ── Anomali İstatistikleri ────────────────────────────────────────────────

/**
 * Genel anomali istatistiklerini çeker.
 */
export function useAnomalyStats(config?: SWRConfiguration) {
  return useSWR<StatsResponse>(
    "anomaly-stats",
    () => anomalyApi.getStats(),
    {
      ...DEFAULT_SWR_CONFIG,
      refreshInterval: 60_000, // 1 dakikada bir yenile
      ...config,
    }
  );
}

// ── Tarama Durumu ─────────────────────────────────────────────────────────

/**
 * Aktif tarama görevinin durumunu polling ile izler.
 * pollInterval: tamamlanınca polling durur.
 */
export function useScanStatus(
  taskId: string | null | undefined,
  config?: SWRConfiguration
) {
  const { data, ...rest } = useSWR<ScanStatusResponse>(
    taskId ? `scan-status-${taskId}` : null,
    () => anomalyApi.getScanStatus(taskId!),
    {
      ...DEFAULT_SWR_CONFIG,
      refreshInterval: (latestData) => {
        // Tamamlandı veya başarısız → polling durdur
        if (
          latestData?.status === "complete" ||
          latestData?.status === "failed"
        ) {
          return 0;
        }
        return 2_000; // 2 saniyede bir
      },
      ...config,
    }
  );

  return {
    data,
    isRunning: data?.status === "running" || data?.status === "pending",
    isComplete: data?.status === "complete",
    isFailed: data?.status === "failed",
    progress: data?.progress_percent ?? 0,
    ...rest,
  };
}

// ── Harita Viewport Tabanlı Liste ─────────────────────────────────────────

/**
 * Harita viewport'undaki anomalileri çeker.
 * Merkez koordinat ve yarıçapa göre filtreler.
 */
export function useMapAnomalies(
  viewport: {
    latitude: number;
    longitude: number;
    zoom: number;
  } | null,
  additionalParams?: Partial<AnomalyListParams>,
  config?: SWRConfiguration
) {
  // Zoom seviyesine göre yarıçap hesapla (yakınlaştıkça küçük alan)
  const radiusKm = viewport
    ? Math.min(500, Math.max(1, 40_000 / Math.pow(2, viewport.zoom)))
    : 50;

  const params: AnomalyListParams | undefined = viewport
    ? {
        lat: viewport.latitude,
        lng: viewport.longitude,
        radius_km: radiusKm,
        limit: 100,
        ...additionalParams,
      }
    : undefined;

  return useAnomalyList(params, {
    refreshInterval: 15_000,
    ...config,
  });
}
