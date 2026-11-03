// ═══════════════════════════════════════════════════════════════════════════
// MapChrome.tsx — Harita ekranının kabuğu (üst çubuk, sol panel, alt istatistik)
// Sunucuda render edilir (MapLibre beklenmez); filtreler, altlık ve seçim doğrudan
// harita bağlamını (useMapContext) değiştirir.
// ═══════════════════════════════════════════════════════════════════════════

"use client";

import { useState, type FormEvent } from "react";
import Link from "next/link";
import {
  Compass,
  Layers,
  ListFilter,
  Loader2,
  LogIn,
  MapPin,
  Search,
  ShieldAlert,
  User,
  X,
} from "lucide-react";
import { useMapContext, BASEMAPS, type BasemapId } from "./MapState";
import { useAnomalyList, useAnomalyStats } from "@/hooks/useAnomaly";
import { useAuth } from "@/hooks/useAuth";
import {
  BASELINE_P99_SCORE,
  CATEGORY_COLORS,
  CATEGORY_LABELS,
  cn,
  formatRelativeTime,
  formatScore,
} from "@/lib/utils";
import { AnomalyCategory, AnomalyStatus, type AnomalyListItem } from "@/lib/types";

const CATEGORY_ORDER: AnomalyCategory[] = [
  AnomalyCategory.CENSORED_AREA,
  AnomalyCategory.IMAGE_DISCREPANCY,
  AnomalyCategory.GHOST_BUILDING,
  AnomalyCategory.HIDDEN_STRUCTURE,
];

interface SearchHit {
  label: string;
  lat: number;
  lng: number;
}

export default function MapChrome() {
  const [sheetOpen, setSheetOpen] = useState(false);
  const { selectedAnomalyId } = useMapContext();

  return (
    <>
      <TopBar />

      {/* Masaüstü: sol panel */}
      <aside
        className="map-overlay left-4 top-24 bottom-24 hidden w-[320px] md:flex"
        aria-label="Katmanlar ve bulgular"
      >
        <PanelBody />
      </aside>

      {/* Mobil: alt çekmece (bulgu paneli açıkken gizli) */}
      {!selectedAnomalyId && (
      <button
        type="button"
        onClick={() => setSheetOpen(true)}
        className="map-overlay bottom-20 left-1/2 -translate-x-1/2 glass-panel-strong flex items-center gap-2 px-4 py-2.5 text-sm font-medium text-foreground md:hidden"
      >
        <ListFilter className="size-4 text-secondary" aria-hidden /> Katmanlar ve bulgular
      </button>
      )}
      {sheetOpen && (
        <div className="fixed inset-0 z-40 md:hidden" role="dialog" aria-modal="true" aria-label="Katmanlar ve bulgular">
          <button
            type="button"
            className="absolute inset-0 bg-black/50"
            aria-label="Paneli kapat"
            onClick={() => setSheetOpen(false)}
          />
          <div className="absolute inset-x-0 bottom-0 flex max-h-[75dvh] flex-col rounded-t-2xl border-t border-white/10 bg-surface">
            <div className="flex items-center justify-between px-4 pt-3">
              <span className="text-sm font-semibold text-foreground">Katmanlar ve bulgular</span>
              <button
                type="button"
                onClick={() => setSheetOpen(false)}
                className="flex size-9 items-center justify-center rounded-lg text-muted hover:text-foreground"
                aria-label="Kapat"
              >
                <X className="size-4" aria-hidden />
              </button>
            </div>
            <div className="flex min-h-0 flex-1 flex-col p-3">
              <PanelBody onPick={() => setSheetOpen(false)} />
            </div>
          </div>
        </div>
      )}

      <StatsBar />
    </>
  );
}

// ── Üst çubuk ─────────────────────────────────────────────────────────────

function TopBar() {
  const { flyTo } = useMapContext();
  const { isAuthenticated, user } = useAuth();
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<SearchHit[]>([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  // Nominatim kullanım politikası otomatik tamamlamaya izin vermez: arama yalnız gönderimle.
  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    const q = query.trim();
    setMessage(null);
    if (q.length < 2) return;

    const coords = q.match(/^(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)$/);
    if (coords) {
      const lat = parseFloat(coords[1]);
      const lng = parseFloat(coords[2]);
      if (Math.abs(lat) <= 90 && Math.abs(lng) <= 180) {
        flyTo(lat, lng, 15);
        setHits([]);
        return;
      }
    }

    setBusy(true);
    try {
      const resp = await fetch(
        `https://nominatim.openstreetmap.org/search?q=${encodeURIComponent(q)}&format=json&limit=5&accept-language=tr`
      );
      const data: Array<{ display_name: string; lat: string; lon: string }> = await resp.json();
      setHits(data.map((r) => ({ label: r.display_name, lat: parseFloat(r.lat), lng: parseFloat(r.lon) })));
      if (data.length === 0) setMessage("Sonuç yok. Yer adını ya da “enlem, boylam” biçimini deneyin.");
    } catch {
      setMessage("Adres araması şu an yanıt vermiyor. Koordinatla arayabilirsiniz.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <header className="map-overlay inset-x-3 top-3 md:inset-x-auto md:left-1/2 md:w-[min(760px,calc(100vw-2rem))] md:-translate-x-1/2">
      <div className="glass-panel-strong flex items-center gap-2 px-3 py-2">
        <Link href="/" className="flex shrink-0 items-center gap-2 pr-1" aria-label="GhostBuilding ana harita">
          <span className="rounded-lg bg-gradient-primary p-1.5">
            <ShieldAlert className="size-4 text-white" aria-hidden />
          </span>
          <span className="hidden text-sm font-bold text-gradient-brand lg:inline">GhostBuilding</span>
        </Link>

        <form onSubmit={onSubmit} className="relative min-w-0 flex-1" role="search">
          <label htmlFor="map-search" className="sr-only">
            Yer adı ya da koordinat ara
          </label>
          <div className="flex items-center gap-2 rounded-xl border border-white/[0.06] bg-black/30 px-3 py-1.5 focus-within:border-secondary/50">
            {busy ? (
              <Loader2 className="size-4 animate-spin text-secondary" aria-hidden />
            ) : (
              <Search className="size-4 text-muted" aria-hidden />
            )}
            <input
              id="map-search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Yer adı ya da 48.3055, -4.5140"
              className="w-full min-w-0 bg-transparent text-sm text-foreground outline-none placeholder:text-muted-foreground"
              autoComplete="off"
            />
          </div>
          {(hits.length > 0 || message) && (
            <div className="glass-panel-strong absolute inset-x-0 top-full mt-2 max-h-72 overflow-y-auto p-1.5">
              {message && <p className="px-2.5 py-2 text-xs text-muted">{message}</p>}
              {hits.map((hit) => (
                <button
                  key={`${hit.lat},${hit.lng}`}
                  type="button"
                  onClick={() => {
                    flyTo(hit.lat, hit.lng, 14);
                    setHits([]);
                  }}
                  className="flex w-full items-start gap-2 rounded-lg px-2.5 py-2 text-left text-xs text-foreground/90 hover:bg-white/[0.06]"
                >
                  <MapPin className="mt-0.5 size-3.5 shrink-0 text-secondary" aria-hidden />
                  <span className="line-clamp-2">{hit.label}</span>
                </button>
              ))}
              <p className="px-2.5 pb-1 pt-1.5 text-[10px] text-muted-foreground">Arama: © OpenStreetMap Nominatim</p>
            </div>
          )}
        </form>

        <nav className="flex shrink-0 items-center gap-1">
          <Link
            href="/explore"
            aria-label="Keşfet"
            className="inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-sm text-muted hover:bg-white/[0.06] hover:text-foreground"
          >
            <Compass className="size-4" aria-hidden />
            <span className="hidden sm:inline">Keşfet</span>
          </Link>
          {isAuthenticated && user ? (
            <Link
              href={`/profile/${user.username}`}
              aria-label={`Profil: ${user.username}`}
              className="inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-sm text-muted hover:bg-white/[0.06] hover:text-foreground"
            >
              <User className="size-4" aria-hidden />
              <span className="hidden sm:inline">{user.username}</span>
            </Link>
          ) : (
            <Link
              href="/auth/login"
              aria-label="Giriş"
              className="inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-sm text-muted hover:bg-white/[0.06] hover:text-foreground"
            >
              <LogIn className="size-4" aria-hidden />
              <span className="hidden sm:inline">Giriş</span>
            </Link>
          )}
        </nav>
      </div>
    </header>
  );
}

// ── Panel gövdesi (masaüstü panel + mobil çekmece) ─────────────────────────

function PanelBody({ onPick }: { onPick?: () => void }) {
  const {
    basemap,
    setBasemap,
    activeCategories,
    toggleCategory,
    minConfidence,
    setMinConfidence,
    flyTo,
    setSelectedAnomalyId,
  } = useMapContext();
  const { data: stats } = useAnomalyStats();
  const { data: recent, isLoading } = useAnomalyList({ limit: 20, page: 1 });
  const counts = new Map((stats?.by_category ?? []).map((c) => [c.category, c.count]));

  const items = (recent?.data ?? []).filter(
    (a) => activeCategories.has(a.category) && a.confidence_score >= minConfidence
  );

  const open = (a: AnomalyListItem) => {
    flyTo(a.lat, a.lng, 15);
    setSelectedAnomalyId(a.id);
    onPick?.();
  };

  return (
    <div className="glass-panel flex min-h-0 w-full flex-1 flex-col gap-4 overflow-hidden p-3.5">
      {/* Altlık */}
      <section aria-labelledby="basemap-title">
        <h2 id="basemap-title" className="mb-2 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted">
          <Layers className="size-3.5" aria-hidden /> Altlık
        </h2>
        <div className="grid grid-cols-2 gap-1.5" role="radiogroup" aria-labelledby="basemap-title">
          {(Object.keys(BASEMAPS) as BasemapId[])
            .filter((id) => id === "dark" || BASEMAPS[id].tiles)
            .map((id) => {
              const active = basemap === id;
              return (
                <button
                  key={id}
                  type="button"
                  role="radio"
                  aria-checked={active}
                  onClick={() => setBasemap(id)}
                  className={cn(
                    "rounded-lg border px-2.5 py-1.5 text-left text-xs transition-colors",
                    active
                      ? "border-secondary/50 bg-secondary/15 text-foreground"
                      : "border-white/[0.06] text-muted hover:bg-white/[0.04] hover:text-foreground"
                  )}
                >
                  <span className="block font-medium">{BASEMAPS[id].label}</span>
                  {BASEMAPS[id].hint && <span className="block text-[10px] text-muted-foreground">{BASEMAPS[id].hint}</span>}
                </button>
              );
            })}
        </div>
      </section>

      {/* Kategoriler */}
      <section aria-labelledby="category-title">
        <h2 id="category-title" className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-muted">
          Kategoriler
        </h2>
        <ul className="space-y-1">
          {CATEGORY_ORDER.map((cat) => {
            const on = activeCategories.has(cat);
            const count = counts.get(cat) ?? 0;
            return (
              <li key={cat}>
                <label className="flex cursor-pointer items-center gap-2.5 rounded-lg px-2 py-1.5 text-xs hover:bg-white/[0.04]">
                  <input
                    type="checkbox"
                    checked={on}
                    onChange={() => toggleCategory(cat)}
                    className="size-3.5 accent-secondary"
                  />
                  <span className={cn("size-2 rounded-full", CATEGORY_COLORS[cat].dot)} aria-hidden />
                  <span className={cn("flex-1", on ? "text-foreground" : "text-muted")}>{CATEGORY_LABELS[cat]}</span>
                  <span className="font-mono tabular-nums text-muted">{count}</span>
                </label>
              </li>
            );
          })}
        </ul>
      </section>

      {/* Puan eşiği */}
      <section>
        <div className="mb-1.5 flex items-baseline justify-between">
          <label htmlFor="min-score" className="text-[11px] font-semibold uppercase tracking-wider text-muted">
            En düşük puan
          </label>
          <span className="font-mono text-xs tabular-nums text-foreground">{minConfidence}</span>
        </div>
        <input
          id="min-score"
          type="range"
          min={0}
          max={100}
          step={5}
          value={minConfidence}
          onChange={(e) => setMinConfidence(Number(e.target.value))}
          className="w-full accent-secondary"
        />
        <p className="mt-1 text-[10px] leading-relaxed text-muted-foreground">
          Puan {BASELINE_P99_SCORE} = sıradan konumların %99&apos;u. Kayıtlı her bulgu bu çizginin üstündedir.
        </p>
      </section>

      {/* Son bulgular */}
      <section aria-labelledby="recent-title" className="flex min-h-0 flex-1 flex-col">
        <h2 id="recent-title" className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-muted">
          Son bulgular
        </h2>
        <ul className="-mx-1 min-h-0 flex-1 space-y-1 overflow-y-auto px-1 thin-scrollbar">
          {isLoading && <li className="px-2 py-3 text-xs text-muted">Yükleniyor…</li>}
          {!isLoading && items.length === 0 && (
            <li className="rounded-lg border border-dashed border-white/10 px-3 py-4 text-xs leading-relaxed text-muted">
              Bu filtrelerle bulgu yok. Kategorileri açın ya da haritada bir yere gidip sağdaki tarama düğmesiyle tarayın.
            </li>
          )}
          {items.map((a) => (
            <li key={a.id}>
              <button
                type="button"
                onClick={() => open(a)}
                className="w-full rounded-lg border border-transparent px-2.5 py-2 text-left hover:border-white/[0.06] hover:bg-white/[0.04]"
              >
                <div className="flex items-center gap-2">
                  <span className={cn("size-2 shrink-0 rounded-full", CATEGORY_COLORS[a.category].dot)} aria-hidden />
                  <span className="min-w-0 flex-1 truncate text-xs font-medium text-foreground">
                    {a.location_label ?? `${a.lat.toFixed(4)}, ${a.lng.toFixed(4)}`}
                  </span>
                  <span className="font-mono text-xs tabular-nums text-foreground">{formatScore(a.confidence_score)}</span>
                </div>
                <div className="mt-0.5 flex justify-between pl-4 text-[11px] text-muted">
                  <span>{CATEGORY_LABELS[a.category]}</span>
                  <span>{formatRelativeTime(a.detected_at)}</span>
                </div>
              </button>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}

// ── Alt istatistik çubuğu ──────────────────────────────────────────────────

function StatsBar() {
  const { data: stats } = useAnomalyStats();
  const byStatus = new Map((stats?.by_status ?? []).map((s) => [s.status, s.count]));
  const pending = (byStatus.get(AnomalyStatus.PENDING) ?? 0) + (byStatus.get(AnomalyStatus.UNDER_REVIEW) ?? 0);
  const verified = byStatus.get(AnomalyStatus.VERIFIED) ?? 0;

  const items = [
    { label: "Bulgu", value: stats?.total_count },
    { label: "İnceleme bekliyor", value: stats ? pending : undefined },
    { label: "Toplulukça doğrulandı", value: stats ? verified : undefined },
  ];

  return (
    <div className="map-overlay bottom-5 left-1/2 hidden -translate-x-1/2 md:block">
      <dl className="glass-panel-strong flex items-center divide-x divide-white/[0.06] px-2 py-2">
        {items.map((it) => (
          <div key={it.label} className="px-4">
            <dt className="text-[10px] font-medium uppercase tracking-wider text-muted">{it.label}</dt>
            <dd className="font-mono text-sm font-bold tabular-nums text-foreground">
              {it.value ?? "—"}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
}
