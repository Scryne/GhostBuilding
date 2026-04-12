"""
test_auth.py — Kimlik doğrulama endpoint testleri.

Register, login, refresh, logout ve profil endpoint'lerini
test eder. Tüm harici bağımlılıklar mock'lanmıştır.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import AsyncClient

from tests.conftest import auth_header


# ═══════════════════════════════════════════════════════════════════════════
# POST /api/v1/auth/register
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_register_success(client: AsyncClient):
    """Yeni kullanıcı kaydı başarılı olmalı."""
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "newuser@ghostbuilding.io",
            "username": "new_ghost",
            "password": "SecurePass1",
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "newuser@ghostbuilding.io"
    assert data["username"] == "new_ghost"
    assert data["role"] == "USER"
    assert "id" in data
    assert "message" in data


@pytest.mark.asyncio
async def test_register_duplicate_email(client: AsyncClient, test_user):
    """Mevcut email ile kayıt 409 dönmeli."""
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": test_user.email,
            "username": "another_user",
            "password": "SecurePass1",
        },
    )

    assert response.status_code == 409
    data = response.json()
    assert data["detail"]["error"] == "email_already_exists"


@pytest.mark.asyncio
async def test_register_duplicate_username(client: AsyncClient, test_user):
    """Mevcut kullanıcı adı ile kayıt 409 dönmeli."""
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "unique@ghostbuilding.io",
            "username": test_user.username,
            "password": "SecurePass1",
        },
    )

    assert response.status_code == 409
    data = response.json()
    assert data["detail"]["error"] == "username_already_exists"


@pytest.mark.asyncio
async def test_register_weak_password(client: AsyncClient):
    """Zayıf şifre (rakam yok) 422 dönmeli."""
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "weakpass@ghostbuilding.io",
            "username": "weak_user",
            "password": "nodigits",
        },
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_register_invalid_username(client: AsyncClient):
    """Geçersiz kullanıcı adı (özel karakter) 422 dönmeli."""
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "invalid@ghostbuilding.io",
            "username": "invalid user!",
            "password": "SecurePass1",
        },
    )

    assert response.status_code == 422


# ═══════════════════════════════════════════════════════════════════════════
# POST /api/v1/auth/login
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient, test_user):
    """Doğru kimlik bilgileri ile giriş başarılı olmalı."""
    response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": test_user.email,
            "password": "TestPass1",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"
    assert data["expires_in"] == 3600


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient, test_user):
    """Yanlış şifre 401 dönmeli."""
    response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": test_user.email,
            "password": "WrongPassword1",
        },
    )

    assert response.status_code == 401
    data = response.json()
    assert data["detail"]["error"] == "invalid_credentials"


@pytest.mark.asyncio
async def test_login_nonexistent_email(client: AsyncClient):
    """Var olmayan email 401 dönmeli."""
    response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "nonexistent@ghostbuilding.io",
            "password": "SomePass1",
        },
    )

    assert response.status_code == 401


# ═══════════════════════════════════════════════════════════════════════════
# POST /api/v1/auth/refresh
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_token_refresh(client: AsyncClient, test_user):
    """Geçerli refresh token ile yeni access token alınabilmeli."""
    # Önce login yap
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": test_user.email, "password": "TestPass1"},
    )
    tokens = login_resp.json()

    # Refresh
    response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )

    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["expires_in"] == 3600


@pytest.mark.asyncio
async def test_refresh_with_access_token_fails(client: AsyncClient, user_token):
    """Access token ile refresh 401 dönmeli (yanlış tip)."""
    response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": user_token},
    )

    assert response.status_code == 401
    data = response.json()
    assert data["detail"]["error"] == "invalid_token_type"


# ═══════════════════════════════════════════════════════════════════════════
# GET /api/v1/auth/me — Korumalı Endpoint
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_protected_route_without_token(client: AsyncClient):
    """Token olmadan korumalı endpoint 401 dönmeli."""
    response = await client.get("/api/v1/auth/me")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_profile(client: AsyncClient, test_user, user_token):
    """Geçerli token ile profil alınabilmeli."""
    response = await client.get(
        "/api/v1/auth/me",
        headers=auth_header(user_token),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["email"] == test_user.email
    assert data["username"] == test_user.username
    assert data["role"] == "USER"
    assert "trust_score" in data


@pytest.mark.asyncio
async def test_get_profile_with_invalid_token(client: AsyncClient):
    """Geçersiz token ile profil isteği 401 dönmeli."""
    response = await client.get(
        "/api/v1/auth/me",
        headers=auth_header("invalid.token.here"),
    )

    assert response.status_code == 401


# ═══════════════════════════════════════════════════════════════════════════
# PATCH /api/v1/auth/me — Profil Güncelleme
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_update_username(client: AsyncClient, test_user, user_token):
    """Kullanıcı adı güncellenebilmeli."""
    response = await client.patch(
        "/api/v1/auth/me",
        headers=auth_header(user_token),
        json={"username": "updated_ghost"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["username"] == "updated_ghost"


@pytest.mark.asyncio
async def test_update_password(client: AsyncClient, test_user, user_token):
    """Şifre doğru bilgilerle değiştirilebilmeli."""
    response = await client.patch(
        "/api/v1/auth/me",
        headers=auth_header(user_token),
        json={
            "current_password": "TestPass1",
            "new_password": "NewSecure2",
        },
    )

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_update_password_wrong_current(client: AsyncClient, test_user, user_token):
    """Yanlış mevcut şifre ile değiştirme 401 dönmeli."""
    response = await client.patch(
        "/api/v1/auth/me",
        headers=auth_header(user_token),
        json={
            "current_password": "WrongCurrent1",
            "new_password": "NewSecure2",
        },
    )

    assert response.status_code == 401
