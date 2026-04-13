"""
anomalies.py — GhostBuilding anomali API endpoint'leri.

Anomali listeleme (mekansal filtreleme), detay görüntüleme,
tarama başlatma, görev durumu sorgulama, tile karşılaştırma
ve istatistik endpoint'lerini sağlar.

Tüm response'lar Pydantic v2 schema'ları kullanır.
OpenAPI dokümantasyonu eksiksiz olarak tanımlanmıştır.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Generic, List, Optional, TypeVar

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field, ConfigDict, field_validator
from sqlalchemy import func, text, case, select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.session import get_db
from app.models.anomaly import Anomaly
from app.models.anomaly_image import AnomalyImage
from app.models.verification import Verification
from app.models.enums import (
    AnomalyCategory,
    AnomalyStatus,
    ImageProvider,
    VerificationVote,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# ═══════════════════════════════════════════════════════════════════════════
# Pydantic v2 Schemas
# ═══════════════════════════════════════════════════════════════════════════

DataT = TypeVar("DataT")


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------


class PaginationMeta(BaseModel):
    """Sayfalama meta bilgisi."""

    model_config = ConfigDict(json_schema_extra={
        "example": {"page": 1, "limit": 20, "total": 142, "total_pages": 8},
    })

    page: int = Field(..., description="Mevcut sayfa numarası", ge=1)
    limit: int = Field(..., description="Sayfa başına kayıt sayısı", ge=1, le=100)
    total: int = Field(..., description="Toplam kayıt sayısı", ge=0)
    total_pages: int = Field(..., description="Toplam sayfa sayısı", ge=0)


class PaginatedResponse(BaseModel, Generic[DataT]):
    """Genel sayfalanmış yanıt wrapper'ı."""

    model_config = ConfigDict(from_attributes=True)

    data: List[DataT] = Field(..., description="Sonuç listesi")
    pagination: PaginationMeta


# ---------------------------------------------------------------------------
# Anomaly — List Item
# ---------------------------------------------------------------------------


class AnomalyListItem(BaseModel):
    """GET /anomalies listesinde dönen kısaltılmış anomali özeti."""

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                "lat": 41.0082,
                "lng": 28.9784,
                "category": "GHOST_BUILDING",
                "confidence_score": 87.5,
                "title": "İstanbul — Hayalet yapı tespit edildi",
                "status": "PENDING",
                "detected_at": "2026-04-12T10:30:00Z",
                "thumbnail_url": None,
            }
        },
    )

    id: str = Field(..., description="Anomali UUID")
    lat: float = Field(..., description="Enlem")
    lng: float = Field(..., description="Boylam")
    category: str = Field(..., description="Anomali kategorisi", examples=["GHOST_BUILDING"])
    confidence_score: float = Field(..., description="Güven skoru (0–100)")
    title: Optional[str] = Field(None, description="Kısa başlık")
    status: str = Field(..., description="Doğrulama durumu", examples=["PENDING"])
    detected_at: Optional[datetime] = Field(None, description="Tespit zamanı (UTC)")
    thumbnail_url: Optional[str] = Field(None, description="Küçük resim URL'si")


# ---------------------------------------------------------------------------
# Anomaly — Image Detail
# ---------------------------------------------------------------------------


class AnomalyImageSchema(BaseModel):
    """Anomali ile ilişkili görüntü bilgisi."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Görüntü UUID")
    provider: str = Field(..., description="Harita sağlayıcısı", examples=["GOOGLE"])
    image_url: str = Field(..., description="Görüntü erişim URL'si")
    captured_at: Optional[datetime] = Field(None, description="Yakalama zamanı")
    zoom_level: Optional[int] = Field(None, description="Zoom seviyesi")
    tile_x: Optional[int] = Field(None, description="Tile X koordinatı")
    tile_y: Optional[int] = Field(None, description="Tile Y koordinatı")
    tile_z: Optional[int] = Field(None, description="Tile Z koordinatı")
    diff_score: Optional[float] = Field(None, description="Piksel fark skoru")
    is_blurred: bool = Field(False, description="Bulanıklaştırma tespit edildi mi")


# ---------------------------------------------------------------------------
# Anomaly — Verification Stats
# ---------------------------------------------------------------------------


class VerificationStats(BaseModel):
    """Anomali doğrulama istatistikleri."""

    total_votes: int = Field(0, description="Toplam oy sayısı")
    confirm_count: int = Field(0, description="Onay oyu sayısı")
    deny_count: int = Field(0, description="Red oyu sayısı")
    uncertain_count: int = Field(0, description="Belirsiz oy sayısı")
    confirmation_rate: float = Field(0.0, description="Onay oranı (%)")


# ---------------------------------------------------------------------------
# Anomaly — Time Series Entry
# ---------------------------------------------------------------------------


class TimeSeriesEntry(BaseModel):
    """Tarihsel zaman serisi veri noktası."""

    date: str = Field(..., description="Tarih (YYYY-MM-DD)")
    confidence_score: Optional[float] = Field(None, description="O tarihteki güven skoru")
    provider_count: Optional[int] = Field(None, description="Tile sağlayıcı sayısı")
    event: Optional[str] = Field(None, description="Olay açıklaması")


# ---------------------------------------------------------------------------
# Anomaly — Full Detail
# ---------------------------------------------------------------------------


class AnomalyDetail(BaseModel):
    """GET /anomalies/{id} — Tam anomali detayı."""

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                "lat": 41.0082,
                "lng": 28.9784,
                "category": "GHOST_BUILDING",
                "confidence_score": 87.5,
                "title": "İstanbul — Hayalet yapı tespit edildi",
                "description": "Google Maps uydu görüntüsünde mevcut ancak OSM haritasında bulunmayan yapı.",
                "status": "PENDING",
                "detected_at": "2026-04-12T10:30:00Z",
                "verified_at": None,
                "source_providers": ["GOOGLE", "OSM"],
                "detection_methods": ["pixel_diff", "geospatial"],
                "meta_data": {"task_id": "abc123"},
                "created_at": "2026-04-12T10:30:00Z",
                "updated_at": "2026-04-12T10:30:00Z",
                "images": [],
                "verification_stats": {
                    "total_votes": 5,
                    "confirm_count": 4,
                    "deny_count": 1,
                    "uncertain_count": 0,
                    "confirmation_rate": 80.0,
                },
                "time_series": [],
            }
        },
    )

    id: str = Field(..., description="Anomali UUID")
    lat: float = Field(..., description="Enlem")
    lng: float = Field(..., description="Boylam")
    category: str = Field(..., description="Anomali kategorisi")
    confidence_score: float = Field(..., description="Güven skoru (0–100)")
    title: Optional[str] = Field(None, description="Kısa başlık")
    description: Optional[str] = Field(None, description="Detaylı açıklama")
    status: str = Field(..., description="Doğrulama durumu")
    detected_at: Optional[datetime] = Field(None, description="Tespit zamanı (UTC)")
    verified_at: Optional[datetime] = Field(None, description="Doğrulama zamanı (UTC)")
    source_providers: Optional[List[str]] = Field(None, description="Kaynak sağlayıcılar")
    detection_methods: Optional[List[str]] = Field(None, description="Tespit yöntemleri")
    meta_data: Optional[Dict[str, Any]] = Field(None, description="Ek metadata")
    created_at: Optional[datetime] = Field(None, description="Kayıt oluşturulma zamanı")
    updated_at: Optional[datetime] = Field(None, description="Son güncelleme zamanı")

    images: List[AnomalyImageSchema] = Field(default_factory=list, description="İlgili görüntüler")
    verification_stats: VerificationStats = Field(
        default_factory=VerificationStats, description="Doğrulama istatistikleri"
    )
    time_series: List[TimeSeriesEntry] = Field(
        default_factory=list, description="Tarihsel zaman serisi özeti"
    )


# ---------------------------------------------------------------------------
# Scan — Request & Response
# ---------------------------------------------------------------------------


class ScanRequest(BaseModel):
    """POST /anomalies/scan — Tarama başlatma isteği."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "lat": 41.0082,
                "lng": 28.9784,
                "zoom": 15,
                "radius_km": 5.0,
            }
        }
    )

    lat: float = Field(..., description="Tarama merkez enlemi", ge=-90.0, le=90.0)
    lng: float = Field(..., description="Tarama merkez boylamı", ge=-180.0, le=180.0)
    zoom: Optional[int] = Field(15, description="Zoom seviyesi (varsayılan 15)", ge=1, le=20)
    radius_km: Optional[float] = Field(
        5.0, description="Tarama yarıçapı (km, 0.1–50)", ge=0.1, le=50.0
    )

    @field_validator("lat")
    @classmethod
    def validate_lat(cls, v: float) -> float:
        """Enlem -90..90 arasında olmalıdır."""
        if not -90.0 <= v <= 90.0:
            raise ValueError("Enlem -90 ile 90 arasında olmalıdır.")
        return round(v, 8)

    @field_validator("lng")
    @classmethod
    def validate_lng(cls, v: float) -> float:
        """Boylam -180..180 arasında olmalıdır."""
        if not -180.0 <= v <= 180.0:
            raise ValueError("Boylam -180 ile 180 arasında olmalıdır.")
        return round(v, 8)


class ScanResponse(BaseModel):
    """POST /anomalies/scan — Tarama başlatma yanıtı."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "task_id": "d4e5f6a7-b8c9-0123-4567-890abcdef123",
                "estimated_seconds": 120,
                "status_url": "/api/v1/anomalies/scan/d4e5f6a7-b8c9-0123-4567-890abcdef123/status",
            }
        }
    )

    task_id: str = Field(..., description="Celery görev ID'si")
    estimated_seconds: int = Field(..., description="Tahmini tamamlanma süresi (saniye)")
    status_url: str = Field(..., description="Görev durumu sorgulama URL'si")


# ---------------------------------------------------------------------------
# Scan — Task Status
# ---------------------------------------------------------------------------


class ScanStatusResponse(BaseModel):
    """GET /anomalies/scan/{task_id}/status — Görev durumu yanıtı."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "task_id": "d4e5f6a7-b8c9-0123-4567-890abcdef123",
                "status": "running",
                "progress_percent": 65,
                "current_step": "Anomali analizi çalıştırılıyor",
                "anomaly_count": None,
                "anomaly_urls": None,
            }
        }
    )

    task_id: str = Field(..., description="Celery görev ID'si")
    status: str = Field(
        ...,
        description="Görev durumu: pending | running | complete | failed",
        examples=["pending"],
    )
    progress_percent: Optional[int] = Field(None, description="İlerleme yüzdesi (0–100)")
    current_step: Optional[str] = Field(None, description="Mevcut adım açıklaması")
    anomaly_count: Optional[int] = Field(
        None, description="Tamamlandıysa: bulunan anomali sayısı"
    )
    anomaly_urls: Optional[List[str]] = Field(
        None, description="Tamamlandıysa: anomali detay URL'leri"
    )


# ---------------------------------------------------------------------------
# Tile Compare
# ---------------------------------------------------------------------------


class TileCompareResponse(BaseModel):
    """GET /anomalies/tiles/compare — Tile karşılaştırma yanıtı."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "lat": 41.0082,
                "lng": 28.9784,
                "zoom": 15,
                "tile_coords": {"x": 19295, "y": 11826, "z": 15},
                "provider_images": {
                    "osm": "/tiles/cache/osm_15_19295_11826.png",
                    "google": "/tiles/cache/google_15_19295_11826.png",
                },
                "diff_scores": {"osm_vs_google": 0.23, "osm_vs_bing": 0.67},
                "anomaly_indicators": {
                    "has_significant_diff": True,
                    "max_diff_pair": "osm_vs_bing",
                    "max_diff_score": 0.67,
                    "providers_missing": ["yandex"],
                },
            }
        }
    )

    lat: float = Field(..., description="Sorgu enlemi")
    lng: float = Field(..., description="Sorgu boylamı")
    zoom: int = Field(..., description="Zoom seviyesi")
    tile_coords: Dict[str, int] = Field(..., description="Tile koordinatları {x, y, z}")
    provider_images: Dict[str, str] = Field(
        default_factory=dict,
        description="Sağlayıcı => görüntü URL/path eşleşmesi",
    )
    diff_scores: Dict[str, float] = Field(
        default_factory=dict,
        description="Sağlayıcı çifti => fark skoru (0–1)",
    )
    anomaly_indicators: Dict[str, Any] = Field(
        default_factory=dict,
        description="Anomali göstergeleri (önemli fark var mı, vs.)",
    )


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


class CategoryCount(BaseModel):
    """Kategori bazında anomali sayısı."""

    category: str = Field(..., description="Anomali kategorisi")
    count: int = Field(..., description="Anomali sayısı")


class TopAnomaly(BaseModel):
    """En yüksek güven skorlu anomali özeti."""

    id: str
    lat: float
    lng: float
    category: str
    confidence_score: float
    title: Optional[str] = None
    status: str


class RegionDistribution(BaseModel):
    """Ülke/bölge dağılımı."""

    region: str = Field(..., description="Ülke veya bölge adı")
    count: int = Field(..., description="Anomali sayısı")


class StatsResponse(BaseModel):
    """GET /anomalies/stats — İstatistik yanıtı."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "total_count": 1247,
                "by_category": [
                    {"category": "GHOST_BUILDING", "count": 523},
                    {"category": "CENSORED_AREA", "count": 312},
                ],
                "last_30_days_count": 89,
                "top_10": [],
                "region_distribution": [
                    {"region": "Turkey", "count": 210},
                    {"region": "Unknown", "count": 1037},
                ],
            }
        }
    )

    total_count: int = Field(..., description="Toplam anomali sayısı")
    by_category: List[CategoryCount] = Field(
        default_factory=list, description="Kategori bazında dağılım"
    )
    last_30_days_count: int = Field(0, description="Son 30 günde eklenen anomali sayısı")
    top_10: List[TopAnomaly] = Field(
        default_factory=list, description="En yüksek güven skorlu 10 anomali"
    )
    region_distribution: List[RegionDistribution] = Field(
        default_factory=list, description="Ülke/bölge dağılımı"
    )


# ═══════════════════════════════════════════════════════════════════════════
# Yardımcı Fonksiyonlar
# ═══════════════════════════════════════════════════════════════════════════


async def _get_redis_client():
    """Async Redis client döndürür."""
    import redis.asyncio as aioredis

    return aioredis.from_url(settings.REDIS_URL, decode_responses=True)


async def _check_rate_limit(request: Request) -> None:
    """
    IP başına saatte 5 istek sınırı uygular.

    Rate limit aşıldığında HTTP 429 döndürür.

    Args:
        request: FastAPI Request nesnesi.

    Raises:
        HTTPException: Rate limit aşıldığında (429).
    """
    client_ip = request.client.host if request.client else "unknown"
    rate_key = f"ratelimit:scan:{client_ip}"

    try:
        r = await _get_redis_client()
        current = await r.get(rate_key)

        if current is not None and int(current) >= 5:
            ttl = await r.ttl(rate_key)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "error": "Rate limit exceeded",
                    "message": f"IP başına saatte en fazla 5 tarama isteği gönderilebilir.",
                    "retry_after_seconds": max(ttl, 0),
                },
            )

        pipe = r.pipeline()
        pipe.incr(rate_key)
        pipe.expire(rate_key, 3600)  # 1 saat TTL
        await pipe.execute()
        await r.aclose()

    except HTTPException:
        raise
    except Exception as exc:
        # Redis bağlantı hatası durumunda isteği engelleme — grace mode
        logger.warning("Rate limit kontrolü başarısız (grace): %s", exc)


# ═══════════════════════════════════════════════════════════════════════════
# ENDPOINT: GET /anomalies — Anomali Listesi
# ═══════════════════════════════════════════════════════════════════════════


@router.get(
    "/",
    response_model=PaginatedResponse[AnomalyListItem],
    summary="Anomali listesi",
    description=(
        "Opsiyonel mekansal filtreleme (lat/lng/radius_km), kategori, güven skoru "
        "ve durum filtresi ile sayfalanmış anomali listesi döndürür. "
        "Mekansal sorgulama PostGIS ST_DWithin fonksiyonu ile yapılır."
    ),
    response_description="Sayfalanmış anomali özet listesi",
    tags=["anomalies"],
)
async def list_anomalies(
    lat: Optional[float] = Query(None, description="Merkez enlemi (mekansal filtre)", ge=-85.0511, le=85.0511),
    lng: Optional[float] = Query(None, description="Merkez boylamı (mekansal filtre)", ge=-180.0, le=180.0),
    radius_km: float = Query(50.0, description="Arama yarıçapı (km)", gt=0, le=500),
    category: Optional[str] = Query(
        None,
        description="Anomali kategorisi filtresi",
        examples=["GHOST_BUILDING", "CENSORED_AREA"],
    ),
    min_confidence: float = Query(40.0, description="Minimum güven skoru (0–100)", ge=0, le=100),
    status_filter: Optional[str] = Query(
        None,
        alias="status",
        description="Durum filtresi",
        examples=["PENDING", "VERIFIED"],
    ),
    page: int = Query(1, description="Sayfa numarası", ge=1),
    limit: int = Query(20, description="Sayfa başına kayıt sayısı", ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse[AnomalyListItem]:
    """
    Anomali listesini döndürür.

    - **Mekansal Filtre**: `lat` ve `lng` parametreleri verildiğinde,
      belirtilen `radius_km` içindeki anomaliler PostGIS `ST_DWithin`
      ile filtrelenir.
    - **Kategori Filtresi**: `category` parametresi ile belirli bir
      anomali türüne daraltılabilir.
    - **Güven Skoru**: `min_confidence` ile minimum skor belirlenir.
    - **Durum Filtresi**: `status` ile PENDING/VERIFIED/REJECTED
      gibi durumlara göre filtrelenir.
    """

    # --- Filtre koşulları ---
    conditions: list = []

    # Güven skoru filtresi
    conditions.append(Anomaly.confidence_score >= min_confidence)

    # Kategori filtresi
    if category:
        conditions.append(Anomaly.category == category)

    # Durum filtresi
    if status_filter:
        conditions.append(Anomaly.status == status_filter)

    # Mekansal filtre — PostGIS ST_DWithin
    if lat is not None and lng is not None:
        # radius_km → metre cevir; ST_DWithin geography modunda metre kullanır
        radius_m = radius_km * 1000.0
        point_wkt = f"SRID=4326;POINT({lng} {lat})"
        spatial_filter = func.ST_DWithin(
            Anomaly.geom.cast(text("geography")),
            func.ST_GeographyFromText(point_wkt),
            radius_m,
        )
        conditions.append(spatial_filter)

    # --- Toplam sayı ---
    count_stmt = select(func.count(Anomaly.id)).where(and_(*conditions))
    total_result = await db.execute(count_stmt)
    total = total_result.scalar() or 0

    total_pages = max(1, (total + limit - 1) // limit)

    # --- Veri sorgusu ---
    offset = (page - 1) * limit
    data_stmt = (
        select(Anomaly)
        .where(and_(*conditions))
        .order_by(Anomaly.detected_at.desc().nullslast())
        .offset(offset)
        .limit(limit)
    )

    result = await db.execute(data_stmt)
    rows = result.scalars().all()

    # Thumbnail: ilk ilişkili görüntü URL'si
    items: List[AnomalyListItem] = []
    for row in rows:
        thumbnail = None
        if row.images:
            thumbnail = row.images[0].image_url if row.images else None

        items.append(
            AnomalyListItem(
                id=str(row.id),
                lat=row.lat,
                lng=row.lng,
                category=row.category,
                confidence_score=row.confidence_score,
                title=row.title,
                status=row.status,
                detected_at=row.detected_at,
                thumbnail_url=thumbnail,
            )
        )

    return PaginatedResponse[AnomalyListItem](
        data=items,
        pagination=PaginationMeta(
            page=page,
            limit=limit,
            total=total,
            total_pages=total_pages,
        ),
    )


# ═══════════════════════════════════════════════════════════════════════════
# ENDPOINT: GET /anomalies/stats — İstatistikler
# ═══════════════════════════════════════════════════════════════════════════
# NOT: /stats rotası, /{id} rotasından ÖNCE tanımlanmalı (path param çakışması)


@router.get(
    "/stats",
    response_model=StatsResponse,
    summary="Anomali istatistikleri",
    description=(
        "Toplam anomali sayısı (kategori bazında), son 30 günde eklenenler, "
        "en yüksek güven skorlu top-10 anomali ve ülke/bölge dağılımı."
    ),
    response_description="Anomali istatistik özeti",
    tags=["anomalies"],
)
async def get_anomaly_stats(
    db: AsyncSession = Depends(get_db),
) -> StatsResponse:
    """
    Anomali istatistiklerini döndürür.

    Tüm veriler tek bir endpoint'te toplanmıştır:
    - Kategori bazında toplam sayılar
    - Son 30 gündeki eklenmeler
    - En yüksek güven skorlu top-10
    - Ülke/bölge dağılımı (meta_data'dan)
    """

    # --- Toplam sayı ---
    total_result = await db.execute(select(func.count(Anomaly.id)))
    total_count = total_result.scalar() or 0

    # --- Kategori bazında dağılım ---
    category_stmt = (
        select(Anomaly.category, func.count(Anomaly.id).label("count"))
        .group_by(Anomaly.category)
        .order_by(func.count(Anomaly.id).desc())
    )
    category_result = await db.execute(category_stmt)
    by_category = [
        CategoryCount(category=row.category, count=row.count)
        for row in category_result.all()
    ]

    # --- Son 30 gün ---
    thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
    recent_stmt = select(func.count(Anomaly.id)).where(
        Anomaly.detected_at >= thirty_days_ago
    )
    recent_result = await db.execute(recent_stmt)
    last_30_days_count = recent_result.scalar() or 0

    # --- Top-10 (en yüksek güven skoru) ---
    top_stmt = (
        select(Anomaly)
        .order_by(Anomaly.confidence_score.desc())
        .limit(10)
    )
    top_result = await db.execute(top_stmt)
    top_rows = top_result.scalars().all()
    top_10 = [
        TopAnomaly(
            id=str(row.id),
            lat=row.lat,
            lng=row.lng,
            category=row.category,
            confidence_score=row.confidence_score,
            title=row.title,
            status=row.status,
        )
        for row in top_rows
    ]

    # --- Ülke/bölge dağılımı ---
    # meta_data JSONB içinde "country" veya "region" alanından okunur.
    # Eğer yoksa "Unknown" olarak gruplandırılır.
    region_stmt = (
        select(
            func.coalesce(
                Anomaly.meta_data.op("->>")("country"),
                Anomaly.meta_data.op("->>")("region"),
                text("'Unknown'"),
            ).label("region"),
            func.count(Anomaly.id).label("count"),
        )
        .group_by(text("region"))
        .order_by(func.count(Anomaly.id).desc())
        .limit(50)
    )
    region_result = await db.execute(region_stmt)
    region_distribution = [
        RegionDistribution(region=row.region, count=row.count)
        for row in region_result.all()
    ]

    return StatsResponse(
        total_count=total_count,
        by_category=by_category,
        last_30_days_count=last_30_days_count,
        top_10=top_10,
        region_distribution=region_distribution,
    )


# ═══════════════════════════════════════════════════════════════════════════
# ENDPOINT: GET /anomalies/tiles/compare — Tile Karşılaştırma
# ═══════════════════════════════════════════════════════════════════════════


@router.get(
    "/tiles/compare",
    response_model=TileCompareResponse,
    summary="Anlık tile karşılaştırması",
    description=(
        "Belirtilen koordinat ve zoom seviyesinde farklı harita sağlayıcılarının "
        "tile görüntülerini anlık olarak indirir, pixel-diff analizi yapar "
        "ve fark skorlarını döndürür."
    ),
    response_description="Sağlayıcı tile görüntüleri, fark skorları ve anomali göstergeleri",
    tags=["anomalies"],
)
async def compare_tiles(
    lat: float = Query(..., description="Enlem", ge=-85.0511, le=85.0511),
    lng: float = Query(..., description="Boylam", ge=-180.0, le=180.0),
    zoom: int = Query(15, description="Zoom seviyesi", ge=1, le=20),
    providers: Optional[List[str]] = Query(
        None,
        description="Karşılaştırılacak sağlayıcılar (varsayılan: tümü)",
        examples=["OSM", "GOOGLE"],
    ),
) -> TileCompareResponse:
    """
    Anlık tile karşılaştırması yapar.

    1. Belirtilen sağlayıcılardan tile'ları indirir.
    2. Her sağlayıcı çifti için pixel-diff skoru hesaplar.
    3. Anomali göstergelerini (önemli fark, eksik sağlayıcı, vb.) döndürür.
    """
    from app.services.tile_fetcher import TileFetcher, TileProvider, lat_lng_to_tile

    x, y, z = lat_lng_to_tile(lat, lng, zoom)

    # Sağlayıcı filtresi
    requested_providers: Optional[List[TileProvider]] = None
    if providers:
        requested_providers = []
        for p_name in providers:
            try:
                requested_providers.append(TileProvider(p_name.lower()))
            except ValueError:
                logger.warning("Bilinmeyen sağlayıcı: %s — atlanıyor", p_name)

    # Tile'ları indir
    provider_images: Dict[str, str] = {}
    tile_data: Dict[str, Any] = {}
    try:
        async with TileFetcher() as fetcher:
            tiles = await fetcher.fetch_all_providers(
                lat, lng, zoom, providers=requested_providers
            )
            for tp, img in tiles.items():
                cache_path = f"/tiles/cache/{tp.value}_{z}_{x}_{y}.png"
                provider_images[tp.value] = cache_path
                tile_data[tp.value] = img
    except Exception as exc:
        logger.error("Tile karşılaştırma — indirme hatası: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Tile indirme sırasında hata oluştu: {str(exc)}",
        )

    # Pixel-diff skorları hesapla
    diff_scores: Dict[str, float] = {}
    anomaly_indicators: Dict[str, Any] = {
        "has_significant_diff": False,
        "max_diff_pair": None,
        "max_diff_score": 0.0,
        "providers_missing": [],
    }

    provider_keys = list(tile_data.keys())

    # Eksik sağlayıcıları kontrol et
    all_providers = [tp.value for tp in (requested_providers or list(TileProvider))]
    anomaly_indicators["providers_missing"] = [
        p for p in all_providers if p not in provider_keys
    ]

    # Her sağlayıcı çifti için diff hesapla
    if len(provider_keys) >= 2:
        try:
            from app.services.analyzers.pixel_diff import PixelDiffAnalyzer
            import numpy as np

            analyzer = PixelDiffAnalyzer()

            for i in range(len(provider_keys)):
                for j in range(i + 1, len(provider_keys)):
                    p1, p2 = provider_keys[i], provider_keys[j]
                    pair_key = f"{p1}_vs_{p2}"

                    try:
                        img1 = np.array(tile_data[p1].convert("RGB"))
                        img2 = np.array(tile_data[p2].convert("RGB"))
                        diff_result = analyzer.analyze(img1, img2)
                        score = diff_result.get("diff_score", 0.0)
                        diff_scores[pair_key] = round(score, 4)

                        if score > anomaly_indicators["max_diff_score"]:
                            anomaly_indicators["max_diff_score"] = round(score, 4)
                            anomaly_indicators["max_diff_pair"] = pair_key

                    except Exception as diff_exc:
                        logger.warning("Diff hesaplama hatası (%s): %s", pair_key, diff_exc)
                        diff_scores[pair_key] = -1.0

        except ImportError:
            logger.warning("PixelDiffAnalyzer import edilemiyor — diff skoru hesaplanamayacak")
        except Exception as exc:
            logger.warning("Diff analizi genel hatası: %s", exc)

    # Önemli fark eşiği: 0.3
    anomaly_indicators["has_significant_diff"] = anomaly_indicators["max_diff_score"] > 0.3

    return TileCompareResponse(
        lat=lat,
        lng=lng,
        zoom=zoom,
        tile_coords={"x": x, "y": y, "z": z},
        provider_images=provider_images,
        diff_scores=diff_scores,
        anomaly_indicators=anomaly_indicators,
    )


# ═══════════════════════════════════════════════════════════════════════════
# ENDPOINT: POST /anomalies/scan — Tarama Başlat
# ═══════════════════════════════════════════════════════════════════════════


@router.post(
    "/scan",
    response_model=ScanResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Anomali taraması başlat",
    description=(
        "Belirtilen koordinat ve yarıçapta yeni bir anomali taraması başlatır. "
        "Celery arka plan görevi olarak çalışır. IP başına saatte 5 istek limiti uygulanır."
    ),
    response_description="Başlatılan görevin ID'si, tahmini süre ve durum sorgulama URL'si",
    tags=["anomalies"],
)
async def start_scan(
    body: ScanRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> ScanResponse:
    """
    Yeni bir anomali taraması başlatır.

    - **Rate Limit**: IP başına saatte en fazla 5 istek.
    - **Celery Task**: `scan_coordinate` görevi arka planda başlatılır.
    - Tahmini süre radius ve zoom'a göre hesaplanır.
    """

    # Rate limiting kontrolü
    await _check_rate_limit(request)

    # Yarıçap sınır kontrolü
    radius = body.radius_km or 5.0
    if radius > settings.MAX_SCAN_RADIUS_KM:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Maksimum tarama yarıçapı {settings.MAX_SCAN_RADIUS_KM} km'dir.",
        )

    # ScanJob kaydı oluştur
    scan_job_id = str(uuid.uuid4())
    insert_sql = text("""
        INSERT INTO scan_jobs (id, status, center_lat, center_lng, radius_km)
        VALUES (:id, 'PENDING', :lat, :lng, :radius_km)
    """)
    await db.execute(
        insert_sql,
        {
            "id": scan_job_id,
            "lat": body.lat,
            "lng": body.lng,
            "radius_km": radius,
        },
    )
    await db.commit()

    # Celery görevi başlat
    from app.tasks.scan_tasks import scan_coordinate

    task = scan_coordinate.apply_async(
        kwargs={
            "lat": body.lat,
            "lng": body.lng,
            "zoom": body.zoom or 15,
            "radius_km": radius,
            "scan_job_id": scan_job_id,
        },
        queue="scan",
    )

    # Tahmini süre (basit heuristik)
    estimated = int(30 + radius * 8 + (body.zoom or 15) * 2)

    status_url = f"/api/v1/anomalies/scan/{task.id}/status"

    logger.info(
        "Tarama başlatıldı: task_id=%s lat=%.4f lng=%.4f radius=%.1fkm",
        task.id, body.lat, body.lng, radius,
    )

    return ScanResponse(
        task_id=task.id,
        estimated_seconds=estimated,
        status_url=status_url,
    )


# ═══════════════════════════════════════════════════════════════════════════
# ENDPOINT: GET /anomalies/scan/{task_id}/status — Tarama Durumu
# ═══════════════════════════════════════════════════════════════════════════


@router.get(
    "/scan/{task_id}/status",
    response_model=ScanStatusResponse,
    summary="Tarama görev durumu",
    description=(
        "Celery görev durumunu ve ilerleme yüzdesini sorgular. "
        "Tamamlandıysa bulunan anomali sayısı ve detay URL'leri döndürülür."
    ),
    response_description="Görev durumu, ilerleme ve sonuçlar",
    tags=["anomalies"],
)
async def get_scan_status(task_id: str) -> ScanStatusResponse:
    """
    Celery görev durumunu sorgular.

    İlerleme verileri Redis'ten okunur (`scan:progress:{task_id}`).
    Celery result backend'den nihai durum kontrol edilir.

    Dönen durum değerleri:
    - **pending**: Görev henüz başlamadı
    - **running**: Görev çalışıyor
    - **complete**: Görev tamamlandı
    - **failed**: Görev başarısız oldu
    """
    from app.tasks.celery_app import celery_app

    # Celery görev durumu
    async_result = celery_app.AsyncResult(task_id)
    celery_state = async_result.state  # PENDING, STARTED, SUCCESS, FAILURE, etc.

    # Durum eşleşmesi
    STATUS_MAP = {
        "PENDING": "pending",
        "RECEIVED": "pending",
        "STARTED": "running",
        "PROGRESS": "running",
        "RETRY": "running",
        "SUCCESS": "complete",
        "FAILURE": "failed",
        "REVOKED": "failed",
    }
    mapped_status = STATUS_MAP.get(celery_state, "pending")

    # Redis ilerleme verisi
    progress_percent: Optional[int] = None
    current_step: Optional[str] = None
    anomaly_count: Optional[int] = None
    anomaly_urls: Optional[List[str]] = None

    try:
        r = await _get_redis_client()
        progress_raw = await r.get(f"scan:progress:{task_id}")
        await r.aclose()

        if progress_raw:
            progress_data = json.loads(progress_raw)
            progress_percent = progress_data.get("percent")
            current_step = progress_data.get("step")

            # Hata durumu kontrolü
            if progress_percent == -1:
                mapped_status = "failed"
                progress_percent = 0

            # Extra verilerden anomali sayısı
            extra = progress_data.get("extra", {})
            if extra and "anomaly_count" in extra:
                anomaly_count = extra["anomaly_count"]

    except Exception as exc:
        logger.warning("Redis ilerleme okuma hatası: %s", exc)

    # Tamamlandıysa sonuç verisini kontrol et
    if mapped_status == "complete" and async_result.result:
        task_result = async_result.result
        if isinstance(task_result, dict):
            anomalies = task_result.get("anomalies", [])
            anomaly_count = len(anomalies)
            anomaly_urls = [
                f"/api/v1/anomalies/{a.get('id', 'unknown')}"
                for a in anomalies
                if isinstance(a, dict)
            ]

    return ScanStatusResponse(
        task_id=task_id,
        status=mapped_status,
        progress_percent=progress_percent,
        current_step=current_step,
        anomaly_count=anomaly_count,
        anomaly_urls=anomaly_urls if anomaly_urls else None,
    )


# ═══════════════════════════════════════════════════════════════════════════
# ENDPOINT: GET /anomalies/{id} — Anomali Detayı
# ═══════════════════════════════════════════════════════════════════════════


@router.get(
    "/{anomaly_id}",
    response_model=AnomalyDetail,
    summary="Anomali detayı",
    description=(
        "Belirtilen ID'ye sahip anomalinin tam detayını döndürür. "
        "İlgili görüntüler, doğrulama istatistikleri ve tarihsel zaman serisi özeti dahildir."
    ),
    response_description="Tam anomali detayı (görüntüler, doğrulama, zaman serisi)",
    tags=["anomalies"],
)
async def get_anomaly_detail(
    anomaly_id: str,
    db: AsyncSession = Depends(get_db),
) -> AnomalyDetail:
    """
    Anomali detayını döndürür.

    Yanıt şunları içerir:
    - Temel anomali bilgileri (konum, kategori, skor, vb.)
    - İlişkili tile/uydu görüntüleri
    - Topluluk doğrulama istatistikleri (onay/red oranları)
    - Tarihsel zaman serisi özeti
    """

    # Anomali kaydını getir
    stmt = select(Anomaly).where(Anomaly.id == anomaly_id)
    result = await db.execute(stmt)
    anomaly = result.scalar_one_or_none()

    if anomaly is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Anomali bulunamadı: {anomaly_id}",
        )

    # İlişkili görüntüler
    img_stmt = (
        select(AnomalyImage)
        .where(AnomalyImage.anomaly_id == anomaly_id)
        .order_by(AnomalyImage.captured_at.desc().nullslast())
    )
    img_result = await db.execute(img_stmt)
    images = img_result.scalars().all()

    image_schemas = [
        AnomalyImageSchema(
            id=str(img.id),
            provider=img.provider,
            image_url=img.image_url,
            captured_at=img.captured_at,
            zoom_level=img.zoom_level,
            tile_x=img.tile_x,
            tile_y=img.tile_y,
            tile_z=img.tile_z,
            diff_score=img.diff_score,
            is_blurred=img.is_blurred or False,
        )
        for img in images
    ]

    # Doğrulama istatistikleri
    verif_stmt = (
        select(
            func.count(Verification.id).label("total"),
            func.count(case((Verification.vote == VerificationVote.CONFIRM.value, 1))).label("confirm"),
            func.count(case((Verification.vote == VerificationVote.DENY.value, 1))).label("deny"),
            func.count(case((Verification.vote == VerificationVote.UNCERTAIN.value, 1))).label("uncertain"),
        )
        .where(Verification.anomaly_id == anomaly_id)
    )
    verif_result = await db.execute(verif_stmt)
    verif_row = verif_result.one()

    total_votes = verif_row.total or 0
    confirm_count = verif_row.confirm or 0
    deny_count = verif_row.deny or 0
    uncertain_count = verif_row.uncertain or 0
    confirmation_rate = round((confirm_count / total_votes) * 100, 1) if total_votes > 0 else 0.0

    verification_stats = VerificationStats(
        total_votes=total_votes,
        confirm_count=confirm_count,
        deny_count=deny_count,
        uncertain_count=uncertain_count,
        confirmation_rate=confirmation_rate,
    )

    # Zaman serisi özeti — görüntü tarihlerinden ve meta_data'dan oluşturulur
    time_series: List[TimeSeriesEntry] = []

    # Tespit anı
    if anomaly.detected_at:
        time_series.append(
            TimeSeriesEntry(
                date=anomaly.detected_at.strftime("%Y-%m-%d"),
                confidence_score=anomaly.confidence_score,
                event="Anomali tespit edildi",
            )
        )

    # Görüntü tarihlerinden veri noktaları
    for img in images:
        if img.captured_at:
            time_series.append(
                TimeSeriesEntry(
                    date=img.captured_at.strftime("%Y-%m-%d"),
                    provider_count=1,
                    event=f"{img.provider} görüntüsü yakalandı",
                )
            )

    # Doğrulama tarihi
    if anomaly.verified_at:
        time_series.append(
            TimeSeriesEntry(
                date=anomaly.verified_at.strftime("%Y-%m-%d"),
                confidence_score=anomaly.confidence_score,
                event=f"Durum güncellendi: {anomaly.status}",
            )
        )

    # Kronolojik sırala
    time_series.sort(key=lambda ts: ts.date)

    return AnomalyDetail(
        id=str(anomaly.id),
        lat=anomaly.lat,
        lng=anomaly.lng,
        category=anomaly.category,
        confidence_score=anomaly.confidence_score,
        title=anomaly.title,
        description=anomaly.description,
        status=anomaly.status,
        detected_at=anomaly.detected_at,
        verified_at=anomaly.verified_at,
        source_providers=anomaly.source_providers,
        detection_methods=anomaly.detection_methods,
        meta_data=anomaly.meta_data,
        created_at=anomaly.created_at,
        updated_at=anomaly.updated_at,
        images=image_schemas,
        verification_stats=verification_stats,
        time_series=time_series,
    )
