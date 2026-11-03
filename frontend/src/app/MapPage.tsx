"use client";

import dynamic from "next/dynamic";
import { AnomalyDetailPanel } from "@/components/anomaly";
import MapChrome from "@/components/map/MapChrome";
import MapControls from "@/components/map/MapControls";
import { MapStateProvider, useMapContext } from "@/components/map/MapState";
import ScanProgressToast from "@/components/map/ScanProgressToast";

// Kabuk (üst çubuk, paneller, kontroller) harita bağlamıyla birlikte sunucuda render edilir;
// MapLibre bağlamdan ayrıdır. Harita tuvali ve maplibre-gl ayrı bir parça olarak, yalnız
// tarayıcıda ve kabuk çizildikten sonra yüklenir. Yüklenene kadar yerinde yer tutucu durur.
const GhostMap = dynamic(() => import("@/components/map/GhostMap"), {
  ssr: false,
  loading: () => (
    <div className="absolute inset-0 flex items-center justify-center bg-background" role="status">
      <div className="flex flex-col items-center gap-3">
        <div className="size-10 animate-spin rounded-full border-2 border-secondary/25 border-t-secondary" />
        <span className="text-sm text-muted">Harita yükleniyor…</span>
      </div>
    </div>
  ),
});

export default function MapPage() {
  return (
    <main className="relative h-dvh w-full overflow-hidden bg-background">
      <h1 className="sr-only">GhostBuilding — uydu kaynakları arasındaki farkların haritası</h1>
      <div className="absolute inset-0">
        <MapStateProvider>
          <MapScreen />
        </MapStateProvider>
      </div>
    </main>
  );
}

function MapScreen() {
  const { activeScanTaskId, selectedAnomalyId, setSelectedAnomalyId } = useMapContext();

  return (
    <div className="w-full h-full relative">
      <div className="absolute inset-0">
        <GhostMap />
      </div>

      {/* Harita üstü kontroller (zoom, konum, tarama) */}
      <MapControls />

      {/* Tarama İlerleme */}
      {activeScanTaskId && <ScanProgressToast taskId={activeScanTaskId} />}

      {/* Anomali Detay Paneli — sağ kenar */}
      {selectedAnomalyId && (
        <AnomalyDetailPanel
          anomalyId={selectedAnomalyId}
          onClose={() => setSelectedAnomalyId(null)}
        />
      )}

      {/* Kabuk: üst çubuk, sol panel, alt istatistik */}
      <MapChrome />
    </div>
  );
}
