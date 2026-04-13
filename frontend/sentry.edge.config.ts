/**
 * sentry.edge.config.ts — Frontend Sentry SDK (Edge Runtime)
 *
 * Next.js Edge Runtime (middleware, edge API routes) için Sentry konfigürasyonu.
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

    // Edge runtime'da düşük sample rate
    tracesSampleRate: process.env.NODE_ENV === "production" ? 0.1 : 0.5,
  });
}
