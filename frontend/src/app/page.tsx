

/**
 * Ana sayfa — harita sayfasına yönlendirir.
 *
 * Şu an için tek sayfa "/" → harita olduğu için
 * doğrudan harita bileşenini render eder.
 * İleride /map route'u eklendiğinde redirect kullanılır.
 */
export default function HomePage() {
  // İleride: redirect("/map");
  // Şimdilik: harita ana sayfada render edilir
  return <MapPage />;
}

// ── Inline Map Page (ileride /map route'a taşınacak) ──────────────────────

import dynamic from "next/dynamic";
import {
  ShieldAlert,
  Layers,
  Activity,
  Search,
  Radar,
  MapPin,

  Crosshair,
} from "lucide-react";

const Map = dynamic(() => import("@/components/Map"), {
  ssr: false,
  loading: () => (
    <div className="absolute inset-0 bg-background flex items-center justify-center">
      <div className="flex flex-col items-center gap-4">
        <div className="h-12 w-12 rounded-full border-3 border-secondary/20 border-t-secondary animate-spin" />
        <span className="text-sm text-muted-foreground animate-pulse">
          Harita yükleniyor...
        </span>
      </div>
    </div>
  ),
});

function MapPage() {
  return (
    <main className="relative w-screen h-screen overflow-hidden bg-background">
      {/* ── Tam Ekran Harita ────────────────────────────────────────── */}
      <div className="absolute inset-0 z-0">
        <Map />
      </div>

      {/* ── Harita Vignette Efekti ──────────────────────────────────── */}
      <div className="absolute inset-0 pointer-events-none z-[1] shadow-[inset_0_0_120px_rgba(0,0,0,0.7)]" />

      {/* ── Üst Navbar — Float ──────────────────────────────────────── */}
      <header className="map-overlay map-overlay-top w-auto max-w-3xl z-30">
        <div className="glass-panel px-5 py-3 flex items-center gap-4">
          {/* Logo */}
          <div className="flex items-center gap-2.5 mr-2">
            <div className="p-1.5 bg-secondary/10 rounded-lg border border-secondary/20">
              <ShieldAlert className="w-5 h-5 text-secondary" />
            </div>
            <h1 className="text-base font-bold text-gradient-brand tracking-tight whitespace-nowrap">
              GhostBuilding
            </h1>
          </div>

          {/* Arama */}
          <div className="flex items-center gap-2 flex-1 min-w-[260px] bg-black/30 rounded-xl px-3 py-1.5 border border-white/5 focus-within:border-secondary/40 focus-within:ring-1 focus-within:ring-secondary/30 transition-all">
            <Search className="w-4 h-4 text-gray-500" />
            <input
              id="search-input"
              type="text"
              placeholder="Koordinat, bölge veya anomali ara..."
              className="bg-transparent border-none outline-none text-sm text-gray-200 w-full placeholder:text-gray-600"
            />
          </div>

          {/* Durum */}
          <div className="flex items-center gap-2 text-[11px] font-semibold text-emerald-400 bg-emerald-400/10 px-3 py-1.5 rounded-lg border border-emerald-400/15 whitespace-nowrap">
            <div className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
            Canlı
          </div>
        </div>
      </header>

      {/* ── Sol Sidebar — Float ─────────────────────────────────────── */}
      <aside className="map-overlay map-overlay-left z-20 flex flex-col gap-3 pt-16">
        {/* Veri Kaynakları */}
        <div className="glass-panel p-4">
          <h2 className="text-[11px] font-bold tracking-widest uppercase mb-3 text-gray-500 flex items-center gap-2">
            <Layers className="w-3.5 h-3.5" /> Veri Kaynakları
          </h2>
          <div className="space-y-2">
            {[
              { name: "Google Maps", color: "bg-blue-400", active: true },
              { name: "OpenStreetMap", color: "bg-emerald-400", active: true },
              { name: "Bing Maps", color: "bg-cyan-400", active: false },
              { name: "Yandex Maps", color: "bg-red-400", active: false },
            ].map((provider) => (
              <label
                key={provider.name}
                className="flex items-center justify-between p-2.5 rounded-xl bg-white/[0.03] hover:bg-white/[0.06] cursor-pointer transition-all border border-transparent hover:border-white/[0.06] group"
              >
                <div className="flex items-center gap-2.5">
                  <div
                    className={`w-3.5 h-3.5 rounded border-2 flex items-center justify-center transition-colors ${
                      provider.active
                        ? "border-secondary bg-secondary"
                        : "border-gray-600 bg-transparent"
                    }`}
                  >
                    {provider.active && (
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
                  <span className="text-xs font-medium text-gray-400 group-hover:text-gray-200 transition-colors">
                    {provider.name}
                  </span>
                </div>
                <div
                  className={`w-1.5 h-1.5 rounded-full ${provider.color} ${
                    provider.active ? "opacity-100" : "opacity-30"
                  }`}
                />
              </label>
            ))}
          </div>
        </div>

        {/* İstihbarat Akışı */}
        <div className="glass-panel p-4 flex-1 overflow-hidden flex flex-col min-h-0">
          <h2 className="text-[11px] font-bold tracking-widest uppercase mb-3 text-gray-500 flex items-center gap-2">
            <Activity className="w-3.5 h-3.5" /> İstihbarat Akışı
          </h2>
          <div className="space-y-2 overflow-y-auto flex-1 pr-1 thin-scrollbar">
            {[
              {
                loc: "Kısıtlı Bölge B",
                diff: "Google Maps'te eksik yapı",
                time: "2 dk",
                status: "critical" as const,
              },
              {
                loc: "Sektör 7G",
                diff: "Çözünürlük uyumsuzluğu",
                time: "45 dk",
                status: "warning" as const,
              },
              {
                loc: "Bilinmeyen Tesis",
                diff: "Sadece yerel kayıtta mevcut",
                time: "3 sa",
                status: "info" as const,
              },
              {
                loc: "Sansür Katmanı",
                diff: "Pikselleştirme atlatma",
                time: "5 sa",
                status: "critical" as const,
              },
            ].map((item, i) => (
              <div
                key={i}
                className="group cursor-pointer p-3 rounded-xl border border-white/[0.04] bg-white/[0.02] hover:bg-white/[0.05] hover:border-white/[0.08] transition-all"
              >
                <div className="flex justify-between items-start gap-2 mb-1">
                  <div className="flex items-center gap-2">
                    <div
                      className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${
                        item.status === "critical"
                          ? "bg-red-400 shadow-[0_0_6px_rgba(248,113,113,0.6)]"
                          : item.status === "warning"
                          ? "bg-yellow-400 shadow-[0_0_6px_rgba(250,204,21,0.6)]"
                          : "bg-blue-400 shadow-[0_0_6px_rgba(96,165,250,0.6)]"
                      }`}
                    />
                    <h3 className="text-xs font-semibold text-gray-300 group-hover:text-white transition-colors">
                      {item.loc}
                    </h3>
                  </div>
                  <span className="text-[9px] uppercase text-gray-600 font-bold bg-black/30 px-1.5 py-0.5 rounded-md whitespace-nowrap">
                    {item.time}
                  </span>
                </div>
                <p className="text-[11px] text-gray-500 leading-relaxed pl-3.5">
                  {item.diff}
                </p>
              </div>
            ))}
          </div>
        </div>
      </aside>

      {/* ── Sağ Alt — Hızlı Eylemler ───────────────────────────────── */}
      <div className="map-overlay z-20 right-4 bottom-6 flex flex-col gap-2">
        <button
          id="btn-scan"
          className="glass-panel p-3 hover:bg-secondary/10 transition-colors group"
          title="Tarama Başlat"
        >
          <Radar className="w-5 h-5 text-secondary group-hover:text-secondary-300 transition-colors" />
        </button>
        <button
          id="btn-locate"
          className="glass-panel p-3 hover:bg-white/5 transition-colors group"
          title="Konumuma Git"
        >
          <Crosshair className="w-5 h-5 text-gray-400 group-hover:text-white transition-colors" />
        </button>
      </div>

      {/* ── Alt Bar — Özet İstatistik ───────────────────────────────── */}
      <div className="map-overlay map-overlay-bottom z-20">
        <div className="glass-panel px-5 py-2.5 flex items-center gap-6">
          {[
            { label: "Toplam Anomali", value: "1,247", icon: MapPin },
            { label: "Aktif Tarama", value: "3", icon: Radar },
            { label: "Doğrulanmış", value: "523", icon: ShieldAlert },
          ].map((stat, i) => (
            <div key={i} className="flex items-center gap-2">
              <stat.icon className="w-3.5 h-3.5 text-gray-500" />
              <span className="text-[11px] text-gray-500">{stat.label}</span>
              <span className="text-xs font-bold text-gray-200">
                {stat.value}
              </span>
              {i < 2 && (
                <div className="w-px h-3 bg-white/[0.06] ml-4" />
              )}
            </div>
          ))}
        </div>
      </div>
    </main>
  );
}
