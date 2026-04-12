"""
tile_fetcher.py — Asenkron harita tile indirme servisi.

Farklı harita sağlayıcılarından (OSM, Google, Bing, Yandex) tile
görüntülerini indirir. Redis önbellekleme, retry logic, rate limiting
ve User-Agent rotasyonu destekler.

Wayback Machine CDX API üzerinden tarihsel tile snapshot'ları sorgular.
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import logging
import math
import random
import time
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Tuple

import httpx
from PIL import Image

from app.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Redis bağlantısı (lazy init)
# ---------------------------------------------------------------------------
_redis_client = None


async def _get_redis() -> "redis.asyncio.Redis":
    """Redis async client'ı lazy olarak oluşturur ve döndürür."""
    global _redis_client
    if _redis_client is None:
        import redis.asyncio as aioredis

        _redis_client = aioredis.from_url(
            settings.REDIS_URL,
            decode_responses=False,  # binary data saklayacağız
        )
    return _redis_client


# ---------------------------------------------------------------------------
# Sabitler
# ---------------------------------------------------------------------------

TILE_CACHE_TTL: int = 86_400  # 24 saat (saniye)
MAX_RETRIES: int = 3
RATE_LIMIT_PER_SECOND: int = 10  # sağlayıcı başına

USER_AGENTS: List[str] = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 Edg/123.0.0.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
]


class TileProvider(str, Enum):
    """Desteklenen harita sağlayıcıları."""

    OSM = "osm"
    GOOGLE = "google"
    BING = "bing"
    YANDEX = "yandex"


# Sağlayıcı URL şablonları
PROVIDER_URL_TEMPLATES: Dict[TileProvider, str] = {
    TileProvider.OSM: "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
    TileProvider.GOOGLE: "https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}",
    # Bing quadkey tabanlı olduğu için ayrı işlenir
    TileProvider.BING: (
        "https://ecn.t{subdomain}.tiles.virtualearth.net/tiles/a{quadkey}"
        ".jpeg?g=587&mkt=en-US&n=z"
    ),
    TileProvider.YANDEX: (
        "https://sat01.maps.yandex.net/tiles?l=sat&x={x}&y={y}&z={z}"
    ),
}


# ---------------------------------------------------------------------------
# Koordinat dönüşüm fonksiyonları (Slippy Map)
# ---------------------------------------------------------------------------


def lat_lng_to_tile(lat: float, lng: float, zoom: int) -> Tuple[int, int, int]:
    """
    Enlem/boylam ve zoom seviyesini Slippy Map tile koordinatlarına çevirir.

    Slippy Map (a.k.a. XYZ / TMS) tile sistemi, Mercator projeksiyonuna
    dayalıdır. Bu fonksiyon verilen coğrafi noktanın hangi tile içinde
    düştüğünü hesaplar.

    Args:
        lat: Enlem (derece), -85.0511 ile 85.0511 arasında.
        lng: Boylam (derece), -180.0 ile 180.0 arasında.
        zoom: Zoom seviyesi (0–20).

    Returns:
        (x, y, z) tile koordinatları.

    Raises:
        ValueError: Geçersiz koordinat veya zoom seviyesi.

    Examples:
        >>> lat_lng_to_tile(41.0082, 28.9784, 15)
        (19295, 11826, 15)
    """
    if not -85.0511 <= lat <= 85.0511:
        raise ValueError(f"Geçersiz enlem: {lat}. [-85.0511, 85.0511] aralığında olmalı.")
    if not -180.0 <= lng <= 180.0:
        raise ValueError(f"Geçersiz boylam: {lng}. [-180, 180] aralığında olmalı.")
    if not 0 <= zoom <= 20:
        raise ValueError(f"Geçersiz zoom: {zoom}. [0, 20] aralığında olmalı.")

    n = 2 ** zoom
    x = int((lng + 180.0) / 360.0 * n)
    lat_rad = math.radians(lat)
    y = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)

    # Sınır kontrolü
    x = max(0, min(x, n - 1))
    y = max(0, min(y, n - 1))

    return (x, y, zoom)


def tile_to_lat_lng(x: int, y: int, z: int) -> Tuple[float, float]:
    """
    Tile koordinatlarını (sol-üst köşe) enlem/boylam'a çevirir.

    Bu fonksiyon tile'ın kuzeybatı (sol-üst) köşesinin coğrafi
    koordinatlarını döndürür.

    Args:
        x: Tile X koordinatı.
        y: Tile Y koordinatı.
        z: Zoom seviyesi.

    Returns:
        (lat, lng) derece cinsinden.

    Raises:
        ValueError: Geçersiz tile koordinatları.

    Examples:
        >>> tile_to_lat_lng(19295, 11826, 15)
        (41.00857..., 28.97705...)
    """
    n = 2 ** z
    if not (0 <= x < n and 0 <= y < n):
        raise ValueError(
            f"Geçersiz tile koordinatları: x={x}, y={y}, z={z}. "
            f"x ve y [0, {n - 1}] aralığında olmalı."
        )

    lng = x / n * 360.0 - 180.0
    lat_rad = math.atan(math.sinh(math.pi * (1 - 2 * y / n)))
    lat = math.degrees(lat_rad)

    return (lat, lng)


def tile_to_quadkey(x: int, y: int, z: int) -> str:
    """
    Tile koordinatlarını Bing Maps quadkey string'ine çevirir.

    Bing Maps, tile'ları tanımlamak için quadkey sistemi kullanır. Her zoom
    seviyesi için tile koordinatları tek bir string'e dönüştürülür.

    Args:
        x: Tile X koordinatı.
        y: Tile Y koordinatı.
        z: Zoom seviyesi.

    Returns:
        Quadkey string (örn. "0213102310").

    Raises:
        ValueError: z < 1 ise.

    Examples:
        >>> tile_to_quadkey(3, 5, 3)
        '213'
    """
    if z < 1:
        raise ValueError("Quadkey zoom ≥ 1 olmalıdır.")

    quadkey_digits: List[str] = []
    for i in range(z, 0, -1):
        digit = 0
        mask = 1 << (i - 1)
        if x & mask:
            digit += 1
        if y & mask:
            digit += 2
        quadkey_digits.append(str(digit))

    return "".join(quadkey_digits)


# ---------------------------------------------------------------------------
# Rate Limiter
# ---------------------------------------------------------------------------


class _TokenBucketRateLimiter:
    """
    Token-bucket tabanlı asenkron rate limiter.

    Her sağlayıcı için ayrı bir bucket tutarak saniye başına izin
    verilen istek sayısını sınırlar.
    """

    def __init__(self, rate: int = RATE_LIMIT_PER_SECOND) -> None:
        self._rate = rate
        self._buckets: Dict[str, float] = {}
        self._tokens: Dict[str, float] = {}
        self._lock = asyncio.Lock()

    async def acquire(self, provider: str) -> None:
        """
        Belirtilen sağlayıcı için bir token tüketir.

        Yeterli token yoksa, replenish olana kadar bekler.

        Args:
            provider: Sağlayıcı adı (rate limit grubu).
        """
        async with self._lock:
            now = time.monotonic()

            if provider not in self._buckets:
                self._buckets[provider] = now
                self._tokens[provider] = float(self._rate)

            elapsed = now - self._buckets[provider]
            self._tokens[provider] = min(
                self._rate,
                self._tokens[provider] + elapsed * self._rate,
            )
            self._buckets[provider] = now

            if self._tokens[provider] < 1.0:
                wait_time = (1.0 - self._tokens[provider]) / self._rate
                await asyncio.sleep(wait_time)
                self._tokens[provider] = 0.0
            else:
                self._tokens[provider] -= 1.0


# ---------------------------------------------------------------------------
# TileFetcher
# ---------------------------------------------------------------------------


class TileFetcher:
    """
    Harita tile'larını asenkron olarak indiren servis.

    Farklı sağlayıcılardan (OSM, Google, Bing, Yandex) tile görüntülerini
    indirir. Redis önbellekleme, otomatik retry, rate limiting ve User-Agent
    rotasyonu destekler.

    Attributes:
        _client: Paylaşılan httpx async HTTP client.
        _rate_limiter: Sağlayıcı bazlı rate limiter.
        _use_cache: Redis önbellek kullanılıp kullanılmayacağı.

    Examples:
        >>> async with TileFetcher() as fetcher:
        ...     img = await fetcher.fetch_tile(TileProvider.OSM, 15, 19295, 11826)
        ...     img.size
        (256, 256)
    """

    def __init__(self, *, use_cache: bool = True) -> None:
        """
        Args:
            use_cache: Redis önbellek kullanılsın mı (varsayılan True).
        """
        self._client: Optional[httpx.AsyncClient] = None
        self._rate_limiter = _TokenBucketRateLimiter(rate=RATE_LIMIT_PER_SECOND)
        self._use_cache = use_cache

    async def __aenter__(self) -> "TileFetcher":
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=10.0),
            follow_redirects=True,
            http2=True,
        )
        return self

    async def __aexit__(self, *exc) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    # ------------------------------------------------------------------ #
    # Dahili yardımcılar
    # ------------------------------------------------------------------ #

    @staticmethod
    def _random_user_agent() -> str:
        """Rastgele bir User-Agent string'i seçer."""
        return random.choice(USER_AGENTS)

    @staticmethod
    def _cache_key(provider: str, z: int, x: int, y: int) -> str:
        """Redis önbellek anahtarı üretir."""
        return f"tile:{provider}:{z}:{x}:{y}"

    def _build_url(self, provider: TileProvider, z: int, x: int, y: int) -> str:
        """
        Sağlayıcı için tile URL'sini oluşturur.

        Args:
            provider: Harita sağlayıcısı.
            z: Zoom seviyesi.
            x: Tile X koordinatı.
            y: Tile Y koordinatı.

        Returns:
            Tam tile URL'si.
        """
        template = PROVIDER_URL_TEMPLATES[provider]

        if provider == TileProvider.BING:
            quadkey = tile_to_quadkey(x, y, z)
            subdomain = random.choice(["0", "1", "2", "3"])
            return template.format(quadkey=quadkey, subdomain=subdomain)

        return template.format(z=z, x=x, y=y)

    def _build_headers(self, provider: TileProvider) -> Dict[str, str]:
        """
        İstek başlıklarını oluşturur.

        Args:
            provider: Harita sağlayıcısı.

        Returns:
            HTTP başlıkları sözlüğü.
        """
        headers: Dict[str, str] = {
            "User-Agent": self._random_user_agent(),
            "Accept": "image/png,image/jpeg,image/*;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.openstreetmap.org/",
        }

        # Bing API anahtarı varsa header'a ekle
        if provider == TileProvider.BING and settings.BING_MAPS_API_KEY:
            headers["BingMapsKey"] = settings.BING_MAPS_API_KEY

        return headers

    async def _cache_get(self, key: str) -> Optional[bytes]:
        """Redis'ten önbellek verisini okur."""
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

    async def _cache_set(self, key: str, data: bytes) -> None:
        """Redis'e önbellek verisini yazar (TTL: 24 saat)."""
        if not self._use_cache:
            return
        try:
            r = await _get_redis()
            await r.set(key, data, ex=TILE_CACHE_TTL)
            logger.debug("Cache SET: %s (TTL=%ds)", key, TILE_CACHE_TTL)
        except Exception as exc:
            logger.warning("Redis yazma hatası (%s): %s", key, exc)

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    async def fetch_tile(
        self,
        provider: TileProvider,
        z: int,
        x: int,
        y: int,
    ) -> Image.Image:
        """
        Belirtilen sağlayıcıdan tek bir tile görüntüsünü indirir.

        Önce Redis önbelleğini kontrol eder; cache miss ise HTTP isteği
        gönderir. Başarısızlık durumunda exponential backoff ile 3 kez
        yeniden dener.

        Args:
            provider: Harita sağlayıcısı (OSM, Google, Bing, Yandex).
            z: Zoom seviyesi (0–20).
            x: Tile X koordinatı.
            y: Tile Y koordinatı.

        Returns:
            PIL.Image.Image objesi (genellikle 256×256 piksel).

        Raises:
            httpx.HTTPStatusError: HTTP hata kodu alınırsa (retry sonrası).
            httpx.RequestError: Ağ bağlantı hatası (retry sonrası).
            ValueError: Geçersiz parametre.
        """
        if self._client is None:
            raise RuntimeError(
                "TileFetcher context manager ile kullanılmalı: "
                "'async with TileFetcher() as fetcher: ...'"
            )

        # --- Cache kontrolü ---
        cache_key = self._cache_key(provider.value, z, x, y)
        cached = await self._cache_get(cache_key)
        if cached is not None:
            return Image.open(io.BytesIO(cached))

        # --- Rate limiting ---
        await self._rate_limiter.acquire(provider.value)

        # --- HTTP isteği (retry ile) ---
        url = self._build_url(provider, z, x, y)
        headers = self._build_headers(provider)
        last_exc: Optional[Exception] = None

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                logger.info(
                    "[%s] Tile indiriliyor z=%d x=%d y=%d (deneme %d/%d)",
                    provider.value,
                    z, x, y,
                    attempt,
                    MAX_RETRIES,
                )
                response = await self._client.get(url, headers=headers)
                response.raise_for_status()

                img_bytes = response.content
                if not img_bytes:
                    raise ValueError(f"Boş yanıt alındı: {url}")

                # Geçerli bir görüntü mü kontrol et
                img = Image.open(io.BytesIO(img_bytes))
                img.load()  # lazy decode'u zorla

                # Başarılı — önbelleğe al
                await self._cache_set(cache_key, img_bytes)

                logger.info(
                    "[%s] Tile başarıyla indirildi z=%d x=%d y=%d (%d bytes)",
                    provider.value,
                    z, x, y,
                    len(img_bytes),
                )
                return img

            except (httpx.HTTPStatusError, httpx.RequestError) as exc:
                last_exc = exc
                if attempt < MAX_RETRIES:
                    backoff = (2 ** attempt) + random.uniform(0, 1)
                    logger.warning(
                        "[%s] İstek başarısız (deneme %d/%d): %s — "
                        "%.1f sn sonra tekrar deneniyor",
                        provider.value,
                        attempt,
                        MAX_RETRIES,
                        str(exc),
                        backoff,
                    )
                    # Retry'da farklı User-Agent dene
                    headers["User-Agent"] = self._random_user_agent()
                    await asyncio.sleep(backoff)
                else:
                    logger.error(
                        "[%s] Tile indirilemedi z=%d x=%d y=%d — "
                        "%d deneme tükendi: %s",
                        provider.value,
                        z, x, y,
                        MAX_RETRIES,
                        str(exc),
                    )

            except Exception as exc:
                last_exc = exc
                logger.error(
                    "[%s] Beklenmeyen hata (deneme %d/%d): %s",
                    provider.value,
                    attempt,
                    MAX_RETRIES,
                    str(exc),
                )
                if attempt >= MAX_RETRIES:
                    break
                backoff = (2 ** attempt) + random.uniform(0, 1)
                await asyncio.sleep(backoff)

        raise RuntimeError(
            f"[{provider.value}] Tile indirilemiyor z={z} x={x} y={y} — "
            f"tüm denemeler başarısız"
        ) from last_exc

    async def fetch_all_providers(
        self,
        lat: float,
        lng: float,
        zoom: int,
        *,
        providers: Optional[List[TileProvider]] = None,
    ) -> Dict[TileProvider, Image.Image]:
        """
        Tüm desteklenen sağlayıcılardan aynı konumun tile'larını indirir.

        Verilen koordinatı tile koordinatlarına çevirir ve her sağlayıcıdan
        eş zamanlı olarak indirir. Başarısız sağlayıcılar sonuçtan çıkarılır
        (hata loglanır).

        Args:
            lat: Enlem (derece).
            lng: Boylam (derece).
            zoom: Zoom seviyesi (0–20).
            providers: İndirilecek sağlayıcılar listesi. None ise hepsi.

        Returns:
            {TileProvider: PIL.Image} sözlüğü. Başarısız sağlayıcılar
            dahil edilmez.

        Examples:
            >>> async with TileFetcher() as fetcher:
            ...     tiles = await fetcher.fetch_all_providers(41.0, 29.0, 15)
            ...     list(tiles.keys())
            [<TileProvider.OSM: 'osm'>, ...]
        """
        x, y, z = lat_lng_to_tile(lat, lng, zoom)

        if providers is None:
            providers = list(TileProvider)

        async def _safe_fetch(provider: TileProvider) -> Tuple[TileProvider, Optional[Image.Image]]:
            try:
                img = await self.fetch_tile(provider, z, x, y)
                return (provider, img)
            except Exception as exc:
                logger.error(
                    "[%s] fetch_all_providers sırasında hata: %s",
                    provider.value,
                    str(exc),
                )
                return (provider, None)

        tasks = [_safe_fetch(p) for p in providers]
        results = await asyncio.gather(*tasks)

        return {
            provider: img
            for provider, img in results
            if img is not None
        }


# ---------------------------------------------------------------------------
# WaybackFetcher — Tarihsel tile snapshot'ları
# ---------------------------------------------------------------------------


class WaybackFetcher:
    """
    Wayback Machine CDX API üzerinden tarihsel harita tile arşivlerini sorgular.

    Internet Archive'ın CDX sunucusunu kullanarak belirli bir konumun
    harita tile'larının geçmiş snapshot'larını bulur.

    Examples:
        >>> async with WaybackFetcher() as wb:
        ...     snapshots = await wb.fetch_historical(
        ...         lat=41.0, lng=29.0, zoom=15,
        ...         date_from=datetime(2020, 1, 1),
        ...         date_to=datetime(2024, 1, 1),
        ...     )
        ...     len(snapshots) <= 10
        True
    """

    CDX_API_URL: str = "http://web.archive.org/cdx/search/cdx"
    MAX_SNAPSHOTS: int = 10

    def __init__(self) -> None:
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self) -> "WaybackFetcher":
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(60.0, connect=15.0),
            follow_redirects=True,
        )
        return self

    async def __aexit__(self, *exc) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    @staticmethod
    def _build_tile_url_pattern(
        provider: TileProvider,
        z: int,
        x: int,
        y: int,
    ) -> str:
        """
        CDX API için aranacak URL kalıbını oluşturur.

        Args:
            provider: Harita sağlayıcısı.
            z: Zoom seviyesi.
            x: Tile X koordinatı.
            y: Tile Y koordinatı.

        Returns:
            CDX sorgusunda kullanılacak URL string'i.
        """
        patterns: Dict[TileProvider, str] = {
            TileProvider.OSM: f"tile.openstreetmap.org/{z}/{x}/{y}.png",
            TileProvider.GOOGLE: f"mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}",
            TileProvider.BING: f"ecn.t*.tiles.virtualearth.net/tiles/a*",
            TileProvider.YANDEX: f"sat01.maps.yandex.net/tiles?l=sat&x={x}&y={y}&z={z}",
        }
        return patterns.get(provider, patterns[TileProvider.OSM])

    async def _query_cdx(
        self,
        url_pattern: str,
        date_from: datetime,
        date_to: datetime,
    ) -> List[Dict[str, str]]:
        """
        CDX API'yi sorgular ve snapshot listesi döndürür.

        Args:
            url_pattern: Aranacak URL kalıbı.
            date_from: Başlangıç tarihi.
            date_to: Bitiş tarihi.

        Returns:
            Her snapshot için {timestamp, url, status, mime, digest} sözlükleri.

        Raises:
            httpx.HTTPStatusError: CDX API hata döndürürse.
        """
        if self._client is None:
            raise RuntimeError(
                "WaybackFetcher context manager ile kullanılmalı: "
                "'async with WaybackFetcher() as wb: ...'"
            )

        params = {
            "url": url_pattern,
            "matchType": "prefix",
            "output": "json",
            "fl": "timestamp,original,statuscode,mimetype,digest",
            "filter": "statuscode:200",
            "filter": "mimetype:image/.*",
            "from": date_from.strftime("%Y%m%d%H%M%S"),
            "to": date_to.strftime("%Y%m%d%H%M%S"),
            "limit": self.MAX_SNAPSHOTS * 3,  # fazla çek, sonra filtrele
            "collapse": "timestamp:8",  # günde en fazla 1 kayıt
        }

        logger.info("CDX API sorgusu: %s", url_pattern)

        response = await self._client.get(
            self.CDX_API_URL,
            params=params,
            headers={"User-Agent": random.choice(USER_AGENTS)},
        )
        response.raise_for_status()

        data = response.json()
        if not data or len(data) < 2:
            return []

        # İlk satır başlık
        headers_row = data[0]
        results: List[Dict[str, str]] = []
        for row in data[1:]:
            entry = dict(zip(headers_row, row))
            results.append(entry)

        return results

    async def fetch_historical(
        self,
        lat: float,
        lng: float,
        zoom: int,
        date_from: datetime,
        date_to: datetime,
        *,
        provider: TileProvider = TileProvider.OSM,
    ) -> List[Dict[str, object]]:
        """
        Belirtilen konum ve tarih aralığı için tarihsel tile snapshot'larını döndürür.

        Wayback Machine CDX API üzerinden harita tile arşivini tarihsel
        olarak sorgular ve en fazla 10 benzersiz snapshot döndürür.

        Her snapshot şu bilgileri içerir:
        - timestamp: Arşivlenme zamanı (ISO 8601)
        - wayback_url: Wayback Machine erişim URL'si
        - original_url: Orijinal tile URL'si
        - digest: İçerik hash'i (değişiklik tespiti için)
        - tile_coords: (x, y, z) tile koordinatları

        Args:
            lat: Enlem (derece).
            lng: Boylam (derece).
            zoom: Zoom seviyesi (0–20).
            date_from: Sorgu başlangıç tarihi.
            date_to: Sorgu bitiş tarihi.
            provider: Hangi sağlayıcının arşivi sorgulanacak (varsayılan OSM).

        Returns:
            En fazla 10 snapshot sözlüğü listesi, kronolojik sırada.

        Raises:
            ValueError: Geçersiz parametreler.
            httpx.HTTPStatusError: CDX API hata döndürürse.

        Examples:
            >>> async with WaybackFetcher() as wb:
            ...     results = await wb.fetch_historical(
            ...         41.0, 29.0, 15,
            ...         datetime(2020, 1, 1),
            ...         datetime(2024, 12, 31),
            ...     )
            ...     for snap in results:
            ...         print(snap["timestamp"], snap["wayback_url"])
        """
        if date_from >= date_to:
            raise ValueError("date_from, date_to'dan önce olmalıdır.")

        x, y, z = lat_lng_to_tile(lat, lng, zoom)

        url_pattern = self._build_tile_url_pattern(provider, z, x, y)

        try:
            raw_snapshots = await self._query_cdx(url_pattern, date_from, date_to)
        except httpx.HTTPStatusError as exc:
            logger.error("CDX API hatası: %s", str(exc))
            raise
        except Exception as exc:
            logger.error("CDX sorgu hatası: %s", str(exc))
            return []

        # Benzersiz digest'lere göre filtrele (aynı içerik tekrarını atla)
        seen_digests: set[str] = set()
        unique_snapshots: List[Dict[str, object]] = []

        for snap in raw_snapshots:
            digest = snap.get("digest", "")
            if digest in seen_digests:
                continue
            seen_digests.add(digest)

            # Wayback Machine erişim URL'si oluştur
            timestamp = snap.get("timestamp", "")
            original_url = snap.get("original", "")
            wayback_url = f"https://web.archive.org/web/{timestamp}/{original_url}"

            # Timestamp'i ISO 8601 formatına çevir
            iso_timestamp = ""
            if len(timestamp) >= 14:
                try:
                    dt = datetime.strptime(timestamp[:14], "%Y%m%d%H%M%S")
                    iso_timestamp = dt.isoformat()
                except ValueError:
                    iso_timestamp = timestamp

            unique_snapshots.append(
                {
                    "timestamp": iso_timestamp,
                    "wayback_url": wayback_url,
                    "original_url": original_url,
                    "digest": digest,
                    "tile_coords": {"x": x, "y": y, "z": z},
                    "provider": provider.value,
                }
            )

            if len(unique_snapshots) >= self.MAX_SNAPSHOTS:
                break

        logger.info(
            "Tarihsel sorgu tamamlandı: %d snapshot bulundu "
            "(lat=%.4f, lng=%.4f, z=%d, provider=%s)",
            len(unique_snapshots),
            lat,
            lng,
            zoom,
            provider.value,
        )

        return unique_snapshots

    async def fetch_snapshot_image(
        self,
        wayback_url: str,
    ) -> Optional[Image.Image]:
        """
        Wayback Machine'den belirli bir snapshot görüntüsünü indirir.

        Args:
            wayback_url: Wayback Machine erişim URL'si.

        Returns:
            PIL.Image.Image veya indirilemezse None.
        """
        if self._client is None:
            raise RuntimeError(
                "WaybackFetcher context manager ile kullanılmalı."
            )

        try:
            response = await self._client.get(
                wayback_url,
                headers={"User-Agent": random.choice(USER_AGENTS)},
            )
            response.raise_for_status()

            img = Image.open(io.BytesIO(response.content))
            img.load()
            return img

        except Exception as exc:
            logger.warning(
                "Wayback snapshot indirilemedi (%s): %s",
                wayback_url,
                str(exc),
            )
            return None
