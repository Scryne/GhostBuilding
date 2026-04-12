"""
osm_collector.py — OpenStreetMap Overpass API bina/yapı veri toplama servisi.

Overpass API üzerinden belirli bir konum çevresindeki bina ve yapı
verilerini asenkron olarak sorgular. Askeri tesisler, havaalanları gibi
özel yapıları ayrı olarak çekebilir. Sonuçlar GeoJSON FeatureCollection
olarak döndürülür ve Redis'te önbelleklenir.

İki Overpass API uç noktası arasında otomatik failover sağlar.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import random
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Redis bağlantısı (lazy init — tile_fetcher ile ortak pattern)
# ---------------------------------------------------------------------------
_redis_client = None

OSM_CACHE_TTL: int = 21_600  # 6 saat (saniye)


async def _get_redis() -> "redis.asyncio.Redis":
    """Redis async client'ı lazy olarak oluşturur ve döndürür."""
    global _redis_client
    if _redis_client is None:
        import redis.asyncio as aioredis

        _redis_client = aioredis.from_url(
            settings.REDIS_URL,
            decode_responses=True,  # JSON saklanacak
        )
    return _redis_client


# ---------------------------------------------------------------------------
# Sabitler
# ---------------------------------------------------------------------------

# Overpass API uç noktaları (failover sırasıyla)
OVERPASS_ENDPOINTS: List[str] = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]

MAX_RETRIES: int = 2  # Her endpoint için

USER_AGENTS: List[str] = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
]

# Özel yapı kategorileri — gizli yapı tespiti için öncelikli
SENSITIVE_TAGS: Dict[str, List[str]] = {
    "military": ["*"],
    "aeroway": ["*"],
    "landuse": ["military"],
    "building": ["military", "bunker", "hangar"],
    "amenity": ["prison", "police"],
    "barrier": ["fence", "wall"],
}


# ---------------------------------------------------------------------------
# Veri modelleri
# ---------------------------------------------------------------------------


@dataclass
class Building:
    """
    Tek bir OSM binasını temsil eden veri sınıfı.

    Attributes:
        osm_id: OpenStreetMap element ID'si.
        osm_type: Element tipi ('way' veya 'relation').
        name: Bina adı (varsa).
        building_type: Bina türü (ör. 'residential', 'commercial', 'military').
        geometry: GeoJSON Polygon/MultiPolygon geometrisi.
        centroid: Binanın merkez noktası (lat, lng).
        area_m2: Yaklaşık alan (m²).
        tags: Tüm OSM etiketleri.
        is_sensitive: Askeri/özel yapı mı.
    """

    osm_id: int
    osm_type: str  # "way" | "relation"
    name: Optional[str]
    building_type: str
    geometry: Dict[str, Any]  # GeoJSON Polygon
    centroid: Tuple[float, float]  # (lat, lng)
    area_m2: float
    tags: Dict[str, str] = field(default_factory=dict)
    is_sensitive: bool = False

    def to_geojson_feature(self) -> Dict[str, Any]:
        """
        Bu binayı GeoJSON Feature olarak döndürür.

        Returns:
            GeoJSON Feature sözlüğü.
        """
        return {
            "type": "Feature",
            "id": f"{self.osm_type}/{self.osm_id}",
            "geometry": self.geometry,
            "properties": {
                "osm_id": self.osm_id,
                "osm_type": self.osm_type,
                "name": self.name,
                "building_type": self.building_type,
                "centroid": {"lat": self.centroid[0], "lng": self.centroid[1]},
                "area_m2": round(self.area_m2, 2),
                "is_sensitive": self.is_sensitive,
                **self.tags,
            },
        }


def buildings_to_feature_collection(
    buildings: List[Building],
) -> Dict[str, Any]:
    """
    Building listesini GeoJSON FeatureCollection'a çevirir.

    Args:
        buildings: Building dataclass listesi.

    Returns:
        GeoJSON FeatureCollection sözlüğü.
    """
    return {
        "type": "FeatureCollection",
        "features": [b.to_geojson_feature() for b in buildings],
        "properties": {
            "total_count": len(buildings),
            "sensitive_count": sum(1 for b in buildings if b.is_sensitive),
        },
    }


# ---------------------------------------------------------------------------
# Geometri yardımcıları
# ---------------------------------------------------------------------------


def _calculate_polygon_area_m2(
    coords: List[List[float]],
    center_lat: float,
) -> float:
    """
    Basit shoelace formülüyle polygon alanını hesaplar (m²).

    Küçük alanlar için Mercator projeksiyonu yeterli doğruluk sağlar.

    Args:
        coords: [[lng, lat], ...] koordinat listesi.
        center_lat: Alan hesabı için referans enlem.

    Returns:
        Yaklaşık alan (m²).
    """
    if len(coords) < 3:
        return 0.0

    # Derece → metre dönüşüm faktörleri
    lat_m = 111_320.0  # 1 derece enlem ≈ 111.32 km
    lng_m = 111_320.0 * math.cos(math.radians(center_lat))

    area = 0.0
    n = len(coords)
    for i in range(n):
        j = (i + 1) % n
        x_i = coords[i][0] * lng_m
        y_i = coords[i][1] * lat_m
        x_j = coords[j][0] * lng_m
        y_j = coords[j][1] * lat_m
        area += x_i * y_j
        area -= x_j * y_i

    return abs(area) / 2.0


def _compute_centroid(coords: List[List[float]]) -> Tuple[float, float]:
    """
    Polygon koordinatlarından merkez noktayı hesaplar.

    Args:
        coords: [[lng, lat], ...] koordinat listesi.

    Returns:
        (lat, lng) tuple.
    """
    if not coords:
        return (0.0, 0.0)

    sum_lat = sum(c[1] for c in coords)
    sum_lng = sum(c[0] for c in coords)
    n = len(coords)
    return (sum_lat / n, sum_lng / n)


def _is_sensitive_element(tags: Dict[str, str]) -> bool:
    """
    Verilen OSM etiketlerinin hassas/özel yapı olup olmadığını kontrol eder.

    Args:
        tags: OSM etiketi sözlüğü.

    Returns:
        True ise hassas yapıdır.
    """
    for key, values in SENSITIVE_TAGS.items():
        if key in tags:
            if "*" in values or tags[key] in values:
                return True
    return False


def _geometry_to_coords(geom: List[Dict[str, float]]) -> List[List[float]]:
    """
    Overpass API 'geometry' yanıtını [lng, lat] listesine çevirir.

    Args:
        geom: [{"lat": ..., "lon": ...}, ...] biçiminde geometry.

    Returns:
        [[lng, lat], ...] koordinat listesi.
    """
    return [[pt["lon"], pt["lat"]] for pt in geom if "lat" in pt and "lon" in pt]


def _overpass_element_to_building(element: Dict[str, Any]) -> Optional[Building]:
    """
    Overpass API yanıtındaki tek bir elementi Building objesine çevirir.

    Args:
        element: Overpass API element sözlüğü.

    Returns:
        Building objesi veya geometri yoksa None.
    """
    osm_type = element.get("type", "way")
    osm_id = element.get("id", 0)
    tags = element.get("tags", {})
    geom_raw = element.get("geometry", [])

    if not geom_raw:
        # Geometry yoksa atla
        return None

    coords = _geometry_to_coords(geom_raw)
    if len(coords) < 3:
        return None

    # GeoJSON Polygon oluştur
    # Polygon'un kapalı olmasını sağla
    if coords[0] != coords[-1]:
        coords.append(coords[0])

    geometry: Dict[str, Any] = {
        "type": "Polygon",
        "coordinates": [coords],
    }

    centroid = _compute_centroid(coords)
    area = _calculate_polygon_area_m2(coords, centroid[0])

    building_type = tags.get("building", "yes")
    name = tags.get("name") or tags.get("name:en") or tags.get("name:tr")

    return Building(
        osm_id=osm_id,
        osm_type=osm_type,
        name=name,
        building_type=building_type,
        geometry=geometry,
        centroid=centroid,
        area_m2=area,
        tags=tags,
        is_sensitive=_is_sensitive_element(tags),
    )


# ---------------------------------------------------------------------------
# Overpass sorgu oluşturucuları
# ---------------------------------------------------------------------------


def _build_buildings_query(lat: float, lng: float, radius_m: int) -> str:
    """
    Bina sorgusu için Overpass QL oluşturur.

    Args:
        lat: Merkez enlemi.
        lng: Merkez boylamı.
        radius_m: Arama yarıçapı (metre).

    Returns:
        Overpass QL sorgu string'i.
    """
    return (
        f'[out:json][timeout:30];\n'
        f'(\n'
        f'  way["building"](around:{radius_m},{lat},{lng});\n'
        f'  relation["building"](around:{radius_m},{lat},{lng});\n'
        f');\n'
        f'out geom;'
    )


def _build_amenities_query(lat: float, lng: float, radius_m: int) -> str:
    """
    Özel/hassas yapı sorgusu için Overpass QL oluşturur.

    military=*, aeroway=*, landuse=military gibi gizli yapı tespiti
    için öncelikli kategorileri sorgular.

    Args:
        lat: Merkez enlemi.
        lng: Merkez boylamı.
        radius_m: Arama yarıçapı (metre).

    Returns:
        Overpass QL sorgu string'i.
    """
    return (
        f'[out:json][timeout:30];\n'
        f'(\n'
        f'  way["military"](around:{radius_m},{lat},{lng});\n'
        f'  relation["military"](around:{radius_m},{lat},{lng});\n'
        f'  way["aeroway"](around:{radius_m},{lat},{lng});\n'
        f'  relation["aeroway"](around:{radius_m},{lat},{lng});\n'
        f'  way["landuse"="military"](around:{radius_m},{lat},{lng});\n'
        f'  relation["landuse"="military"](around:{radius_m},{lat},{lng});\n'
        f'  way["building"="military"](around:{radius_m},{lat},{lng});\n'
        f'  way["building"="bunker"](around:{radius_m},{lat},{lng});\n'
        f'  way["building"="hangar"](around:{radius_m},{lat},{lng});\n'
        f'  way["amenity"="prison"](around:{radius_m},{lat},{lng});\n'
        f'  way["amenity"="police"](around:{radius_m},{lat},{lng});\n'
        f');\n'
        f'out geom;'
    )


def _build_bbox_count_query(
    south: float,
    west: float,
    north: float,
    east: float,
) -> str:
    """
    Bounding box içindeki bina sayısını sayan Overpass QL sorgusu.

    Args:
        south: Güney sınırı (enlem).
        west: Batı sınırı (boylam).
        north: Kuzey sınırı (enlem).
        east: Doğu sınırı (boylam).

    Returns:
        Overpass QL sorgu string'i.
    """
    return (
        f'[out:json][timeout:30];\n'
        f'(\n'
        f'  way["building"]({south},{west},{north},{east});\n'
        f'  relation["building"]({south},{west},{north},{east});\n'
        f');\n'
        f'out count;'
    )


# ---------------------------------------------------------------------------
# Cache yardımcıları
# ---------------------------------------------------------------------------


def _cache_key_for_query(prefix: str, lat: float, lng: float, radius_m: int) -> str:
    """
    Koordinat + yarıçap tabanlı Redis cache anahtarı oluşturur.

    Koordinatlar 4 ondalık haneye yuvarlanarak benzer sorguların aynı
    cache girdisini paylaşması sağlanır.

    Args:
        prefix: Cache anahtar ön eki (ör. "osm:buildings").
        lat: Enlem.
        lng: Boylam.
        radius_m: Yarıçap (metre).

    Returns:
        Redis anahtar string'i.
    """
    # 4 ondalık hane ≈ 11m hassasiyet — cache hit oranını artırır
    lat_r = round(lat, 4)
    lng_r = round(lng, 4)
    raw = f"{prefix}:{lat_r}:{lng_r}:{radius_m}"
    digest = hashlib.md5(raw.encode()).hexdigest()[:12]
    return f"{prefix}:{digest}"


def _cache_key_for_bbox(
    south: float,
    west: float,
    north: float,
    east: float,
) -> str:
    """
    Bounding box tabanlı Redis cache anahtarı oluşturur.

    Args:
        south, west, north, east: Bbox sınırları.

    Returns:
        Redis anahtar string'i.
    """
    raw = f"osm:bbox:{round(south,4)}:{round(west,4)}:{round(north,4)}:{round(east,4)}"
    digest = hashlib.md5(raw.encode()).hexdigest()[:12]
    return f"osm:bbox:{digest}"


# ---------------------------------------------------------------------------
# OSMCollector
# ---------------------------------------------------------------------------


class OSMCollector:
    """
    OpenStreetMap Overpass API üzerinden bina ve yapı verisi çeken servis.

    İki Overpass API uç noktası arasında otomatik failover sağlar.
    Sonuçlar Redis'te 6 saat önbelleklenir. Koordinat + yarıçap hash'i
    ile cache anahtarı üretilir.

    Attributes:
        _client: Paylaşılan httpx async HTTP client.
        _use_cache: Redis önbellek kullanılıp kullanılmayacağı.

    Examples:
        >>> async with OSMCollector() as collector:
        ...     buildings = await collector.fetch_buildings(41.0082, 28.9784, 500)
        ...     print(f"Bulunan bina sayısı: {len(buildings)}")
        ...     geojson = buildings_to_feature_collection(buildings)
    """

    def __init__(self, *, use_cache: bool = True) -> None:
        """
        Args:
            use_cache: Redis önbellek kullanılsın mı (varsayılan True).
        """
        self._client: Optional[httpx.AsyncClient] = None
        self._use_cache = use_cache

    async def __aenter__(self) -> "OSMCollector":
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(45.0, connect=10.0),
            follow_redirects=True,
        )
        return self

    async def __aexit__(self, *exc) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    # ------------------------------------------------------------------ #
    # Dahili yardımcılar
    # ------------------------------------------------------------------ #

    def _ensure_client(self) -> None:
        """Client'ın başlatıldığını doğrular."""
        if self._client is None:
            raise RuntimeError(
                "OSMCollector context manager ile kullanılmalı: "
                "'async with OSMCollector() as collector: ...'"
            )

    async def _cache_get(self, key: str) -> Optional[str]:
        """Redis'ten önbellek verisini okur (JSON string)."""
        if not self._use_cache:
            return None
        try:
            r = await _get_redis()
            data = await r.get(key)
            if data:
                logger.debug("Cache HIT: %s", key)
            return data
        except Exception as exc:
            logger.warning("Redis okuma hatası (%s): %s", key, exc)
            return None

    async def _cache_set(self, key: str, data: str) -> None:
        """Redis'e önbellek verisini yazar (TTL: 6 saat)."""
        if not self._use_cache:
            return
        try:
            r = await _get_redis()
            await r.set(key, data, ex=OSM_CACHE_TTL)
            logger.debug("Cache SET: %s (TTL=%ds)", key, OSM_CACHE_TTL)
        except Exception as exc:
            logger.warning("Redis yazma hatası (%s): %s", key, exc)

    async def _execute_overpass_query(self, query: str) -> Dict[str, Any]:
        """
        Overpass API'ye sorgu gönderir. Failover mantığıyla çalışır.

        Birinci endpoint başarısız olursa ikincisini dener. Her endpoint
        için MAX_RETRIES kadar tekrar dener.

        Args:
            query: Overpass QL sorgu string'i.

        Returns:
            Overpass API JSON yanıtı.

        Raises:
            RuntimeError: Tüm endpoint'ler ve denemeler başarısız olursa.
        """
        self._ensure_client()

        last_exc: Optional[Exception] = None

        for endpoint in OVERPASS_ENDPOINTS:
            for attempt in range(1, MAX_RETRIES + 1):
                try:
                    logger.info(
                        "Overpass sorgusu gönderiliyor: %s (deneme %d/%d)",
                        endpoint,
                        attempt,
                        MAX_RETRIES,
                    )

                    response = await self._client.post(
                        endpoint,
                        data={"data": query},
                        headers={
                            "User-Agent": random.choice(USER_AGENTS),
                            "Content-Type": "application/x-www-form-urlencoded",
                        },
                    )
                    response.raise_for_status()

                    result = response.json()
                    elements = result.get("elements", [])
                    logger.info(
                        "Overpass sorgusu başarılı: %d element döndü (%s)",
                        len(elements),
                        endpoint,
                    )
                    return result

                except httpx.HTTPStatusError as exc:
                    last_exc = exc
                    status = exc.response.status_code

                    # 429 Too Many Requests — rate limit, diğer endpoint'e geç
                    if status == 429:
                        logger.warning(
                            "Overpass rate limit (%s), diğer endpoint deneniyor",
                            endpoint,
                        )
                        break

                    # 504 Gateway Timeout — sorgu zaman aşımı
                    if status == 504:
                        logger.warning(
                            "Overpass timeout (%s), tekrar deneniyor",
                            endpoint,
                        )
                        continue

                    logger.error(
                        "Overpass HTTP hatası %d (%s, deneme %d/%d): %s",
                        status,
                        endpoint,
                        attempt,
                        MAX_RETRIES,
                        str(exc),
                    )

                except httpx.RequestError as exc:
                    last_exc = exc
                    logger.warning(
                        "Overpass bağlantı hatası (%s, deneme %d/%d): %s",
                        endpoint,
                        attempt,
                        MAX_RETRIES,
                        str(exc),
                    )

                except Exception as exc:
                    last_exc = exc
                    logger.error(
                        "Overpass beklenmeyen hata (%s, deneme %d/%d): %s",
                        endpoint,
                        attempt,
                        MAX_RETRIES,
                        str(exc),
                    )

        raise RuntimeError(
            "Overpass API'ye ulaşılamıyor — tüm endpoint'ler ve denemeler başarısız."
        ) from last_exc

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    async def fetch_buildings(
        self,
        lat: float,
        lng: float,
        radius_m: int,
    ) -> List[Building]:
        """
        Belirtilen konum çevresindeki binaları Overpass API'den çeker.

        Önce Redis önbelleğini kontrol eder. Cache miss ise Overpass
        sorgusunu çalıştırır, yanıtı parse eder ve Building listesi döndürür.

        Args:
            lat: Merkez enlemi (derece).
            lng: Merkez boylamı (derece).
            radius_m: Arama yarıçapı (metre, max ayarlardaki MAX_SCAN_RADIUS_KM ile sınırlı).

        Returns:
            Building dataclass listesi.

        Raises:
            ValueError: Geçersiz parametreler.
            RuntimeError: Overpass API'ye ulaşılamıyorsa.

        Examples:
            >>> async with OSMCollector() as collector:
            ...     buildings = await collector.fetch_buildings(41.0082, 28.9784, 500)
            ...     for b in buildings[:3]:
            ...         print(b.osm_id, b.building_type, b.area_m2)
        """
        if not -90.0 <= lat <= 90.0:
            raise ValueError(f"Geçersiz enlem: {lat}")
        if not -180.0 <= lng <= 180.0:
            raise ValueError(f"Geçersiz boylam: {lng}")
        if radius_m <= 0:
            raise ValueError(f"Yarıçap pozitif olmalı: {radius_m}")

        max_radius = settings.MAX_SCAN_RADIUS_KM * 1000
        if radius_m > max_radius:
            logger.warning(
                "İstenen yarıçap (%dm) maksimumu (%dm) aşıyor, kısıtlanıyor",
                radius_m,
                max_radius,
            )
            radius_m = max_radius

        # --- Cache kontrolü ---
        cache_key = _cache_key_for_query("osm:buildings", lat, lng, radius_m)
        cached = await self._cache_get(cache_key)
        if cached is not None:
            try:
                raw_elements = json.loads(cached)
                buildings = [
                    _overpass_element_to_building(el)
                    for el in raw_elements
                ]
                return [b for b in buildings if b is not None]
            except (json.JSONDecodeError, KeyError) as exc:
                logger.warning("Cache parse hatası, yeniden sorgulanıyor: %s", exc)

        # --- Overpass sorgusu ---
        query = _build_buildings_query(lat, lng, radius_m)
        result = await self._execute_overpass_query(query)
        elements = result.get("elements", [])

        # Parse
        buildings: List[Building] = []
        for el in elements:
            building = _overpass_element_to_building(el)
            if building is not None:
                buildings.append(building)

        logger.info(
            "Bina sorgusu tamamlandı: %d bina bulundu "
            "(lat=%.4f, lng=%.4f, r=%dm)",
            len(buildings),
            lat,
            lng,
            radius_m,
        )

        # Cache'e yaz (ham element listesini sakla)
        await self._cache_set(cache_key, json.dumps(elements, ensure_ascii=False))

        return buildings

    async def fetch_amenities(
        self,
        lat: float,
        lng: float,
        radius_m: int,
    ) -> List[Building]:
        """
        Belirtilen konum çevresindeki özel/hassas yapıları çeker.

        Askeri tesisler, havaalanları, cezaevleri gibi gizli yapı tespiti
        için öncelikli kategorileri sorgular. Bu yapılar anomali tespitinde
        daha yüksek ağırlık alır.

        Args:
            lat: Merkez enlemi (derece).
            lng: Merkez boylamı (derece).
            radius_m: Arama yarıçapı (metre).

        Returns:
            Building dataclass listesi (hepsi is_sensitive=True olarak işaretli).

        Raises:
            ValueError: Geçersiz parametreler.
            RuntimeError: Overpass API'ye ulaşılamıyorsa.

        Examples:
            >>> async with OSMCollector() as collector:
            ...     sensitive = await collector.fetch_amenities(39.9334, 32.8597, 5000)
            ...     for s in sensitive:
            ...         print(s.name, s.building_type, s.is_sensitive)
        """
        if not -90.0 <= lat <= 90.0:
            raise ValueError(f"Geçersiz enlem: {lat}")
        if not -180.0 <= lng <= 180.0:
            raise ValueError(f"Geçersiz boylam: {lng}")
        if radius_m <= 0:
            raise ValueError(f"Yarıçap pozitif olmalı: {radius_m}")

        # --- Cache kontrolü ---
        cache_key = _cache_key_for_query("osm:amenities", lat, lng, radius_m)
        cached = await self._cache_get(cache_key)
        if cached is not None:
            try:
                raw_elements = json.loads(cached)
                buildings = [
                    _overpass_element_to_building(el)
                    for el in raw_elements
                ]
                result_list = [b for b in buildings if b is not None]
                # Hassas olarak işaretle
                for b in result_list:
                    b.is_sensitive = True
                return result_list
            except (json.JSONDecodeError, KeyError) as exc:
                logger.warning("Cache parse hatası, yeniden sorgulanıyor: %s", exc)

        # --- Overpass sorgusu ---
        query = _build_amenities_query(lat, lng, radius_m)
        result = await self._execute_overpass_query(query)
        elements = result.get("elements", [])

        # Parse — amenity sorgusundan gelen her şey hassas kabul edilir
        buildings: List[Building] = []
        seen_ids: set[int] = set()  # Duplikasyonu önle

        for el in elements:
            eid = el.get("id", 0)
            if eid in seen_ids:
                continue
            seen_ids.add(eid)

            building = _overpass_element_to_building(el)
            if building is not None:
                building.is_sensitive = True
                buildings.append(building)

        logger.info(
            "Hassas yapı sorgusu tamamlandı: %d yapı bulundu "
            "(lat=%.4f, lng=%.4f, r=%dm)",
            len(buildings),
            lat,
            lng,
            radius_m,
        )

        # Cache'e yaz
        await self._cache_set(cache_key, json.dumps(elements, ensure_ascii=False))

        return buildings

    async def fetch_buildings_as_geojson(
        self,
        lat: float,
        lng: float,
        radius_m: int,
        *,
        include_amenities: bool = True,
    ) -> Dict[str, Any]:
        """
        Binaları GeoJSON FeatureCollection olarak döndürür.

        Opsiyonel olarak hassas yapıları da dahil edebilir.

        Args:
            lat: Merkez enlemi.
            lng: Merkez boylamı.
            radius_m: Arama yarıçapı (metre).
            include_amenities: Hassas yapıları da dahil et (varsayılan True).

        Returns:
            GeoJSON FeatureCollection sözlüğü.

        Examples:
            >>> async with OSMCollector() as collector:
            ...     geojson = await collector.fetch_buildings_as_geojson(
            ...         41.0082, 28.9784, 1000
            ...     )
            ...     print(geojson["properties"]["total_count"])
        """
        buildings = await self.fetch_buildings(lat, lng, radius_m)

        if include_amenities:
            amenities = await self.fetch_amenities(lat, lng, radius_m)

            # Mevcut building ID'leri
            existing_ids = {b.osm_id for b in buildings}

            # Amenity'leri ekle (duplikasyonu önle)
            for am in amenities:
                if am.osm_id not in existing_ids:
                    buildings.append(am)
                else:
                    # Zaten varsa is_sensitive işaretle
                    for b in buildings:
                        if b.osm_id == am.osm_id:
                            b.is_sensitive = True
                            break

        return buildings_to_feature_collection(buildings)

    async def building_count_in_bbox(
        self,
        bbox: Tuple[float, float, float, float],
    ) -> int:
        """
        Bounding box içindeki bina sayısını döndürür.

        Anomali skorlama için kullanılır: farklı sağlayıcıların bina
        sayılarını karşılaştırarak tutarsızlık puanı hesaplanır.

        Args:
            bbox: (south, west, north, east) sınırları.
                  south/north: enlem, west/east: boylam.

        Returns:
            Bina sayısı (int).

        Raises:
            ValueError: Geçersiz bbox koordinatları.
            RuntimeError: Overpass API'ye ulaşılamıyorsa.

        Examples:
            >>> async with OSMCollector() as collector:
            ...     count = await collector.building_count_in_bbox(
            ...         (40.98, 28.95, 41.05, 29.05)
            ...     )
            ...     print(f"Bbox'ta {count} bina var")
        """
        south, west, north, east = bbox

        if south >= north:
            raise ValueError(
                f"Geçersiz bbox: south ({south}) >= north ({north})"
            )
        if west >= east:
            raise ValueError(
                f"Geçersiz bbox: west ({west}) >= east ({east})"
            )
        if not (-90.0 <= south <= 90.0 and -90.0 <= north <= 90.0):
            raise ValueError("Bbox enlem değerleri [-90, 90] arasında olmalı")
        if not (-180.0 <= west <= 180.0 and -180.0 <= east <= 180.0):
            raise ValueError("Bbox boylam değerleri [-180, 180] arasında olmalı")

        # --- Cache kontrolü ---
        cache_key = _cache_key_for_bbox(south, west, north, east)
        cached = await self._cache_get(cache_key)
        if cached is not None:
            try:
                return int(cached)
            except (ValueError, TypeError):
                pass

        # --- Overpass sorgusu ---
        query = _build_bbox_count_query(south, west, north, east)
        result = await self._execute_overpass_query(query)

        # 'out count;' yanıtı: elements[0].tags.total
        elements = result.get("elements", [])
        count = 0
        if elements:
            tags = elements[0].get("tags", {})
            count = int(tags.get("total", 0))

        logger.info(
            "Bbox bina sayısı: %d (%.4f,%.4f,%.4f,%.4f)",
            count,
            south, west, north, east,
        )

        # Cache'e yaz
        await self._cache_set(cache_key, str(count))

        return count
