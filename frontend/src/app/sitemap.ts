import type { MetadataRoute } from "next";
import { SERVER_API_URL, SITE_URL } from "@/lib/site";

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const staticRoutes: MetadataRoute.Sitemap = [
    { url: SITE_URL, lastModified: new Date(), changeFrequency: "daily", priority: 1 },
    { url: `${SITE_URL}/explore`, lastModified: new Date(), changeFrequency: "hourly", priority: 0.8 },
  ];

  // Yalnız topluluk tarafından doğrulanmış bulgular dizine girer (detay sayfası da aynı kuralı uygular).
  // Liste yanıtı { data, pagination } biçimindedir; eskiden "items" okunduğu için hiçbir bulgu girmiyordu.
  let dynamicRoutes: MetadataRoute.Sitemap = [];
  try {
    const res = await fetch(`${SERVER_API_URL}/anomalies/?status=VERIFIED&min_confidence=0&limit=100`, {
      next: { revalidate: 3600 },
    });
    if (res.ok) {
      const body: { data: Array<{ id: string; detected_at: string | null }> } = await res.json();
      dynamicRoutes = body.data.map((a) => ({
        url: `${SITE_URL}/explore/${a.id}`,
        lastModified: a.detected_at ? new Date(a.detected_at) : new Date(),
        changeFrequency: "weekly",
        priority: 0.6,
      }));
    }
  } catch (error) {
    console.error("Sitemap için bulgular alınamadı:", error);
  }

  return [...staticRoutes, ...dynamicRoutes];
}
