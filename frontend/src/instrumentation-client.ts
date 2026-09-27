/**
 * sentry.client.config.ts — Frontend Sentry SDK (Client-Side)
 *
 * Next.js client tarafı Sentry konfigürasyonu.
 * Browser'da çalışan JavaScript hatalarını ve performans verilerini yakalar.
 *
 * @see https://docs.sentry.io/platforms/javascript/guides/nextjs/
 */

import * as Sentry from "@sentry/nextjs";

const SENTRY_DSN = process.env.NEXT_PUBLIC_SENTRY_DSN;

if (SENTRY_DSN) {
  Sentry.init({
    dsn: SENTRY_DSN,

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
}
