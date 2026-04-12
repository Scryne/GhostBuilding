// ═══════════════════════════════════════════════════════════════════════════
// Auth Layout — Login/Register sayfaları için ortak layout
// Ortada cam panel, arka planda gradient + animasyonlu grid.
// ═══════════════════════════════════════════════════════════════════════════

import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Giriş Yap",
};

export default function AuthLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="min-h-screen flex items-center justify-center bg-background relative overflow-hidden">
      {/* Animated grid background */}
      <div
        className="absolute inset-0 opacity-[0.03]"
        style={{
          backgroundImage: `
            linear-gradient(rgba(46, 109, 164, 0.4) 1px, transparent 1px),
            linear-gradient(90deg, rgba(46, 109, 164, 0.4) 1px, transparent 1px)
          `,
          backgroundSize: "60px 60px",
        }}
      />

      {/* Radial glow */}
      <div className="absolute top-1/4 left-1/2 -translate-x-1/2 w-[600px] h-[600px] bg-secondary/[0.06] rounded-full blur-[120px] pointer-events-none" />
      <div className="absolute bottom-0 right-0 w-[400px] h-[400px] bg-ghost/[0.04] rounded-full blur-[100px] pointer-events-none" />

      {/* Content */}
      <div className="relative z-10 w-full max-w-[440px] mx-4">
        {children}
      </div>

      {/* Override body overflow */}
      <style>{`body { overflow: auto !important; }`}</style>
    </div>
  );
}
