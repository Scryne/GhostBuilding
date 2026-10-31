// ═══════════════════════════════════════════════════════════════════════════
// HistoryStrip.tsx — Bulgunun konumunun yıllar içindeki Esri Wayback görüntüleri
// Kanıttır, puan değildir: sıradan şehirler de yıllar içinde bu kadar değişir
// (docs/calibration-history-z16.json). Zaman serisi tarama sonrası arka planda
// üretilir; henüz yoksa ilk istek kuyruğa atar ve şerit "hazırlanıyor" der.
// ═══════════════════════════════════════════════════════════════════════════

"use client";

import Image from "next/image";
import useSWR from "swr";
import { anomalyApi, resolveMediaUrl } from "@/lib/api";
import { cn, formatScore } from "@/lib/utils";
import type { AnomalyHistory } from "@/lib/types";

const PENDING_POLL_MS = 5000;

const dateFormat = new Intl.DateTimeFormat("tr-TR", { day: "numeric", month: "short", year: "numeric" });

function formatDay(iso: string): string {
  const date = new Date(`${iso}T00:00:00Z`);
  return Number.isNaN(date.getTime()) ? iso : dateFormat.format(date);
}

export default function HistoryStrip({ anomalyId, compact = false }: { anomalyId: string; compact?: boolean }) {
  const { data, error, isLoading, mutate } = useSWR<AnomalyHistory>(
    ["anomaly-history", anomalyId],
    () => anomalyApi.getHistory(anomalyId),
    {
      refreshInterval: (latest) => (latest?.status === "pending" ? PENDING_POLL_MS : 0),
      revalidateOnFocus: false,
    }
  );

  return (
    <section aria-labelledby={`history-${anomalyId}`} className="space-y-3">
      <div className="flex items-baseline justify-between gap-3">
        <h3 id={`history-${anomalyId}`} className="text-xs font-semibold uppercase tracking-wider text-muted">
          Yıllar içinde · Esri Wayback
        </h3>
        {data?.status === "ready" && (
          <span className="font-mono text-[11px] tabular-nums text-muted-foreground">
            {data.snapshots.length} farklı görüntü
          </span>
        )}
      </div>

      {error ? (
        <div className="flex items-center justify-between gap-3 rounded-xl border border-border bg-surface/60 px-3 py-2.5">
          <p className="text-xs text-foreground/90">Zaman serisi alınamadı.</p>
          <button
            type="button"
            onClick={() => mutate()}
            className="rounded-lg border border-secondary/30 px-2.5 py-1 text-xs font-medium text-secondary hover:bg-secondary/10"
          >
            Tekrar dene
          </button>
        </div>
      ) : isLoading || !data || data.status === "pending" ? (
        <div className="space-y-2" aria-busy="true">
          <div className={cn("grid gap-2", compact ? "grid-cols-3" : "grid-cols-4")} aria-hidden>
            {Array.from({ length: compact ? 3 : 4 }, (_, i) => (
              <div key={i} className="aspect-square animate-pulse rounded-lg border border-border bg-card" />
            ))}
          </div>
          <p className="text-[11px] text-muted-foreground">
            {data?.status === "pending"
              ? "Hazırlanıyor: Esri'nin arşivlenmiş sürümleri indiriliyor. Birkaç dakika sürebilir; sayfa kendini yeniler."
              : "Yükleniyor…"}
          </p>
        </div>
      ) : data.status === "empty" ? (
        <p className="rounded-xl border border-border bg-surface/60 px-3 py-2.5 text-xs text-muted">
          Esri arşivinde bu konum için birbirinden farklı görüntü bulunamadı.
        </p>
      ) : data.status === "failed" ? (
        <p className="rounded-xl border border-border bg-surface/60 px-3 py-2.5 text-xs text-muted">
          Zaman serisi üretilemedi. Bir saat sonra sayfa açıldığında yeniden denenir.
        </p>
      ) : (
        <ReadyHistory history={data} compact={compact} />
      )}
    </section>
  );
}

function ReadyHistory({ history, compact }: { history: AnomalyHistory; compact: boolean }) {
  const changedOn = new Set(history.changes.map((c) => c.date));

  return (
    <div className="space-y-3">
      {/* Sayfada kareler satıra sarılır (kesik kare bırakmaz); dar panelde yatay kaydırılır. */}
      <ol
        className={cn(
          compact
            ? "-mx-1 flex snap-x snap-mandatory gap-2 overflow-x-auto px-1 pb-1"
            : "grid grid-cols-3 gap-2 sm:grid-cols-4"
        )}
        aria-label="Konumun tarih sırasıyla arşiv görüntüleri"
      >
        {history.snapshots.map((snap) => (
          <li key={snap.image_url} className={cn(compact && "w-[30%] shrink-0 snap-start")}>
            <figure className="space-y-1.5">
              <div className="relative aspect-square overflow-hidden rounded-lg border border-border bg-black">
                <Image
                  src={resolveMediaUrl(snap.image_url) ?? ""}
                  alt={`Esri arşiv görüntüsü, ${formatDay(snap.date)}`}
                  fill
                  unoptimized
                  sizes={compact ? "110px" : "(max-width: 1024px) 23vw, 150px"}
                  className="object-cover [image-rendering:pixelated]"
                />
                {changedOn.has(snap.date) && (
                  <span className="absolute bottom-1 left-1 rounded bg-black/75 px-1.5 py-0.5 text-[10px] font-semibold text-foreground">
                    Değişti
                  </span>
                )}
              </div>
              <figcaption className="font-mono text-[11px] tabular-nums text-muted">{formatDay(snap.date)}</figcaption>
            </figure>
          </li>
        ))}
      </ol>

      {history.changes.length > 0 && (
        <ul className="divide-y divide-border rounded-xl border border-border bg-surface/60 text-xs">
          {history.changes.map((change) => (
            <li key={`${change.date_before}-${change.date}`} className="flex items-baseline justify-between gap-3 px-3 py-2">
              <span className="min-w-0">
                <span className="text-foreground/90">{change.label}</span>
                <span className="block font-mono text-[11px] tabular-nums text-muted-foreground">
                  {formatDay(change.date_before)} → {formatDay(change.date)}
                </span>
              </span>
              <span className="shrink-0 font-mono tabular-nums text-muted">%{formatScore(change.diff_score)} fark</span>
            </li>
          ))}
        </ul>
      )}

      <p className="text-[11px] leading-relaxed text-muted-foreground">
        Puana katılmaz: sıradan şehirler de yıllar içinde bu kadar değişir. Görüntünün ne zaman ve nasıl değiştiğini
        karşılaştırmak içindir. Kaynak: {history.source ?? "Esri World Imagery Wayback"}.
      </p>
    </div>
  );
}
