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
  metadataBase: new URL(process.env.NEXT_PUBLIC_APP_URL || "https://ghostbuilding.dev"),
  title: {
    default: "GhostBuilding — Global Map Intelligence",
    template: "%s | GhostBuilding — Global Map Intelligence",
  },
  description:
    "Discover censored areas, hidden structures and map anomalies worldwide.",
  keywords: [
    "OSINT",
    "map anomalies",
    "censored maps",
    "hidden buildings",
    "satellite intelligence",
  ],
  authors: [{ name: "GhostBuilding Team" }],
  openGraph: {
    type: "website",
    locale: "en_US",
    siteName: "GhostBuilding",
    title: "GhostBuilding — Global Map Intelligence",
    description:
      "Discover censored areas, hidden structures and map anomalies worldwide.",
    images: [
      {
        url: "/api/og", // Fallback OG Image
        width: 1200,
        height: 630,
        alt: "GhostBuilding OG Image",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: "GhostBuilding — Global Map Intelligence",
    description:
      "Discover censored areas, hidden structures and map anomalies worldwide.",
  },
  robots: {
    index: true,
    follow: true,
  },
  alternates: {
    canonical: "/",
  },
};

export const viewport: Viewport = {
  themeColor: "#0A0E1A",
  width: "device-width",
  initialScale: 1,
};

// ── Root Layout ───────────────────────────────────────────────────────────

// Organization Schema (JSON-LD)
const organizationSchema = {
  "@context": "https://schema.org",
  "@type": "Organization",
  name: "GhostBuilding",
  url: "https://ghostbuilding.dev",
  logo: "https://ghostbuilding.dev/logo.png",
  description: "Global Map Intelligence & OSINT platform for identifying geographic manipulation.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark" suppressHydrationWarning>
      <head>
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(organizationSchema) }}
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
