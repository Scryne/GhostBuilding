import { Metadata } from "next";
import { notFound } from "next/navigation";

interface AnomalyProps {
  params: { id: string };
}

// Optional: Simulate API fetch
async function getAnomalyData(id: string) {
  try {
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1';
    const res = await fetch(`${apiUrl}/anomalies/${id}`, {
      next: { revalidate: 60 * 5 },
    });
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

export async function generateMetadata({ params }: AnomalyProps): Promise<Metadata> {
  const anomaly = await getAnomalyData(params.id);

  if (!anomaly) {
    return {
      title: "Anomaly Not Found",
    };
  }

  const title = `${anomaly.category.replace(/_/g, ' ')} detected at ${anomaly.lat}, ${anomaly.lng}`;
  const description = anomaly.description || `A verified geospatial anomaly at coordinates ${anomaly.lat}, ${anomaly.lng}. Confidence score: ${anomaly.confidence_score}.`;
  
  // Example for robots noindex option based on anomaly status or confidence
  const shouldIndex = anomaly.status === "VERIFIED";

  return {
    title,
    description,
    openGraph: {
      title,
      description,
      images: [
        {
          url: `/api/og?id=${anomaly.id}&category=${anomaly.category}&score=${anomaly.confidence_score}&lat=${anomaly.lat}&lng=${anomaly.lng}`,
          width: 1200,
          height: 630,
          alt: title,
        },
      ],
    },
    robots: {
      index: shouldIndex,
      follow: shouldIndex,
    },
    alternates: {
      canonical: `/explore/${anomaly.id}`,
    },
  };
}

export default async function AnomalyPage({ params }: AnomalyProps) {
  const anomaly = await getAnomalyData(params.id);

  if (!anomaly) {
    notFound();
  }

  // Schema.org structured data for Place
  const placeSchema = {
    "@context": "https://schema.org",
    "@type": "Place",
    name: `Geospatial Anomaly: ${anomaly.category.replace(/_/g, ' ')}`,
    description: anomaly.description || "Detected geographic mapping discrepancy.",
    geo: {
      "@type": "GeoCoordinates",
      latitude: anomaly.lat,
      longitude: anomaly.lng,
    },
    url: `https://ghostbuilding.dev/explore/${anomaly.id}`,
    identifier: anomaly.id,
  };

  return (
    <main className="container mx-auto px-4 py-8 mt-16 max-w-4xl text-white">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(placeSchema) }}
      />
      <div className="glass-panel p-8">
        <h1 className="text-3xl font-bold mb-4">{anomaly.category.replace(/_/g, ' ')}</h1>
        
        <div className="flex items-center gap-4 mb-6">
          <div className="px-3 py-1 bg-secondary/20 text-secondary rounded-full font-mono text-sm border border-secondary/30">
            Score: {anomaly.confidence_score}
          </div>
          <div className="px-3 py-1 bg-white/5 text-gray-300 rounded-full font-mono text-sm border border-white/10">
            {anomaly.lat}, {anomaly.lng}
          </div>
          <div className={`px-3 py-1 rounded-full font-mono text-sm border ${anomaly.status === 'VERIFIED' ? 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30' : 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30'}`}>
            {anomaly.status}
          </div>
        </div>

        <p className="text-gray-300 mb-8 whitespace-pre-wrap">{anomaly.description || "No detailed description provided for this anomaly."}</p>

        {/* Detailed satellite UI placeholder */}
        <div className="w-full h-96 bg-black/50 rounded-xl flex items-center justify-center border border-white/10 relative overflow-hidden">
             <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
                 <div className="w-32 h-32 border border-secondary/50 rounded-lg animate-pulse" />
             </div>
             <span className="text-gray-500 font-mono text-sm">Interactive Map Viewer (Focus on {anomaly.lat}, {anomaly.lng})</span>
        </div>
      </div>
    </main>
  );
}
