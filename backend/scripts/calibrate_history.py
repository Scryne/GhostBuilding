"""Tarihsel değişim (Esri Wayback) skoru için taban çizgisi ölçümü.

Sıradan bir konum da yıllar içinde değişir: yeni çekim, mevsim, renk dengesi, yeni bina.
Bu betik ``TimeSeriesAnalyzer``'ın ham tarihsel skorunun sıradan konumlardaki dağılımını
ölçer; ``historical_to_score`` eşikleri tahminle değil bu dağılımın üst yüzdelikleriyle
belirlenir (piksel farkı ve bulanıklıkla aynı yöntem, bkz. calibrate_diff.py).
Referans tesisleri (docs/reference-scan.json) ayrıca ölçülür; eşik onlardan kurulmaz.

Kullanım (backend/ içinden; anahtar gerekmez, Esri Wayback açık):
    python scripts/calibrate_history.py [--zoom 16] [--json ../docs/calibration-history-z16.json]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import sys
from collections import Counter
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.analyzers.time_series import TimeSeriesAnalyzer  # noqa: E402
from scripts.calibrate_diff import BASELINE_LOCATIONS, FRANCE_BASELINE, percentile  # noqa: E402

REFERENCE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "docs",
    "reference-scan.json",
)


async def measure_one(analyzer: TimeSeriesAnalyzer, lat: float, lng: float, zoom: int) -> dict[str, object]:
    timeline = await analyzer.fetch_timeline(lat, lng, zoom)
    changes = analyzer.detect_changes(timeline)
    score = analyzer.compute_historical_score(timeline, changes)
    return {
        "snapshot": len(timeline.entries),
        "yillar": [e.year for e in timeline.entries],
        "ham_skor": round(score, 2),
        "olaylar": dict(Counter(c.change_type.value for c in changes)),
    }


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--zoom", type=int, default=16)
    parser.add_argument("--json", default=None)
    args = parser.parse_args()

    analyzer = TimeSeriesAnalyzer()
    baseline: list[dict[str, object]] = []
    print("Taban (sıradan konumlar):")
    for name, lat, lng in BASELINE_LOCATIONS + FRANCE_BASELINE:
        row = {"konum": name, "lat": lat, "lng": lng, **await measure_one(analyzer, lat, lng, args.zoom)}
        baseline.append(row)
        print(f"  {name:24s} n={row['snapshot']:2d} skor={row['ham_skor']:6.2f} {row['olaylar']}")

    with open(REFERENCE_PATH, encoding="utf-8") as fh:
        reference_locations = json.load(fh)["konumlar"]
    reference: list[dict[str, object]] = []
    print("Referans konumlar:")
    for loc in reference_locations:
        row = {
            "konum": loc["konum"], "tur": loc["tur"], "lat": loc["lat"], "lng": loc["lng"],
            **await measure_one(analyzer, loc["lat"], loc["lng"], args.zoom),
        }
        reference.append(row)
        print(f"  [{row['tur']:7s}] {row['konum'][:30]:30s} n={row['snapshot']:2d} skor={row['ham_skor']:6.2f}")

    measured = [r for r in baseline if int(r["snapshot"]) >= 2]  # type: ignore[arg-type]
    scores = [float(r["ham_skor"]) for r in measured]  # type: ignore[arg-type]
    summary = {
        "median": round(statistics.median(scores), 2),
        "p90": round(percentile(scores, 0.90), 2),
        "p99": round(percentile(scores, 0.99), 2),
        "max": round(max(scores), 2),
    } if scores else {}
    events = Counter()
    for r in measured:
        events.update(r["olaylar"])  # type: ignore[arg-type]

    result = {
        "tarih": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "zoom": args.zoom,
        "olculen_taban": len(measured),
        "taban_toplam": len(baseline),
        "ham_skor": summary,
        "taban_olay_sayilari": dict(events),
        "taban": baseline,
        "referans": reference,
    }
    print(json.dumps({k: result[k] for k in ("olculen_taban", "ham_skor", "taban_olay_sayilari")},
                     ensure_ascii=False, indent=1))
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(result, fh, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    asyncio.run(main())
