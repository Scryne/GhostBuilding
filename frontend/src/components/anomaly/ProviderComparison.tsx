// ═══════════════════════════════════════════════════════════════════════════
// ProviderComparison.tsx — Sağlayıcı görüntü karşılaştırması
// İki sağlayıcı seçimi, sürüklenebilir before/after slider, diff skoru.
// ═══════════════════════════════════════════════════════════════════════════

"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
} from "react";
import { cn } from "@/lib/utils";
import type { AnomalyImage, ImageProvider } from "@/lib/types";
import Image from "next/image";

// ── Sağlayıcı Etiketleri ─────────────────────────────────────────────────

const PROVIDER_LABELS: Record<string, string> = {
  OSM: "OpenStreetMap",
  GOOGLE: "Google Maps",
  BING: "Bing Maps",
  SENTINEL: "Sentinel-2",
  YANDEX: "Yandex Maps",
  WAYBACK: "Wayback",
};

const PROVIDER_COLORS: Record<string, string> = {
  OSM: "#7EB26D",
  GOOGLE: "#4285F4",
  BING: "#00A4EF",
  SENTINEL: "#1DB954",
  YANDEX: "#FC3F1D",
  WAYBACK: "#9B59B6",
};

// ═══════════════════════════════════════════════════════════════════════════

interface ProviderComparisonProps {
  images: AnomalyImage[];
  className?: string;
}

export default function ProviderComparison({
  images,
  className,
}: ProviderComparisonProps) {
  // Mevcut provider'ları çıkar
  const availableProviders = Array.from(
    new Set(images.map((img) => img.provider))
  );

  const [leftProvider, setLeftProvider] = useState<ImageProvider>(
    availableProviders[0] || ("GOOGLE" as ImageProvider)
  );
  const [rightProvider, setRightProvider] = useState<ImageProvider>(
    availableProviders[1] || availableProviders[0] || ("OSM" as ImageProvider)
  );

  const leftImage = images.find((img) => img.provider === leftProvider);
  const rightImage = images.find((img) => img.provider === rightProvider);

  // Diff skoru
  const diffScore = (() => {
    const leftDiff = leftImage?.diff_score;
    const rightDiff = rightImage?.diff_score;
    if (leftDiff != null && rightDiff != null)
      return ((leftDiff + rightDiff) / 2).toFixed(1);
    if (leftDiff != null) return leftDiff.toFixed(1);
    if (rightDiff != null) return rightDiff.toFixed(1);
    return null;
  })();

  const diffColor =
    diffScore !== null
      ? parseFloat(diffScore) >= 70
        ? "text-red-400"
        : parseFloat(diffScore) >= 40
        ? "text-yellow-400"
        : "text-emerald-400"
      : "text-gray-500";

  // ── Before/After Slider ────────────────────────────────────────────

  const containerRef = useRef<HTMLDivElement>(null);
  const [sliderPos, setSliderPos] = useState(50); // yüzde
  const [isDragging, setIsDragging] = useState(false);

  const updateSlider = useCallback(
    (clientX: number) => {
      const rect = containerRef.current?.getBoundingClientRect();
      if (!rect) return;
      const x = clientX - rect.left;
      const pct = Math.max(0, Math.min(100, (x / rect.width) * 100));
      setSliderPos(pct);
    },
    []
  );

  const onPointerDown = useCallback(
    (e: ReactPointerEvent) => {
      setIsDragging(true);
      (e.target as HTMLElement).setPointerCapture(e.pointerId);
      updateSlider(e.clientX);
    },
    [updateSlider]
  );

  const onPointerMove = useCallback(
    (e: ReactPointerEvent) => {
      if (!isDragging) return;
      updateSlider(e.clientX);
    },
    [isDragging, updateSlider]
  );

  const onPointerUp = useCallback(() => {
    setIsDragging(false);
  }, []);

  // Touch desteği — container'dan pointer yakalama
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    el.style.touchAction = "none";
  }, []);

  // ── Render ─────────────────────────────────────────────────────────

  const hasImages = leftImage && rightImage;

  return (
    <div className={cn("space-y-3", className)}>
      {/* Üst: Diff Skoru */}
      {diffScore !== null && (
        <div className="flex items-center justify-between px-1">
          <span className="text-[10px] font-semibold uppercase tracking-wider text-gray-500">
            Fark Skoru
          </span>
          <div className="flex items-center gap-1.5">
            <div className="w-16 h-1.5 rounded-full bg-white/5 overflow-hidden">
              <div
                className={cn(
                  "h-full rounded-full transition-all duration-500",
                  parseFloat(diffScore) >= 70
                    ? "bg-red-500"
                    : parseFloat(diffScore) >= 40
                    ? "bg-yellow-500"
                    : "bg-emerald-500"
                )}
                style={{ width: `${Math.min(100, parseFloat(diffScore))}%` }}
              />
            </div>
            <span className={cn("text-xs font-bold tabular-nums", diffColor)}>
              {diffScore}%
            </span>
          </div>
        </div>
      )}

      {/* Provider Seçimi */}
      <div className="grid grid-cols-2 gap-2">
        <ProviderSelect
          label="Sol"
          value={leftProvider}
          options={availableProviders}
          onChange={setLeftProvider}
        />
        <ProviderSelect
          label="Sağ"
          value={rightProvider}
          options={availableProviders}
          onChange={setRightProvider}
        />
      </div>

      {/* Before/After Slider */}
      {hasImages ? (
        <div
          ref={containerRef}
          className="relative w-full aspect-square rounded-xl overflow-hidden cursor-col-resize select-none border border-white/5"
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          id="provider-comparison-slider"
        >
          <Image
            src={leftImage.image_url}
            alt={`${PROVIDER_LABELS[leftProvider] || leftProvider}`}
            fill
            sizes="(max-width: 768px) 100vw, (max-width: 1200px) 50vw, 33vw"
            className="object-cover"
            draggable={false}
          />

          {/* Sağ resim (kırpılmış) — dynamic external tile, not optimizable */}
          <div
            className="absolute inset-0 overflow-hidden"
            style={{ clipPath: `inset(0 0 0 ${sliderPos}%)` }}
          >
            <Image
              src={rightImage.image_url}
              alt={`${PROVIDER_LABELS[rightProvider] || rightProvider}`}
              fill
              sizes="(max-width: 768px) 100vw, (max-width: 1200px) 50vw, 33vw"
              className="object-cover"
              draggable={false}
            />
          </div>

          {/* Dikey ayırıcı çizgi */}
          <div
            className="absolute top-0 bottom-0 z-10"
            style={{ left: `${sliderPos}%`, transform: "translateX(-50%)" }}
          >
            {/* Çizgi */}
            <div className="absolute inset-0 w-[2px] bg-white/80 shadow-[0_0_8px_rgba(255,255,255,0.4)]" />

            {/* Tutamak */}
            <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-8 h-8 rounded-full bg-white/90 backdrop-blur-md shadow-lg flex items-center justify-center">
              <svg
                width="14"
                height="14"
                viewBox="0 0 14 14"
                fill="none"
                className="text-gray-800"
              >
                <path
                  d="M4 3L1 7L4 11"
                  stroke="currentColor"
                  strokeWidth="1.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
                <path
                  d="M10 3L13 7L10 11"
                  stroke="currentColor"
                  strokeWidth="1.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </div>
          </div>

          {/* Sağlayıcı etiketleri */}
          <div className="absolute top-2 left-2 z-20">
            <span
              className="px-2 py-0.5 text-[10px] font-bold uppercase rounded-md backdrop-blur-md"
              style={{
                backgroundColor: `${PROVIDER_COLORS[leftProvider] || "#2E6DA4"}33`,
                color: PROVIDER_COLORS[leftProvider] || "#2E6DA4",
                border: `1px solid ${PROVIDER_COLORS[leftProvider] || "#2E6DA4"}44`,
              }}
            >
              {PROVIDER_LABELS[leftProvider] || leftProvider}
            </span>
          </div>
          <div className="absolute top-2 right-2 z-20">
            <span
              className="px-2 py-0.5 text-[10px] font-bold uppercase rounded-md backdrop-blur-md"
              style={{
                backgroundColor: `${PROVIDER_COLORS[rightProvider] || "#457B9D"}33`,
                color: PROVIDER_COLORS[rightProvider] || "#457B9D",
                border: `1px solid ${PROVIDER_COLORS[rightProvider] || "#457B9D"}44`,
              }}
            >
              {PROVIDER_LABELS[rightProvider] || rightProvider}
            </span>
          </div>
        </div>
      ) : (
        <div className="w-full aspect-square rounded-xl bg-white/[0.02] border border-white/5 flex items-center justify-center">
          <div className="text-center">
            <div className="text-2xl mb-2 opacity-30">🖼️</div>
            <span className="text-xs text-gray-500">
              Karşılaştırma için en az 2 sağlayıcı gerekli
            </span>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Provider Dropdown ────────────────────────────────────────────────────

function ProviderSelect({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: ImageProvider;
  options: ImageProvider[];
  onChange: (v: ImageProvider) => void;
}) {
  return (
    <div className="relative">
      <label className="block text-[9px] font-semibold uppercase tracking-wider text-gray-600 mb-1 px-1">
        {label}
      </label>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value as ImageProvider)}
        className={cn(
          "w-full appearance-none px-3 py-1.5 rounded-lg text-xs font-medium",
          "bg-white/[0.03] border border-white/8 text-gray-200",
          "hover:bg-white/[0.05] hover:border-white/12",
          "focus:outline-none focus:ring-1 focus:ring-secondary/40",
          "transition-all duration-200 cursor-pointer"
        )}
        id={`provider-select-${label.toLowerCase()}`}
      >
        {options.map((p) => (
          <option key={p} value={p} className="bg-surface text-gray-200">
            {PROVIDER_LABELS[p] || p}
          </option>
        ))}
      </select>
      {/* Dropdown ok */}
      <div className="absolute right-2.5 bottom-2 pointer-events-none">
        <svg
          width="10"
          height="10"
          viewBox="0 0 10 10"
          fill="none"
          className="text-gray-500"
        >
          <path
            d="M2 4L5 7L8 4"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
          />
        </svg>
      </div>
    </div>
  );
}
