"use client";

import Link from "next/link";
import { ArrowLeft, Map as MapIcon, ShieldAlert } from "lucide-react";
import { EvidenceView } from "@/components/anomaly";
import { useAnomalyDetail } from "@/hooks/useAnomaly";
import type { AnomalyDetail } from "@/lib/types";

export default function AnomalyPageView({ initial }: { initial: AnomalyDetail }) {
  const { data, mutate } = useAnomalyDetail(initial.id, { fallbackData: initial });
  const detail = data ?? initial;

  return (
    <div className="min-h-dvh bg-background">
      <header className="sticky top-0 z-30 border-b border-border bg-background/85 backdrop-blur-md">
        <div className="mx-auto flex max-w-6xl items-center gap-3 px-4 py-3">
          <Link href="/" className="flex items-center gap-2" aria-label="GhostBuilding haritası">
            <span className="rounded-lg bg-gradient-primary p-1.5">
              <ShieldAlert className="size-4 text-white" aria-hidden />
            </span>
            <span className="hidden text-sm font-bold text-gradient-brand sm:inline">GhostBuilding</span>
          </Link>
          <span className="h-5 w-px bg-border" aria-hidden />
          <Link
            href="/explore"
            className="inline-flex items-center gap-1.5 text-sm text-muted hover:text-foreground"
          >
            <ArrowLeft className="size-4" aria-hidden /> Tüm bulgular
          </Link>
          <Link
            href={`/?a=${detail.id}&lat=${detail.lat}&lng=${detail.lng}&z=15`}
            className="ml-auto inline-flex items-center gap-1.5 rounded-lg border border-secondary/30 bg-secondary/10 px-3 py-1.5 text-sm font-medium text-secondary hover:bg-secondary/15"
          >
            <MapIcon className="size-4" aria-hidden /> Haritada göster
          </Link>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-8">
        <EvidenceView detail={detail} variant="page" onUpdated={() => mutate()} />
      </main>
    </div>
  );
}
