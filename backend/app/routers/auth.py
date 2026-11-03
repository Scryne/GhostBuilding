"""
auth.py — GhostBuilding kimlik doğrulama endpoint'leri.

JWT tabanlı register, login, refresh, logout ve profil yönetimi
endpoint'lerini sağlar. Tüm response'lar Pydantic v2 schema kullanır.

E-posta akışları (SMTP, bkz. app/services/email_service.py):
- POST /auth/verify-email          — doğrulama (süresi dolmuş / geçersiz ayrı kodlarla; GET de var)
- POST /auth/resend-verification   — yeniden gönder (hesap varlığını sızdırmaz)
- POST /auth/forgot-password       — sıfırlama bağlantısı (hesap varlığını sızdırmaz)
- POST /auth/reset-password        — tek kullanımlık token ile yeni şifre; eski oturumlar düşer

Güvenlik:
- Bcrypt şifre hashing
- Brute force koruması (5 başarısız → 15 dk blok)
- Token blacklist (logout)
- Rol tabanlı yetkilendirme (USER / MODERATOR / ADMIN)
"""

from __future__ import annotations

import hmac
import logging
import re
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field, ConfigDict, field_validator
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.user import User
from app.models.enums import UserRole
from app.services import email_service
from app.services.auth_service import (
    EMAIL_VERIFY_AUDIENCE,
    PASSWORD_RESET_AUDIENCE,
    PurposeTokenError,
    auth_service,
    get_current_user,
    oauth2_scheme,
    session_revoked,
)
from app.utils.sanitizer import validate_safe_string

logger = logging.getLogger(__name__)

router = APIRouter()

# ═══════════════════════════════════════════════════════════════════════════
# Pydantic v2 Schemas
# ═══════════════════════════════════════════════════════════════════════════

# ---------------------------------------------------------------------------
# Register
# ---------------------------------------------------------------------------


class RegisterRequest(BaseModel):
    """POST /auth/register — Kayıt isteği."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "email": "user@ghostbuilding.io",
                "username": "ghost_hunter",
                "password": "SecurePass1",
            }
        }
    )

    email: EmailStr = Field(..., description="Email adresi")
    username: str = Field(
        ...,
        description="Kullanıcı adı (3–30 karakter, alfanümerik ve alt çizgi)",
        min_length=3,
        max_length=30,
    )
    password: str = Field(
        ...,
        description="Şifre (min 8 karakter, en az 1 büyük harf, 1 rakam)",
        min_length=8,
        max_length=128,
    )

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        """Kullanıcı adı formatını doğrular ve XSS kontrolü yapar."""
        if not re.match(r"^[a-zA-Z0-9_]+$", v):
            raise ValueError(
                "Kullanıcı adı sadece harf, rakam ve alt çizgi içerebilir."
            )
        validate_safe_string(v, "Kullanıcı adı")
        return v


class RegisterResponse(BaseModel):
    """POST /auth/register — Kayıt yanıtı."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                "email": "user@ghostbuilding.io",
                "username": "ghost_hunter",
                "role": "USER",
                "message": "Kayıt başarılı. Doğrulama bağlantısı e-posta adresinize gönderiliyor.",
                "email_delivery": "enabled",
            }
        }
    )

    id: str = Field(..., description="Kullanıcı UUID")
    email: str = Field(..., description="Email adresi")
    username: str = Field(..., description="Kullanıcı adı")
    role: str = Field(..., description="Atanan rol")
    message: str = Field(..., description="Bilgi mesajı")
    email_delivery: str = Field(
        "enabled",
        description="Sunucuda e-posta gönderimi açık mı: 'enabled' | 'disabled'",
    )


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------


class LoginRequest(BaseModel):
    """POST /auth/login — Giriş isteği."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "email": "user@ghostbuilding.io",
                "password": "SecurePass1",
            }
        }
    )

    email: EmailStr = Field(..., description="Email adresi")
    password: str = Field(..., description="Şifre")


class TokenResponse(BaseModel):
    """POST /auth/login & /auth/refresh — Token yanıtı."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "access_token": "eyJhbGciOiJIUzI1NiIs...",
                "refresh_token": "eyJhbGciOiJIUzI1NiIs...",
                "token_type": "bearer",
                "expires_in": 3600,
            }
        }
    )

    access_token: str = Field(..., description="JWT access token")
    refresh_token: Optional[str] = Field(None, description="JWT refresh token")
    token_type: str = Field("bearer", description="Token tipi")
    expires_in: int = Field(..., description="Access token geçerlilik süresi (saniye)")


# ---------------------------------------------------------------------------
# Refresh
# ---------------------------------------------------------------------------


class RefreshRequest(BaseModel):
    """POST /auth/refresh — Token yenileme isteği."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "refresh_token": "eyJhbGciOiJIUzI1NiIs...",
            }
        }
    )

    refresh_token: str = Field(..., description="Mevcut refresh token")


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------


class LogoutRequest(BaseModel):
    """POST /auth/logout — Çıkış isteği."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "refresh_token": "eyJhbGciOiJIUzI1NiIs...",
            }
        }
    )

    refresh_token: Optional[str] = Field(
        None, description="Varsa refresh token da iptal edilir"
    )


class MessageResponse(BaseModel):
    """Genel bilgi mesajı yanıtı."""

    message: str = Field(..., description="Bilgi mesajı")


# ---------------------------------------------------------------------------
# E-posta doğrulama / şifre sıfırlama
# ---------------------------------------------------------------------------


class VerifyEmailResponse(BaseModel):
    """GET /auth/verify-email — Doğrulama sonucu."""

    status: str = Field(..., description="'verified' | 'already_verified'")
    message: str = Field(..., description="Bilgi mesajı")


class VerifyEmailRequest(BaseModel):
    """POST /auth/verify-email — Doğrulama token'ı."""

    token: str = Field(..., min_length=1, max_length=2048, description="E-postadaki doğrulama token'ı")


class ResendVerificationRequest(BaseModel):
    """POST /auth/resend-verification — e-posta adresi YA DA süresi dolmuş bağlantının token'ı."""

    email: Optional[EmailStr] = Field(None, description="Hesabın e-posta adresi")
    token: Optional[str] = Field(
        None,
        description="Süresi dolmuş doğrulama bağlantısındaki token (imzası yine doğrulanır)",
        max_length=2048,
    )


class ForgotPasswordRequest(BaseModel):
    """POST /auth/forgot-password — Sıfırlama bağlantısı isteği."""

    email: EmailStr = Field(..., description="Hesabın e-posta adresi")


class ResetPasswordRequest(BaseModel):
    """POST /auth/reset-password — Yeni şifre."""

    token: str = Field(..., min_length=1, max_length=2048, description="E-postadaki sıfırlama token'ı")
    new_password: str = Field(..., min_length=8, max_length=128, description="Yeni şifre")


# ---------------------------------------------------------------------------
# User Profile
# ---------------------------------------------------------------------------


class UserProfileResponse(BaseModel):
    """GET /auth/me — Kullanıcı profil yanıtı."""

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                "email": "user@ghostbuilding.io",
                "username": "ghost_hunter",
                "role": "USER",
                "trust_score": 50.0,
                "verified_count": 12,
                "submitted_count": 3,
                "is_active": True,
                "is_verified": False,
                "created_at": "2026-04-12T10:30:00Z",
            }
        },
    )

    id: str = Field(..., description="Kullanıcı UUID")
    email: str = Field(..., description="Email adresi")
    username: str = Field(..., description="Kullanıcı adı")
    role: str = Field(..., description="Kullanıcı rolü")
    trust_score: float = Field(..., description="Güvenilirlik skoru")
    verified_count: int = Field(..., description="Doğruladığı anomali sayısı")
    submitted_count: int = Field(..., description="Gönderdiği rapor sayısı")
    is_active: bool = Field(True, description="Hesap aktif mi")
    is_verified: bool = Field(False, description="Email doğrulanmış mı")
    created_at: Optional[datetime] = Field(None, description="Kayıt tarihi")


class ProfileUpdateRequest(BaseModel):
    """PATCH /auth/me — Profil güncelleme isteği."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "username": "new_username",
                "current_password": "OldPass1",
                "new_password": "NewSecure2",
            }
        }
    )

    username: Optional[str] = Field(
        None,
        description="Yeni kullanıcı adı",
        min_length=3,
        max_length=30,
    )
    current_password: Optional[str] = Field(
        None, description="Mevcut şifre (şifre değişikliği için zorunlu)"
    )
    new_password: Optional[str] = Field(
        None,
        description="Yeni şifre (min 8 karakter, 1 büyük harf, 1 rakam)",
        min_length=8,
        max_length=128,
    )

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not re.match(r"^[a-zA-Z0-9_]+$", v):
            raise ValueError(
                "Kullanıcı adı sadece harf, rakam ve alt çizgi içerebilir."
            )
        if v is not None:
            validate_safe_string(v, "Kullanıcı adı")
        return v


# ═══════════════════════════════════════════════════════════════════════════
# ENDPOINT: POST /auth/register — Kayıt
# ═══════════════════════════════════════════════════════════════════════════


@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Yeni kullanıcı kaydı",
    description=(
        "Email, kullanıcı adı ve şifre ile yeni bir hesap oluşturur. "
        "Şifre bcrypt ile hash'lenir. E-posta gönderimi açıksa doğrulama bağlantısı "
        "arka planda gönderilir; kapalıysa yanıt bunu `email_delivery: disabled` ile söyler."
    ),
    response_description="Oluşturulan kullanıcı bilgisi ve doğrulama mesajı",
    tags=["auth"],
)
async def register(
    body: RegisterRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> RegisterResponse:
    """
    Yeni kullanıcı kaydı oluşturur.

    1. Şifre kurallarını doğrular (min 8 karakter, 1 büyük, 1 rakam)
    2. Email ve kullanıcı adı benzersizliğini kontrol eder
    3. Şifreyi bcrypt ile hash'ler
    4. Kullanıcıyı veritabanına ekler
    5. E-posta doğrulama bağlantısını arka planda gönderir (gönderim kapalıysa söyler)
    """

    # Şifre kurallarını doğrula
    auth_service.validate_password(body.password)

    # Email benzersizlik kontrolü
    email_stmt = select(User).where(User.email == body.email.lower())
    email_result = await db.execute(email_stmt)
    if email_result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "email_already_exists",
                "message": "Bu email adresi zaten kullanılıyor.",
            },
        )

    # Kullanıcı adı benzersizlik kontrolü
    username_stmt = select(User).where(User.username == body.username)
    username_result = await db.execute(username_stmt)
    if username_result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "username_already_exists",
                "message": "Bu kullanıcı adı zaten kullanılıyor.",
            },
        )

    # Şifreyi hash'le
    hashed = auth_service.hash_password(body.password)

    # Yeni kullanıcı oluştur
    new_user = User(
        email=body.email.lower(),
        username=body.username,
        hashed_password=hashed,
        role=UserRole.USER.value,
        is_active=True,
        is_verified=False,
    )

    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    # E-posta doğrulama — yanıtı SMTP'ye bekletmemek için arka planda
    if email_service.email_enabled():
        background_tasks.add_task(
            auth_service.send_verification_email,
            email=new_user.email,
            user_id=str(new_user.id),
        )
        delivery = "enabled"
        message = "Kayıt başarılı. Doğrulama bağlantısı e-posta adresinize gönderiliyor."
    else:
        delivery = "disabled"
        message = (
            "Kayıt başarılı. E-posta gönderimi bu sunucuda kapalı olduğu için "
            "doğrulama bağlantısı gönderilemedi."
        )

    # Log'a kişisel veri (e-posta) yazılmaz; kimlik yeterli
    logger.info("Yeni kullanıcı kaydedildi: id=%s e-posta_gönderimi=%s", new_user.id, delivery)

    return RegisterResponse(
        id=str(new_user.id),
        email=new_user.email,
        username=new_user.username,
        role=new_user.role,
        message=message,
        email_delivery=delivery,
    )


# ═══════════════════════════════════════════════════════════════════════════
# ENDPOINT: GET /auth/verify-email — Email Doğrulama
# ═══════════════════════════════════════════════════════════════════════════


def _email_disabled_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={
            "error": "email_disabled",
            "message": "E-posta gönderimi bu sunucuda kapalı; bu işlem şu an yapılamıyor.",
        },
    )


def _token_error(reason: str, *, purpose: str) -> HTTPException:
    if reason == "expired":
        message = (
            "Doğrulama bağlantısının süresi dolmuş."
            if purpose == "verify"
            else "Şifre sıfırlama bağlantısının süresi dolmuş."
        )
        return HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "token_expired", "message": message},
        )
    message = (
        "Doğrulama bağlantısı geçersiz."
        if purpose == "verify"
        else "Şifre sıfırlama bağlantısı geçersiz ya da daha önce kullanılmış."
    )
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={"error": "invalid_token", "message": message},
    )


async def _get_user_by_id(db: AsyncSession, user_id: Optional[str]) -> Optional[User]:
    if not user_id:
        return None
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def _get_user_by_email(db: AsyncSession, email: str) -> Optional[User]:
    result = await db.execute(select(User).where(User.email == email.lower()))
    return result.scalar_one_or_none()


async def _apply_email_verification(token: str, db: AsyncSession) -> VerifyEmailResponse:
    """Doğrulama idempotenttir: aynı bağlantı ikinci kez açılırsa ``already_verified`` döner."""
    try:
        payload = auth_service.decode_purpose_token(token, EMAIL_VERIFY_AUDIENCE)
    except PurposeTokenError as exc:
        raise _token_error(exc.reason, purpose="verify") from exc

    user = await _get_user_by_id(db, payload.get("sub"))
    if user is None or not getattr(user, "is_active", True):
        raise _token_error("invalid", purpose="verify")

    if user.is_verified:
        return VerifyEmailResponse(
            status="already_verified",
            message="E-posta adresiniz zaten doğrulanmış.",
        )

    user.is_verified = True
    await db.commit()
    logger.info("Email doğrulandı: user_id=%s", user.id)

    return VerifyEmailResponse(status="verified", message="E-posta adresiniz doğrulandı.")


@router.post(
    "/verify-email",
    response_model=VerifyEmailResponse,
    summary="Email doğrulama",
    description=(
        "E-postadaki doğrulama token'ı ile adresi doğrular (token gövdede: erişim log'larına "
        "düşmez). Token imzalıdır ve EMAIL_VERIFY_TOKEN_HOURS (varsayılan 24) saat geçerlidir. "
        "Süresi dolmuş token `token_expired`, bozuk/başka amaçlı token `invalid_token` döner."
    ),
    response_description="Doğrulama sonucu",
    tags=["auth"],
)
async def verify_email_post(
    body: VerifyEmailRequest,
    db: AsyncSession = Depends(get_db),
) -> VerifyEmailResponse:
    return await _apply_email_verification(body.token, db)


@router.get(
    "/verify-email",
    response_model=VerifyEmailResponse,
    summary="Email doğrulama (sorgu parametresiyle)",
    description=(
        "POST ile aynı işlem; eski istemciler için korunur. Token sorgu dizesinde olduğundan "
        "vekil sunucu log'larına düşebilir — yeni istemciler POST kullanmalı."
    ),
    response_description="Doğrulama sonucu",
    tags=["auth"],
)
async def verify_email(
    token: str,
    db: AsyncSession = Depends(get_db),
) -> VerifyEmailResponse:
    return await _apply_email_verification(token, db)


# ═══════════════════════════════════════════════════════════════════════════
# ENDPOINT: POST /auth/resend-verification — Doğrulama bağlantısını yeniden gönder
# ═══════════════════════════════════════════════════════════════════════════

RESEND_ACCEPTED_MESSAGE = (
    "Bu adrese ait doğrulanmamış bir hesap varsa yeni doğrulama bağlantısı gönderildi."
)


@router.post(
    "/resend-verification",
    response_model=MessageResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Doğrulama bağlantısını yeniden gönder",
    description=(
        "E-posta adresi ya da süresi dolmuş bağlantının token'ı ile yeni doğrulama bağlantısı "
        "ister. Yanıt, hesabın var olup olmadığını ya da doğrulanmış olup olmadığını "
        "SIZDIRMAZ: her durumda aynıdır. IP başına ve adres başına saatlik sınır vardır."
    ),
    tags=["auth"],
)
async def resend_verification(
    body: ResendVerificationRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    if not body.email and not body.token:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": "email_or_token_required",
                "message": "E-posta adresi ya da doğrulama bağlantısı gerekli.",
            },
        )
    if not email_service.email_enabled():
        raise _email_disabled_error()

    user: Optional[User] = None
    if body.token:
        try:
            payload = auth_service.decode_purpose_token(body.token, EMAIL_VERIFY_AUDIENCE, verify_exp=False)
            user = await _get_user_by_id(db, payload.get("sub"))
        except PurposeTokenError:
            user = None
    elif body.email:
        user = await _get_user_by_email(db, body.email)

    if (
        user is not None
        and getattr(user, "is_active", True)
        and not user.is_verified
        and await auth_service.allow_email_to_address("verify", user.email)
    ):
        background_tasks.add_task(
            auth_service.send_verification_email,
            email=user.email,
            user_id=str(user.id),
        )

    return MessageResponse(message=RESEND_ACCEPTED_MESSAGE)


# ═══════════════════════════════════════════════════════════════════════════
# ENDPOINT: POST /auth/forgot-password — Şifre sıfırlama bağlantısı iste
# ═══════════════════════════════════════════════════════════════════════════

FORGOT_ACCEPTED_MESSAGE = (
    "Bu adrese ait bir hesap varsa şifre sıfırlama bağlantısı gönderildi. "
    "Gelen kutunuzu ve istenmeyen klasörünü kontrol edin."
)


@router.post(
    "/forgot-password",
    response_model=MessageResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Şifre sıfırlama bağlantısı iste",
    description=(
        "Hesap varsa e-postaya tek kullanımlık, süreli (PASSWORD_RESET_TOKEN_MINUTES, "
        "varsayılan 30 dk) bir sıfırlama bağlantısı gönderir. Yanıt hesabın varlığını "
        "SIZDIRMAZ ve gönderim arka planda yapıldığı için süresi de hesaba göre değişmez. "
        "IP başına ve adres başına saatlik sınır vardır. E-posta kapalıysa 503."
    ),
    tags=["auth"],
)
async def forgot_password(
    body: ForgotPasswordRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    if not email_service.email_enabled():
        raise _email_disabled_error()

    user = await _get_user_by_email(db, body.email)
    if (
        user is not None
        and getattr(user, "is_active", True)
        and await auth_service.allow_email_to_address("reset", user.email)
    ):
        background_tasks.add_task(auth_service.send_password_reset_email, user)

    return MessageResponse(message=FORGOT_ACCEPTED_MESSAGE)


# ═══════════════════════════════════════════════════════════════════════════
# ENDPOINT: POST /auth/reset-password — Yeni şifre belirle
# ═══════════════════════════════════════════════════════════════════════════


@router.post(
    "/reset-password",
    response_model=MessageResponse,
    summary="Yeni şifre belirle",
    description=(
        "Sıfırlama token'ı ile şifreyi değiştirir. Token tek kullanımlıktır: şifre ve "
        "oturum sürümü değiştiği anda geçersizleşir. Başarılı sıfırlama TÜM eski oturumları "
        "(access + refresh token) geçersiz kılar ve e-postayı doğrulanmış sayar."
    ),
    tags=["auth"],
)
async def reset_password(
    body: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    try:
        payload = auth_service.decode_purpose_token(body.token, PASSWORD_RESET_AUDIENCE)
    except PurposeTokenError as exc:
        raise _token_error(exc.reason, purpose="reset") from exc

    user = await _get_user_by_id(db, payload.get("sub"))
    if user is None or not getattr(user, "is_active", True):
        raise _token_error("invalid", purpose="reset")

    try:
        token_version = int(payload.get("tv", -1))
    except (TypeError, ValueError):
        token_version = -1
    current_version = int(getattr(user, "session_version", 0) or 0)
    fingerprint_ok = hmac.compare_digest(
        str(payload.get("pwf", "")),
        auth_service.password_fingerprint(user.hashed_password),
    )
    if token_version != current_version or not fingerprint_ok:
        # Token daha önce kullanılmış ya da o tarihten beri şifre değişmiş
        raise _token_error("invalid", purpose="reset")

    # Kurallar token'dan SONRA: geçersiz bağlantıya şifre kuralı hatası gösterilmesin
    auth_service.validate_password(body.new_password)

    # Koşullu güncelleme: iki eşzamanlı istekten yalnızca biri sürümü ilerletebilir
    result = await db.execute(
        update(User)
        .where(User.id == user.id, User.session_version == current_version)
        .values(
            hashed_password=auth_service.hash_password(body.new_password),
            session_version=current_version + 1,
            is_verified=True,
        )
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        await db.rollback()
        raise _token_error("invalid", purpose="reset")
    await db.commit()
    await db.refresh(user)

    # Kilitlenmiş girişleri aç: kullanıcı e-postasının sahibi olduğunu kanıtladı
    await auth_service.clear_failed_attempts(user.email)
    logger.info("Şifre sıfırlandı, eski oturumlar geçersiz: user_id=%s", user.id)

    return MessageResponse(
        message="Şifreniz güncellendi. Açık olan tüm oturumlarınız kapatıldı; yeni şifrenizle giriş yapın."
    )


# ═══════════════════════════════════════════════════════════════════════════
# ENDPOINT: POST /auth/login — Giriş
# ═══════════════════════════════════════════════════════════════════════════


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Kullanıcı girişi",
    description=(
        "Email ve şifre ile kimlik doğrulama yapar. Başarılı olursa "
        "access token (1 saat) ve refresh token (30 gün) döndürür. "
        "Brute force koruması: 5 başarısız deneme → 15 dakika kilitleme."
    ),
    response_description="JWT access ve refresh token çifti",
    tags=["auth"],
)
async def login(
    body: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """
    Email/şifre ile giriş yapar.

    1. Brute force kontrolü (5 başarısız → 15 dk blok)
    2. Email ile kullanıcı arar
    3. Şifre doğrulama (bcrypt)
    4. Access + Refresh token oluşturur
    5. Başarısız deneme sayacını sıfırlar
    """

    email_lower = body.email.lower()

    # Brute force kontrolü
    await auth_service.check_brute_force(email_lower)

    # Kullanıcıyı bul
    stmt = select(User).where(User.email == email_lower)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if user is None:
        # Kullanıcı bulunamadı — yine de brute force kaydet
        await auth_service.record_failed_attempt(email_lower)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "invalid_credentials",
                "message": "Email veya şifre hatalı.",
            },
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Hesap aktiflik kontrolü
    if hasattr(user, "is_active") and not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "account_disabled",
                "message": "Hesabınız devre dışı bırakılmış. Yönetici ile iletişime geçin.",
            },
        )

    # Şifre doğrulama
    if not hasattr(user, "hashed_password") or not user.hashed_password:
        await auth_service.record_failed_attempt(email_lower)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "invalid_credentials",
                "message": "Email veya şifre hatalı.",
            },
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not auth_service.verify_password(body.password, user.hashed_password):
        await auth_service.record_failed_attempt(email_lower)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "invalid_credentials",
                "message": "Email veya şifre hatalı.",
            },
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Başarılı giriş — brute force sayacını sıfırla
    await auth_service.clear_failed_attempts(email_lower)

    # Token'ları oluştur
    session_version = int(getattr(user, "session_version", 0) or 0)
    access_token = auth_service.create_access_token(
        user_id=str(user.id),
        role=user.role,
        session_version=session_version,
    )
    refresh_token = auth_service.create_refresh_token(
        user_id=str(user.id), session_version=session_version
    )

    logger.info("Kullanıcı giriş yaptı: id=%s", user.id)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=3600,  # 1 saat
    )


# ═══════════════════════════════════════════════════════════════════════════
# ENDPOINT: POST /auth/refresh — Token Yenileme
# ═══════════════════════════════════════════════════════════════════════════


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Token yenileme",
    description=(
        "Geçerli bir refresh token ile yeni bir access token alır. "
        "Refresh token'ın kendisi değişmez."
    ),
    response_description="Yeni JWT access token",
    tags=["auth"],
)
async def refresh_token(
    body: RefreshRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """
    Refresh token ile yeni access token oluşturur.

    1. Refresh token'ı decode eder
    2. Token tipinin "refresh" olduğunu doğrular
    3. Blacklist kontrolü yapar
    4. Kullanıcının hala aktif olduğunu doğrular
    5. Yeni access token döndürür
    """

    # Token decode
    payload = auth_service.decode_token(body.refresh_token)

    # Tip kontrolü
    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "invalid_token_type",
                "message": "Refresh token bekleniyor.",
            },
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Blacklist kontrolü
    if await auth_service.is_token_blacklisted(body.refresh_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "token_revoked",
                "message": "Bu refresh token iptal edilmiş.",
            },
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Kullanıcı varlık ve aktiflik kontrolü
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid_token", "message": "Token geçersiz."},
            headers={"WWW-Authenticate": "Bearer"},
        )

    stmt = select(User).where(User.id == user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "user_not_found",
                "message": "Kullanıcı bulunamadı.",
            },
            headers={"WWW-Authenticate": "Bearer"},
        )

    if hasattr(user, "is_active") and not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "account_disabled",
                "message": "Hesabınız devre dışı bırakılmış.",
            },
        )

    # Şifre sıfırlamadan önce verilmiş refresh token yeni oturum açamaz
    if session_revoked(payload, user):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "session_revoked",
                "message": "Oturumunuz sona erdi. Lütfen yeniden giriş yapın.",
            },
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Yeni access token oluştur
    new_access_token = auth_service.create_access_token(
        user_id=str(user.id),
        role=user.role,
        session_version=int(getattr(user, "session_version", 0) or 0),
    )

    logger.info("Token yenilendi: user_id=%s", user.id)

    return TokenResponse(
        access_token=new_access_token,
        refresh_token=None,  # Refresh token değişmez
        token_type="bearer",
        expires_in=3600,
    )


# ═══════════════════════════════════════════════════════════════════════════
# ENDPOINT: POST /auth/logout — Çıkış
# ═══════════════════════════════════════════════════════════════════════════


@router.post(
    "/logout",
    response_model=MessageResponse,
    summary="Oturumu kapat",
    description=(
        "Mevcut access token'ı ve opsiyonel olarak refresh token'ı "
        "Redis blacklist'e ekleyerek geçersiz kılar."
    ),
    response_description="Çıkış onay mesajı",
    tags=["auth"],
)
async def logout(
    body: LogoutRequest = LogoutRequest(),
    current_user: User = Depends(get_current_user),
    token: str = Depends(oauth2_scheme),
) -> MessageResponse:
    """
    Kullanıcı oturumunu kapatır.

    1. Access token'ı blacklist'e ekler
    2. Varsa refresh token'ı da blacklist'e ekler
    """

    # Access token'ı blacklist'e ekle
    await auth_service.blacklist_token(token)

    # Refresh token varsa onu da blacklist'e ekle
    if body.refresh_token:
        await auth_service.blacklist_token(body.refresh_token)

    logger.info("Kullanıcı çıkış yaptı: id=%s", current_user.id)

    return MessageResponse(message="Oturum başarıyla kapatıldı.")


# ═══════════════════════════════════════════════════════════════════════════
# ENDPOINT: GET /auth/me — Profil Görüntüleme
# ═══════════════════════════════════════════════════════════════════════════


@router.get(
    "/me",
    response_model=UserProfileResponse,
    summary="Kullanıcı profili",
    description="Mevcut oturumdaki kullanıcının profil bilgilerini döndürür.",
    response_description="Kullanıcı profil detayları",
    tags=["auth"],
)
async def get_me(
    current_user: User = Depends(get_current_user),
) -> UserProfileResponse:
    """
    Mevcut kullanıcının profilini döndürür.
    """
    return UserProfileResponse(
        id=str(current_user.id),
        email=current_user.email,
        username=current_user.username,
        role=current_user.role,
        trust_score=current_user.trust_score or 50.0,
        verified_count=current_user.verified_count or 0,
        submitted_count=current_user.submitted_count or 0,
        is_active=getattr(current_user, "is_active", True),
        is_verified=getattr(current_user, "is_verified", False),
        created_at=getattr(current_user, "created_at", None),
    )


class MyVerificationItem(BaseModel):
    """Kullanıcının verdiği bir doğrulama oyu ve ilgili bulgu."""

    anomaly_id: str
    vote: str
    comment: Optional[str] = None
    created_at: Optional[datetime] = None
    category: str
    anomaly_status: str
    confidence_score: float
    lat: float
    lng: float
    location_label: Optional[str] = None


@router.get(
    "/me/verifications",
    response_model=list[MyVerificationItem],
    summary="Doğrulamalarım",
    description="Mevcut kullanıcının verdiği son doğrulama oyları (en yeni önce).",
    tags=["auth"],
)
async def get_my_verifications(
    limit: int = 20,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[MyVerificationItem]:
    """Profil sayfası için gerçek oy geçmişi (eskiden arayüz demo verisi gösteriyordu)."""
    from app.models.anomaly import Anomaly
    from app.models.verification import Verification

    stmt = (
        select(Verification, Anomaly)
        .join(Anomaly, Anomaly.id == Verification.anomaly_id)
        .where(Verification.user_id == current_user.id)
        .order_by(Verification.created_at.desc())
        .limit(max(1, min(limit, 100)))
    )
    rows = (await db.execute(stmt)).all()
    items: list[MyVerificationItem] = []
    for verification, anomaly in rows:
        meta = anomaly.meta_data or {}
        items.append(
            MyVerificationItem(
                anomaly_id=str(anomaly.id),
                vote=verification.vote,
                comment=verification.comment,
                created_at=verification.created_at,
                category=anomaly.category,
                anomaly_status=anomaly.status or "PENDING",
                confidence_score=anomaly.confidence_score or 0.0,
                lat=anomaly.lat,
                lng=anomaly.lng,
                location_label=meta.get("reference_site") or meta.get("location_label"),
            )
        )
    return items


# ═══════════════════════════════════════════════════════════════════════════
# ENDPOINT: PATCH /auth/me — Profil Güncelleme
# ═══════════════════════════════════════════════════════════════════════════


@router.patch(
    "/me",
    response_model=UserProfileResponse,
    summary="Profil güncelle",
    description=(
        "Kullanıcı adını ve/veya şifreyi günceller. Şifre değişikliği için "
        "mevcut şifrenin doğru girilmesi gerekir."
    ),
    response_description="Güncellenmiş kullanıcı profili",
    tags=["auth"],
)
async def update_me(
    body: ProfileUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserProfileResponse:
    """
    Kullanıcı profilini günceller.

    - **Kullanıcı adı**: Benzersizlik kontrol edilir.
    - **Şifre değişikliği**: `current_password` zorunlu,
      `new_password` güvenlik kurallarına uymalı.
    """

    updated = False

    # Kullanıcı adı güncelleme
    if body.username is not None and body.username != current_user.username:
        # Benzersizlik kontrolü
        check_stmt = select(User).where(
            User.username == body.username,
            User.id != current_user.id,
        )
        check_result = await db.execute(check_stmt)
        if check_result.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error": "username_already_exists",
                    "message": "Bu kullanıcı adı zaten kullanılıyor.",
                },
            )
        current_user.username = body.username
        updated = True

    # Şifre değişikliği
    if body.new_password is not None:
        if body.current_password is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "current_password_required",
                    "message": "Şifre değişikliği için mevcut şifrenizi girmelisiniz.",
                },
            )

        # Mevcut şifre doğrulama
        if not hasattr(current_user, "hashed_password") or not current_user.hashed_password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "no_password_set",
                    "message": "Hesabınızda şifre tanımlı değil.",
                },
            )

        if not auth_service.verify_password(
            body.current_password, current_user.hashed_password
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "error": "invalid_current_password",
                    "message": "Mevcut şifreniz hatalı.",
                },
            )

        # Yeni şifre kurallarını doğrula
        auth_service.validate_password(body.new_password)

        # Yeni şifreyi hash'le
        current_user.hashed_password = auth_service.hash_password(body.new_password)
        updated = True

    if not updated:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "no_changes",
                "message": "Güncellenecek bir alan belirtilmedi.",
            },
        )

    await db.commit()
    await db.refresh(current_user)

    logger.info("Profil güncellendi: user_id=%s", current_user.id)

    return UserProfileResponse(
        id=str(current_user.id),
        email=current_user.email,
        username=current_user.username,
        role=current_user.role,
        trust_score=current_user.trust_score or 50.0,
        verified_count=current_user.verified_count or 0,
        submitted_count=current_user.submitted_count or 0,
        is_active=getattr(current_user, "is_active", True),
        is_verified=getattr(current_user, "is_verified", False),
        created_at=getattr(current_user, "created_at", None),
    )
