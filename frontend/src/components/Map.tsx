// ═══════════════════════════════════════════════════════════════════════════
// Map.tsx — GhostMap'i istemci tarafında yükleyen köprü.
// children, harita bağlamının (useMapContext) İÇİNDE render edilir.
// ═══════════════════════════════════════════════════════════════════════════

"use client";

import type { ReactNode } from "react";
import GhostMap from "./map/GhostMap";

export default function AppMap({ children }: { children?: ReactNode }) {
  return <GhostMap>{children}</GhostMap>;
}
