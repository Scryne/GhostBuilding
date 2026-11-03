/**
 * sentry-client.ts — Tarayıcı Sentry SDK kurulumu.
 *
 * Yalnız NEXT_PUBLIC_SENTRY_DSN tanımlıyken instrumentation-client.ts tarafından dinamik
 * import ile yüklenir. Böylece SDK (Session Replay/rrweb dahil, küçültülmüş ~370 KB) ana parçaya girmez;
 * DSN yokken hiç indirilmez, varken kabuğun hidrasyonunu beklemeden ayrı parça olarak gelir.
 *
 * @see https://docs.sentry.io/platforms/javascript/guides/nextjs/
 */

import * as Sentry from "@sentry/nextjs";

Sentry.init({
  dsn: process.env.NEXT_PUBLIC_SENTRY_DSN,

  // Environment
  environment: process.env.NODE_ENV || "development",
  release: `ghostbuilding-frontend@${process.env.NEXT_PUBLIC_APP_VERSION || "0.1.0"}`,

  // Performance Monitoring
  tracesSampleRate: process.env.NODE_ENV === "production" ? 0.2 : 1.0,

  // Session Replay — üretimde %10 normal, %100 hata durumunda
  replaysSessionSampleRate: 0.1,
  replaysOnErrorSampleRate: 1.0,

  integrations: [
    Sentry.replayIntegration({
      // Hassas verileri maskeleme
      maskAllText: false,
      maskAllInputs: true,
      blockAllMedia: false,
    }),
    Sentry.browserTracingIntegration({
      // Slow request eşiği
      enableLongTask: true,
    }),
  ],

  // Hassas verileri filtrele
  beforeSend(event) {
    // Authorization header'larını temizle
    if (event.request?.headers) {
      const headers = event.request.headers as Record<string, string>;
      if (headers["authorization"]) {
        headers["authorization"] = "***REDACTED***";
      }
      if (headers["cookie"]) {
        headers["cookie"] = "***REDACTED***";
      }
    }
    return event;
  },

  // Gürültücü hataları filtrele
  ignoreErrors: [
    // Browser eklentileri
    "top.GLOBALS",
    "ResizeObserver loop",
    // Ağ hataları (kullanıcı tarafı)
    "Network request failed",
    "Failed to fetch",
    "Load failed",
    // Cancelled navigasyon
    "Navigation cancelled",
    "AbortError",
  ],
});

export { Sentry };
