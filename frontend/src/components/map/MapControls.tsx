// ═══════════════════════════════════════════════════════════════════════════
// MapControls.tsx — Harita kontrolleri
// Zoom, konumuma git, bu alanı tara, koordinat göstergesi.
// ═══════════════════════════════════════════════════════════════════════════

"use client";

import { useCallback, useState } from "react";
import {
  Plus,
  Minus,
  Crosshair,
  Radar,
  Copy,
  Check,
} from "lucide-react";
import { useMapContext } from "./GhostMap";
import { anomalyApi } from "@/lib/api";
import { formatCoordsDecimal, cn } from "@/lib/utils";
import { toast } from "@/components/ui/Toast";

// ═══════════════════════════════════════════════════════════════════════════
// Component
// ═══════════════════════════════════════════════════════════════════════════

export default function MapControls() {
  const {
    mapRef,
    viewport,
    cursorPosition,
    flyTo,
    setActiveScanTaskId,
  } = useMapContext();

  const [isScanning, setIsScanning] = useState(false);
  const [copiedCoords, setCopiedCoords] = useState(false);

  // ── Zoom In/Out ─────────────────────────────────────────────────────

  const handleZoomIn = useCallback(() => {
    mapRef.current?.zoomIn({ duration: 300 });
  }, [mapRef]);

  const handleZoomOut = useCallback(() => {
    mapRef.current?.zoomOut({ duration: 300 });
  }, [mapRef]);

  // ── Konumuma Git ────────────────────────────────────────────────────

  const handleLocateMe = useCallback(() => {
    if (!("geolocation" in navigator)) {
      toast.warning("Konum erişimi desteklenmiyor", {
        description: "Tarayıcınız konum erişimini desteklemiyor.",
      });
      return;
    }

    navigator.geolocation.getCurrentPosition(
      (pos) => {
        flyTo(pos.coords.latitude, pos.coords.longitude, 14);
        toast.success("Konumunuza gidiliyor", {
          description: formatCoordsDecimal(
            pos.coords.latitude,
            pos.coords.longitude
          ),
        });
      },
      (err) => {
        toast.error("Konum alınamadı", {
          description:
            err.code === 1
              ? "Konum izni reddedildi."
              : "Konum servisi yanıt vermedi.",
        });
      },
      { enableHighAccuracy: true, timeout: 10_000 }
    );
  }, [flyTo]);

  // ── Bu Alanı Tara ──────────────────────────────────────────────────

  const handleScanArea = useCallback(async () => {
    if (isScanning) return;

    setIsScanning(true);

    try {
      const result = await anomalyApi.startScan({
        lat: viewport.latitude,
        lng: viewport.longitude,
        zoom: Math.round(viewport.zoom),
        radius_km: Math.min(50, Math.max(1, 40_000 / Math.pow(2, viewport.zoom))),
      });

      setActiveScanTaskId(result.task_id);

      toast.info("Tarama başlatıldı", {
        description: `Tahmini süre: ~${result.estimated_seconds} saniye`,
      });
    } catch {
      toast.error("Tarama başlatılamadı", {
        description: "API bağlantı hatası. Tekrar deneyin.",
      });
    } finally {
      setIsScanning(false);
    }
  }, [isScanning, viewport, setActiveScanTaskId]);

  // ── Koordinat Kopyala ───────────────────────────────────────────────

  const handleCopyCoords = useCallback(() => {
    if (!cursorPosition) return;
    const text = `${cursorPosition.lat.toFixed(6)}, ${cursorPosition.lng.toFixed(6)}`;
    navigator.clipboard.writeText(text).then(() => {
      setCopiedCoords(true);
      setTimeout(() => setCopiedCoords(false), 1500);
    });
  }, [cursorPosition]);

  // ── Render ──────────────────────────────────────────────────────────

  return (
    <>
      {/* ── Sağ Kenar — Zoom + Konum + Tara ───────────────────────── */}
      <div className="absolute right-4 bottom-20 z-20 pointer-events-auto flex flex-col gap-2">
        {/* Zoom In */}
        <button
          id="btn-zoom-in"
          onClick={handleZoomIn}
          className="glass-panel p-2.5 hover:bg-white/[0.06] transition-colors group"
          title="Yakınlaştır"
        >
          <Plus className="w-4 h-4 text-gray-400 group-hover:text-white transition-colors" />
        </button>

        {/* Zoom Out */}
        <button
          id="btn-zoom-out"
          onClick={handleZoomOut}
          className="glass-panel p-2.5 hover:bg-white/[0.06] transition-colors group"
          title="Uzaklaştır"
        >
          <Minus className="w-4 h-4 text-gray-400 group-hover:text-white transition-colors" />
        </button>

        {/* Divider */}
        <div className="w-full h-px bg-white/[0.06]" />

        {/* Konumuma Git */}
        <button
          id="btn-locate"
          onClick={handleLocateMe}
          className="glass-panel p-2.5 hover:bg-white/[0.06] transition-colors group"
          title="Konumuma git"
        >
          <Crosshair className="w-4 h-4 text-gray-400 group-hover:text-white transition-colors" />
        </button>

        {/* Bu Alanı Tara */}
        <button
          id="btn-scan-area"
          onClick={handleScanArea}
          disabled={isScanning}
          className={cn(
            "glass-panel p-2.5 transition-all group",
            isScanning
              ? "opacity-50 cursor-not-allowed"
              : "hover:bg-secondary/10 hover:border-secondary/20"
          )}
          title="Bu alanı tara"
        >
          <Radar
            className={cn(
              "w-4 h-4 transition-colors",
              isScanning
                ? "text-secondary animate-spin"
                : "text-secondary group-hover:text-secondary-300"
            )}
          />
        </button>
      </div>

      {/* ── Alt Sol — Koordinat Göstergesi ─────────────────────────── */}
      <div className="absolute left-4 bottom-4 z-20 pointer-events-auto">
        <button
          onClick={handleCopyCoords}
          className="glass-panel px-3 py-1.5 flex items-center gap-2 hover:bg-white/[0.04] transition-colors group"
          title="Koordinatları kopyala"
        >
          <span className="text-[10px] font-mono text-gray-500 tabular-nums">
            {cursorPosition
              ? `${cursorPosition.lat.toFixed(5)}° ${cursorPosition.lat >= 0 ? "N" : "S"}, ${cursorPosition.lng.toFixed(5)}° ${cursorPosition.lng >= 0 ? "E" : "W"}`
              : "—"}
          </span>
          {copiedCoords ? (
            <Check className="w-3 h-3 text-emerald-400" />
          ) : (
            <Copy className="w-3 h-3 text-gray-600 group-hover:text-gray-400 transition-colors" />
          )}
        </button>
      </div>

      {/* ── Alt Sol +1 — Zoom Level Badge ──────────────────────────── */}
      <div className="absolute left-4 bottom-12 z-20 pointer-events-none">
        <div className="glass-panel px-2.5 py-1 flex items-center gap-1.5">
          <span className="text-[9px] font-bold uppercase tracking-wider text-gray-600">
            Zoom
          </span>
          <span className="text-[11px] font-bold text-gray-300 font-mono tabular-nums">
            {viewport.zoom.toFixed(1)}
          </span>
        </div>
      </div>
    </>
  );
}
