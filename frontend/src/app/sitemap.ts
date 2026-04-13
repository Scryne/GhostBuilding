import { MetadataRoute } from 'next'

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const baseUrl = process.env.NEXT_PUBLIC_APP_URL || 'https://ghostbuilding.dev';
  
  const staticRoutes: MetadataRoute.Sitemap = [
    {
      url: `${baseUrl}`,
      lastModified: new Date(),
      changeFrequency: 'daily',
      priority: 1,
    },
    {
      url: `${baseUrl}/explore`,
      lastModified: new Date(),
      changeFrequency: 'hourly',
      priority: 0.8,
    },
  ];

  let dynamicRoutes: MetadataRoute.Sitemap = [];
  try {
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1';
    // Sadece VERIFIED olan anomalileri sitemap'e dahil et
    const res = await fetch(`${apiUrl}/anomalies/?status=VERIFIED&limit=1000`, { 
      next: { revalidate: 3600 * 24 } // günlük yenile
    });
    
    if (res.ok) {
        const data = await res.json();
        const anomalies = data.items || [];
        dynamicRoutes = anomalies.map((anomaly: { id: string, updated_at: string, created_at: string }) => ({
            url: `${baseUrl}/explore/${anomaly.id}`,
            lastModified: new Date(anomaly.updated_at || anomaly.created_at),
            changeFrequency: 'weekly',
            priority: 0.6,
        }));
    }
  } catch (error) {
    console.error("Failed to generate sitemap for anomalies:", error);
  }

  return [...staticRoutes, ...dynamicRoutes];
}
