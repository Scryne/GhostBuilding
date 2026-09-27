/**
 * instrumentation.ts — Next.js Instrumentation Hook
 *
 * Sunucu ve edge Sentry SDK'sını başlatır; sunucu tarafı istek hatalarını Sentry'ye iletir.
 *
 * @see https://nextjs.org/docs/app/guides/instrumentation
 */

import * as Sentry from "@sentry/nextjs";

export async function register() {
  if (process.env.NEXT_RUNTIME === "nodejs") {
    await import("../sentry.server.config");
  }

  if (process.env.NEXT_RUNTIME === "edge") {
    await import("../sentry.edge.config");
  }
}

export const onRequestError = Sentry.captureRequestError;
