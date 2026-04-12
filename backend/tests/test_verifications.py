"""
test_verifications.py — Topluluk doğrulama endpoint testleri.

Oy verme, oy değiştirme, güven skoru güncelleme ve
otomatik durum geçişi mantığını test eder.
"""

from __future__ import annotations

import uuid
from unittest.mock import patch, AsyncMock

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import TestAnomaly, TestUser, TestVerification, auth_header


# ═══════════════════════════════════════════════════════════════════════════
# POST /api/v1/anomalies/{id}/verify — Oy Ver
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_verify_anomaly(
    client: AsyncClient, test_anomaly, test_user, user_token
):
    """Anomali için CONFIRM oyu başarıyla kaydedilmeli."""
    response = await client.post(
        f"/api/v1/anomalies/{test_anomaly.id}/verify",
        json={"vote": "CONFIRM", "comment": "Yapı görünüyor."},
        headers=auth_header(user_token),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["vote"] == "CONFIRM"
    assert data["is_update"] is False
    assert "verification_id" in data
    assert "anomaly_status" in data
    assert "new_confidence_score" in data
    assert data["message"] == "Oyunuz kaydedildi."


@pytest.mark.asyncio
async def test_verify_deny(
    client: AsyncClient, test_anomaly, test_user, user_token
):
    """DENY oyu da kaydedilmeli."""
    response = await client.post(
        f"/api/v1/anomalies/{test_anomaly.id}/verify",
        json={"vote": "DENY", "comment": "Yapı yok."},
        headers=auth_header(user_token),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["vote"] == "DENY"


@pytest.mark.asyncio
async def test_verify_uncertain(
    client: AsyncClient, test_anomaly, test_user, user_token
):
    """UNCERTAIN oyu da kaydedilmeli."""
    response = await client.post(
        f"/api/v1/anomalies/{test_anomaly.id}/verify",
        json={"vote": "UNCERTAIN"},
        headers=auth_header(user_token),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["vote"] == "UNCERTAIN"


@pytest.mark.asyncio
async def test_change_vote(
    client: AsyncClient, test_anomaly, test_user, user_token
):
    """Mevcut oy değiştirilebilmeli (is_update=True)."""
    # İlk oy
    await client.post(
        f"/api/v1/anomalies/{test_anomaly.id}/verify",
        json={"vote": "CONFIRM"},
        headers=auth_header(user_token),
    )

    # Oy değiştir
    response = await client.post(
        f"/api/v1/anomalies/{test_anomaly.id}/verify",
        json={"vote": "DENY", "comment": "Fikrimi değiştirdim."},
        headers=auth_header(user_token),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["vote"] == "DENY"
    assert data["is_update"] is True
    assert data["message"] == "Oyunuz güncellendi."


@pytest.mark.asyncio
async def test_verify_without_auth(client: AsyncClient, test_anomaly):
    """Auth olmadan oy verme 401 dönmeli."""
    response = await client.post(
        f"/api/v1/anomalies/{test_anomaly.id}/verify",
        json={"vote": "CONFIRM"},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_verify_nonexistent_anomaly(
    client: AsyncClient, user_token
):
    """Var olmayan anomali için oy verme 404 dönmeli."""
    fake_id = str(uuid.uuid4())
    response = await client.post(
        f"/api/v1/anomalies/{fake_id}/verify",
        json={"vote": "CONFIRM"},
        headers=auth_header(user_token),
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_verify_invalid_vote_type(
    client: AsyncClient, test_anomaly, user_token
):
    """Geçersiz oy tipi 422 dönmeli."""
    response = await client.post(
        f"/api/v1/anomalies/{test_anomaly.id}/verify",
        json={"vote": "INVALID_VOTE"},
        headers=auth_header(user_token),
    )

    assert response.status_code == 422


# ═══════════════════════════════════════════════════════════════════════════
# GET /api/v1/anomalies/{id}/verifications — Oy Özeti
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_get_verifications_empty(
    client: AsyncClient, test_anomaly
):
    """Doğrulama olmayan anomali için boş özet dönmeli."""
    response = await client.get(
        f"/api/v1/anomalies/{test_anomaly.id}/verifications"
    )

    assert response.status_code == 200
    data = response.json()
    assert data["anomaly_id"] == str(test_anomaly.id)
    assert data["total_votes"] == 0
    assert data["confirm_count"] == 0
    assert data["deny_count"] == 0
    assert data["uncertain_count"] == 0
    assert data["verifications"] == []


@pytest.mark.asyncio
async def test_get_verifications_after_voting(
    client: AsyncClient, test_anomaly, test_user, user_token
):
    """Oy verdikten sonra özette görünmeli."""
    # Oy ver
    await client.post(
        f"/api/v1/anomalies/{test_anomaly.id}/verify",
        json={"vote": "CONFIRM", "comment": "Test comment."},
        headers=auth_header(user_token),
    )

    # Özeti kontrol et
    response = await client.get(
        f"/api/v1/anomalies/{test_anomaly.id}/verifications"
    )

    assert response.status_code == 200
    data = response.json()
    assert data["total_votes"] >= 1
    assert data["confirm_count"] >= 1

    # Doğrulama listesinde görünmeli
    assert len(data["verifications"]) >= 1
    verif = data["verifications"][0]
    assert verif["username"] == test_user.username
    assert verif["vote"] == "CONFIRM"
    assert verif["comment"] == "Test comment."
    assert "is_trusted_verifier" in verif
    assert "vote_weight" in verif


@pytest.mark.asyncio
async def test_verifications_nonexistent_anomaly(client: AsyncClient):
    """Var olmayan anomali 404 dönmeli."""
    fake_id = str(uuid.uuid4())
    response = await client.get(
        f"/api/v1/anomalies/{fake_id}/verifications"
    )

    assert response.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════
# Güven Skoru Güncelleme Mantığı
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_confidence_score_updates(
    client: AsyncClient,
    db_session: AsyncSession,
    user_token,
):
    """Oylar sonrası confidence_score güncellenmeli."""
    # Test anomalisi oluştur
    anomaly = TestAnomaly(
        id=str(uuid.uuid4()),
        lat=40.5,
        lng=29.5,
        category="GHOST_BUILDING",
        confidence_score=70.0,
        status="PENDING",
        meta_data={"base_confidence": 70.0},
    )
    db_session.add(anomaly)

    # 4 farklı kullanıcı ile CONFIRM oyları ekle (community_score hesaplaması için)
    from app.services.auth_service import AuthService

    for i in range(4):
        user = TestUser(
            id=str(uuid.uuid4()),
            email=f"voter{i}@test.io",
            username=f"voter_{i}",
            hashed_password=AuthService.hash_password("TestPass1"),
            role="USER",
            trust_score=50.0,
        )
        db_session.add(user)
        await db_session.flush()

        verif = TestVerification(
            id=str(uuid.uuid4()),
            anomaly_id=str(anomaly.id),
            user_id=str(user.id),
            vote="CONFIRM",
        )
        db_session.add(verif)

    await db_session.commit()

    # Şimdi API üzerinden oy ver — skor yeniden hesaplanacak
    response = await client.post(
        f"/api/v1/anomalies/{anomaly.id}/verify",
        json={"vote": "CONFIRM"},
        headers=auth_header(user_token),
    )

    assert response.status_code == 200
    data = response.json()

    # 5 CONFIRM oy (4 + 1 yeni) → total_effective=5, 3-9 aralığı
    # community_score = 1.0 × 8 = 8.0
    # final = 70.0 + 8.0 = 78.0
    assert data["new_confidence_score"] > 70.0


@pytest.mark.asyncio
async def test_community_score_structure(
    client: AsyncClient, test_anomaly, test_user, user_token
):
    """Doğrulama özeti community_score alanlarını içermeli."""
    # Oy ver
    await client.post(
        f"/api/v1/anomalies/{test_anomaly.id}/verify",
        json={"vote": "CONFIRM"},
        headers=auth_header(user_token),
    )

    response = await client.get(
        f"/api/v1/anomalies/{test_anomaly.id}/verifications"
    )
    data = response.json()

    assert "community_score" in data
    assert "confirm_ratio" in data
    assert "weighted_confirm_count" in data
    assert "weighted_deny_count" in data
    assert "base_confidence" in data
    assert "final_confidence" in data
