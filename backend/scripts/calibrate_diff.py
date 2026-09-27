"""Sağlayıcılar arası piksel farkı ve bulanıklık için taban çizgisi ölçümü (eşik kalibrasyonu).

İki bağımsız uydu mozaiği (Esri World Imagery, MapTiler Satellite) sıradan bir yerde de
farklıdır: çekim tarihi, mevsim, güneş açısı, renk dengesi, çözünürlük. Bu betik sıradan
konumlarda bu "normal" farkın ve bulanıklık-sansür skorunun dağılımını ölçer; anomali eşikleri tahminle değil bu dağılımın üst
yüzdelikleriyle belirlenir (bkz. docs/algorithms.md).

Kullanım (backend/ içinden, MAPTILER_API_KEY tanımlı):
    python scripts/calibrate_diff.py [--zoom 16] [--bolge dunya|fransa] [--json cikti.json]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.analyzers.blur_detector import BlurDetector  # noqa: E402
from app.services.analyzers.pixel_diff import PixelDiffAnalyzer  # noqa: E402
from app.services.tile_fetcher import TileFetcher, imagery_providers  # noqa: E402

# Sıradan, sansür beklenmeyen konumlar: farklı kıtalar, yoğunluklar ve arazi türleri.
BASELINE_LOCATIONS: list[tuple[str, float, float]] = [
    ("Istanbul Kadikoy", 40.9903, 29.0290),
    ("Ankara Kizilay", 39.9208, 32.8541),
    ("Izmir Alsancak", 38.4370, 27.1430),
    ("Konya merkez", 37.8716, 32.4930),
    ("Eskisehir", 39.7767, 30.5206),
    ("Trabzon", 41.0027, 39.7168),
    ("Berlin Mitte", 52.5200, 13.4050),
    ("Madrid Centro", 40.4168, -3.7038),
    ("Rome Trastevere", 41.8894, 12.4700),
    ("Warsaw", 52.2297, 21.0122),
    ("Lyon", 45.7640, 4.8357),
    ("Porto", 41.1579, -8.6291),
    ("Chicago Loop", 41.8781, -87.6298),
    ("Denver", 39.7392, -104.9903),
    ("Toronto", 43.6532, -79.3832),
    ("Mexico City", 19.4326, -99.1332),
    ("Bogota", 4.7110, -74.0721),
    ("Sao Paulo", -23.5505, -46.6333),
    ("Buenos Aires", -34.6037, -58.3816),
    ("Lima", -12.0464, -77.0428),
    ("Nairobi", -1.2921, 36.8219),
    ("Lagos", 6.5244, 3.3792),
    ("Cairo Zamalek", 30.0626, 31.2197),
    ("Casablanca", 33.5731, -7.5898),
    ("Johannesburg", -26.2041, 28.0473),
    ("Mumbai Bandra", 19.0596, 72.8295),
    ("Bangkok", 13.7563, 100.5018),
    ("Jakarta", -6.2088, 106.8456),
    ("Seoul", 37.5665, 126.9780),
    ("Osaka", 34.6937, 135.5023),
    ("Melbourne", -37.8136, 144.9631),
    ("Auckland", -36.8485, 174.7633),
    ("Iowa farmland", 42.0308, -93.6319),
    ("Anatolia farmland", 38.9000, 33.5000),
    ("Ukraine farmland", 49.5000, 32.0000),
    ("Sahara edge", 31.6295, -7.9811),
    ("Norway coast", 60.3913, 5.3221),
    ("Amazon edge", -3.1190, -60.0217),
    ("Alps valley", 46.5197, 7.9800),
    ("Scottish highlands", 57.1200, -4.7100),
]

# Fransa: burada IGN üçüncü kaynak olarak girer; üç kaynaklı karşılaştırmanın tabanı ayrı ölçülür.
FRANCE_BASELINE: list[tuple[str, float, float]] = [
    ("Paris 11e", 48.8590, 2.3800),
    ("Lyon Part-Dieu", 45.7606, 4.8570),
    ("Marseille", 43.2965, 5.3698),
    ("Toulouse", 43.6047, 1.4442),
    ("Nantes", 47.2184, -1.5536),
    ("Lille", 50.6292, 3.0573),
    ("Strasbourg", 48.5734, 7.7521),
    ("Bordeaux", 44.8378, -0.5792),
    ("Rennes", 48.1173, -1.6778),
    ("Dijon", 47.3220, 5.0415),
    ("Clermont-Ferrand", 45.7772, 3.0870),
    ("Rouen", 49.4432, 1.0999),
    ("Beauce tarım", 48.3000, 1.7000),
    ("Champagne bağları", 49.0400, 3.9500),
    ("Landes ormanı", 44.1500, -0.9000),
    ("Bretagne kıyısı", 47.8700, -3.9300),
    ("Alpes vadisi", 45.9000, 6.1200),
    ("Provence", 43.9500, 4.8000),
    ("Massif Central", 45.2000, 2.8000),
    ("Normandiya bocage", 49.1800, -0.3700),
]


def percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    k = (len(ordered) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (k - lo)


async def measure(zoom: int, locations: list[tuple[str, float, float]]) -> dict[str, object]:
    if len(imagery_providers()) < 2:
        raise SystemExit("İki uydu kaynağı gerekli (MAPTILER_API_KEY tanımlı mı?).")
    analyzer = PixelDiffAnalyzer()
    blur = BlurDetector()
    rows: list[dict[str, object]] = []
    async with TileFetcher(use_cache=False) as fetcher:
        for name, lat, lng in locations:
            providers = imagery_providers(lat, lng)
            tiles = await fetcher.fetch_all_providers(lat, lng, zoom, providers=providers)
            if len(tiles) < len(providers):
                print(f"  atlandı (eksik kaynak): {name}")
                continue
            images = {p.value: img for p, img in tiles.items()}
            # Motorla aynı ölçü: en farklı kaynak çiftinin farkı
            pair = analyzer.compare_providers(images).max_diff_pair
            if pair is None:
                continue
            result = pair.diff_result
            censorship = blur.compare_blur_across_providers(images).censorship_score
            rows.append({"konum": name, "kaynaklar": sorted(images),
                         "diff_score": round(result.diff_score, 2),
                         "ssim": round(result.structural_similarity, 3),
                         "censorship": round(censorship, 1)})
            print(f"  {name:22s} diff={result.diff_score:5.1f}  ssim={result.structural_similarity:.3f}"
                  f"  sansur={censorship:5.1f}")

    def summary(key: str) -> dict[str, float]:
        values = [float(r[key]) for r in rows]  # type: ignore[arg-type]
        return {
            "median": round(statistics.median(values), 2),
            "p90": round(percentile(values, 0.90), 2),
            "p99": round(percentile(values, 0.99), 2),
            "max": round(max(values), 2),
        }

    return {
        "zoom": zoom,
        "n": len(rows),
        "diff_score": summary("diff_score"),
        "censorship": summary("censorship"),
        "rows": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--zoom", type=int, default=16)
    parser.add_argument("--json", default=None)
    parser.add_argument("--bolge", choices=["dunya", "fransa"], default="dunya",
                        help="fransa: IGN'in de girdiği üç kaynaklı taban")
    args = parser.parse_args()
    locations = FRANCE_BASELINE if args.bolge == "fransa" else BASELINE_LOCATIONS
    summary = asyncio.run(measure(args.zoom, locations))
    print(json.dumps({k: v for k, v in summary.items() if k != "rows"}, ensure_ascii=False))
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(summary, fh, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
