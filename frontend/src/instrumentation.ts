/**
 * instrumentation.ts — Next.js Instrumentation Hook
 *
 * Server-side ve edge Sentry SDK'yı başlatır.
 * Next.js 14+ instrumentation hook'u ile otomatik yüklenir.
 *
 * @see https://nextjs.org/docs/app/building-your-application/optimizing/instrumentation
 */

export async function register() {
  if (process.env.NEXT_RUNTIME === "nodejs") {
    await import("../sentry.server.config");
  }

  if (process.env.NEXT_RUNTIME === "edge") {
    await import("../sentry.edge.config");
  }
}
