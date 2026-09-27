"use client";

import dynamic from "next/dynamic";
import MapChrome from "@/components/map/MapChrome";

// MapLibre tarayıcıda çalışır; harita ve kabuk (bağlamı paylaştıkları için) istemcide yüklenir.
const Map = dynamic(() => import("@/components/Map"), {
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
        <Map>
          <MapChrome />
        </Map>
      </div>
    </main>
  );
}
