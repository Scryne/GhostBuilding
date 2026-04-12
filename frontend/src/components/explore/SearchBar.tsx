// ═══════════════════════════════════════════════════════════════════════════
// SearchBar.tsx — Global arama çubuğu
// Koordinat girişi, Nominatim geocoding, debounced arama.
// ═══════════════════════════════════════════════════════════════════════════

"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { cn } from "@/lib/utils";
import { Search, X, MapPin, Globe, Navigation } from "lucide-react";

// ── Nominatim Sonuç Tipi ──────────────────────────────────────────────────

interface NominatimResult {
  place_id: number;
  display_name: string;
  lat: string;
  lon: string;
  type: string;
  address?: {
    country?: string;
    state?: string;
    city?: string;
    town?: string;
  };
}

// ── Koordinat parse ───────────────────────────────────────────────────────

function parseCoordinates(
  input: string
): { lat: number; lng: number } | null {
  // "41.0082, 28.9784" veya "41.0082 28.9784"
  const match = input.match(
    /^\s*(-?\d+\.?\d*)\s*[,\s]\s*(-?\d+\.?\d*)\s*$/
  );
  if (!match) return null;

  const lat = parseFloat(match[1]);
  const lng = parseFloat(match[2]);

  if (lat < -90 || lat > 90 || lng < -180 || lng > 180) return null;
  return { lat, lng };
}

// ═══════════════════════════════════════════════════════════════════════════

interface SearchBarProps {
  onLocationSelect?: (lat: number, lng: number, label: string) => void;
  onTextSearch?: (query: string) => void;
  className?: string;
  placeholder?: string;
}

export default function SearchBar({
  onLocationSelect,
  onTextSearch,
  className,
  placeholder = "Koordinat, bölge veya anomali ara...",
}: SearchBarProps) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<NominatimResult[]>([]);
  const [isOpen, setIsOpen] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(-1);
  const inputRef = useRef<HTMLInputElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  // ── Koordinat mı kontrol et ───────────────────────────────────────

  const detectedCoords = useMemo(() => parseCoordinates(query), [query]);

  // ── Debounced Nominatim arama ─────────────────────────────────────

  useEffect(() => {
    if (!query.trim() || query.length < 3 || detectedCoords) {
      setResults([]);
      return;
    }

    const timer = setTimeout(async () => {
      // Önceki isteği iptal et
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;

      setIsLoading(true);
      try {
        const url = new URL("https://nominatim.openstreetmap.org/search");
        url.searchParams.set("q", query);
        url.searchParams.set("format", "json");
        url.searchParams.set("addressdetails", "1");
        url.searchParams.set("limit", "6");
        url.searchParams.set("accept-language", "tr");

        const res = await fetch(url.toString(), {
          signal: controller.signal,
          headers: { "User-Agent": "GhostBuilding/1.0" },
        });

        if (!res.ok) throw new Error("Nominatim error");
        const data: NominatimResult[] = await res.json();
        setResults(data);
        setIsOpen(data.length > 0);
        setSelectedIndex(-1);
      } catch (err) {
        if ((err as Error).name !== "AbortError") {
          setResults([]);
        }
      } finally {
        setIsLoading(false);
      }
    }, 300);

    return () => {
      clearTimeout(timer);
      abortRef.current?.abort();
    };
  }, [query, detectedCoords]);

  // ── Seçim işleyicileri ────────────────────────────────────────────

  const handleSelect = useCallback(
    (result: NominatimResult) => {
      const lat = parseFloat(result.lat);
      const lng = parseFloat(result.lon);
      onLocationSelect?.(lat, lng, result.display_name);
      setQuery(result.display_name.split(",")[0]);
      setIsOpen(false);
      inputRef.current?.blur();
    },
    [onLocationSelect]
  );

  const handleCoordSelect = useCallback(() => {
    if (!detectedCoords) return;
    onLocationSelect?.(
      detectedCoords.lat,
      detectedCoords.lng,
      `${detectedCoords.lat.toFixed(4)}, ${detectedCoords.lng.toFixed(4)}`
    );
    setIsOpen(false);
  }, [detectedCoords, onLocationSelect]);

  const handleSubmit = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault();
      if (detectedCoords) {
        handleCoordSelect();
      } else if (selectedIndex >= 0 && results[selectedIndex]) {
        handleSelect(results[selectedIndex]);
      } else {
        onTextSearch?.(query);
      }
    },
    [
      query,
      detectedCoords,
      handleCoordSelect,
      selectedIndex,
      results,
      handleSelect,
      onTextSearch,
    ]
  );

  // ── Klavye navigasyonu ────────────────────────────────────────────

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      const total =
        results.length + (detectedCoords ? 1 : 0);

      if (e.key === "ArrowDown") {
        e.preventDefault();
        setSelectedIndex((prev) => Math.min(prev + 1, total - 1));
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setSelectedIndex((prev) => Math.max(prev - 1, -1));
      } else if (e.key === "Escape") {
        setIsOpen(false);
        inputRef.current?.blur();
      }
    },
    [results.length, detectedCoords]
  );

  // ── Dış tıklama ile kapat ─────────────────────────────────────────

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (
        containerRef.current &&
        !containerRef.current.contains(e.target as Node)
      ) {
        setIsOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  // ── Render ─────────────────────────────────────────────────────────

  return (
    <div ref={containerRef} className={cn("relative", className)}>
      <form onSubmit={handleSubmit}>
        <div
          className={cn(
            "flex items-center gap-2.5 px-4 py-2.5 rounded-xl",
            "bg-surface/80 border border-white/5",
            "focus-within:border-secondary/30 focus-within:ring-1 focus-within:ring-secondary/20",
            "transition-all duration-200"
          )}
        >
          {/* Arama ikonu */}
          <Search
            className={cn(
              "w-4 h-4 flex-shrink-0 transition-colors",
              isLoading ? "text-secondary animate-pulse" : "text-gray-500"
            )}
          />

          {/* Input */}
          <input
            ref={inputRef}
            id="explore-search-input"
            type="text"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              if (e.target.value.length > 0) setIsOpen(true);
            }}
            onFocus={() => {
              if (results.length > 0 || detectedCoords) setIsOpen(true);
            }}
            onKeyDown={handleKeyDown}
            placeholder={placeholder}
            autoComplete="off"
            className={cn(
              "flex-1 bg-transparent border-none outline-none",
              "text-sm text-gray-200 placeholder:text-gray-600",
              "min-w-0"
            )}
          />

          {/* Temizle butonu */}
          {query && (
            <button
              type="button"
              onClick={() => {
                setQuery("");
                setResults([]);
                setIsOpen(false);
                inputRef.current?.focus();
              }}
              className="p-1 rounded-md hover:bg-white/5 text-gray-500 hover:text-white transition-colors"
              aria-label="Aramayı temizle"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
      </form>

      {/* ── Dropdown sonuçları ───────────────────────────────────────── */}
      {isOpen && (detectedCoords || results.length > 0) && (
        <div
          className={cn(
            "absolute top-full left-0 right-0 mt-2 z-50",
            "glass-panel-strong rounded-xl overflow-hidden",
            "animate-slide-down shadow-panel",
            "max-h-80 overflow-y-auto custom-scrollbar thin-scrollbar"
          )}
        >
          {/* Koordinat algılandı */}
          {detectedCoords && (
            <button
              onClick={handleCoordSelect}
              className={cn(
                "w-full flex items-center gap-3 px-4 py-3 text-left",
                "hover:bg-secondary/10 transition-colors",
                "border-b border-white/[0.03]",
                selectedIndex === 0 && "bg-secondary/10"
              )}
              id="search-coord-result"
            >
              <div className="w-8 h-8 rounded-lg bg-secondary/10 border border-secondary/20 flex items-center justify-center flex-shrink-0">
                <Navigation className="w-3.5 h-3.5 text-secondary" />
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-xs font-semibold text-white">
                  Koordinata Git
                </p>
                <p className="text-[10px] text-gray-400 font-mono">
                  {detectedCoords.lat.toFixed(4)}°N,{" "}
                  {detectedCoords.lng.toFixed(4)}°E
                </p>
              </div>
              <kbd className="text-[9px] text-gray-600 bg-white/[0.03] px-1.5 py-0.5 rounded border border-white/5">
                Enter
              </kbd>
            </button>
          )}

          {/* Nominatim sonuçları */}
          {results.map((result, i) => {
            const idx = detectedCoords ? i + 1 : i;
            const parts = result.display_name.split(",");
            const mainName = parts[0]?.trim();
            const subText = parts.slice(1, 3).join(",").trim();

            return (
              <button
                key={result.place_id}
                onClick={() => handleSelect(result)}
                className={cn(
                  "w-full flex items-center gap-3 px-4 py-2.5 text-left",
                  "hover:bg-white/[0.04] transition-colors",
                  i < results.length - 1 && "border-b border-white/[0.02]",
                  selectedIndex === idx && "bg-white/[0.04]"
                )}
              >
                <div className="w-8 h-8 rounded-lg bg-white/[0.03] border border-white/5 flex items-center justify-center flex-shrink-0">
                  {result.type === "country" ? (
                    <Globe className="w-3.5 h-3.5 text-gray-400" />
                  ) : (
                    <MapPin className="w-3.5 h-3.5 text-gray-400" />
                  )}
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-xs font-medium text-gray-200 truncate">
                    {mainName}
                  </p>
                  {subText && (
                    <p className="text-[10px] text-gray-500 truncate">
                      {subText}
                    </p>
                  )}
                </div>
                <span className="text-[9px] text-gray-600 font-mono flex-shrink-0">
                  {parseFloat(result.lat).toFixed(2)},{" "}
                  {parseFloat(result.lon).toFixed(2)}
                </span>
              </button>
            );
          })}

          {/* Yükleniyor */}
          {isLoading && results.length === 0 && (
            <div className="px-4 py-6 text-center">
              <div className="w-5 h-5 rounded-full border-2 border-secondary/30 border-t-secondary animate-spin mx-auto mb-2" />
              <span className="text-[10px] text-gray-500">Aranıyor...</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
