// ═══════════════════════════════════════════════════════════════════════════
// GhostBuilding — Utility Fonksiyonları
// Tarih formatlama, koordinat formatlama, kategori renkleri, vb.
// ═══════════════════════════════════════════════════════════════════════════

import { AnomalyCategory, AnomalyStatus, VerificationVote } from "./types";

// ── Tarih Formatlama ──────────────────────────────────────────────────────

/**
 * ISO tarih string'ini kullanıcı dostu formata çevirir.
 * Örn: "12 Nis 2026, 15:30"
 */
export function formatDate(isoDate: string | null | undefined): string {
  if (!isoDate) return "—";
  try {
    const date = new Date(isoDate);
    return date.toLocaleDateString("tr-TR", {
      day: "numeric",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return "—";
  }
}

/**
 * ISO tarih string'ini kısa göreceli formata çevirir.
 * Örn: "2 dk önce", "3 saat önce", "5 gün önce"
 */
export function formatRelativeTime(isoDate: string | null | undefined): string {
  if (!isoDate) return "—";
  try {
    const now = Date.now();
    const then = new Date(isoDate).getTime();
    const diffMs = now - then;

    if (diffMs < 0) return "az önce";

    const seconds = Math.floor(diffMs / 1000);
    const minutes = Math.floor(seconds / 60);
    const hours = Math.floor(minutes / 60);
    const days = Math.floor(hours / 24);
    const weeks = Math.floor(days / 7);
    const months = Math.floor(days / 30);

    if (seconds < 60) return "az önce";
    if (minutes < 60) return `${minutes} dk önce`;
    if (hours < 24) return `${hours} saat önce`;
    if (days < 7) return `${days} gün önce`;
    if (weeks < 4) return `${weeks} hafta önce`;
    return `${months} ay önce`;
  } catch {
    return "—";
  }
}

/**
 * Sadece tarih kısmı: "12.04.2026"
 */
export function formatDateShort(isoDate: string | null | undefined): string {
  if (!isoDate) return "—";
  try {
    const date = new Date(isoDate);
    return date.toLocaleDateString("tr-TR");
  } catch {
    return "—";
  }
}

// ── Koordinat Formatlama ──────────────────────────────────────────────────

/**
 * Koordinatları derece-dakika-saniye formatına çevirir.
 * Örn: 41°0'29.5"N, 28°58'42.2"E
 */
export function formatCoordsDMS(lat: number, lng: number): string {
  const latDir = lat >= 0 ? "N" : "S";
  const lngDir = lng >= 0 ? "E" : "W";

  const formatDMS = (value: number): string => {
    const abs = Math.abs(value);
    const deg = Math.floor(abs);
    const minFloat = (abs - deg) * 60;
    const min = Math.floor(minFloat);
    const sec = ((minFloat - min) * 60).toFixed(1);
    return `${deg}°${min}'${sec}"`;
  };

  return `${formatDMS(lat)}${latDir}, ${formatDMS(lng)}${lngDir}`;
}

/**
 * Koordinatları ondalık formatta döndürür.
 * Örn: "41.0082, 28.9784"
 */
export function formatCoordsDecimal(
  lat: number,
  lng: number,
  precision: number = 4
): string {
  return `${lat.toFixed(precision)}, ${lng.toFixed(precision)}`;
}

/**
 * Koordinatı kopyalanabilir kısa formata çevirir.
 * Örn: "41.0082°N 28.9784°E"
 */
export function formatCoordsCompact(lat: number, lng: number): string {
  const latDir = lat >= 0 ? "N" : "S";
  const lngDir = lng >= 0 ? "E" : "W";
  return `${Math.abs(lat).toFixed(4)}°${latDir} ${Math.abs(lng).toFixed(4)}°${lngDir}`;
}

// ── Kategori Renkleri ─────────────────────────────────────────────────────

/** Her anomali kategorisi için Tailwind renk sınıfları */
export const CATEGORY_COLORS: Record<
  AnomalyCategory,
  {
    bg: string;
    text: string;
    border: string;
    dot: string;
    glow: string;
    hex: string;
  }
> = {
  [AnomalyCategory.GHOST_BUILDING]: {
    bg: "bg-ghost/10",
    text: "text-ghost",
    border: "border-ghost/30",
    dot: "bg-ghost",
    glow: "shadow-glow-ghost",
    hex: "#F4A261",
  },
  [AnomalyCategory.HIDDEN_STRUCTURE]: {
    bg: "bg-accent/10",
    text: "text-accent",
    border: "border-accent/30",
    dot: "bg-accent",
    glow: "shadow-glow-accent",
    hex: "#E63946",
  },
  [AnomalyCategory.CENSORED_AREA]: {
    bg: "bg-censored/10",
    text: "text-censored",
    border: "border-censored/30",
    dot: "bg-censored",
    glow: "",
    hex: "#9B2226",
  },
  [AnomalyCategory.IMAGE_DISCREPANCY]: {
    bg: "bg-discrepancy/10",
    text: "text-discrepancy",
    border: "border-discrepancy/30",
    dot: "bg-discrepancy",
    glow: "",
    hex: "#457B9D",
  },
};

/** Kategori etiketleri (Türkçe) */
export const CATEGORY_LABELS: Record<AnomalyCategory, string> = {
  [AnomalyCategory.GHOST_BUILDING]: "Hayalet Yapı",
  [AnomalyCategory.HIDDEN_STRUCTURE]: "Gizli Yapı",
  [AnomalyCategory.CENSORED_AREA]: "Sansürlü Alan",
  [AnomalyCategory.IMAGE_DISCREPANCY]: "Görüntü Farkı",
};

/** Kategori ikonları (emoji/karakter) */
export const CATEGORY_ICONS: Record<AnomalyCategory, string> = {
  [AnomalyCategory.GHOST_BUILDING]: "👻",
  [AnomalyCategory.HIDDEN_STRUCTURE]: "🔒",
  [AnomalyCategory.CENSORED_AREA]: "🚫",
  [AnomalyCategory.IMAGE_DISCREPANCY]: "🔍",
};

// ── Durum Renkleri ────────────────────────────────────────────────────────

export const STATUS_COLORS: Record<
  AnomalyStatus,
  { bg: string; text: string; border: string; label: string }
> = {
  [AnomalyStatus.PENDING]: {
    bg: "bg-yellow-500/10",
    text: "text-yellow-400",
    border: "border-yellow-500/30",
    label: "Beklemede",
  },
  [AnomalyStatus.VERIFIED]: {
    bg: "bg-emerald-500/10",
    text: "text-emerald-400",
    border: "border-emerald-500/30",
    label: "Doğrulandı",
  },
  [AnomalyStatus.REJECTED]: {
    bg: "bg-red-500/10",
    text: "text-red-400",
    border: "border-red-500/30",
    label: "Reddedildi",
  },
  [AnomalyStatus.UNDER_REVIEW]: {
    bg: "bg-blue-500/10",
    text: "text-blue-400",
    border: "border-blue-500/30",
    label: "İnceleniyor",
  },
};

// ── Oy Renkleri ───────────────────────────────────────────────────────────

export const VOTE_COLORS: Record<
  VerificationVote,
  { bg: string; text: string; label: string }
> = {
  [VerificationVote.CONFIRM]: {
    bg: "bg-emerald-500/10",
    text: "text-emerald-400",
    label: "Onay",
  },
  [VerificationVote.DENY]: {
    bg: "bg-red-500/10",
    text: "text-red-400",
    label: "Red",
  },
  [VerificationVote.UNCERTAIN]: {
    bg: "bg-yellow-500/10",
    text: "text-yellow-400",
    label: "Belirsiz",
  },
};

// ── Yardımcı Fonksiyonlar ─────────────────────────────────────────────────

/**
 * Güven skorunu renk sınıfına çevirir.
 */
export function getConfidenceColor(score: number): string {
  if (score >= 80) return "text-emerald-400";
  if (score >= 60) return "text-yellow-400";
  if (score >= 40) return "text-orange-400";
  return "text-red-400";
}

/**
 * Güven skorunu progress bar renk sınıfına çevirir.
 */
export function getConfidenceBarColor(score: number): string {
  if (score >= 80) return "bg-emerald-500";
  if (score >= 60) return "bg-yellow-500";
  if (score >= 40) return "bg-orange-500";
  return "bg-red-500";
}

/**
 * Sayıyı kısa formatta gösterir.
 * Örn: 1234 → "1.2K", 1234567 → "1.2M"
 */
export function formatNumber(num: number): string {
  if (num >= 1_000_000) return `${(num / 1_000_000).toFixed(1)}M`;
  if (num >= 1_000) return `${(num / 1_000).toFixed(1)}K`;
  return num.toString();
}

/**
 * Yüzde değerini formatlı string olarak döndürür.
 */
export function formatPercent(value: number, decimals: number = 1): string {
  return `${value.toFixed(decimals)}%`;
}

/**
 * CSS class name'lerini birleştirir (falsy değerleri filtreler).
 */
export function cn(...classes: (string | false | null | undefined)[]): string {
  return classes.filter(Boolean).join(" ");
}

/**
 * String'i kısaltır.
 * Örn: truncate("Çok uzun metin", 10) → "Çok uzun m…"
 */
export function truncate(str: string, maxLength: number): string {
  if (str.length <= maxLength) return str;
  return str.slice(0, maxLength) + "…";
}
