// ═══════════════════════════════════════════════════════════════════════════
// EvidenceView.tsx — Bir anomalinin kanıt dosyası
// Harita yan paneli (variant="panel") ve /explore/[id] sayfası (variant="page") aynı
// içeriği kullanır: kaynak karoları yan yana, neden işaretlendiği, sinyal puanları,
// topluluk doğrulaması ve künye.
// ═══════════════════════════════════════════════════════════════════════════

"use client";

import Image from "next/image";
import useSWR from "swr";
import { useCallback } from "react";
import { resolveMediaUrl, verificationApi } from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";
import {
  BASELINE_P99_SCORE,
  CATEGORY_COLORS,
  CATEGORY_LABELS,
  STATUS_COLORS,
  cn,
  describeScore,
  formatCoordsDMS,
  formatCoordsDecimal,
  formatDate,
  formatScore,
  providerMeta,
} from "@/lib/utils";
import { AnomalyCategory, type AnomalyDetail, type VerificationVote } from "@/lib/types";
import ProviderComparison from "./ProviderComparison";
import VerificationPanel from "./VerificationPanel";
import HistoryStrip from "./HistoryStrip";

const PROVIDER_ORDER = ["esri", "maptiler", "ign"];

const METHOD_LABELS: Record<string, string> = {
  pixel_diff: "Piksel farkı",
  ssim: "Yapısal benzerlik (SSIM)",
  histogram_comparison: "Histogram karşılaştırması",
  blur_detection: "Bulanıklık (Laplacian)",
  fft_analysis: "Frekans analizi (FFT)",
  regional_blur_map: "Bölgesel bulanıklık haritası",
  geospatial_cross_reference: "OSM ↔ görüntü eşleştirme",
  yolo_v8: "Bina dedektörü",
};

interface EvidenceViewProps {
  detail: AnomalyDetail;
  variant?: "panel" | "page";
  onUpdated?: () => void;
}

export default function EvidenceView({ detail, variant = "panel", onUpdated }: EvidenceViewProps) {
  const { isAuthenticated } = useAuth();
  const { data: summary, mutate: mutateSummary } = useSWR(
    ["verification-summary", detail.id],
    () => verificationApi.getSummary(detail.id)
  );

  const handleVote = useCallback(
    async (vote: VerificationVote, comment?: string) => {
      await verificationApi.verify(detail.id, { vote, comment });
      await mutateSummary();
      onUpdated?.();
    },
    [detail.id, mutateSummary, onUpdated]
  );

  const meta = detail.meta_data ?? {};
  const breakdown = meta.score_breakdown;
  const category = CATEGORY_COLORS[detail.category];
  const status = STATUS_COLORS[detail.status];
  const images = [...detail.images].sort(
    (a, b) =>
      PROVIDER_ORDER.indexOf(a.provider.toLowerCase()) -
      PROVIDER_ORDER.indexOf(b.provider.toLowerCase())
  );

  const blurred = meta.most_blurred_provider?.toLowerCase();
  const sharpest = meta.sharpest_provider?.toLowerCase();
  const diffPair = (meta.max_diff_pair ?? null)?.map((p) => p.toLowerCase());
  const initialPair: [string, string] | undefined =
    detail.category === AnomalyCategory.CENSORED_AREA && blurred && sharpest
      ? [blurred, sharpest]
      : diffPair && diffPair.length === 2
        ? [diffPair[0], diffPair[1]]
        : undefined;

  const isPage = variant === "page";

  const header = (
    <header className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <span
          className={cn(
            "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[11px] font-semibold",
            category.bg,
            category.text,
            category.border
          )}
        >
          <span className={cn("size-1.5 rounded-full", category.dot)} aria-hidden />
          {CATEGORY_LABELS[detail.category]}
        </span>
        <span
          className={cn(
            "rounded-full border px-2.5 py-0.5 text-[11px] font-semibold",
            status.bg,
            status.text,
            status.border
          )}
        >
          {status.label}
        </span>
        {meta.reference_scan && (
          <span className="rounded-full border border-border px-2.5 py-0.5 text-[11px] text-muted">
            Referans taraması
          </span>
        )}
      </div>
      <div>
        {isPage ? (
          <h1 className="text-2xl sm:text-3xl font-bold text-foreground text-balance">
            {detail.location_label ?? CATEGORY_LABELS[detail.category]}
          </h1>
        ) : (
          <h2 className="text-lg font-bold text-foreground text-balance">
            {detail.location_label ?? CATEGORY_LABELS[detail.category]}
          </h2>
        )}
        <p className="mt-1 font-mono text-xs text-muted">
          {formatCoordsDecimal(detail.lat, detail.lng)} · {formatDate(detail.detected_at)}
        </p>
      </div>
      <ScoreBlock score={detail.confidence_score} hex={category.hex} />
    </header>
  );

  const evidence = (
    <section aria-labelledby={`evidence-${detail.id}`} className="space-y-3">
      <SectionTitle id={`evidence-${detail.id}`}>Kaynak karoları · aynı konum, aynı zoom</SectionTitle>
      <div className={cn("grid gap-2", images.length >= 3 ? "grid-cols-3" : "grid-cols-2")}>
        {images.map((img) => {
          const p = img.provider.toLowerCase();
          const pm = providerMeta(p);
          const flag =
            p === blurred ? "En bulanık" : p === sharpest ? "En yüksek kenar keskinliği" : diffPair?.includes(p) ? "En farklı çift" : null;
          return (
            <figure key={img.id} className="space-y-1.5">
              <div className="relative aspect-square overflow-hidden rounded-lg border border-border bg-black">
                <Image
                  src={resolveMediaUrl(img.image_url) ?? ""}
                  alt={`${pm.label} karosu, ${detail.location_label ?? "anomali konumu"}`}
                  fill
                  unoptimized
                  sizes={isPage ? "(max-width: 1024px) 33vw, 260px" : "130px"}
                  className="object-cover [image-rendering:pixelated]"
                />
                {flag && (
                  <span className="absolute bottom-1 left-1 rounded bg-black/75 px-1.5 py-0.5 text-[10px] font-semibold text-foreground">
                    {flag}
                  </span>
                )}
              </div>
              <figcaption className="flex items-center gap-1.5 text-[11px] text-muted">
                <span className="size-1.5 rounded-full" style={{ backgroundColor: pm.hex }} aria-hidden />
                {pm.label}
              </figcaption>
            </figure>
          );
        })}
      </div>
      <p className="text-[10px] leading-relaxed text-muted-foreground">
        {images.map((img) => providerMeta(img.provider).attribution).filter(Boolean).join(" · ")}
      </p>
    </section>
  );

  const why = (
    <section aria-labelledby={`why-${detail.id}`} className="space-y-3">
      <SectionTitle id={`why-${detail.id}`}>Neden işaretlendi</SectionTitle>
      {detail.description && (
        <p className="text-sm leading-relaxed text-foreground/90">{detail.description}</p>
      )}
      {breakdown && (
        <dl className="divide-y divide-border rounded-xl border border-border bg-surface/60">
          <SignalRow
            label="Piksel farkı"
            raw={rawLine(
              breakdown.raw_max_diff != null ? `En farklı iki karo %${formatScore(breakdown.raw_max_diff)} farklı` : undefined,
              breakdown.raw_max_diff_p90 != null ? `%${formatScore(breakdown.raw_max_diff_p90)}` : undefined,
            )}
            score={breakdown.pixel_diff_score}
          />
          <SignalRow
            label="Bulanıklık farkı"
            raw={rawLine(
              breakdown.raw_censorship != null ? `Ham skor ${formatScore(breakdown.raw_censorship)}` : undefined,
              breakdown.raw_censorship_p90 != null ? formatScore(breakdown.raw_censorship_p90) : undefined,
            )}
            score={breakdown.blur_censorship_score}
          />
          {(breakdown.inactive_signals ?? []).map((reason) => (
            <div key={reason} className="px-3 py-2.5">
              <dt className="text-xs font-medium text-muted">{inactiveLabel(reason)}</dt>
              <dd className="mt-0.5 text-[11px] text-muted-foreground">{inactiveReason(reason)}</dd>
            </div>
          ))}
        </dl>
      )}
      {meta.reasons && meta.reasons.length > 0 && (
        <ul className="space-y-1 text-xs text-muted">
          {meta.reasons.map((r) => (
            <li key={r} className="flex gap-2">
              <span aria-hidden className="text-muted-foreground">—</span>
              <span>{r}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );

  const compare =
    images.length >= 2 ? (
      <section aria-labelledby={`compare-${detail.id}`} className="space-y-3">
        <SectionTitle id={`compare-${detail.id}`}>Üst üste karşılaştır</SectionTitle>
        <ProviderComparison images={images} initialPair={initialPair} />
      </section>
    ) : null;

  const history = <HistoryStrip anomalyId={detail.id} compact={!isPage} />;

  const verification = (
    <section>
      <VerificationPanel
        anomalyId={detail.id}
        summary={summary ?? null}
        isLoggedIn={isAuthenticated}
        onVote={handleVote}
      />
    </section>
  );

  const record = (
    <section aria-labelledby={`record-${detail.id}`} className="space-y-2">
      <SectionTitle id={`record-${detail.id}`}>Künye</SectionTitle>
      <dl className="divide-y divide-border rounded-xl border border-border bg-surface/60 text-xs">
        <MetaRow label="Koordinat" value={<span className="font-mono">{formatCoordsDMS(detail.lat, detail.lng)}</span>} />
        <MetaRow label="Tespit" value={formatDate(detail.detected_at)} />
        {detail.detection_methods && detail.detection_methods.length > 0 && (
          <MetaRow
            label="Yöntemler"
            value={detail.detection_methods.map((m) => METHOD_LABELS[m] ?? m).join(", ")}
          />
        )}
        <MetaRow label="Kayıt" value={<span className="font-mono select-all">{detail.id.slice(0, 8)}</span>} />
      </dl>
    </section>
  );

  if (isPage) {
    return (
      <div className="grid gap-8 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]">
        <div className="space-y-8 min-w-0">
          {header}
          {evidence}
          {compare}
          {history}
        </div>
        <div className="space-y-8 min-w-0">
          {why}
          {verification}
          {record}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {header}
      {evidence}
      {why}
      {compare}
      {history}
      {verification}
      {record}
    </div>
  );
}

// ── Parçalar ──────────────────────────────────────────────────────────────

function SectionTitle({ id, children }: { id: string; children: React.ReactNode }) {
  return (
    <h3 id={id} className="text-xs font-semibold uppercase tracking-wider text-muted">
      {children}
    </h3>
  );
}

/** Puan + taban çizgisi: 50 = sıradan konumların %99'u. */
export function ScoreScale({ score, hex, className }: { score: number; hex: string; className?: string }) {
  return (
    <div className={cn("relative h-2 rounded-full bg-white/[0.06]", className)} aria-hidden>
      <div
        className="absolute inset-y-0 left-0 rounded-full"
        style={{ width: `${Math.min(100, Math.max(0, score))}%`, backgroundColor: hex }}
      />
      <div
        className="absolute -inset-y-1 w-px bg-foreground/70"
        style={{ left: `${BASELINE_P99_SCORE}%` }}
      />
    </div>
  );
}

function ScoreBlock({ score, hex }: { score: number; hex: string }) {
  return (
    <div className="rounded-xl border border-border bg-surface/60 p-3">
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-xs text-muted">Anomali puanı</span>
        <span className="font-mono text-xl font-bold tabular-nums text-foreground">
          {formatScore(score)}
          <span className="text-xs font-normal text-muted"> / 100</span>
        </span>
      </div>
      <ScoreScale score={score} hex={hex} className="mt-2.5" />
      <p className="mt-2 text-xs text-foreground/90">{describeScore(score)}</p>
      <p className="mt-0.5 text-[11px] text-muted-foreground">
        Dikey çizgi 50: sıradan konumların %99&apos;u bu puanın altında kalır.
      </p>
    </div>
  );
}

function SignalRow({ label, raw, score }: { label: string; raw?: string; score: number }) {
  const flagged = score > BASELINE_P99_SCORE;
  return (
    <div className="px-3 py-2.5">
      <div className="flex items-baseline justify-between gap-3">
        <dt className={cn("text-xs font-medium", flagged ? "text-foreground" : "text-muted")}>{label}</dt>
        <dd className="font-mono text-xs tabular-nums text-foreground">{formatScore(score)}</dd>
      </div>
      <ScoreScale score={score} hex={flagged ? "#F0F2F5" : "#5A5F72"} className="mt-2 h-1.5" />
      {raw && <p className="mt-1 text-[11px] text-muted-foreground">{raw}</p>}
    </div>
  );
}

function MetaRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4 px-3 py-2">
      <dt className="shrink-0 text-muted">{label}</dt>
      <dd className="text-right text-foreground/90">{value}</dd>
    </div>
  );
}

/** Ham ölçüm + sıradan konumlarda normal sayılan üst sınır (taban p90). */
function rawLine(measured?: string, p90?: string): string | undefined {
  if (!measured) return undefined;
  return p90 ? `${measured} · sıradan konumların %90'ı en fazla ${p90}` : measured;
}

function inactiveLabel(reason: string): string {
  if (reason.startsWith("geospatial")) return "OSM ↔ görüntü karşılaştırması · kapalı";
  if (reason.startsWith("historical")) return "Tarihsel değişim · puana katılmaz";
  return reason.split(":")[0];
}

function inactiveReason(reason: string): string {
  if (reason.startsWith("geospatial"))
    return "Hava görüntüsünde bina tanıyan bir model tanımlı değil; genel amaçlı model yukarıdan bina tanımaz, sonuç uydurma olurdu.";
  if (reason.startsWith("historical"))
    return "Ölçüldü: sıradan şehirler de yıllar içinde sürekli değişiyor (60 konumun medyanı 95/100), bu yüzden ayırt etmiyor. Arşiv görüntüleri bu bulgunun kanıtı olarak ayrıca gösteriliyor.";
  return reason;
}
