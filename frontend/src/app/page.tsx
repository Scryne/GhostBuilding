import type { Metadata } from "next";
import MapPage from "./MapPage";

export const metadata: Metadata = {
  title: { absolute: "GhostBuilding — uydu görüntüsü farkları haritası" },
};

export default function HomePage() {
  return <MapPage />;
}
