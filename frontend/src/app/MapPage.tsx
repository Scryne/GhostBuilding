"use client";

import { useState, useCallback, useRef } from "react";
import dynamic from "next/dynamic";
import {
  ShieldAlert,
  Layers,
  Activity,
  Search,
  Radar,
  MapPin,
  Crosshair,
  X,
  Loader2,
  Download,
  Compass,
  Globe,
  Eye,
  Settings,
  HelpCircle,
  LogOut,
  ChevronRight,
  Zap,
} from "lucide-react";
import { useAnomalyStats, useAnomalyList } from "@/hooks/useAnomaly";
import type { AnomalyListItem } from "@/lib/types";

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

export default function MapPage() {
  // ── Stats from API ───────────────────────────────────────────────────
  const { data: stats } = useAnomalyStats();
  const totalAnomalies = stats?.total_count ?? 0;
  const verifiedCount = stats?.by_category?.reduce((sum, c) => sum + c.count, 0) ?? 0;

  // ── Recent anomalies for intel feed ──────────────────────────────────
  const { data: recentData } = useAnomalyList({ limit: 6, page: 1 });
  const recentAnomalies = recentData?.data ?? [];

  // ── Search ───────────────────────────────────────────────────────────
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<
    Array<{ display_name: string; lat: number; lng: number }>
  >([]);
  const [isSearching, setIsSearching] = useState(false);
  const [showSearchResults, setShowSearchResults] = useState(false);
  const searchTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  const handleSearch = useCallback(async (query: string) => {
    if (query.length < 2) {
      setSearchResults([]);
      setShowSearchResults(false);
      return;
    }

    // Check if it's coordinates (e.g., "41.0082, 28.9784")
    const coordMatch = query.match(/^(-?\d+\.?\d*)\s*,\s*(-?\d+\.?\d*)$/);
    if (coordMatch) {
      const lat = parseFloat(coordMatch[1]);
      const lng = parseFloat(coordMatch[2]);
      if (lat >= -90 && lat <= 90 && lng >= -180 && lng <= 180) {
        setSearchResults([{ display_name: `📍 ${lat.toFixed(4)}, ${lng.toFixed(4)}`, lat, lng }]);
        setShowSearchResults(true);
        return;
      }
    }

    setIsSearching(true);
    try {
      const resp = await fetch(
        `https://nominatim.openstreetmap.org/search?q=${encodeURIComponent(query)}&format=json&limit=5`,
        { headers: { "User-Agent": "GhostBuilding/1.0" } }
      );
      const data = await resp.json();
      setSearchResults(
        data.map((r: { display_name: string; lat: string; lon: string }) => ({
          display_name: r.display_name,
          lat: parseFloat(r.lat),
          lng: parseFloat(r.lon),
        }))
      );
      setShowSearchResults(true);
    } catch {
      setSearchResults([]);
    } finally {
      setIsSearching(false);
    }
  }, []);

  const handleSearchInput = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const value = e.target.value;
      setSearchQuery(value);

      if (searchTimeoutRef.current) clearTimeout(searchTimeoutRef.current);
      searchTimeoutRef.current = setTimeout(() => handleSearch(value), 400);
    },
    [handleSearch]
  );

  const handleSearchSelect = useCallback(
    (result: { lat: number; lng: number }) => {
      // Dispatch custom event for map to fly to location
      window.dispatchEvent(
        new CustomEvent("ghostbuilding:flyto", {
          detail: { lat: result.lat, lng: result.lng, zoom: 14 },
        })
      );
      setShowSearchResults(false);
      setSearchQuery("");
    },
    []
  );

  // ── Provider toggles ────────────────────────────────────────────────
  const [providers, setProviders] = useState([
    { name: "Google Maps", color: "bg-blue-400", active: true },
    { name: "OpenStreetMap", color: "bg-emerald-400", active: true },
    { name: "Bing Maps", color: "bg-cyan-400", active: false },
    { name: "Yandex Maps", color: "bg-red-400", active: false },
  ]);

  const toggleProvider = useCallback((index: number) => {
    setProviders((prev) =>
      prev.map((p, i) => (i === index ? { ...p, active: !p.active } : p))
    );
  }, []);

  // ── Scan action ──────────────────────────────────────────────────────
  const [isScanning, setIsScanning] = useState(false);

  const handleScan = useCallback(async () => {
    setIsScanning(true);
    // Dispatch scan event for GhostMap to handle
    window.dispatchEvent(new CustomEvent("ghostbuilding:scan"));
    setTimeout(() => setIsScanning(false), 2000);
  }, []);

  // ── Geolocation ──────────────────────────────────────────────────────
  const handleLocate = useCallback(() => {
    if (!navigator.geolocation) return;
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        window.dispatchEvent(
          new CustomEvent("ghostbuilding:flyto", {
            detail: {
              lat: pos.coords.latitude,
              lng: pos.coords.longitude,
              zoom: 14,
            },
          })
        );
      },
      () => {
        // Geolocation denied — silently ignore
      },
      { enableHighAccuracy: true, timeout: 10000 }
    );
  }, []);

  // ── Status category badge color ────────────────────────────────────
  const getCategoryBadge = (category: string) => {
    switch (category) {
      case "GHOST_BUILDING":
        return { label: "Hayalet Yapı", color: "bg-red-400", dotColor: "#F87171", glow: "shadow-[0_0_6px_rgba(248,113,113,0.5)]" };
      case "CENSORED_AREA":
        return { label: "Sansürlü", color: "bg-amber-400", dotColor: "#FBBF24", glow: "shadow-[0_0_6px_rgba(251,191,36,0.5)]" };
      case "HIDDEN_STRUCTURE":
        return { label: "Gizli Yapı", color: "bg-violet-400", dotColor: "#A78BFA", glow: "shadow-[0_0_6px_rgba(167,139,250,0.5)]" };
      default:
        return { label: "Görüntü Farkı", color: "bg-blue-400", dotColor: "#60A5FA", glow: "shadow-[0_0_6px_rgba(96,165,250,0.5)]" };
    }
  };

  const formatTimeAgo = (dateStr: string | null) => {
    if (!dateStr) return "";
    const diff = Date.now() - new Date(dateStr).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 60) return `${mins} dk`;
    const hours = Math.floor(mins / 60);
    if (hours < 24) return `${hours} sa`;
    return `${Math.floor(hours / 24)} gün`;
  };

  // ── Sidebar collapsed state ─────────────────────────────────────────
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  return (
    <main className="relative w-screen h-screen overflow-hidden bg-background">
      {/* ── Tam Ekran Harita ────────────────────────────────────────── */}
      <div className="absolute inset-0 z-0">
        <Map />
      </div>

      {/* ── Harita Vignette Efekti ──────────────────────────────────── */}
      <div className="absolute inset-0 pointer-events-none z-[1] shadow-[inset_0_0_120px_rgba(0,0,0,0.6)]" />

      {/* ── Üst Navbar — Premium Dashboard Style ───────────────────── */}
      <header className="map-overlay map-overlay-top w-auto max-w-3xl z-30">
        <div className="glass-panel-strong px-4 py-2.5 flex items-center gap-3 relative">
          {/* Logo */}
          <div className="flex items-center gap-2.5 mr-1">
            <div className="p-2 bg-gradient-primary rounded-xl shadow-glow-sm">
              <ShieldAlert className="w-4.5 h-4.5 text-white" />
            </div>
            <h1 className="text-sm font-bold text-gradient-brand tracking-tight whitespace-nowrap">
              GhostBuilding
            </h1>
          </div>

          {/* Separator */}
          <div className="w-px h-5 bg-white/[0.06]" />

          {/* Arama — Fonksiyonel */}
          <div className="relative flex-1 min-w-[240px]">
            <div className="flex items-center gap-2 bg-black/25 rounded-xl px-3 py-1.5 border border-white/[0.05] focus-within:border-secondary/40 focus-within:ring-1 focus-within:ring-secondary/20 transition-all">
              {isSearching ? (
                <Loader2 className="w-3.5 h-3.5 text-secondary animate-spin" />
              ) : (
                <Search className="w-3.5 h-3.5 text-muted-foreground" />
              )}
              <input
                id="search-input"
                type="text"
                value={searchQuery}
                onChange={handleSearchInput}
                onFocus={() => searchResults.length > 0 && setShowSearchResults(true)}
                onBlur={() => setTimeout(() => setShowSearchResults(false), 200)}
                placeholder="Koordinat, bölge veya anomali ara..."
                className="bg-transparent border-none outline-none text-sm text-gray-200 w-full placeholder:text-muted-foreground/50"
              />
              {searchQuery && (
                <button
                  onClick={() => {
                    setSearchQuery("");
                    setSearchResults([]);
                    setShowSearchResults(false);
                  }}
                  className="text-muted-foreground hover:text-white transition-colors"
                >
                  <X className="w-3 h-3" />
                </button>
              )}
            </div>

            {/* Search Results Dropdown */}
            {showSearchResults && searchResults.length > 0 && (
              <div className="absolute top-full left-0 right-0 mt-2 glass-panel-strong p-2 space-y-0.5 max-h-64 overflow-y-auto thin-scrollbar animate-slide-down">
                {searchResults.map((result, i) => (
                  <button
                    key={i}
                    onMouseDown={() => handleSearchSelect(result)}
                    className="w-full text-left p-2.5 rounded-lg hover:bg-white/[0.05] transition-colors flex items-start gap-2.5 group"
                  >
                    <div className="p-1 rounded-md bg-secondary/10 mt-0.5 flex-shrink-0">
                      <MapPin className="w-3 h-3 text-secondary" />
                    </div>
                    <span className="text-xs text-gray-300 leading-relaxed line-clamp-2 group-hover:text-white transition-colors">
                      {result.display_name}
                    </span>
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Live Status Badge */}
          <div className="flex items-center gap-1.5 text-[10px] font-bold text-emerald-400 bg-emerald-500/10 px-2.5 py-1.5 rounded-lg border border-emerald-500/15 whitespace-nowrap">
            <div className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
            Canlı
          </div>
        </div>
      </header>

      {/* ── Sol Sidebar — Dashboard Navigation Style ───────────────── */}
      <aside className={`map-overlay z-20 flex flex-col gap-2.5 pt-16 transition-all duration-300 ${sidebarCollapsed ? 'left-1 top-1 bottom-1 w-[52px]' : 'map-overlay-left'}`}>
        
        {/* Veri Kaynakları — Toggle Cards */}
        <div className="glass-panel p-3.5 animate-fade-in">
          <div className="flex items-center justify-between mb-3">
            <h2 className="nav-section-title !p-0 !m-0 flex items-center gap-1.5">
              <Layers className="w-3 h-3" /> Veri Kaynakları
            </h2>
            <span className="text-[9px] font-bold text-secondary bg-secondary/10 px-1.5 py-0.5 rounded-md">
              {providers.filter(p => p.active).length}/{providers.length}
            </span>
          </div>
          <div className="space-y-1.5">
            {providers.map((provider, index) => (
              <label
                key={provider.name}
                onClick={() => toggleProvider(index)}
                className="flex items-center justify-between p-2.5 rounded-xl bg-white/[0.02] hover:bg-white/[0.04] cursor-pointer transition-all border border-transparent hover:border-white/[0.05] group"
              >
                <div className="flex items-center gap-2.5">
                  <div
                    className={`w-4 h-4 rounded-md border-2 flex items-center justify-center transition-all duration-200 ${
                      provider.active
                        ? "border-secondary bg-secondary shadow-glow-sm"
                        : "border-gray-600/50 bg-transparent"
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
                  <span className="text-xs font-medium text-muted group-hover:text-foreground transition-colors">
                    {provider.name}
                  </span>
                </div>
                <div
                  className={`w-2 h-2 rounded-full transition-all duration-200 ${provider.color} ${
                    provider.active ? "opacity-100 scale-100" : "opacity-25 scale-75"
                  }`}
                />
              </label>
            ))}
          </div>
        </div>

        {/* İstihbarat Akışı — Recent Anomalies */}
        <div className="glass-panel p-3.5 flex-1 overflow-hidden flex flex-col min-h-0 animate-fade-in" style={{ animationDelay: '0.1s' }}>
          <div className="flex items-center justify-between mb-3">
            <h2 className="nav-section-title !p-0 !m-0 flex items-center gap-1.5">
              <Activity className="w-3 h-3" /> İstihbarat Akışı
            </h2>
            <div className="flex items-center gap-1 text-[9px] font-bold text-secondary">
              <Zap className="w-3 h-3" />
              {recentAnomalies.length > 0 ? recentAnomalies.length : '—'}
            </div>
          </div>
          <div className="space-y-1.5 overflow-y-auto flex-1 pr-1 thin-scrollbar">
            {recentAnomalies.length > 0
              ? recentAnomalies.map((anomaly: AnomalyListItem) => {
                  const badge = getCategoryBadge(anomaly.category);
                  return (
                    <div
                      key={anomaly.id}
                      onClick={() =>
                        window.dispatchEvent(
                          new CustomEvent("ghostbuilding:flyto", {
                            detail: { lat: anomaly.lat, lng: anomaly.lng, zoom: 16 },
                          })
                        )
                      }
                      className="group cursor-pointer p-3 rounded-xl border border-white/[0.03] bg-white/[0.015] hover:bg-white/[0.04] hover:border-white/[0.07] transition-all duration-200"
                    >
                      <div className="flex justify-between items-start gap-2 mb-1.5">
                        <div className="flex items-center gap-2">
                          <div
                            className={`w-2 h-2 rounded-full flex-shrink-0 ${badge.glow}`}
                            style={{ backgroundColor: badge.dotColor }}
                          />
                          <h3 className="text-xs font-semibold text-gray-300 group-hover:text-white transition-colors leading-tight">
                            {anomaly.title || badge.label}
                          </h3>
                        </div>
                        <span className="text-[9px] uppercase text-muted-foreground font-bold bg-black/20 px-1.5 py-0.5 rounded-md whitespace-nowrap">
                          {formatTimeAgo(anomaly.detected_at)}
                        </span>
                      </div>
                      <div className="flex items-center justify-between pl-4">
                        <p className="text-[10px] text-muted-foreground leading-relaxed">
                          Skor: <span className="font-semibold text-secondary">{anomaly.confidence_score.toFixed(1)}%</span>
                        </p>
                        <p className="text-[10px] text-muted-foreground font-mono">
                          {anomaly.lat.toFixed(4)}, {anomaly.lng.toFixed(4)}
                        </p>
                      </div>
                    </div>
                  );
                })
              : /* Fallback — API henüz bağlı değilse placeholder */
                [
                  { loc: "Veri yükleniyor...", diff: "API bağlantısı bekleniyor", time: "—", status: "info" as const },
                ].map((item, i) => (
                  <div
                    key={i}
                    className="p-3 rounded-xl border border-white/[0.03] bg-white/[0.015] animate-pulse"
                  >
                    <div className="flex items-center gap-2 mb-1">
                      <div className="w-2 h-2 rounded-full bg-blue-400/40" />
                      <span className="text-xs text-muted-foreground">{item.loc}</span>
                    </div>
                    <p className="text-[10px] text-muted-foreground/50 pl-4">{item.diff}</p>
                  </div>
                ))}
          </div>
        </div>

        {/* Pro/Upgrade Card */}
        <div className="promo-card animate-fade-in" style={{ animationDelay: '0.2s' }}>
          <div className="relative z-10">
            <div className="flex items-center gap-2 mb-2">
              <div className="p-1.5 bg-secondary/15 rounded-lg">
                <Compass className="w-4 h-4 text-secondary" />
              </div>
              <div>
                <p className="text-xs font-bold text-white">GhostBuilding Pro</p>
                <p className="text-[10px] text-muted-foreground">Gelişmiş OSINT araçları</p>
              </div>
            </div>
            <button className="w-full mt-2 py-2 rounded-lg bg-gradient-primary text-white text-xs font-semibold hover:shadow-glow transition-all duration-200">
              Keşfet
            </button>
          </div>
        </div>
      </aside>

      {/* ── Sağ Alt — Hızlı Eylemler (Fonksiyonel) ──────────────────── */}
      <div className="map-overlay z-20 right-4 bottom-6 flex flex-col gap-2">
        <button
          id="btn-scan"
          onClick={handleScan}
          disabled={isScanning}
          className="glass-panel p-3 hover:bg-secondary/10 transition-all duration-200 group disabled:opacity-50 hover:border-secondary/20"
          title="Tarama Başlat"
        >
          <Radar
            className={`w-5 h-5 text-secondary group-hover:text-secondary-300 transition-colors ${
              isScanning ? "animate-spin" : ""
            }`}
          />
        </button>
        <button
          id="btn-locate"
          onClick={handleLocate}
          className="glass-panel p-3 hover:bg-white/5 transition-all duration-200 group hover:border-white/10"
          title="Konumuma Git"
        >
          <Crosshair className="w-5 h-5 text-muted group-hover:text-white transition-colors" />
        </button>
        <a
          href="/api/v1/anomalies/export?format=csv"
          target="_blank"
          rel="noopener noreferrer"
          className="glass-panel p-3 hover:bg-white/5 transition-all duration-200 group hover:border-emerald-500/15"
          title="Verileri İndir (CSV)"
        >
          <Download className="w-5 h-5 text-muted group-hover:text-emerald-400 transition-colors" />
        </a>
      </div>

      {/* ── Alt Bar — Dashboard Stats ─────────────────────────────────── */}
      <div className="map-overlay map-overlay-bottom z-20">
        <div className="glass-panel-strong px-5 py-2.5 flex items-center gap-5">
          {[
            { label: "Toplam Anomali", value: totalAnomalies.toLocaleString("tr-TR"), icon: MapPin, color: "#4A7CF7" },
            { label: "Aktif Tarama", value: isScanning ? "1" : "0", icon: Radar, color: "#10B981" },
            { label: "Doğrulanmış", value: verifiedCount.toLocaleString("tr-TR"), icon: ShieldAlert, color: "#F4A261" },
          ].map((stat, i) => (
            <div key={i} className="flex items-center gap-2.5">
              <div
                className="p-1.5 rounded-lg"
                style={{ backgroundColor: `${stat.color}15`, border: `1px solid ${stat.color}20` }}
              >
                <stat.icon className="w-3 h-3" style={{ color: stat.color }} />
              </div>
              <div className="flex flex-col">
                <span className="text-xs font-bold text-foreground tabular-nums">
                  {stat.value}
                </span>
                <span className="text-[9px] text-muted-foreground font-medium uppercase tracking-wider">
                  {stat.label}
                </span>
              </div>
              {i < 2 && (
                <div className="w-px h-6 bg-white/[0.05] ml-2.5" />
              )}
            </div>
          ))}
        </div>
      </div>
    </main>
  );
}
