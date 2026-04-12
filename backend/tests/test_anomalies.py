"""
test_anomalies.py — Anomali endpoint testleri.

Liste, detay, scan, rate limit ve stats endpoint'lerini test eder.
PostGIS mekansal sorgulamalar mock'lanmıştır.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import TestAnomaly, TestAnomalyImage, auth_header


# ═══════════════════════════════════════════════════════════════════════════
# GET /api/v1/anomalies — Anomali Listesi
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_list_anomalies_empty(client: AsyncClient):
    """Boş veritabanında anomali listesi boş dönmeli."""
    response = await client.get("/api/v1/anomalies/")

    assert response.status_code == 200
    data = response.json()
    assert data["data"] == []
    assert data["pagination"]["total"] == 0


@pytest.mark.asyncio
async def test_list_anomalies_with_data(client: AsyncClient, test_anomaly):
    """Anomali varken listede görünmeli."""
    response = await client.get("/api/v1/anomalies/?min_confidence=0")

    assert response.status_code == 200
    data = response.json()
    assert data["pagination"]["total"] >= 1
    assert len(data["data"]) >= 1

    item = data["data"][0]
    assert "id" in item
    assert "lat" in item
    assert "lng" in item
    assert "category" in item
    assert "confidence_score" in item
    assert "status" in item


@pytest.mark.asyncio
async def test_list_anomalies_with_filters(
    client: AsyncClient, test_anomaly, db_session: AsyncSession
):
    """Kategori ve confidence filtresi çalışmalı."""
    # GHOST_BUILDING filtresi
    response = await client.get(
        "/api/v1/anomalies/?category=GHOST_BUILDING&min_confidence=0"
    )
    assert response.status_code == 200
    data = response.json()
    for item in data["data"]:
        assert item["category"] == "GHOST_BUILDING"

    # Yüksek min_confidence — mevcut anomali'yi filtrelemeli
    response2 = await client.get("/api/v1/anomalies/?min_confidence=99")
    assert response2.status_code == 200
    data2 = response2.json()
    assert data2["pagination"]["total"] == 0


@pytest.mark.asyncio
async def test_list_anomalies_status_filter(
    client: AsyncClient, test_anomaly
):
    """Status filtresi çalışmalı."""
    # PENDING — test_anomaly PENDING durumunda
    response = await client.get(
        "/api/v1/anomalies/?status=PENDING&min_confidence=0"
    )
    assert response.status_code == 200
    data = response.json()
    assert data["pagination"]["total"] >= 1

    # VERIFIED — henüz doğrulanmış yok
    response2 = await client.get(
        "/api/v1/anomalies/?status=VERIFIED&min_confidence=0"
    )
    data2 = response2.json()
    assert data2["pagination"]["total"] == 0


@pytest.mark.asyncio
async def test_list_anomalies_pagination(
    client: AsyncClient, db_session: AsyncSession
):
    """Sayfalama parametreleri doğru çalışmalı."""
    # 5 anomali oluştur
    for i in range(5):
        anomaly = TestAnomaly(
            id=str(uuid.uuid4()),
            lat=40.0 + i * 0.1,
            lng=29.0 + i * 0.1,
            category="GHOST_BUILDING",
            confidence_score=50.0 + i,
            title=f"Pagination Test {i}",
            status="PENDING",
        )
        db_session.add(anomaly)
    await db_session.commit()

    # Sayfa 1, limit 2
    response = await client.get(
        "/api/v1/anomalies/?page=1&limit=2&min_confidence=0"
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["data"]) == 2
    assert data["pagination"]["page"] == 1
    assert data["pagination"]["limit"] == 2
    assert data["pagination"]["total"] >= 5


# ═══════════════════════════════════════════════════════════════════════════
# GET /api/v1/anomalies/{id} — Detay
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_get_anomaly_detail(client: AsyncClient, test_anomaly):
    """Anomali detayı doğru dönmeli."""
    response = await client.get(f"/api/v1/anomalies/{test_anomaly.id}")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(test_anomaly.id)
    assert data["lat"] == test_anomaly.lat
    assert data["lng"] == test_anomaly.lng
    assert data["category"] == "GHOST_BUILDING"
    assert "images" in data
    assert "verification_stats" in data
    assert "time_series" in data


@pytest.mark.asyncio
async def test_get_anomaly_not_found(client: AsyncClient):
    """Var olmayan anomali 404 dönmeli."""
    fake_id = str(uuid.uuid4())
    response = await client.get(f"/api/v1/anomalies/{fake_id}")

    assert response.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════
# POST /api/v1/anomalies/scan
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_scan_coordinate_returns_task_id(
    client: AsyncClient, mock_celery, user_token
):
    """Scan isteği task_id ve status_url dönmeli."""
    response = await client.post(
        "/api/v1/anomalies/scan",
        json={"lat": 41.0082, "lng": 28.9784, "zoom": 15, "radius_km": 5.0},
        headers=auth_header(user_token),
    )

    # scan endpoint auth gerektirmiyor olabilir — 200 veya 201
    assert response.status_code in (200, 201, 202)

    data = response.json()
    assert "task_id" in data
    assert "status_url" in data
    assert "estimated_seconds" in data


@pytest.mark.asyncio
async def test_scan_invalid_coordinates(client: AsyncClient, user_token):
    """Geçersiz koordinat 422 dönmeli."""
    response = await client.post(
        "/api/v1/anomalies/scan",
        json={"lat": 999.0, "lng": 28.9784},
        headers=auth_header(user_token),
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_scan_rate_limit(client: AsyncClient, user_token):
    """
    Rate limit aşıldığında 429 dönmeli.

    Redis mock'ı rate limit count'unu 5+ olarak döndürür.
    """
    # Redis'in rate limit sayısını 5 olarak döndürmesini sağla
    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value="5")  # 5 = limit'te
    mock_redis.ttl = AsyncMock(return_value=1800)
    mock_redis.aclose = AsyncMock()

    with patch(
        "app.routers.anomalies._get_redis_client",
        return_value=mock_redis,
    ):
        response = await client.post(
            "/api/v1/anomalies/scan",
            json={"lat": 41.0082, "lng": 28.9784},
        )

    assert response.status_code == 429
    data = response.json()
    assert "retry_after_seconds" in data["detail"]


# ═══════════════════════════════════════════════════════════════════════════
# GET /api/v1/anomalies/stats
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_get_stats(client: AsyncClient, test_anomaly):
    """İstatistikler doğru dönmeli."""
    response = await client.get("/api/v1/anomalies/stats")

    assert response.status_code == 200
    data = response.json()
    assert "total_count" in data
    assert "by_category" in data
    assert "last_30_days_count" in data
    assert "top_10" in data
    assert "region_distribution" in data
    assert data["total_count"] >= 1


@pytest.mark.asyncio
async def test_stats_category_breakdown(
    client: AsyncClient, db_session: AsyncSession
):
    """Kategori bazlı istatistikler doğru olmalı."""
    # Farklı kategorilerde anomali ekle
    for cat in ["GHOST_BUILDING", "CENSORED_AREA", "CENSORED_AREA"]:
        a = TestAnomaly(
            id=str(uuid.uuid4()),
            lat=41.0,
            lng=28.0,
            category=cat,
            confidence_score=60.0,
            status="PENDING",
        )
        db_session.add(a)
    await db_session.commit()

    response = await client.get("/api/v1/anomalies/stats")
    data = response.json()

    categories = {item["category"]: item["count"] for item in data["by_category"]}
    assert "CENSORED_AREA" in categories
    assert categories["CENSORED_AREA"] >= 2


# ═══════════════════════════════════════════════════════════════════════════
# GET /api/v1/anomalies/tiles/compare
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_tile_compare(client: AsyncClient):
    """Tile karşılaştırma endpoint'i mock tile verisiyle çalışmalı."""
    # TileFetcher'ı mock'la
    from PIL import Image

    mock_img = Image.new("RGB", (256, 256), color=(128, 128, 128))

    mock_fetcher = AsyncMock()
    mock_fetcher.fetch_all_providers = AsyncMock(
        return_value={"osm": mock_img, "google": mock_img}
    )
    mock_fetcher.__aenter__ = AsyncMock(return_value=mock_fetcher)
    mock_fetcher.__aexit__ = AsyncMock(return_value=False)

    # PixelDiffAnalyzer'ı mock'la
    mock_diff = MagicMock()
    mock_diff.compute_diff = MagicMock(
        return_value=MagicMock(
            diff_score=12.5,
            structural_similarity=0.87,
        )
    )

    with patch(
        "app.routers.anomalies.TileFetcher",
        return_value=mock_fetcher,
        create=True, # In case it's not directly imported over there
    ), patch(
        "app.routers.anomalies.PixelDiffAnalyzer",
        return_value=mock_diff,
        create=True,
    ):
        response = await client.get(
            "/api/v1/anomalies/tiles/compare?lat=41.0082&lng=28.9784&zoom=15"
        )

    assert response.status_code == 200
    data = response.json()
    assert "tile_coords" in data
    assert "provider_images" in data
    assert "diff_scores" in data
    assert "anomaly_indicators" in data
