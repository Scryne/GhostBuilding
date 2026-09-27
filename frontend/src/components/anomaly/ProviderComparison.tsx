// ═══════════════════════════════════════════════════════════════════════════
// ProviderComparison.tsx — İki kaynağın aynı karosunu üst üste kaydırarak karşılaştırma
// Görseller API'nin kaydettiği kanıt karolarıdır (/media/...), yeniden sıkıştırılmaz.
// ═══════════════════════════════════════════════════════════════════════════

"use client";

import {
  useCallback,
  useRef,
  useState,
  type KeyboardEvent,
  type PointerEvent as ReactPointerEvent,
} from "react";
import Image from "next/image";
import { resolveMediaUrl } from "@/lib/api";
import { cn, providerMeta } from "@/lib/utils";
import type { AnomalyImage } from "@/lib/types";

interface ProviderComparisonProps {
  images: AnomalyImage[];
  /** Başlangıçta karşılaştırılacak çift (ör. en bulanık ↔ en keskin) */
  initialPair?: [string, string];
  className?: string;
}

export default function ProviderComparison({
  images,
  initialPair,
  className,
}: ProviderComparisonProps) {
  const available = Array.from(new Set(images.map((img) => img.provider.toLowerCase())));
  const pick = (want: string | undefined, fallback: number) =>
    want && available.includes(want.toLowerCase()) ? want.toLowerCase() : available[fallback];

  const [left, setLeft] = useState<string>(() => pick(initialPair?.[0], 0) ?? "");
  const [right, setRight] = useState<string>(
    () => pick(initialPair?.[1], 1) ?? available[0] ?? ""
  );

  const leftImage = images.find((img) => img.provider.toLowerCase() === left);
  const rightImage = images.find((img) => img.provider.toLowerCase() === right);

  const containerRef = useRef<HTMLDivElement>(null);
  const [sliderPos, setSliderPos] = useState(50);
  const [dragging, setDragging] = useState(false);

  const updateSlider = useCallback((clientX: number) => {
    const rect = containerRef.current?.getBoundingClientRect();
    if (!rect) return;
    setSliderPos(Math.max(0, Math.min(100, ((clientX - rect.left) / rect.width) * 100)));
  }, []);

  const onPointerDown = (e: ReactPointerEvent<HTMLDivElement>) => {
    setDragging(true);
    e.currentTarget.setPointerCapture(e.pointerId);
    updateSlider(e.clientX);
  };

  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key === "ArrowLeft") setSliderPos((p) => Math.max(0, p - 5));
    if (e.key === "ArrowRight") setSliderPos((p) => Math.min(100, p + 5));
  };

  if (available.length < 2) {
    return (
      <p className={cn("text-xs text-muted", className)}>
        Karşılaştırma için en az iki kaynağın görüntüsü gerekir.
      </p>
    );
  }

  const leftMeta = providerMeta(left);
  const rightMeta = providerMeta(right);

  return (
    <div className={cn("space-y-3", className)}>
      <div className="grid grid-cols-2 gap-2">
        <ProviderSelect label="Sol kaynak" value={left} options={available} onChange={setLeft} />
        <ProviderSelect label="Sağ kaynak" value={right} options={available} onChange={setRight} />
      </div>

      {leftImage && rightImage && (
        <div
          ref={containerRef}
          role="slider"
          tabIndex={0}
          aria-label={`${leftMeta.label} ile ${rightMeta.label} karşılaştırma ayırıcısı`}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={Math.round(sliderPos)}
          onPointerDown={onPointerDown}
          onPointerMove={(e) => dragging && updateSlider(e.clientX)}
          onPointerUp={() => setDragging(false)}
          onKeyDown={onKeyDown}
          className="relative w-full aspect-square rounded-xl overflow-hidden cursor-col-resize select-none touch-none border border-border focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-secondary"
        >
          <Image
            src={resolveMediaUrl(leftImage.image_url) ?? ""}
            alt={`${leftMeta.label} karosu`}
            fill
            unoptimized
            sizes="(max-width: 768px) 100vw, 480px"
            className="object-cover [image-rendering:pixelated]"
            draggable={false}
          />
          <div className="absolute inset-0" style={{ clipPath: `inset(0 0 0 ${sliderPos}%)` }}>
            <Image
              src={resolveMediaUrl(rightImage.image_url) ?? ""}
              alt={`${rightMeta.label} karosu`}
              fill
              unoptimized
              sizes="(max-width: 768px) 100vw, 480px"
              className="object-cover [image-rendering:pixelated]"
              draggable={false}
            />
          </div>
          <div
            className="absolute inset-y-0 w-0.5 bg-white/90 shadow-[0_0_6px_rgba(0,0,0,0.6)]"
            style={{ left: `${sliderPos}%`, transform: "translateX(-50%)" }}
          >
            <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 size-8 rounded-full bg-white text-gray-900 shadow-lg flex items-center justify-center text-xs font-bold">
              ⟷
            </div>
          </div>
          <ProviderTag meta={leftMeta} className="left-2" />
          <ProviderTag meta={rightMeta} className="right-2" />
        </div>
      )}
      <p className="text-[11px] text-muted">
        Ayırıcıyı sürükleyin ya da odaklayıp ← → tuşlarını kullanın.
      </p>
    </div>
  );
}

function ProviderTag({
  meta,
  className,
}: {
  meta: ReturnType<typeof providerMeta>;
  className: string;
}) {
  return (
    <span
      className={cn(
        "absolute top-2 px-2 py-0.5 rounded-md text-[11px] font-semibold bg-black/70 border",
        className
      )}
      style={{ color: meta.hex, borderColor: `${meta.hex}55` }}
    >
      {meta.label}
    </span>
  );
}

function ProviderSelect({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: string[];
  onChange: (v: string) => void;
}) {
  return (
    <label className="block">
      <span className="block text-[11px] font-medium text-muted mb-1">{label}</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-lg bg-surface border border-border px-2.5 py-1.5 text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-secondary/50"
      >
        {options.map((opt) => (
          <option key={opt} value={opt}>
            {providerMeta(opt).label}
          </option>
        ))}
      </select>
    </label>
  );
}
