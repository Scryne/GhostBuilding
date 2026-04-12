import type { Metadata, Viewport } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import { ToastProvider } from "@/components/ui/Toast";
import "./globals.css";

// ── Fontlar ───────────────────────────────────────────────────────────────

const inter = Inter({
  subsets: ["latin", "latin-ext"],
  variable: "--font-inter",
  display: "swap",
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-jetbrains",
  display: "swap",
});

// ── Metadata ──────────────────────────────────────────────────────────────

export const metadata: Metadata = {
  title: {
    default: "GhostBuilding — OSINT Mapping Intelligence",
    template: "%s | GhostBuilding",
  },
  description:
    "Uydu ve harita sağlayıcıları arasındaki farklılıkları tespit eden açık kaynak istihbarat platformu. Hayalet yapılar, sansürlü alanlar ve gizli yapıları ortaya çıkarın.",
  keywords: [
    "OSINT",
    "ghost building",
    "satellite intelligence",
    "map discrepancy",
    "geospatial analysis",
    "censorship detection",
  ],
  authors: [{ name: "GhostBuilding Team" }],
  openGraph: {
    type: "website",
    locale: "tr_TR",
    siteName: "GhostBuilding",
    title: "GhostBuilding — OSINT Mapping Intelligence",
    description:
      "Harita sağlayıcıları arasındaki anomalileri tespit eden istihbarat platformu.",
  },
  robots: {
    index: true,
    follow: true,
  },
};

export const viewport: Viewport = {
  themeColor: "#0A0E1A",
  width: "device-width",
  initialScale: 1,
};

// ── Root Layout ───────────────────────────────────────────────────────────

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="tr" className="dark" suppressHydrationWarning>
      <body
        className={`${inter.variable} ${jetbrainsMono.variable} font-sans antialiased bg-background text-foreground`}
      >
        {children}
        <ToastProvider />
      </body>
    </html>
  );
}
