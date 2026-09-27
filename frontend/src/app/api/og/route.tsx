import { ImageResponse } from "next/og";
import { NextRequest } from "next/server";

import { AnomalyCategory } from "@/lib/types";
import { CATEGORY_COLORS, CATEGORY_LABELS } from "@/lib/utils";

const CATEGORIES: Record<string, { label: string; hex: string }> = Object.fromEntries(
  Object.values(AnomalyCategory).map((c) => [c, { label: CATEGORY_LABELS[c], hex: CATEGORY_COLORS[c].hex }]),
);

const BG = "#0F1117";

export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const id = searchParams.get("id");
    const category = CATEGORIES[searchParams.get("category") ?? ""] ?? { label: "Anomali", hex: "#4A7CF7" };
    const score = Number(searchParams.get("score") ?? "0");
    const lat = Number(searchParams.get("lat"));
    const lng = Number(searchParams.get("lng"));

    if (!id) {
      return new ImageResponse(
        (
          <div
            style={{
              height: "100%",
              width: "100%",
              display: "flex",
              flexDirection: "column",
              justifyContent: "center",
              padding: 80,
              backgroundColor: BG,
              color: "#F0F2F5",
            }}
          >
            <div style={{ fontSize: 84, fontWeight: 800, letterSpacing: "-0.02em" }}>GhostBuilding</div>
            <div style={{ fontSize: 38, marginTop: 24, color: "#8B8FA3", maxWidth: 900 }}>
              Aynı konum, farklı uydu kaynakları: bulanıklaştırma ve sıra dışı farklar.
            </div>
          </div>
        ),
        { width: 1200, height: 630 }
      );
    }

    return new ImageResponse(
      (
        <div
          style={{
            height: "100%",
            width: "100%",
            display: "flex",
            justifyContent: "space-between",
            backgroundColor: BG,
            color: "#F0F2F5",
            padding: 72,
          }}
        >
          <div style={{ display: "flex", flexDirection: "column", justifyContent: "space-between", flex: 1 }}>
            <div style={{ display: "flex", flexDirection: "column" }}>
              <div style={{ display: "flex", alignItems: "center" }}>
                <div style={{ width: 18, height: 18, borderRadius: 9, backgroundColor: category.hex, marginRight: 16 }} />
                <span style={{ fontSize: 34, fontWeight: 600, color: category.hex }}>{category.label}</span>
              </div>
              <div style={{ fontSize: 40, color: "#8B8FA3", marginTop: 40, fontFamily: "monospace" }}>
                {Number.isFinite(lat) && Number.isFinite(lng) ? `${lat.toFixed(4)}, ${lng.toFixed(4)}` : ""}
              </div>
            </div>
            <div style={{ fontSize: 30, color: "#80859A" }}>GhostBuilding</div>
          </div>
          <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", justifyContent: "center", width: 360 }}>
            <div style={{ fontSize: 150, fontWeight: 900, lineHeight: 1 }}>
              {Number.isFinite(score) ? score.toFixed(1).replace(".", ",") : "—"}
            </div>
            <div style={{ fontSize: 30, color: "#8B8FA3", marginTop: 16 }}>anomali puanı / 100</div>
            <div style={{ fontSize: 24, color: "#80859A", marginTop: 8 }}>50 = sıradan konumların %99&apos;u</div>
          </div>
        </div>
      ),
      { width: 1200, height: 630 }
    );
  } catch (e) {
    console.error(e);
    return new Response("OG görseli üretilemedi", { status: 500 });
  }
}
