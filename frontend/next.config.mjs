// Sentry 11: yapılandırma sarmalayıcısı ayrı alt yoldan gelir.
import { withSentryConfig } from "@sentry/nextjs/config";
import { existsSync, readFileSync } from "node:fs";
import { parseEnv } from "node:util";

// Yerel derleme: ortam dosyası repo kökünde (compose ile ortak). NEXT_PUBLIC_* değerleri
// derleme anında koda gömülür; tanımlı değilse MapTiler altlığı sessizce kaybolur. Yalnız
// NEXT_PUBLIC_* alınır (sırlar derleme sürecine girmez), ortamda zaten olan ezilmez.
// Docker derlemesinde bu dosya bağlamda yoktur; orada build arg'ları geçerlidir.
const ROOT_ENV = new URL("../.env", import.meta.url);
if (existsSync(ROOT_ENV)) {
  for (const [key, value] of Object.entries(parseEnv(readFileSync(ROOT_ENV, "utf-8")))) {
    if (key.startsWith("NEXT_PUBLIC_") && process.env[key] === undefined) process.env[key] = value;
  }
}

// API kökeni: CSP'deki connect-src/img-src ve kanıt görselleri (/media/...) buradan gelir.
// Eskiden http://localhost:8000 sabit yazılıydı; üretimde API başka bir adreste olunca
// harita verisi ve görseller tarayıcıda engellenirdi.
const API_ORIGIN = (() => {
  try {
    return new URL(process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1").origin;
  } catch {
    return "http://localhost:8000";
  }
})();

// Harita altlığı (CARTO), uydu karoları (Esri, MapTiler, IGN), adres arama (Nominatim).
const MAP_HOSTS = [
  "https://*.basemaps.cartocdn.com",
  "https://basemaps.cartocdn.com",
  "https://server.arcgisonline.com",
  "https://api.maptiler.com",
  "https://data.geopf.fr",
  "https://tile.openstreetmap.org",
];

const CSP = [
  "default-src 'self'",
  "script-src 'self' 'unsafe-inline' 'unsafe-eval'",
  "style-src 'self' 'unsafe-inline'",
  "font-src 'self' data:",
  `img-src 'self' data: blob: ${API_ORIGIN} ${MAP_HOSTS.join(" ")}`,
  `connect-src 'self' ${API_ORIGIN} ${MAP_HOSTS.join(" ")} https://nominatim.openstreetmap.org https://*.sentry.io`,
  // MapLibre çizimi blob: worker'da yapar; worker-src olmadan harita boş kalıyordu.
  "worker-src 'self' blob:",
  "child-src blob:",
  "object-src 'none'",
  "frame-ancestors 'none'",
  "base-uri 'self'",
  "form-action 'self'",
].join("; ");

/** @type {import('next').NextConfig} */
const nextConfig = {
  // Standalone output for Docker multi-stage builds
  output: "standalone",

  // Kanıt görselleri API'den gelir; yeniden sıkıştırılmaz (piksel farkı görünür kalmalı).
  images: {
    remotePatterns: [new URL(`${API_ORIGIN}/media/**`)],
  },

  // Disable x-powered-by header for security
  poweredByHeader: false,

  // Strict React mode for better dev experience
  reactStrictMode: true,

  // Güvenlik başlıkları — tek kaynak (proxy.ts ikinci bir CSP göndermez).
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: [
          { key: "X-Frame-Options", value: "DENY" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "Strict-Transport-Security", value: "max-age=31536000; includeSubDomains" },
          {
            key: "Permissions-Policy",
            value: "camera=(), microphone=(), geolocation=(self), payment=(), usb=()",
          },
          { key: "Content-Security-Policy", value: CSP },
        ],
      },
    ];
  },

  // Experimental features
  experimental: {
    optimizePackageImports: ["lucide-react"],
  },
};

import withBundleAnalyzer from '@next/bundle-analyzer';

const analyzer = withBundleAnalyzer({
  enabled: process.env.ANALYZE === 'true',
});

// Sentry yapılandırması ile sarmalama
const sentryConfig = {
  // Sentry organization and project slugs
  org: process.env.SENTRY_ORG || "ghostbuilding",
  project: process.env.SENTRY_PROJECT || "ghostbuilding-frontend",

  // Build sırasında source map'leri Sentry'ye yükle
  silent: !process.env.CI,
  widenClientFileUpload: true,

  // Tunnel route — CSP ve ad-blocker'ları bypass et
  tunnelRoute: "/monitoring",
};

// Sentry DSN varsa Sentry wrapper'ı kullan, yoksa sadece bundle analyzer
const finalConfig = process.env.NEXT_PUBLIC_SENTRY_DSN
  ? withSentryConfig(analyzer(nextConfig), sentryConfig)
  : analyzer(nextConfig);

export default finalConfig;
