// ═══════════════════════════════════════════════════════════════════════════
// TimelineChart.tsx — Tarihsel değişim grafiği (D3.js)
// X: yıllar, Y: diff/confidence skoru. Anomali noktaları kırmızı.
// Tıklanınca callback ile ilgili yılın bilgisini döndürür.
// ═══════════════════════════════════════════════════════════════════════════

"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";
import type { TimeSeriesEntry } from "@/lib/types";

// ── D3 Benzeri Mini Çizim Kütüphanesi ─────────────────────────────────
// D3 bağımlılığından kaçınmak için Canvas 2D kullanıyoruz.

interface ChartDimensions {
  width: number;
  height: number;
  margin: { top: number; right: number; bottom: number; left: number };
}

const DEFAULT_DIMS: ChartDimensions = {
  width: 340,
  height: 160,
  margin: { top: 16, right: 12, bottom: 28, left: 36 },
};

// ═══════════════════════════════════════════════════════════════════════════

interface TimelineChartProps {
  data: TimeSeriesEntry[];
  onPointClick?: (entry: TimeSeriesEntry) => void;
  className?: string;
}

export default function TimelineChart({
  data,
  onPointClick,
  className,
}: TimelineChartProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);
  const [dims, setDims] = useState(DEFAULT_DIMS);
  const dataPointsRef = useRef<
    Array<{ x: number; y: number; entry: TimeSeriesEntry }>
  >([]);

  // ── Responsive boyut ──────────────────────────────────────────────

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const ro = new ResizeObserver(([entry]) => {
      const rect = entry.contentRect;
      if (rect.width > 0) {
        setDims((prev) => ({
          ...prev,
          width: rect.width,
          height: Math.max(140, Math.min(180, rect.width * 0.45)),
        }));
      }
    });

    ro.observe(container);
    return () => ro.disconnect();
  }, []);

  // ── Canvas Çizimi ─────────────────────────────────────────────────

  const drawChart = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas || !data.length) return;

    const dpr = window.devicePixelRatio || 1;
    canvas.width = dims.width * dpr;
    canvas.height = dims.height * dpr;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, dims.width, dims.height);

    const { margin } = dims;
    const plotW = dims.width - margin.left - margin.right;
    const plotH = dims.height - margin.top - margin.bottom;

    // Veri parse
    const parsed = data
      .filter((d) => d.date && d.confidence_score != null)
      .map((d) => ({
        date: new Date(d.date),
        score: d.confidence_score!,
        event: d.event,
        entry: d,
      }))
      .sort((a, b) => a.date.getTime() - b.date.getTime());

    if (!parsed.length) return;

    // Scale hesapla
    const minDate = parsed[0].date.getTime();
    const maxDate = parsed[parsed.length - 1].date.getTime();
    const dateRange = maxDate - minDate || 1;

    const scores = parsed.map((p) => p.score);
    const minScore = Math.max(0, Math.min(...scores) - 10);
    const maxScore = Math.min(100, Math.max(...scores) + 10);
    const scoreRange = maxScore - minScore || 1;

    const scaleX = (dateMs: number) =>
      margin.left + ((dateMs - minDate) / dateRange) * plotW;
    const scaleY = (score: number) =>
      margin.top + plotH - ((score - minScore) / scoreRange) * plotH;

    // ── Grid çizgileri ──────────────────────────────────────────────
    ctx.strokeStyle = "rgba(255, 255, 255, 0.04)";
    ctx.lineWidth = 1;

    const yTicks = 5;
    for (let i = 0; i <= yTicks; i++) {
      const val = minScore + (scoreRange * i) / yTicks;
      const y = scaleY(val);
      ctx.beginPath();
      ctx.moveTo(margin.left, y);
      ctx.lineTo(dims.width - margin.right, y);
      ctx.stroke();

      // Y ekseni etiketi
      ctx.fillStyle = "rgba(255, 255, 255, 0.25)";
      ctx.font = "9px Inter, system-ui, sans-serif";
      ctx.textAlign = "right";
      ctx.textBaseline = "middle";
      ctx.fillText(val.toFixed(0), margin.left - 6, y);
    }

    // X ekseni etiketleri
    const years = new Set<number>();
    parsed.forEach((p) => years.add(p.date.getFullYear()));
    const sortedYears = Array.from(years).sort();
    const maxLabels = Math.floor(plotW / 40);
    const step = Math.max(1, Math.ceil(sortedYears.length / maxLabels));

    ctx.fillStyle = "rgba(255, 255, 255, 0.25)";
    ctx.font = "9px Inter, system-ui, sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "top";

    sortedYears.forEach((year, i) => {
      if (i % step !== 0) return;
      const dateMs = new Date(year, 6, 1).getTime();
      const x = scaleX(Math.max(minDate, Math.min(maxDate, dateMs)));
      ctx.fillText(year.toString(), x, dims.height - margin.bottom + 8);
    });

    // ── Gradient alan ───────────────────────────────────────────────
    const gradient = ctx.createLinearGradient(0, margin.top, 0, dims.height - margin.bottom);
    gradient.addColorStop(0, "rgba(46, 109, 164, 0.15)");
    gradient.addColorStop(1, "rgba(46, 109, 164, 0)");

    ctx.beginPath();
    ctx.moveTo(scaleX(parsed[0].date.getTime()), dims.height - margin.bottom);
    parsed.forEach((p) => {
      ctx.lineTo(scaleX(p.date.getTime()), scaleY(p.score));
    });
    ctx.lineTo(
      scaleX(parsed[parsed.length - 1].date.getTime()),
      dims.height - margin.bottom
    );
    ctx.closePath();
    ctx.fillStyle = gradient;
    ctx.fill();

    // ── Çizgi ───────────────────────────────────────────────────────
    ctx.beginPath();
    ctx.strokeStyle = "#2E6DA4";
    ctx.lineWidth = 2;
    ctx.lineJoin = "round";
    ctx.lineCap = "round";

    parsed.forEach((p, i) => {
      const x = scaleX(p.date.getTime());
      const y = scaleY(p.score);
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();

    // ── Noktalar ────────────────────────────────────────────────────
    const points: Array<{ x: number; y: number; entry: TimeSeriesEntry }> = [];

    parsed.forEach((p, i) => {
      const x = scaleX(p.date.getTime());
      const y = scaleY(p.score);
      const isAnomaly = p.event !== null;
      const isHovered = hoveredIndex === i;

      points.push({ x, y, entry: p.entry });

      // Glow
      if (isAnomaly || isHovered) {
        ctx.beginPath();
        ctx.arc(x, y, isHovered ? 12 : 8, 0, Math.PI * 2);
        ctx.fillStyle = isAnomaly
          ? "rgba(230, 57, 70, 0.2)"
          : "rgba(46, 109, 164, 0.2)";
        ctx.fill();
      }

      // Nokta
      ctx.beginPath();
      ctx.arc(x, y, isHovered ? 5 : isAnomaly ? 4 : 3, 0, Math.PI * 2);
      ctx.fillStyle = isAnomaly ? "#E63946" : "#2E6DA4";
      ctx.fill();

      // Beyaz halka
      ctx.beginPath();
      ctx.arc(x, y, isHovered ? 5 : isAnomaly ? 4 : 3, 0, Math.PI * 2);
      ctx.strokeStyle = "rgba(255, 255, 255, 0.4)";
      ctx.lineWidth = 1;
      ctx.stroke();
    });

    dataPointsRef.current = points;
  }, [data, dims, hoveredIndex]);

  useEffect(() => {
    drawChart();
  }, [drawChart]);

  // ── Fare etkileşimi ───────────────────────────────────────────────

  const handlePointerMove = useCallback(
    (e: React.PointerEvent<HTMLCanvasElement>) => {
      const canvas = canvasRef.current;
      if (!canvas) return;

      const rect = canvas.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;

      const threshold = 15;
      let closest: number | null = null;
      let minDist = Infinity;

      dataPointsRef.current.forEach((pt, i) => {
        const dist = Math.sqrt((pt.x - x) ** 2 + (pt.y - y) ** 2);
        if (dist < threshold && dist < minDist) {
          minDist = dist;
          closest = i;
        }
      });

      setHoveredIndex(closest);
      canvas.style.cursor = closest !== null ? "pointer" : "default";
    },
    []
  );

  const handleClick = useCallback(() => {
    if (hoveredIndex !== null && dataPointsRef.current[hoveredIndex]) {
      onPointClick?.(dataPointsRef.current[hoveredIndex].entry);
    }
  }, [hoveredIndex, onPointClick]);

  const handlePointerLeave = useCallback(() => {
    setHoveredIndex(null);
  }, []);

  // ── Tooltip ───────────────────────────────────────────────────────

  const hoveredPoint =
    hoveredIndex !== null ? dataPointsRef.current[hoveredIndex] : null;

  return (
    <div className={cn("space-y-2", className)} ref={containerRef}>
      <div className="flex items-center justify-between px-1">
        <h4 className="text-[10px] font-semibold uppercase tracking-wider text-gray-500">
          Tarihsel Değişim
        </h4>
        {data.length > 0 && (
          <span className="text-[10px] text-gray-600 tabular-nums">
            {data.length} veri noktası
          </span>
        )}
      </div>

      <div className="relative">
        <canvas
          ref={canvasRef}
          width={dims.width}
          height={dims.height}
          className="w-full rounded-lg"
          style={{ height: `${dims.height}px` }}
          onPointerMove={handlePointerMove}
          onPointerLeave={handlePointerLeave}
          onClick={handleClick}
          id="timeline-chart-canvas"
        />

        {/* Tooltip */}
        {hoveredPoint && (
          <div
            className="absolute z-30 pointer-events-none animate-fade-in"
            style={{
              left: `${hoveredPoint.x}px`,
              top: `${hoveredPoint.y - 44}px`,
              transform: "translateX(-50%)",
            }}
          >
            <div className="glass-panel px-2.5 py-1.5 rounded-lg shadow-panel whitespace-nowrap">
              <div className="text-[10px] font-bold text-white tabular-nums">
                {hoveredPoint.entry.confidence_score?.toFixed(1)}%
              </div>
              <div className="text-[9px] text-gray-400">
                {new Date(hoveredPoint.entry.date).toLocaleDateString("tr-TR", {
                  month: "short",
                  year: "numeric",
                })}
              </div>
              {hoveredPoint.entry.event && (
                <div className="text-[9px] text-red-400 font-medium mt-0.5">
                  ⚡ {hoveredPoint.entry.event}
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Legend */}
      <div className="flex items-center gap-4 px-1">
        <div className="flex items-center gap-1.5">
          <div className="w-2 h-2 rounded-full bg-secondary" />
          <span className="text-[9px] text-gray-500">Normal</span>
        </div>
        <div className="flex items-center gap-1.5">
          <div className="w-2 h-2 rounded-full bg-accent" />
          <span className="text-[9px] text-gray-500">Anomali</span>
        </div>
      </div>
    </div>
  );
}
