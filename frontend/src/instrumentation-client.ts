/**
 * instrumentation-client.ts — Frontend Sentry SDK (Client-Side)
 *
 * SDK burada statik import EDİLMEZ: statik import, DSN tanımlı olmasa bile Sentry'yi
 * (Session Replay/rrweb dahil) her sayfanın ana parçasına koyuyor ve ana iş parçacığında
 * ayrıştırılıyordu. Kurulum src/lib/sentry-client.ts'te; yalnız DSN varken yüklenir.
 * DSN derleme anında koda gömülür, yoksa aşağıdaki dal ve parça derlemeden düşer.
 */

import type * as SentryNs from "@sentry/nextjs";

let sentry: typeof SentryNs | null = null;

if (process.env.NEXT_PUBLIC_SENTRY_DSN) {
  void import("./lib/sentry-client").then((m) => {
    sentry = m.Sentry;
  });
}

// Next.js 15+ istemci gezinme izleri. SDK yüklenmeden önceki gezinmeler iz üretmez
// (ilk sayfa yüklemesi browserTracingIntegration tarafından ayrıca ölçülür).
export function onRouterTransitionStart(
  ...args: Parameters<typeof SentryNs.captureRouterTransitionStart>
) {
  sentry?.captureRouterTransitionStart(...args);
}
