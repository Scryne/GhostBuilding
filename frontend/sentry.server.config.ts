/**
 * sentry.server.config.ts — Frontend Sentry SDK (Server-Side)
 *
 * Next.js server tarafı (SSR, API routes) Sentry konfigürasyonu.
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

    // Performance Monitoring — server tarafı
    tracesSampleRate: process.env.NODE_ENV === "production" ? 0.2 : 1.0,

    // Hassas verileri gönderme
    sendDefaultPii: false,

    // Hassas verileri filtrele
    beforeSend(event) {
      if (event.request?.headers) {
        const headers = event.request.headers as Record<string, string>;
        delete headers["cookie"];
        delete headers["authorization"];
      }
      return event;
    },
  });
}
