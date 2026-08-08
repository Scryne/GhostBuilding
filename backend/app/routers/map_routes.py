"""
map_routes.py — Harita istihbarat operasyonları.

Reverse geocoding, bölge istatistikleri ve tile proxy
endpoint'lerini sağlar.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.session import get_db
from app.models.anomaly import Anomaly

logger = logging.getLogger(__name__)

router = APIRouter()


# ═══════════════════════════════════════════════════════════════════════════
# Schemas
# ═══════════════════════════════════════════════════════════════════════════


class ReverseGeocodeResponse(BaseModel):
    """Reverse geocoding yanıtı."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "lat": 41.0082,
                "lng": 28.9784,
                "display_name": "Fatih, İstanbul, Türkiye",
                "country": "Türkiye",
                "country_code": "tr",
                "city": "İstanbul",
                "state": "İstanbul",
            }
        }
    )

    lat: float = Field(..., description="Sorgu enlemi")
    lng: float = Field(..., description="Sorgu boylamı")
    display_name: Optional[str] = Field(None, description="Tam adres")
    country: Optional[str] = Field(None, description="Ülke adı")
    country_code: Optional[str] = Field(None, description="Ülke kodu (ISO 3166)")
    city: Optional[str] = Field(None, description="Şehir")
    state: Optional[str] = Field(None, description="Bölge/Eyalet")


class GeoSearchResult(BaseModel):
    """Geocoding arama sonucu."""

    display_name: str = Field(..., description="Tam adres")
    lat: float = Field(..., description="Enlem")
    lng: float = Field(..., description="Boylam")
    place_type: Optional[str] = Field(None, description="Yer tipi")
    importance: Optional[float] = Field(None, description="Önem derecesi")


class RegionStatItem(BaseModel):
    """Bölge istatistik satırı."""

    region: str = Field(..., description="Ülke/bölge adı")
    total_count: int = Field(0, description="Toplam anomali sayısı")
    verified_count: int = Field(0, description="Doğrulanmış anomali sayısı")
    avg_confidence: float = Field(0.0, description="Ortalama güven skoru")


class RegionStatsResponse(BaseModel):
    """Bölge bazında istatistik yanıtı."""

    regions: List[RegionStatItem] = Field(default_factory=list)
    total_regions: int = Field(0, description="Toplam bölge sayısı")


# ═══════════════════════════════════════════════════════════════════════════
# ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════


@router.get("/", tags=["maps"])
def get_maps():
    """Harita API durumu."""
    return {
        "status": "ok",
        "providers": ["OSM", "GOOGLE", "SENTINEL"],
        "features": ["reverse-geocode", "search", "region-stats"],
    }


@router.get(
    "/reverse-geocode",
    response_model=ReverseGeocodeResponse,
    summary="Reverse geocoding",
    description="Koordinattan adres bilgisi döndürür (Nominatim OSM).",
    tags=["maps"],
)
async def reverse_geocode(
    lat: float = Query(..., description="Enlem", ge=-90.0, le=90.0),
    lng: float = Query(..., description="Boylam", ge=-180.0, le=180.0),
) -> ReverseGeocodeResponse:
    """
    Nominatim API ile koordinattan adres bilgisi alır.
    Rate limit: 1 req/sec (Nominatim usage policy'ye uygun).
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://nominatim.openstreetmap.org/reverse",
                params={
                    "lat": lat,
                    "lon": lng,
                    "format": "json",
                    "addressdetails": 1,
                    "accept-language": "en",
                },
                headers={
                    "User-Agent": "GhostBuilding/1.0 (https://ghostbuilding.dev)",
                },
            )
            resp.raise_for_status()
            data = resp.json()

        address = data.get("address", {})

        return ReverseGeocodeResponse(
            lat=lat,
            lng=lng,
            display_name=data.get("display_name"),
            country=address.get("country"),
            country_code=address.get("country_code"),
            city=address.get("city") or address.get("town") or address.get("village"),
            state=address.get("state"),
        )

    except httpx.HTTPStatusError as exc:
        logger.warning("Nominatim HTTP hatası: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Geocoding servisi yanıt vermedi.",
        )
    except Exception as exc:
        logger.error("Reverse geocode hatası: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Geocoding hatası: {str(exc)}",
        )


@router.get(
    "/search",
    response_model=List[GeoSearchResult],
    summary="Yer arama (geocoding)",
    description="Metin tabanlı yer arama — Nominatim OSM kullanır.",
    tags=["maps"],
)
async def geo_search(
    q: str = Query(..., description="Arama sorgusu", min_length=2, max_length=200),
    limit: int = Query(5, description="Maksimum sonuç sayısı", ge=1, le=10),
) -> List[GeoSearchResult]:
    """
    Nominatim API ile metin tabanlı yer arama.
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://nominatim.openstreetmap.org/search",
                params={
                    "q": q,
                    "format": "json",
                    "limit": limit,
                    "addressdetails": 0,
                },
                headers={
                    "User-Agent": "GhostBuilding/1.0 (https://ghostbuilding.dev)",
                },
            )
            resp.raise_for_status()
            results = resp.json()

        return [
            GeoSearchResult(
                display_name=r.get("display_name", ""),
                lat=float(r.get("lat", 0)),
                lng=float(r.get("lon", 0)),
                place_type=r.get("type"),
                importance=float(r.get("importance", 0)) if r.get("importance") else None,
            )
            for r in results
        ]

    except Exception as exc:
        logger.error("Geo arama hatası: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Arama hatası: {str(exc)}",
        )


@router.get(
    "/region-stats",
    response_model=RegionStatsResponse,
    summary="Bölge bazında istatistikler",
    description="Anomalilerin ülke/bölge bazında dağılım istatistiklerini döndürür.",
    tags=["maps"],
)
async def region_stats(
    db: AsyncSession = Depends(get_db),
) -> RegionStatsResponse:
    """
    meta_data JSONB alanından country/region bilgisini çıkararak
    bölge bazında anomali istatistiklerini hesaplar.
    """
    stmt = select(
        func.coalesce(
            Anomaly.meta_data.op("->>")(  "country"),
            Anomaly.meta_data.op("->>")("region"),
            text("'Unknown'"),
        ).label("region"),
        func.count(Anomaly.id).label("total_count"),
        func.count(
            func.nullif(Anomaly.status, "PENDING")
        ).label("verified_count"),
        func.round(func.avg(Anomaly.confidence_score), 1).label("avg_confidence"),
    ).group_by(text("region")).order_by(func.count(Anomaly.id).desc()).limit(100)

    result = await db.execute(stmt)
    rows = result.all()

    regions = [
        RegionStatItem(
            region=row.region,
            total_count=row.total_count,
            verified_count=row.verified_count or 0,
            avg_confidence=float(row.avg_confidence or 0),
        )
        for row in rows
    ]

    return RegionStatsResponse(
        regions=regions,
        total_regions=len(regions),
    )
