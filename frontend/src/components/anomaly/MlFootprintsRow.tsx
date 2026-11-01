// ═══════════════════════════════════════════════════════════════════════════
// MlFootprintsRow.tsx — Microsoft ML bina izleri ↔ OSM (kanıt satırı, puan değil)
// OSM'de bina olup Bing görüntüsünden çıkarılmış ML izi olmayan karo, binaların bağımsız
// dördüncü bir sağlayıcıda da görünmediğini düşündürür. Deneyde tabanda yanlış alarm 0/49,
// referans tesislerde 5/12 (hepsi Fransa); örneklem küçük olduğu için puana katılmaz ve
// satır taban ölçüsüyle birlikte gösterilir (docs/spike-bina-izleri.md, Deneme 2).
// ═══════════════════════════════════════════════════════════════════════════

"use client";

import useSWR from "swr";
import { anomalyApi } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { AnomalyMlFootprints } from "@/lib/types";

const PENDING_POLL_MS = 8000;
const sayi = new Intl.NumberFormat("tr-TR");
const yuzde = new Intl.NumberFormat("tr-TR", { style: "percent", maximumFractionDigits: 1 });

export default function MlFootprintsRow({ anomalyId }: { anomalyId: string }) {
  const { data, error } = useSWR<AnomalyMlFootprints>(
    ["anomaly-ml-footprints", anomalyId],
    () => anomalyApi.getMlFootprints(anomalyId),
    {
      refreshInterval: (latest) => (latest?.status === "pending" ? PENDING_POLL_MS : 0),
      revalidateOnFocus: false,
    }
  );

  if (data?.status === "disabled") return null;

  return (
    <section aria-labelledby={`ml-${anomalyId}`} className="space-y-2">
      <h3 id={`ml-${anomalyId}`} className="text-xs font-semibold uppercase tracking-wider text-muted">
        Bağımsız sağlayıcı · Microsoft ML bina izleri
      </h3>
      <div
        className={cn(
          "rounded-xl border px-3 py-2.5 text-xs",
          data?.status === "ready" && data.flag
            ? "border-warning/40 bg-warning/10"
            : "border-border bg-surface/60"
        )}
      >
        {error ? (
          <p className="text-foreground/90">ML izi kanıtı alınamadı.</p>
        ) : !data || data.status === "pending" ? (
          <p className="text-muted-foreground" aria-busy="true">
            Hazırlanıyor: bölgenin ML izi dosyası indiriliyor (onlarca MB, bir kez). Sayfa kendini yeniler.
          </p>
        ) : data.status === "no_coverage" ? (
          <p className="text-muted">Microsoft bu bölge için ML izi yayımlamıyor; kıyas yapılamadı.</p>
        ) : data.status === "failed" ? (
          <p className="text-muted">Kanıt üretilemedi. Bir saat sonra sayfa açıldığında yeniden denenir.</p>
        ) : (
          <ReadyRow data={data} />
        )}
      </div>
    </section>
  );
}

function ReadyRow({ data }: { data: AnomalyMlFootprints }) {
  const osm = data.osm ?? 0;
  const ml = data.ml ?? 0;
  const b = data.baseline;
  return (
    <div className="space-y-1.5">
      <p className={cn("text-foreground/90", data.flag && "font-medium")}>
        {data.flag
          ? `Microsoft ML izleri bu karoda neredeyse yok (OSM: ${sayi.format(osm)} bina, ML: ${sayi.format(ml)}).`
          : `ML izleri OSM ile uyumlu (OSM: ${sayi.format(osm)} bina, ML: ${sayi.format(ml)}).`}
      </p>
      <p className="font-mono text-[11px] tabular-nums text-muted-foreground">
        ML payı {data.ml_share == null ? "—" : yuzde.format(data.ml_share)} · işaret eşiği: OSM ≥{" "}
        {data.rule?.osm_min ?? 4} bina ve ML payı &lt; {yuzde.format(data.rule?.ml_share_max ?? 0.02)}
      </p>
      {b && (
        <p className="text-[11px] text-muted-foreground">
          Taban ölçüsü: sıradan konumlarda yanlış alarm {b.false_alarms}/{b.baseline_n}, referans tesislerde{" "}
          {b.reference_hits}/{b.reference_n}. Puana katılmaz; görüntü Bing arşivinden (2022–2023).
        </p>
      )}
    </div>
  );
}
