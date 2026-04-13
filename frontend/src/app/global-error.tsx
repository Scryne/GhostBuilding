"use client";

/**
 * global-error.tsx — Next.js Global Error Boundary (Sentry Entegrasyonu)
 *
 * App Router'da yakalanamayan hatalar bu bileşen tarafından işlenir.
 * Sentry'ye otomatik raporlama yapılır.
 */

import * as Sentry from "@sentry/nextjs";
import { useEffect } from "react";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // Hatayı Sentry'ye raporla
    Sentry.captureException(error);
  }, [error]);

  return (
    <html lang="tr">
      <body
        style={{
          margin: 0,
          minHeight: "100vh",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: "#0a0a0f",
          color: "#e0e0e0",
          fontFamily: "'Inter', sans-serif",
        }}
      >
        <div
          style={{
            textAlign: "center",
            padding: "2rem",
            maxWidth: "480px",
          }}
        >
          <div style={{ fontSize: "4rem", marginBottom: "1rem" }}>⚠️</div>
          <h2
            style={{
              fontSize: "1.5rem",
              fontWeight: 600,
              marginBottom: "0.5rem",
              color: "#fff",
            }}
          >
            Beklenmeyen bir hata oluştu
          </h2>
          <p
            style={{
              color: "#888",
              marginBottom: "1.5rem",
              lineHeight: 1.6,
            }}
          >
            Üzgünüz, bir şeyler ters gitti. Hata otomatik olarak
            ekibimize bildirildi.
          </p>
          <button
            onClick={() => reset()}
            style={{
              padding: "0.75rem 2rem",
              background: "linear-gradient(135deg, #6366f1, #8b5cf6)",
              color: "#fff",
              border: "none",
              borderRadius: "8px",
              fontSize: "1rem",
              fontWeight: 500,
              cursor: "pointer",
              transition: "opacity 0.2s",
            }}
            onMouseEnter={(e) =>
              ((e.target as HTMLElement).style.opacity = "0.85")
            }
            onMouseLeave={(e) =>
              ((e.target as HTMLElement).style.opacity = "1")
            }
          >
            Tekrar Dene
          </button>
        </div>
      </body>
    </html>
  );
}
