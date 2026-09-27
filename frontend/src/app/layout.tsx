import type { Metadata, Viewport } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import { ToastProvider } from "@/components/ui/Toast";
import { SITE_URL } from "@/lib/site";
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

const DESCRIPTION =
  "Aynı konumun farklı uydu kaynaklarındaki görüntülerini karşılaştırır; bulanıklaştırma ve " +
  "sıra dışı farkları, sıradan konumlara göre kalibre edilmiş puanla işaretler.";

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: {
    default: "GhostBuilding — uydu görüntüsü farkları",
    template: "%s · GhostBuilding",
  },
  description: DESCRIPTION,
  keywords: ["OSINT", "uydu görüntüsü", "harita sansürü", "görüntü karşılaştırma", "Esri", "IGN"],
  openGraph: {
    type: "website",
    locale: "tr_TR",
    siteName: "GhostBuilding",
    title: "GhostBuilding — uydu görüntüsü farkları",
    description: DESCRIPTION,
    images: [{ url: "/api/og", width: 1200, height: 630, alt: "GhostBuilding" }],
  },
  twitter: {
    card: "summary_large_image",
    title: "GhostBuilding — uydu görüntüsü farkları",
    description: DESCRIPTION,
  },
  robots: { index: true, follow: true },
  alternates: { canonical: "/" },
};

export const viewport: Viewport = {
  themeColor: "#0F1117",
  width: "device-width",
  initialScale: 1,
};

const websiteSchema = {
  "@context": "https://schema.org",
  "@type": "WebApplication",
  name: "GhostBuilding",
  url: SITE_URL,
  applicationCategory: "Geospatial analysis",
  inLanguage: "tr",
  description: DESCRIPTION,
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="tr" className="dark" suppressHydrationWarning>
      <head>
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(websiteSchema) }}
        />
      </head>
      <body
        className={`${inter.variable} ${jetbrainsMono.variable} font-sans antialiased bg-background text-foreground`}
      >
        {children}
        <ToastProvider />
      </body>
    </html>
  );
}
