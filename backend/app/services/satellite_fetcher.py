"""
satellite_fetcher.py — Uydu görüntüsü indirme servisi.

Sentinel Hub Process API ve NASA GIBS WMTS üzerinden gerçek uydu
görüntülerini asenkron olarak indirir. Sentinel Hub mevcutsa önce onu
dener, başarısız olursa NASA GIBS'e düşer (fallback).

İndirilen görüntüler MinIO'ya veya yerel dosya sistemine kaydedilir;
her görüntü için metadata JSON dosyası oluşturulur.
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import random
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx
from PIL import Image

from app.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Sabitler
# ---------------------------------------------------------------------------

# Sentinel Hub
SENTINEL_AUTH_URL: str = "https://services.sentinel-hub.com/oauth/token"
SENTINEL_PROCESS_URL: str = "https://services.sentinel-hub.com/api/v1/process"

# NASA GIBS WMTS
GIBS_WMTS_BASE: str = "https://gibs.earthdata.nasa.gov/wmts/epsg4326/best"
GIBS_LAYER: str = "MODIS_Terra_CorrectedReflectance_TrueColor"
GIBS_TILE_MATRIX_SET: str = "250m"

# Depolama
DEFAULT_STORAGE_ROOT: str = os.path.join("data", "satellite")

# Evalscript — Sentinel-2 True Color (B04=Red, B03=Green, B02=Blue)
SENTINEL_EVALSCRIPT: str = """
//VERSION=3
function setup() {
  return {
    input: [{
      bands: ["B04", "B03", "B02"],
      units: "DN"
    }],
    output: {
      bands: 3,
      sampleType: "AUTO"
    }
  };
}

function evaluatePixel(sample) {
  return [
    sample.B04 / 10000 * 3.5,
    sample.B03 / 10000 * 3.5,
    sample.B02 / 10000 * 3.5
  ];
}
"""

USER_AGENTS: List[str] = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
]


# ---------------------------------------------------------------------------
# Yardımcı: Bounding box
# ---------------------------------------------------------------------------


def lat_lng_to_bbox(
    lat: float,
    lng: float,
    radius_m: int = 500,
) -> Tuple[float, float, float, float]:
    """
    Merkez koordinat ve yarıçaptan bounding box hesaplar.

    Args:
        lat: Merkez enlemi.
        lng: Merkez boylamı.
        radius_m: Yarıçap (metre).

    Returns:
        (min_lat, min_lng, max_lat, max_lng) tuple'ı.
    """
    import math

    # 1 derece enlem ≈ 111,320 m
    lat_delta = radius_m / 111_320.0
    lng_delta = radius_m / (111_320.0 * math.cos(math.radians(lat)))

    return (
        lat - lat_delta,
        lng - lng_delta,
        lat + lat_delta,
        lng + lng_delta,
    )


# ---------------------------------------------------------------------------
# Depolama yöneticisi
# ---------------------------------------------------------------------------


class _ImageStorage:
    """
    Uydu görüntülerini yerel dosya sistemi veya MinIO'ya kaydeder.

    MinIO kullanılabilir durumda değilse yerel dosya sistemine düşer.
    Her görüntü ile birlikte bir metadata JSON dosyası oluşturulur.

    Yol formatı: satellite/{date}/{lat}_{lng}_{zoom}.jpg
    """

    def __init__(
        self,
        *,
        storage_root: Optional[str] = None,
        use_minio: bool = False,
        minio_bucket: str = "satellite-images",
    ) -> None:
        """
        Args:
            storage_root: Yerel depolama kök dizini.
            use_minio: MinIO kullanılsın mı (varsayılan False).
            minio_bucket: MinIO bucket adı.
        """
        self._storage_root = Path(storage_root or DEFAULT_STORAGE_ROOT)
        self._use_minio = use_minio
        self._minio_bucket = minio_bucket
        self._minio_client = None

    async def _ensure_minio(self) -> bool:
        """
        MinIO client'ı başlatmayı dener. Başarısızsa False döndürür.

        Returns:
            MinIO kullanılabilir mi.
        """
        if not self._use_minio:
            return False

        if self._minio_client is not None:
            return True

        try:
            from minio import Minio

            self._minio_client = Minio(
                getattr(settings, "MINIO_ENDPOINT", "minio:9000"),
                access_key=getattr(settings, "MINIO_ACCESS_KEY", "minioadmin"),
                secret_key=getattr(settings, "MINIO_SECRET_KEY", "minioadmin"),
                secure=getattr(settings, "MINIO_SECURE", False),
            )

            # Bucket yoksa oluştur
            if not self._minio_client.bucket_exists(self._minio_bucket):
                self._minio_client.make_bucket(self._minio_bucket)

            logger.info("MinIO bağlantısı başarılı: %s", self._minio_bucket)
            return True

        except ImportError:
            logger.warning("MinIO SDK yüklü değil, yerel depolama kullanılacak")
            self._use_minio = False
            return False

        except Exception as exc:
            logger.warning("MinIO bağlantı hatası, yerel depolama kullanılacak: %s", exc)
            self._use_minio = False
            return False

    def _build_path(
        self,
        lat: float,
        lng: float,
        zoom: int,
        date: datetime,
    ) -> str:
        """
        Depolama yolunu oluşturur.

        Args:
            lat, lng: Koordinatlar.
            zoom: Zoom seviyesi.
            date: Görüntü tarihi.

        Returns:
            Relatif dosya yolu (uzantısız).
        """
        date_str = date.strftime("%Y-%m-%d")
        filename = f"{lat:.4f}_{lng:.4f}_{zoom}"
        return f"satellite/{date_str}/{filename}"

    async def save(
        self,
        image: Image.Image,
        lat: float,
        lng: float,
        zoom: int,
        date: datetime,
        metadata: Dict[str, Any],
    ) -> str:
        """
        Görüntüyü ve metadata'yı kaydeder.

        Args:
            image: PIL Image objesi.
            lat, lng: Koordinatlar.
            zoom: Zoom seviyesi.
            date: Görüntü tarihi.
            metadata: Ek metadata sözlüğü.

        Returns:
            Kaydedilen dosya yolu (veya MinIO object key).
        """
        rel_path = self._build_path(lat, lng, zoom, date)
        img_path = f"{rel_path}.jpg"
        meta_path = f"{rel_path}_meta.json"

        # Görüntüyü byte'lara çevir
        img_buffer = io.BytesIO()
        image.convert("RGB").save(img_buffer, format="JPEG", quality=90)
        img_bytes = img_buffer.getvalue()

        # Metadata JSON
        full_metadata = {
            "lat": lat,
            "lng": lng,
            "zoom": zoom,
            "date": date.isoformat(),
            "image_size": image.size,
            "file_size_bytes": len(img_bytes),
            "saved_at": datetime.utcnow().isoformat(),
            **metadata,
        }
        meta_bytes = json.dumps(full_metadata, indent=2, ensure_ascii=False).encode("utf-8")

        # MinIO'ya kaydet
        use_minio = await self._ensure_minio()
        if use_minio and self._minio_client is not None:
            try:
                self._minio_client.put_object(
                    self._minio_bucket,
                    img_path,
                    io.BytesIO(img_bytes),
                    len(img_bytes),
                    content_type="image/jpeg",
                )
                self._minio_client.put_object(
                    self._minio_bucket,
                    meta_path,
                    io.BytesIO(meta_bytes),
                    len(meta_bytes),
                    content_type="application/json",
                )
                logger.info("MinIO'ya kaydedildi: %s", img_path)
                return f"minio://{self._minio_bucket}/{img_path}"

            except Exception as exc:
                logger.warning(
                    "MinIO yazma hatası, yerel dosyaya düşülüyor: %s", exc
                )

        # Yerel dosya sistemine kaydet
        full_img_path = self._storage_root / img_path
        full_meta_path = self._storage_root / meta_path

        full_img_path.parent.mkdir(parents=True, exist_ok=True)

        full_img_path.write_bytes(img_bytes)
        full_meta_path.write_bytes(meta_bytes)

        logger.info("Yerel dosyaya kaydedildi: %s", full_img_path)
        return str(full_img_path)


# Modül düzeyinde storage instance
_storage = _ImageStorage()


# ---------------------------------------------------------------------------
# SentinelFetcher
# ---------------------------------------------------------------------------


class SentinelFetcher:
    """
    Sentinel Hub Process API üzerinden Sentinel-2 uydu görüntüsü çeker.

    OAuth2 ile kimlik doğrulama yapar, belirtilen bounding box ve tarih
    aralığı için en az bulutlu True Color görüntüsünü indirir.

    Attributes:
        _client: Paylaşılan httpx async HTTP client.
        _access_token: OAuth2 bearer token.
        _token_expires_at: Token'ın geçerlilik süresi.

    Examples:
        >>> async with SentinelFetcher() as sf:
        ...     img = await sf.fetch_image(
        ...         bbox=(40.98, 28.95, 41.05, 29.05),
        ...         resolution=10,
        ...     )
        ...     img.size
        (780, 780)
    """

    def __init__(self) -> None:
        self._client: Optional[httpx.AsyncClient] = None
        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0.0

    async def __aenter__(self) -> "SentinelFetcher":
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(120.0, connect=15.0),
            follow_redirects=True,
        )
        return self

    async def __aexit__(self, *exc) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    # ------------------------------------------------------------------ #
    # Kimlik doğrulama
    # ------------------------------------------------------------------ #

    async def authenticate(self) -> str:
        """
        Sentinel Hub OAuth2 token alır veya mevcut token'ı yeniler.

        Config'deki SENTINEL_HUB_CLIENT_ID ve SENTINEL_HUB_CLIENT_SECRET
        kullanılır. Token süresi dolmuşsa otomatik olarak yenilenir.

        Returns:
            Geçerli access token string'i.

        Raises:
            ValueError: Client ID/Secret yapılandırılmamışsa.
            RuntimeError: Token alınamıyorsa.
        """
        if self._client is None:
            raise RuntimeError(
                "SentinelFetcher context manager ile kullanılmalı."
            )

        # Token hâlâ geçerliyse yeniden alma
        if self._access_token and time.time() < self._token_expires_at - 60:
            return self._access_token

        client_id = settings.SENTINEL_HUB_CLIENT_ID
        client_secret = settings.SENTINEL_HUB_CLIENT_SECRET

        if not client_id or not client_secret:
            raise ValueError(
                "Sentinel Hub kimlik bilgileri eksik. "
                "SENTINEL_HUB_CLIENT_ID ve SENTINEL_HUB_CLIENT_SECRET "
                "ayarlanmalıdır."
            )

        try:
            response = await self._client.post(
                SENTINEL_AUTH_URL,
                data={
                    "grant_type": "client_credentials",
                    "client_id": client_id,
                    "client_secret": client_secret,
                },
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                },
            )
            response.raise_for_status()

            token_data = response.json()
            self._access_token = token_data["access_token"]
            expires_in = token_data.get("expires_in", 3600)
            self._token_expires_at = time.time() + expires_in

            logger.info(
                "Sentinel Hub OAuth2 token alındı (geçerlilik: %d sn)",
                expires_in,
            )
            return self._access_token

        except httpx.HTTPStatusError as exc:
            logger.error("Sentinel Hub auth hatası: %s", exc.response.text)
            raise RuntimeError(
                f"Sentinel Hub kimlik doğrulama başarısız: {exc.response.status_code}"
            ) from exc

        except Exception as exc:
            logger.error("Sentinel Hub auth beklenmeyen hata: %s", exc)
            raise RuntimeError(
                "Sentinel Hub kimlik doğrulama başarısız"
            ) from exc

    @property
    def is_configured(self) -> bool:
        """Sentinel Hub API anahtarlarının yapılandırılıp yapılandırılmadığını kontrol eder."""
        return bool(
            settings.SENTINEL_HUB_CLIENT_ID
            and settings.SENTINEL_HUB_CLIENT_SECRET
        )

    # ------------------------------------------------------------------ #
    # Görüntü indirme
    # ------------------------------------------------------------------ #

    async def fetch_image(
        self,
        bbox: Tuple[float, float, float, float],
        *,
        resolution: int = 10,
        date: Optional[datetime] = None,
        max_cloud_coverage: float = 20.0,
    ) -> Image.Image:
        """
        Sentinel-2 True Color uydu görüntüsü indirir.

        Belirtilen bounding box alanı için Sentinel Hub Process API'ye
        istek gönderir. Tarih belirtilmezse son 30 günün en az bulutlu
        görüntüsünü getirir.

        Args:
            bbox: (min_lat, min_lng, max_lat, max_lng) sınırları.
            resolution: Piksel başına metre çözünürlüğü (varsayılan 10m).
            date: Belirli bir tarih. None ise son 30 gün taranır.
            max_cloud_coverage: Maksimum bulut oranı (%) , varsayılan 20.

        Returns:
            PIL.Image.Image objesi (True Color RGB).

        Raises:
            ValueError: Geçersiz parametreler veya API yapılandırılmamışsa.
            RuntimeError: İndirme başarısızsa.
        """
        if self._client is None:
            raise RuntimeError(
                "SentinelFetcher context manager ile kullanılmalı."
            )

        min_lat, min_lng, max_lat, max_lng = bbox

        # Parametre doğrulama
        if min_lat >= max_lat:
            raise ValueError(f"Geçersiz bbox: min_lat ({min_lat}) >= max_lat ({max_lat})")
        if min_lng >= max_lng:
            raise ValueError(f"Geçersiz bbox: min_lng ({min_lng}) >= max_lng ({max_lng})")

        # Token al
        token = await self.authenticate()

        # Tarih aralığı
        if date is not None:
            date_from = date.strftime("%Y-%m-%dT00:00:00Z")
            date_to = date.strftime("%Y-%m-%dT23:59:59Z")
        else:
            now = datetime.utcnow()
            date_from = (now - timedelta(days=30)).strftime("%Y-%m-%dT00:00:00Z")
            date_to = now.strftime("%Y-%m-%dT23:59:59Z")

        # Process API request body
        request_body = {
            "input": {
                "bounds": {
                    "bbox": [min_lng, min_lat, max_lng, max_lat],
                    "properties": {"crs": "http://www.opengis.net/def/crs/EPSG/0/4326"},
                },
                "data": [
                    {
                        "type": "sentinel-2-l2a",
                        "dataFilter": {
                            "timeRange": {
                                "from": date_from,
                                "to": date_to,
                            },
                            "maxCloudCoverage": max_cloud_coverage,
                            "mosaickingOrder": "leastCC",
                        },
                    }
                ],
            },
            "output": {
                "width": max(256, int(abs(max_lng - min_lng) * 111_320 / resolution)),
                "height": max(256, int(abs(max_lat - min_lat) * 111_320 / resolution)),
                "responses": [
                    {
                        "identifier": "default",
                        "format": {"type": "image/png"},
                    }
                ],
            },
            "evalscript": SENTINEL_EVALSCRIPT,
        }

        # Boyut sınırı (Sentinel Hub limiti: 2500×2500)
        request_body["output"]["width"] = min(request_body["output"]["width"], 2500)
        request_body["output"]["height"] = min(request_body["output"]["height"], 2500)

        try:
            logger.info(
                "Sentinel Hub isteği: bbox=(%.4f,%.4f,%.4f,%.4f), "
                "resolution=%dm, dates=%s→%s",
                min_lat, min_lng, max_lat, max_lng,
                resolution, date_from, date_to,
            )

            response = await self._client.post(
                SENTINEL_PROCESS_URL,
                json=request_body,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                    "Accept": "image/png",
                },
            )
            response.raise_for_status()

            content_type = response.headers.get("content-type", "")
            if "image" not in content_type:
                # JSON hata yanıtı olabilir
                error_detail = response.text[:500]
                raise RuntimeError(
                    f"Beklenmeyen yanıt tipi: {content_type} — {error_detail}"
                )

            img = Image.open(io.BytesIO(response.content))
            img.load()

            logger.info(
                "Sentinel Hub görüntüsü alındı: %dx%d (%d bytes)",
                img.width, img.height, len(response.content),
            )
            return img

        except httpx.HTTPStatusError as exc:
            error_body = exc.response.text[:500]
            logger.error(
                "Sentinel Hub HTTP hatası %d: %s",
                exc.response.status_code,
                error_body,
            )
            raise RuntimeError(
                f"Sentinel Hub isteği başarısız ({exc.response.status_code})"
            ) from exc

        except Exception as exc:
            logger.error("Sentinel Hub beklenmeyen hata: %s", exc)
            raise


# ---------------------------------------------------------------------------
# NASAGIBSFetcher
# ---------------------------------------------------------------------------


class NASAGIBSFetcher:
    """
    NASA GIBS (Global Imagery Browse Services) WMTS üzerinden MODIS
    uydu görüntüsü çeker.

    Ücretsiz ve API anahtarı gerektirmeyen bir fallback kaynağıdır.
    MODIS Terra True Color katmanını kullanır.

    Examples:
        >>> async with NASAGIBSFetcher() as nf:
        ...     img = await nf.fetch_modis(41.0082, 28.9784, 8)
        ...     img.size
        (256, 256)
    """

    # GIBS WMTS TileMatrixSet bilgileri (EPSG:4326)
    # Matrix set tanımları: zoom → (matrix_width, matrix_height, tile_size)
    TILE_MATRIX_LIMITS: Dict[int, Dict[str, int]] = {
        0: {"matrix_width": 2, "matrix_height": 1},
        1: {"matrix_width": 3, "matrix_height": 2},
        2: {"matrix_width": 5, "matrix_height": 3},
        3: {"matrix_width": 10, "matrix_height": 5},
        4: {"matrix_width": 20, "matrix_height": 10},
        5: {"matrix_width": 40, "matrix_height": 20},
        6: {"matrix_width": 80, "matrix_height": 40},
        7: {"matrix_width": 160, "matrix_height": 80},
        8: {"matrix_width": 320, "matrix_height": 160},
    }

    def __init__(self) -> None:
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self) -> "NASAGIBSFetcher":
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
    def _lat_lng_to_gibs_tile(
        lat: float,
        lng: float,
        zoom: int,
    ) -> Tuple[int, int]:
        """
        Koordinatları GIBS WMTS tile indeksine çevirir (EPSG:4326).

        GIBS, EPSG:4326 projeksiyon kullanır; standart Slippy Map
        (EPSG:3857) yerine farklı bir tile hesabı gerektirir.

        Args:
            lat: Enlem (-90 ile 90 arası).
            lng: Boylam (-180 ile 180 arası).
            zoom: Zoom seviyesi (0–8).

        Returns:
            (col, row) tile indeksleri.
        """
        # EPSG:4326 bounding box: (-180, -90, 180, 90)
        # Tile boyutu: 512×512 piksel
        # Her zoom'da grid boyutu farklı

        # Basitleştirilmiş hesaplama:
        # Toplam derece aralığı: lng=360, lat=180
        n_tiles_x = 2 ** (zoom + 1)  # lng yönünde
        n_tiles_y = 2 ** zoom  # lat yönünde

        col = int((lng + 180.0) / 360.0 * n_tiles_x)
        row = int((90.0 - lat) / 180.0 * n_tiles_y)

        col = max(0, min(col, n_tiles_x - 1))
        row = max(0, min(row, n_tiles_y - 1))

        return (col, row)

    async def fetch_modis(
        self,
        lat: float,
        lng: float,
        zoom: int,
        *,
        date: Optional[datetime] = None,
    ) -> Image.Image:
        """
        NASA GIBS'den MODIS Terra True Color tile görüntüsü indirir.

        Args:
            lat: Enlem (derece).
            lng: Boylam (derece).
            zoom: Zoom seviyesi (0–8, GIBS EPSG:4326 sınırı).
            date: Görüntü tarihi. None ise dün kullanılır
                  (bugünün verisi henüz mevcut olmayabilir).

        Returns:
            PIL.Image.Image objesi (256×256 veya 512×512).

        Raises:
            ValueError: Geçersiz parametreler.
            RuntimeError: İndirme başarısızsa.

        Examples:
            >>> async with NASAGIBSFetcher() as nf:
            ...     img = await nf.fetch_modis(41.0, 29.0, 5)
        """
        if self._client is None:
            raise RuntimeError(
                "NASAGIBSFetcher context manager ile kullanılmalı."
            )

        if not -90.0 <= lat <= 90.0:
            raise ValueError(f"Geçersiz enlem: {lat}")
        if not -180.0 <= lng <= 180.0:
            raise ValueError(f"Geçersiz boylam: {lng}")

        # GIBS zoom limiti
        zoom = max(0, min(zoom, 8))

        # Tarih (GIBS formatı: YYYY-MM-DD)
        if date is None:
            date = datetime.utcnow() - timedelta(days=1)
        date_str = date.strftime("%Y-%m-%d")

        col, row = self._lat_lng_to_gibs_tile(lat, lng, zoom)

        # WMTS KVP URL oluştur
        url = (
            f"{GIBS_WMTS_BASE}?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0"
            f"&LAYER={GIBS_LAYER}"
            f"&STYLE="
            f"&TILEMATRIXSET={GIBS_TILE_MATRIX_SET}"
            f"&TILEMATRIX={zoom}"
            f"&TILEROW={row}"
            f"&TILECOL={col}"
            f"&FORMAT=image/jpeg"
            f"&TIME={date_str}"
        )

        try:
            logger.info(
                "NASA GIBS isteği: lat=%.4f lng=%.4f zoom=%d "
                "col=%d row=%d date=%s",
                lat, lng, zoom, col, row, date_str,
            )

            response = await self._client.get(
                url,
                headers={"User-Agent": random.choice(USER_AGENTS)},
            )
            response.raise_for_status()

            content_type = response.headers.get("content-type", "")
            if "xml" in content_type.lower():
                # WMTS hata yanıtı (XML)
                error_text = response.text[:500]
                logger.error("GIBS XML hatası: %s", error_text)
                raise RuntimeError(f"GIBS WMTS hata yanıtı: {error_text}")

            img = Image.open(io.BytesIO(response.content))
            img.load()

            logger.info(
                "GIBS görüntüsü alındı: %dx%d (%d bytes)",
                img.width, img.height, len(response.content),
            )
            return img

        except httpx.HTTPStatusError as exc:
            logger.error(
                "GIBS HTTP hatası %d: %s",
                exc.response.status_code,
                exc.response.text[:300],
            )
            raise RuntimeError(
                f"NASA GIBS isteği başarısız ({exc.response.status_code})"
            ) from exc

        except Exception as exc:
            if isinstance(exc, RuntimeError):
                raise
            logger.error("GIBS beklenmeyen hata: %s", exc)
            raise RuntimeError(
                "NASA GIBS görüntüsü indirilemedi"
            ) from exc


# ---------------------------------------------------------------------------
# fetch_best_available — Akıllı fallback mantığı
# ---------------------------------------------------------------------------


async def fetch_best_available(
    lat: float,
    lng: float,
    zoom: int,
    *,
    radius_m: int = 500,
    resolution: int = 10,
    date: Optional[datetime] = None,
    save: bool = True,
) -> Dict[str, Any]:
    """
    En iyi mevcut kaynaktan uydu görüntüsü indirir.

    Önce Sentinel Hub'ı dener (API anahtarları yapılandırılmışsa).
    Başarısız olursa NASA GIBS'e düşer. Her iki durumda da PIL.Image
    döndürür ve opsiyonel olarak depoya kaydeder.

    Args:
        lat: Enlem (derece).
        lng: Boylam (derece).
        zoom: Zoom seviyesi.
        radius_m: Bounding box yarıçapı (metre), Sentinel için.
        resolution: Sentinel çözünürlüğü (m/px).
        date: Belirli tarih. None ise en güncel görüntü.
        save: Görüntüyü depoya kaydet (varsayılan True).

    Returns:
        Sözlük:
        - "image": PIL.Image.Image
        - "source": "sentinel" | "gibs"
        - "date": Kullanılan tarih
        - "path": Kaydedilen dosya yolu (save=True ise)
        - "metadata": Ek bilgiler

    Examples:
        >>> result = await fetch_best_available(41.0082, 28.9784, 15)
        >>> result["source"]
        'sentinel'  # veya 'gibs'
        >>> result["image"].size
        (512, 512)
    """
    result_image: Optional[Image.Image] = None
    source: str = "unknown"
    metadata: Dict[str, Any] = {}
    used_date = date or datetime.utcnow()

    # --- 1. Sentinel Hub dene ---
    sentinel = SentinelFetcher()
    if sentinel.is_configured:
        try:
            async with SentinelFetcher() as sf:
                bbox = lat_lng_to_bbox(lat, lng, radius_m)
                result_image = await sf.fetch_image(
                    bbox=bbox,
                    resolution=resolution,
                    date=date,
                    max_cloud_coverage=20.0,
                )
                source = "sentinel"
                metadata = {
                    "provider": "sentinel-2-l2a",
                    "resolution_m": resolution,
                    "bbox": list(bbox),
                    "max_cloud_coverage": 20.0,
                }
                logger.info("Sentinel Hub görüntüsü başarıyla alındı")

        except Exception as exc:
            logger.warning(
                "Sentinel Hub başarısız, GIBS'e düşülüyor: %s", exc
            )
            result_image = None
    else:
        logger.info(
            "Sentinel Hub yapılandırılmamış, doğrudan GIBS kullanılıyor"
        )

    # --- 2. Fallback: NASA GIBS ---
    if result_image is None:
        try:
            async with NASAGIBSFetcher() as nf:
                gibs_zoom = min(zoom, 8)  # GIBS zoom limiti
                result_image = await nf.fetch_modis(
                    lat, lng, gibs_zoom, date=date,
                )
                source = "gibs"
                metadata = {
                    "provider": "MODIS_Terra",
                    "layer": GIBS_LAYER,
                    "gibs_zoom": gibs_zoom,
                }
                logger.info("NASA GIBS görüntüsü başarıyla alındı")

        except Exception as exc:
            logger.error("NASA GIBS de başarısız: %s", exc)
            raise RuntimeError(
                f"Uydu görüntüsü alınamıyor (lat={lat}, lng={lng}): "
                f"tüm kaynaklar başarısız."
            ) from exc

    # --- 3. Depoya kaydet ---
    saved_path: Optional[str] = None
    if save and result_image is not None:
        try:
            saved_path = await _storage.save(
                image=result_image,
                lat=lat,
                lng=lng,
                zoom=zoom,
                date=used_date,
                metadata={
                    "source": source,
                    **metadata,
                },
            )
        except Exception as exc:
            logger.warning("Görüntü kaydedilemedi: %s", exc)

    return {
        "image": result_image,
        "source": source,
        "date": used_date.isoformat() if isinstance(used_date, datetime) else str(used_date),
        "path": saved_path,
        "metadata": metadata,
    }
