import type { Metadata } from "next";
import MapPage from "./MapPage";

const datasetSchema = {
  "@context": "https://schema.org",
  "@type": "Dataset",
  name: "GhostBuilding Anomalies Dataset",
  description: "A comprehensive dataset of global map anomalies, censored areas, and hidden structures.",
  url: "https://ghostbuilding.dev/",
  creator: {
    "@type": "Organization",
    name: "GhostBuilding"
  }
};

export const metadata: Metadata = {
  title: "GhostBuilding OSINT Platform",
  description: "Modern web UI for anomaly detection.",
};

export default function HomePage() {
  return (
    <>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(datasetSchema) }}
      />
      <MapPage />
    </>
  );
}
