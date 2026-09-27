"""Referans taraması: demo verisini gerçek analizle üretir.

Eski seed 20 konuma elle yazılmış güven skorları ve var olmayan görsel adresleri
basıyordu. Bu betik, kamuya açık kaynaklarda adı geçen tesisleri ve karşılaştırma için
sıradan konumları aynı anomali motorundan geçirir. Veritabanına yalnız motorun eşiği
geçirdiği sonuçlar yazılır. Konum başına tüm puanlar, eşik altında kalanlar dahil,
bir JSON raporuna dökülür.

Kullanım (backend/ içinden; DATABASE_URL, MAPTILER_API_KEY tanımlı):
    python scripts/seed_data.py [--reset] [--rapor ../docs/reference-scan.json]

--reset yalnız motorun ürettiği anomalileri siler (meta_data.reference_scan = true).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text  # noqa: E402

from app.config import settings  # noqa: E402
from app.db.session import AsyncSessionLocal, engine as db_engine  # noqa: E402
from app.services.anomaly_engine import AnomalyEngine  # noqa: E402

# (ad, enlem, boylam, tür). "tesis": kamuya açık kaynaklarda adı geçen askeri/nükleer
# tesis. "kontrol": sıradan konum; motorun bunları işaretlememesi beklenir.
REFERENCE_SITES: list[tuple[str, float, float, str]] = [
    ("Groom Lake (Area 51), ABD", 37.2431, -115.7930, "tesis"),
    ("Pine Gap, Avustralya", -23.7990, 133.7370, "tesis"),
    ("RAF Menwith Hill, Birleşik Krallık", 54.0086, -1.6897, "tesis"),
    ("Diego Garcia", -7.3133, 72.4111, "tesis"),
    ("Yongbyon, Kuzey Kore", 39.7950, 125.7550, "tesis"),
    ("Natanz, İran", 33.7250, 51.7270, "tesis"),
    ("Dimona, İsrail", 31.0010, 35.1450, "tesis"),
    ("Île Longue, Fransa", 48.3055, -4.5140, "tesis"),
    ("Istres-Le Tubé hava üssü, Fransa", 43.5230, 4.9240, "tesis"),
    ("Volkel hava üssü, Hollanda", 51.6566, 5.7080, "tesis"),
    ("Sivastopol körfezi", 44.6167, 33.5250, "tesis"),
    # Fransa: IGN ortofotolarında hassas alanlar maskelenir; burada üç kaynak karşılaştırılır.
    ("Brest askeri limanı, Fransa", 48.3830, -4.5000, "tesis"),
    ("Cherbourg askeri limanı, Fransa", 49.6450, -1.6280, "tesis"),
    ("Taverny hava üssü (BA 921), Fransa", 49.0270, 2.2170, "tesis"),
    ("Mont Verdun (BA 942), Fransa", 45.8630, 4.7690, "tesis"),
    ("CEA Valduc, Fransa", 47.5790, 4.8680, "tesis"),
    ("Marcoule nükleer sahası, Fransa", 44.1440, 4.7120, "tesis"),
    ("Saint-Dizier hava üssü (BA 113), Fransa", 48.6360, 4.8990, "tesis"),
    ("Avord hava üssü (BA 702), Fransa", 47.0530, 2.6330, "tesis"),
    ("Luxeuil hava üssü (BA 116), Fransa", 47.7870, 6.3640, "tesis"),
    ("Kadıköy, İstanbul", 40.9903, 29.0290, "kontrol"),
    ("Berlin Mitte", 52.5200, 13.4050, "kontrol"),
    ("Paris merkez", 48.8566, 2.3522, "kontrol"),
    ("Iowa tarım alanı", 42.0308, -93.6319, "kontrol"),
    # Fransız kontroller kalibrasyon setinde yok (bkz. calibrate_diff.FRANCE_BASELINE).
    ("Tours merkez", 47.3941, 0.6848, "kontrol"),
    ("Reims merkez", 49.2583, 4.0317, "kontrol"),
    ("Montpellier merkez", 43.6108, 3.8767, "kontrol"),
]


async def reset_reference_anomalies() -> int:
    async with AsyncSessionLocal() as session:
        ids = "SELECT id FROM anomalies WHERE meta_data->>'reference_scan' = 'true'"
        await session.execute(text(f"DELETE FROM anomaly_images WHERE anomaly_id IN ({ids})"))
        await session.execute(text(f"DELETE FROM verifications WHERE anomaly_id IN ({ids})"))
        result = await session.execute(
            text("DELETE FROM anomalies WHERE meta_data->>'reference_scan' = 'true'")
        )
        await session.commit()
        return result.rowcount or 0


async def tag_reference_anomalies(name: str, kind: str, since: datetime) -> int:
    """Bu konum için motorun az önce yazdığı kayıtlara referans etiketini ekler."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text(
                """
                UPDATE anomalies
                SET meta_data = COALESCE(meta_data, '{}'::jsonb)
                    || jsonb_build_object('reference_scan', true,
                                          'reference_site', CAST(:name AS text),
                                          'reference_kind', CAST(:kind AS text))
                WHERE created_at >= :since
                  AND (meta_data->>'reference_scan') IS NULL
                """
            ),
            {"name": name, "kind": kind, "since": since},
        )
        await session.commit()
        return result.rowcount or 0


async def run(reset: bool) -> list[dict[str, object]]:
    if reset:
        print(f"Önceki referans anomalileri silindi: {await reset_reference_anomalies()}")

    engine = AnomalyEngine(min_confidence=settings.ANOMALY_CONFIDENCE_THRESHOLD)
    rows: list[dict[str, object]] = []
    for name, lat, lng, kind in REFERENCE_SITES:
        started = datetime.now(timezone.utc)
        candidates = await engine.analyze(lat, lng, settings.ANALYSIS_ZOOM)
        tagged = await tag_reference_anomalies(name, kind, started) if candidates else 0
        breakdown = engine.last_run.get("score_breakdown") or {}
        rows.append({
            "konum": name,
            "tur": kind,
            "lat": lat,
            "lng": lng,
            "kaynaklar": engine.last_run.get("providers", []),
            "ham_piksel_farki": breakdown.get("raw_max_diff"),
            "ham_sansur": breakdown.get("raw_censorship"),
            "piksel_puani": breakdown.get("pixel_diff_score"),
            "bulaniklik_puani": breakdown.get("blur_censorship_score"),
            "anomaliler": [
                {"kategori": c.category, "guven": round(c.confidence_score, 1)} for c in candidates
            ],
            "yazilan": tagged,
        })
        flags = ", ".join(f"{c.category} {c.confidence_score:.0f}" for c in candidates) or "—"
        print(
            f"  {name:36s} fark={breakdown.get('raw_max_diff', 0):5.1f} "
            f"sansür={breakdown.get('raw_censorship', 0):4.0f}  → {flags}"
        )
    return rows


async def main_async(args: argparse.Namespace) -> None:
    try:
        rows = await run(args.reset)
    finally:
        await db_engine.dispose()

    flagged = [r for r in rows if r["anomaliler"]]
    controls_flagged = [r for r in flagged if r["tur"] == "kontrol"]
    print(
        f"\n{len(rows)} konum tarandı, {len(flagged)} konumda anomali "
        f"(kontrol konumlarında: {len(controls_flagged)})."
    )
    if args.rapor:
        report = {
            "tarih": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "zoom": settings.ANALYSIS_ZOOM,
            "esik": settings.ANOMALY_CONFIDENCE_THRESHOLD,
            "konumlar": rows,
        }
        with open(args.rapor, "w", encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=1)
        print(f"Rapor: {args.rapor}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--reset", action="store_true", help="önceki referans anomalilerini sil")
    parser.add_argument("--rapor", default=None, help="konum başına puanları JSON'a yaz")
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING)
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
