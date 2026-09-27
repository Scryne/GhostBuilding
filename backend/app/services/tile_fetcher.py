"""
tile_fetcher.py — Asenkron uydu/harita tile indirme servisi.

Görüntü yalnız **kullanım koşulları buna izin veren** kaynaklardan, projeyi dürüstçe
tanıtan tek bir User-Agent ile çekilir (2026-09-26 kararı):

- **Esri World Imagery** — güncel yüksek çözünürlüklü uydu mozaiği (anahtarsız, atıf zorunlu).
- **MapTiler Satellite** — bağımsız ikinci uydu kaynağı (``MAPTILER_API_KEY`` ile).
- **OpenStreetMap** — harita çizimi; yalnız görüntüleme içindir, fotoğraflarla piksel
  karşılaştırmasına girmez (çizim ile fotoğraf her zaman "yüksek fark" verir).
- **Esri World Imagery Wayback** — Esri'nin resmî tarihsel sürüm arşivi (zaman serisi).

Önceki sürüm Google/Bing/Yandex'in resmî olmayan tile uçlarını rastgele User-Agent ve
sahte Referer ile çekiyordu; sağlayıcı koşullarına ve OSM tile politikasına aykırıydı.
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
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

import httpx
from PIL import Image

from app.config import settings

if TYPE_CHECKING:
    import redis.asyncio

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

# Tek, dürüst kimlik: OSM tile politikası uygulamayı tanımlayan bir User-Agent ister.
USER_AGENT: str = "GhostBuilding/0.2 (+https://github.com/Scryne/GhostBuilding)"


class TileProvider(str, Enum):
    """Desteklenen görüntü kaynakları."""

    ESRI = "esri"
    MAPTILER = "maptiler"
    IGN = "ign"
    OSM = "osm"


# Sağlayıcı URL şablonları (Esri: satır/sütun sırası {z}/{y}/{x}).
PROVIDER_URL_TEMPLATES: Dict[TileProvider, str] = {
    TileProvider.ESRI: (
        "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/"
        "tile/{z}/{y}/{x}"
    ),
    TileProvider.MAPTILER: "https://api.maptiler.com/tiles/satellite-v2/{z}/{x}/{y}.jpg?key={key}",
    # IGN Géoplateforme ortofoto (Fransa, açık lisans, anahtarsız WMTS).
    TileProvider.IGN: (
        "https://data.geopf.fr/wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0"
        "&LAYER=ORTHOIMAGERY.ORTHOPHOTOS&STYLE=normal&TILEMATRIXSET=PM"
        "&TILEMATRIX={z}&TILEROW={y}&TILECOL={x}&FORMAT=image/jpeg"
    ),
    TileProvider.OSM: "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
}

# Arayüzde ve raporda gösterilmesi ZORUNLU atıflar (kaynakların kullanım koşulu).
# Açıklama metinlerinde kullanılan okunur adlar.
PROVIDER_NAMES: Dict[str, str] = {
    "esri": "Esri World Imagery",
    "maptiler": "MapTiler Satellite",
    "ign": "IGN Ortofoto",
    "osm": "OpenStreetMap",
}


def provider_name(key: Optional[str]) -> str:
    """Kaynak anahtarının okunur adı (bilinmiyorsa anahtarın kendisi)."""
    if not key:
        return "bilinmeyen kaynak"
    return PROVIDER_NAMES.get(key.lower(), key)


PROVIDER_ATTRIBUTION: Dict[TileProvider, str] = {
    TileProvider.ESRI: "Esri, Maxar, Earthstar Geographics, and the GIS User Community",
    TileProvider.MAPTILER: "© MapTiler",
    TileProvider.IGN: "© IGN – Géoplateforme (Licence Ouverte Etalab 2.0)",
    TileProvider.OSM: "© OpenStreetMap contributors",
}

# Uydu fotoğrafı veren kaynaklar — piksel/blur karşılaştırması yalnız bunlar arasında yapılır.
IMAGERY_PROVIDERS: Tuple[TileProvider, ...] = (
    TileProvider.ESRI,
    TileProvider.MAPTILER,
    TileProvider.IGN,
)

# Bölgesel kaynakların kapsama kutusu (enlem_min, boylam_min, enlem_maks, boylam_maks).
# Kutu kaba bir ön süzgeçtir; kapsama dışındaki düz (boş) karolar ayrıca reddedilir.
REGIONAL_COVERAGE: Dict[TileProvider, Tuple[float, float, float, float]] = {
    TileProvider.IGN: (41.3, -5.2, 51.1, 9.6),  # Fransa anakarası + Korsika
}

# Standart sapması bunun altındaki karo "görüntü yok" sayılır (kapsama dışı beyaz karo).
BLANK_TILE_STD: float = 1.0


class TileUnavailable(Exception):
    """Kaynak bu karo için görüntü vermiyor (kapsama dışı / 4xx). Yeniden denenmez."""


def _is_blank(img: Image.Image) -> bool:
    """Tek renkli (ör. kapsama dışı beyaz) karo mu."""
    from PIL import ImageStat

    return max(ImageStat.Stat(img.convert("L")).stddev) < BLANK_TILE_STD


def provider_configured(provider: TileProvider) -> bool:
    """Sağlayıcı kullanılabilir mi (anahtar gerektirenlerde anahtar tanımlı mı)."""
    if provider == TileProvider.MAPTILER:
        return bool(settings.MAPTILER_API_KEY)
    return True


def covers(provider: TileProvider, lat: float, lng: float) -> bool:
    """Bölgesel kaynak bu noktayı kapsıyor mu (küresel kaynaklar her yeri kapsar)."""
    box = REGIONAL_COVERAGE.get(provider)
    if box is None:
        return True
    lat_min, lng_min, lat_max, lng_max = box
    return lat_min <= lat <= lat_max and lng_min <= lng <= lng_max


def imagery_providers(lat: Optional[float] = None, lng: Optional[float] = None) -> List[TileProvider]:
    """Yapılandırılmış uydu kaynakları (karşılaştırma için varsayılan küme).

    Konum verilirse o noktayı kapsayan bölgesel kaynaklar (ör. Fransa'da IGN) eklenir;
    konum yoksa yalnız küresel kaynaklar döner.
    """
    result = []
    for p in IMAGERY_PROVIDERS:
        if not provider_configured(p):
            continue
        if p in REGIONAL_COVERAGE and (lat is None or lng is None or not covers(p, lat, lng)):
            continue
        result.append(p)
    return result


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

    Esri World Imagery, MapTiler Satellite ve OSM'den tile görüntülerini indirir.
    Redis önbellekleme, otomatik retry ve rate limiting destekler.

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
        if provider == TileProvider.MAPTILER:
            if not settings.MAPTILER_API_KEY:
                raise RuntimeError("MapTiler için MAPTILER_API_KEY tanımlı değil.")
            return template.format(z=z, x=x, y=y, key=settings.MAPTILER_API_KEY)
        return template.format(z=z, x=x, y=y)

    def _build_headers(self, provider: TileProvider) -> Dict[str, str]:
        """
        İstek başlıklarını oluşturur.

        Args:
            provider: Harita sağlayıcısı.

        Returns:
            HTTP başlıkları sözlüğü.
        """
        return {
            "User-Agent": USER_AGENT,
            "Accept": "image/png,image/jpeg,image/*;q=0.9,*/*;q=0.8",
        }

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
            provider: Görüntü kaynağı (Esri, MapTiler, OSM).
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
                if provider in REGIONAL_COVERAGE and _is_blank(img):
                    raise TileUnavailable(f"[{provider.value}] kapsama dışı (boş karo)")

                # Başarılı — önbelleğe al
                await self._cache_set(cache_key, img_bytes)

                logger.info(
                    "[%s] Tile başarıyla indirildi z=%d x=%d y=%d (%d bytes)",
                    provider.value,
                    z, x, y,
                    len(img_bytes),
                )
                return img

            except TileUnavailable:
                raise
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                if 400 <= status < 500 and status != 429:
                    raise TileUnavailable(
                        f"[{provider.value}] HTTP {status}: karo yok"
                    ) from exc
                last_exc = exc
                if attempt < MAX_RETRIES:
                    backoff = (2 ** attempt) + random.uniform(0, 1)
                    logger.warning(
                        "[%s] İstek başarısız (deneme %d/%d): %s — "
                        "%.1f sn sonra tekrar deneniyor",
                        provider.value, attempt, MAX_RETRIES, str(exc), backoff,
                    )
                    await asyncio.sleep(backoff)
            except httpx.RequestError as exc:
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
        Aynı konumun tile'larını birden çok kaynaktan eş zamanlı indirir.

        Verilen koordinatı tile koordinatlarına çevirir ve her sağlayıcıdan
        eş zamanlı olarak indirir. Başarısız sağlayıcılar sonuçtan çıkarılır
        (hata loglanır).

        Args:
            lat: Enlem (derece).
            lng: Boylam (derece).
            zoom: Zoom seviyesi (0–20).
            providers: İndirilecek kaynaklar. None ise yapılandırılmış UYDU kaynakları
                (OSM çizimi fotoğraflarla karşılaştırılmaz).

        Returns:
            {TileProvider: PIL.Image} sözlüğü. Başarısız sağlayıcılar
            dahil edilmez.

        Examples:
            >>> async with TileFetcher() as fetcher:
            ...     tiles = await fetcher.fetch_all_providers(41.0, 29.0, 15)
            ...     list(tiles.keys())
            [<TileProvider.ESRI: 'esri'>, <TileProvider.MAPTILER: 'maptiler'>]
        """
        x, y, z = lat_lng_to_tile(lat, lng, zoom)

        if providers is None:
            providers = imagery_providers(lat, lng)

        async def _safe_fetch(provider: TileProvider) -> Tuple[TileProvider, Optional[Image.Image]]:
            try:
                img = await self.fetch_tile(provider, z, x, y)
                return (provider, img)
            except TileUnavailable as exc:
                logger.info("%s", exc)
                return (provider, None)
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
# WaybackFetcher — Esri World Imagery Wayback (resmî tarihsel sürüm arşivi)
# ---------------------------------------------------------------------------


class WaybackFetcher:
    """
    Esri World Imagery Wayback sürümlerinden bir konumun tarihsel görüntülerini getirir.

    Esri, World Imagery'nin her yayımlanan sürümünü tarihli olarak saklar (2014'ten bu
    yana 190+ sürüm). Bir konumun görüntüsü çoğu sürümde değişmez; bu yüzden tarih
    aralığındaki sürümlerden eşit aralıklı bir örnek alınır, tile indirilir ve içerik
    özetine (SHA-1) göre tekrarlar elenir — yalnız görüntünün gerçekten değiştiği anlar kalır.

    Önceki sürüm Internet Archive'daki Google/Bing/Yandex tile kopyalarını arıyordu; hem
    kaynak koşullarına aykırıydı hem de CDX sorgusundaki tekrarlanan ``filter`` anahtarı
    yüzünden "yalnız HTTP 200" koşulu sessizce düşüyordu.

    Examples:
        >>> async with WaybackFetcher() as wb:
        ...     snapshots = await wb.fetch_historical(
        ...         lat=41.0, lng=29.0, zoom=15,
        ...         date_from=datetime(2016, 1, 1),
        ...         date_to=datetime(2026, 1, 1),
        ...     )
        ...     len(snapshots) <= 10
        True
    """

    CONFIG_URL: str = (
        "https://s3-us-west-2.amazonaws.com/config.maptiles.arcgis.com/waybackconfig.json"
    )
    MAX_SNAPSHOTS: int = 10

    def __init__(self) -> None:
        self._client: Optional[httpx.AsyncClient] = None
        self._images: Dict[str, Image.Image] = {}

    async def __aenter__(self) -> "WaybackFetcher":
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(60.0, connect=15.0),
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT},
        )
        return self

    async def __aexit__(self, *exc) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    def _require_client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError(
                "WaybackFetcher context manager ile kullanılmalı: "
                "'async with WaybackFetcher() as wb: ...'"
            )
        return self._client

    async def list_releases(self) -> List[Dict[str, object]]:
        """Esri Wayback sürümlerini tarih sırasıyla döndürür: {release, date, url_template}."""
        response = await self._require_client().get(self.CONFIG_URL)
        response.raise_for_status()
        releases: List[Dict[str, object]] = []
        for release, item in response.json().items():
            title = str(item.get("itemTitle", ""))
            # "World Imagery (Wayback 2014-02-20)"
            try:
                date = datetime.strptime(title.rsplit(" ", 1)[-1].rstrip(")"), "%Y-%m-%d")
            except ValueError:
                continue
            releases.append(
                {"release": int(release), "date": date, "url_template": item.get("itemURL", "")}
            )
        releases.sort(key=lambda r: r["date"])  # type: ignore[arg-type,return-value]
        return releases

    @staticmethod
    def _spread(items: List[Dict[str, object]], count: int) -> List[Dict[str, object]]:
        """Listeden ilk ve son dahil eşit aralıklı en fazla ``count`` öğe seçer."""
        if len(items) <= count:
            return items
        step = (len(items) - 1) / (count - 1)
        return [items[round(i * step)] for i in range(count)]

    async def fetch_historical(
        self,
        lat: float,
        lng: float,
        zoom: int,
        date_from: datetime,
        date_to: datetime,
        *,
        provider: TileProvider = TileProvider.ESRI,
    ) -> List[Dict[str, object]]:
        """
        Tarih aralığındaki Esri Wayback sürümlerinden, görüntünün DEĞİŞTİĞİ anları döndürür.

        Her kayıt: ``timestamp`` (sürüm tarihi, ISO 8601), ``wayback_url`` (tile adresi),
        ``release``, ``digest`` (içerik SHA-1), ``tile_coords``, ``provider``.
        ``provider`` geriye dönük uyumluluk içindir; tarihsel arşiv yalnız Esri'dedir.
        """
        if date_from >= date_to:
            raise ValueError("date_from, date_to'dan önce olmalıdır.")

        x, y, z = lat_lng_to_tile(lat, lng, zoom)
        try:
            releases = [
                r for r in await self.list_releases() if date_from <= r["date"] <= date_to  # type: ignore[operator]
            ]
        except Exception as exc:
            logger.error("Esri Wayback sürüm listesi alınamadı: %s", exc)
            return []

        # Aynı görüntü çoğu sürümde tekrarlanır; örneklemi geniş tut, tekrarları ele.
        candidates = self._spread(releases, self.MAX_SNAPSHOTS * 2)
        snapshots: List[Dict[str, object]] = []
        seen: set[str] = set()
        for release in candidates:
            url = str(release["url_template"]).format(level=z, row=y, col=x)
            img = await self.fetch_snapshot_image(url)
            if img is None:
                continue
            digest = hashlib.sha1(img.tobytes()).hexdigest()
            if digest in seen:
                continue
            seen.add(digest)
            snapshots.append(
                {
                    "timestamp": release["date"].isoformat(),  # type: ignore[union-attr]
                    "wayback_url": url,
                    "release": release["release"],
                    "digest": digest,
                    "tile_coords": {"x": x, "y": y, "z": z},
                    "provider": "esri_wayback",
                }
            )
            if len(snapshots) >= self.MAX_SNAPSHOTS:
                break

        logger.info(
            "Esri Wayback: %d sürümden %d farklı görüntü (lat=%.4f, lng=%.4f, z=%d)",
            len(candidates), len(snapshots), lat, lng, zoom,
        )
        return snapshots

    async def fetch_snapshot_image(self, wayback_url: str) -> Optional[Image.Image]:
        """Bir sürümün tile görüntüsünü indirir (aynı örnek içinde önbellekli)."""
        if wayback_url in self._images:
            return self._images[wayback_url]
        try:
            response = await self._require_client().get(wayback_url)
            response.raise_for_status()
            img = Image.open(io.BytesIO(response.content))
            img.load()
        except Exception as exc:
            logger.warning("Wayback görüntüsü indirilemedi (%s): %s", wayback_url, exc)
            return None
        self._images[wayback_url] = img
        return img
