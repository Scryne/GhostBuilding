import type { Metadata } from "next";
import { notFound } from "next/navigation";
import type { AnomalyDetail } from "@/lib/types";
import { CATEGORY_LABELS, formatScore } from "@/lib/utils";
import { SERVER_API_URL, SITE_URL } from "@/lib/site";
import AnomalyPageView from "./AnomalyPageView";

interface AnomalyProps {
  params: Promise<{ id: string }>;
}

async function getAnomaly(id: string): Promise<AnomalyDetail | null> {
  try {
    const res = await fetch(`${SERVER_API_URL}/anomalies/${id}`, { next: { revalidate: 60 } });
    if (!res.ok) return null;
    return (await res.json()) as AnomalyDetail;
  } catch {
    return null;
  }
}

function titleOf(anomaly: AnomalyDetail): string {
  const category = CATEGORY_LABELS[anomaly.category] ?? anomaly.category;
  return anomaly.location_label ? `${category} · ${anomaly.location_label}` : category;
}

export async function generateMetadata({ params }: AnomalyProps): Promise<Metadata> {
  const { id } = await params;
  const anomaly = await getAnomaly(id);
  if (!anomaly) return { title: "Anomali bulunamadı" };

  const title = titleOf(anomaly);
  const description =
    anomaly.description ??
    `${anomaly.lat.toFixed(4)}, ${anomaly.lng.toFixed(4)} konumunda kaynaklar arası görüntü anomalisi. Anomali puanı ${formatScore(anomaly.confidence_score)}.`;
  // Yalnız topluluk tarafından doğrulanmış kayıtlar dizine girer.
  const shouldIndex = anomaly.status === "VERIFIED";

  return {
    title,
    description,
    openGraph: {
      title,
      description,
      images: [
        {
          url: `/api/og?id=${anomaly.id}&category=${anomaly.category}&score=${anomaly.confidence_score.toFixed(1)}&lat=${anomaly.lat}&lng=${anomaly.lng}`,
          width: 1200,
          height: 630,
          alt: title,
        },
      ],
    },
    robots: { index: shouldIndex, follow: shouldIndex },
    alternates: { canonical: `/explore/${anomaly.id}` },
  };
}

export default async function AnomalyPage({ params }: AnomalyProps) {
  const { id } = await params;
  const anomaly = await getAnomaly(id);
  if (!anomaly) notFound();

  const placeSchema = {
    "@context": "https://schema.org",
    "@type": "Place",
    name: titleOf(anomaly),
    description: anomaly.description ?? undefined,
    geo: { "@type": "GeoCoordinates", latitude: anomaly.lat, longitude: anomaly.lng },
    url: `${SITE_URL}/explore/${anomaly.id}`,
    identifier: anomaly.id,
  };

  return (
    <>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(placeSchema) }}
      />
      <AnomalyPageView initial={anomaly} />
    </>
  );
}
