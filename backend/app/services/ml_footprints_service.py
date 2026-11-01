"""
ml_footprints_service.py — Microsoft ML bina izleri ile OSM'nin karo düzeyinde kıyası (kanıt, puan değil).

Deneme 2 (docs/spike-bina-izleri.md, ölçüm docs/olcum-bina-izleri-ml-osm.json): Microsoft Global ML
Building Footprints, Bing görüntüsünden makine öğrenmesiyle çıkarılmış bina poligonlarıdır. OSM'de
bina olan bir karoda ML izi hiç yoksa, Bing görüntüsünde de o binalar görünmüyor olabilir: GhostBuilding'in
kıyasladığı Esri / MapTiler / IGN'den **bağımsız dördüncü bir sağlayıcının** sansür izi.

Kural (deneyde 86 konumda ölçüldü): OSM'de en az ``OSM_ESIK`` bina var ve ML payı
``ml / (osm + ml) < ML_PAY_ESIK`` → işaret. Tabanda yanlış alarm 0/49, referans tesislerde 5/12 (hepsi
Fransa). Etiket yanlılığı ve küçük örneklem yüzünden **puana girmez**; bulgu sayfasında taban ölçüsüyle
birlikte kanıt satırı olarak gösterilir.

Veri: ``dataset-links.csv`` z9 quadkey → sıkıştırılmış GeoJSON satırları (dosya başına onlarca MB).
Dizin ve dosyalar diske önbelleklenir (``STORAGE_ROOT/ml_footprints``), dosya akışla indirilir ve satır
satır okunur (belleğe alınmaz). Sayım: poligonun dış halkasının ortalama noktası karo kutusundaysa.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import logging
import math
import os
import time
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.config import settings

logger = logging.getLogger(__name__)

ML_SOURCE = "Microsoft Global ML Building Footprints"
DATASET_INDEX_URL = (
    "https://minedbuildings.z5.web.core.windows.net/global-buildings/dataset-links.csv"
)
OSM_ESIK = 4
ML_PAY_ESIK = 0.02
QUADKEY_ZOOM = 9
INDEX_MAX_AGE_S = 30 * 24 * 3600  # dizin aylık yenilenir
DOSYA_TAVANI = 400 * 1024 * 1024  # tek dosya 400 MB üstüyse indirilmez (disk koruması)

Bbox = Tuple[float, float, float, float]  # (south, west, north, east)


# ── Saf karo yardımcıları ─────────────────────────────────────────────────────


def lat_lng_to_tile(lat: float, lng: float, zoom: int) -> Tuple[int, int]:
    """Web Mercator karo (x, y)."""
    n = 2**zoom
    x = int((lng + 180.0) / 360.0 * n)
    lat_r = math.radians(max(min(lat, 85.05112878), -85.05112878))
    y = int((1.0 - math.asinh(math.tan(lat_r)) / math.pi) / 2.0 * n)
    return min(max(x, 0), n - 1), min(max(y, 0), n - 1)


def tile_bbox(x: int, y: int, zoom: int) -> Bbox:
    n = 2**zoom

    def lat(yy: int) -> float:
        return math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * yy / n))))

    west = x / n * 360.0 - 180.0
    east = (x + 1) / n * 360.0 - 180.0
    return lat(y + 1), west, lat(y), east


def quadkey(x: int, y: int, zoom: int) -> str:
    """Bing quadkey (dataset-links.csv'nin z9 anahtarı)."""
    digits = []
    for i in range(zoom, 0, -1):
        mask = 1 << (i - 1)
        digit = (1 if x & mask else 0) + (2 if y & mask else 0)
        digits.append(str(digit))
    return "".join(digits)


def parent_quadkey(x: int, y: int, zoom: int, parent_zoom: int = QUADKEY_ZOOM) -> str:
    shift = zoom - parent_zoom
    return quadkey(x >> shift, y >> shift, parent_zoom)


def count_in_bbox(lines: Iterable[str], bbox: Bbox) -> int:
    """GeoJSON Feature satırlarından dış halka ortalaması kutuya düşenleri sayar (bozuk satır atlanır)."""
    south, west, north, east = bbox
    n = 0
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            geom = json.loads(line)["geometry"]
            ring = geom["coordinates"][0] if geom["type"] == "Polygon" else geom["coordinates"][0][0]
        except (ValueError, KeyError, IndexError, TypeError):
            continue
        if not ring:
            continue
        lng = sum(p[0] for p in ring) / len(ring)
        lat = sum(p[1] for p in ring) / len(ring)
        if south <= lat <= north and west <= lng <= east:
            n += 1
    return n


@dataclass(frozen=True)
class Karar:
    ml_pay: Optional[float]  # ml / (osm + ml); ikisi de 0 ise tanımsız
    isaret: bool


def karar(osm: int, ml: int) -> Karar:
    toplam = osm + ml
    pay = ml / toplam if toplam else None
    return Karar(ml_pay=pay, isaret=osm >= OSM_ESIK and pay is not None and pay < ML_PAY_ESIK)


def urls_for_quadkey(index_csv: str, qk: str) -> List[str]:
    """dataset-links.csv içinden quadkey'in bütün parça adresleri (sınır bölgelerinde birden çok)."""
    return [
        row["Url"]
        for row in csv.DictReader(io.StringIO(index_csv))
        if row.get("QuadKey") == qk and row.get("Url")
    ]


# ── Disk önbelleği ve indirme ─────────────────────────────────────────────────


def _cache_dir() -> Path:
    root = Path(getattr(settings, "STORAGE_ROOT", "data")) / "ml_footprints"
    root.mkdir(parents=True, exist_ok=True)
    return root


async def _download(client: Any, url: str, target: Path) -> Path:
    """Akışla indirir; yarım dosya bırakmaz (geçici ad + rename)."""
    tmp = target.with_suffix(target.suffix + ".part")
    size = 0
    async with client.stream("GET", url) as resp:
        resp.raise_for_status()
        with open(tmp, "wb") as fh:
            async for chunk in resp.aiter_bytes(1 << 20):
                size += len(chunk)
                if size > DOSYA_TAVANI:
                    raise RuntimeError(f"ML dosyası tavanı aştı ({DOSYA_TAVANI} bayt): {url}")
                fh.write(chunk)
    os.replace(tmp, target)
    return target


async def _index_csv(client: Any) -> str:
    path = _cache_dir() / "dataset-links.csv"
    if not path.exists() or time.time() - path.stat().st_mtime > INDEX_MAX_AGE_S:
        await _download(client, DATASET_INDEX_URL, path)
    return path.read_text(encoding="utf-8")


async def _ml_file(client: Any, url: str) -> Path:
    path = _cache_dir() / (hashlib.sha1(url.encode()).hexdigest()[:20] + ".csv.gz")
    if not path.exists():
        await _download(client, url, path)
    return path


def _gz_lines(path: Path) -> Iterator[str]:
    with gzip.open(path, "rt", encoding="utf-8", errors="replace") as fh:
        yield from fh


# ── Kanıtın üretilmesi ────────────────────────────────────────────────────────


async def build_ml_evidence(
    lat: float,
    lng: float,
    zoom: int,
    *,
    http_client: Any = None,
    osm_counter: Any = None,
) -> Dict[str, Any]:
    """Konumun karosunda ML izi ve OSM bina sayısı; ``Anomaly.meta_data["ml_footprints"]`` biçimi.

    ``status``: ready | no_coverage (bu quadkey için ML dosyası yok: Kore, İran gibi bazı ülkeler).
    """
    import httpx

    from app.services.osm_collector import OSMCollector

    x, y = lat_lng_to_tile(lat, lng, zoom)
    bbox = tile_bbox(x, y, zoom)
    qk = parent_quadkey(x, y, zoom)
    base: Dict[str, Any] = {
        "source": ML_SOURCE,
        "zoom": zoom,
        "quadkey": qk,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "rule": {"osm_min": OSM_ESIK, "ml_share_max": ML_PAY_ESIK},
        "baseline": {"false_alarms": 0, "baseline_n": 49, "reference_hits": 5, "reference_n": 12},
    }
    client = http_client or httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=15.0), follow_redirects=True)
    try:
        urls = urls_for_quadkey(await _index_csv(client), qk)
        if not urls:
            return {**base, "status": "no_coverage", "osm": None, "ml": None, "ml_share": None, "flag": False}
        ml = 0
        for url in urls:
            ml += count_in_bbox(_gz_lines(await _ml_file(client, url)), bbox)
    finally:
        if http_client is None:
            await client.aclose()

    if osm_counter is not None:
        osm = await osm_counter(bbox)
    else:
        async with OSMCollector() as collector:
            osm = await collector.building_count_in_bbox(bbox)

    k = karar(osm, ml)
    return {
        **base,
        "status": "ready",
        "osm": osm,
        "ml": ml,
        "ml_share": round(k.ml_pay, 4) if k.ml_pay is not None else None,
        "flag": k.isaret,
    }


async def store_anomaly_ml_footprints(anomaly_id: str) -> Dict[str, Any]:
    """Kanıtı üretip ``meta_data["ml_footprints"]``'e yazar (Celery görevi çağırır)."""
    from sqlalchemy import select

    from app.db.session import AsyncSessionLocal
    from app.models.anomaly import Anomaly

    async with AsyncSessionLocal() as session:
        anomaly = (await session.execute(select(Anomaly).where(Anomaly.id == anomaly_id))).scalar_one_or_none()
        if anomaly is None:
            return {"status": "missing"}
        lat, lng = anomaly.lat, anomaly.lng

    try:
        evidence = await build_ml_evidence(lat, lng, settings.ANALYSIS_ZOOM)
    except Exception as exc:
        logger.exception("ML izi kanıtı üretilemedi (%s): %s", anomaly_id, exc)
        evidence = {"status": "failed", "generated_at": datetime.now(timezone.utc).isoformat()}

    async with AsyncSessionLocal() as session:
        anomaly = (await session.execute(select(Anomaly).where(Anomaly.id == anomaly_id))).scalar_one_or_none()
        if anomaly is None:
            return {"status": "missing"}
        anomaly.meta_data = {**(anomaly.meta_data or {}), "ml_footprints": evidence}
        await session.commit()
    return evidence
