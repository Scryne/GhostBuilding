import { withSentryConfig } from "@sentry/nextjs";

/** @type {import('next').NextConfig} */
const nextConfig = {
  // Standalone output for Docker multi-stage builds
  output: "standalone",

  // Image optimization — allow external tile/satellite image sources
  images: {
    remotePatterns: [
      { protocol: "https", hostname: "tile.openstreetmap.org" },
      { protocol: "https", hostname: "mt0.google.com" },
      { protocol: "https", hostname: "mt1.google.com" },
      { protocol: "https", hostname: "ecn.t0.tiles.virtualearth.net" },
      { protocol: "https", hostname: "**.bing.com" },
      { protocol: "http", hostname: "localhost" },
    ],
    formats: ["image/avif", "image/webp"],
  },

  // Disable x-powered-by header for security
  poweredByHeader: false,

  // Strict React mode for better dev experience
  reactStrictMode: true,

  // ═══════════════════════════════════════════════════════════════════════
  // Security HTTP Headers
  // ═══════════════════════════════════════════════════════════════════════
  async headers() {
    return [
      {
        // Apply security headers to all routes
        source: "/(.*)",
        headers: [
          // Clickjacking protection
          {
            key: "X-Frame-Options",
            value: "DENY",
          },
          // MIME sniffing protection
          {
            key: "X-Content-Type-Options",
            value: "nosniff",
          },
          // XSS protection for legacy browsers
          {
            key: "X-XSS-Protection",
            value: "1; mode=block",
          },
          // Referrer policy
          {
            key: "Referrer-Policy",
            value: "strict-origin-when-cross-origin",
          },
          // HSTS — enforce HTTPS in production
          {
            key: "Strict-Transport-Security",
            value: "max-age=31536000; includeSubDomains; preload",
          },
          // Permissions policy — disable unnecessary browser APIs
          {
            key: "Permissions-Policy",
            value:
              "camera=(), microphone=(), geolocation=(self), payment=(), usb=()",
          },
          // Content Security Policy
          {
            key: "Content-Security-Policy",
            value: [
              "default-src 'self'",
              "script-src 'self' 'unsafe-inline' 'unsafe-eval'",
              "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
              "font-src 'self' https://fonts.gstatic.com",
              "img-src 'self' data: blob: https://*.openstreetmap.org https://*.google.com https://*.bing.com https://*.virtualearth.net",
              "connect-src 'self' http://localhost:8000 https://*.openstreetmap.org https://*.google.com https://*.bing.com https://*.sentry.io",
              "worker-src 'self' blob:",
              "frame-ancestors 'none'",
              "base-uri 'self'",
              "form-action 'self'",
            ].join("; "),
          },
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

  // Source map'leri deploy sonrası sil (güvenlik)
  widenClientFileUpload: true,
  hideSourceMaps: true,

  // Otomatik tree-shaking
  disableLogger: true,

  // Tunnel route — CSP ve ad-blocker'ları bypass et
  tunnelRoute: "/monitoring",
};

// Sentry DSN varsa Sentry wrapper'ı kullan, yoksa sadece bundle analyzer
const finalConfig = process.env.NEXT_PUBLIC_SENTRY_DSN
  ? withSentryConfig(analyzer(nextConfig), sentryConfig)
  : analyzer(nextConfig);

export default finalConfig;
