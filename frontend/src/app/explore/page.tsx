// ═══════════════════════════════════════════════════════════════════════════
// Explore Page — Server Component (Metadata)
// Next.js App Router: metadata server-side, içerik client-side.
// ═══════════════════════════════════════════════════════════════════════════

import type { Metadata } from "next";
import ExploreContent from "./ExploreContent";

export const metadata: Metadata = {
  title: "Keşfet",
  description:
    "GhostBuilding anomali veritabanını filtreleyin, arayın ve keşfedin. Hayalet yapılar, sansürlü alanlar ve görüntü farklılıkları.",
};

export default function ExplorePage() {
  return <ExploreContent />;
}
