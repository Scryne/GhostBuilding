"""
auth_service.py — JWT kimlik doğrulama ve yetkilendirme servisi.

Bcrypt tabanlı şifre hashing, JWT access/refresh token yönetimi,
Redis üzerinden token blacklist ve brute-force koruması sağlar.

Kullanım:
    from app.services.auth_service import (
        AuthService, get_current_user, require_role,
    )

    @router.get("/protected")
    async def protected(user = Depends(get_current_user)):
        ...

    @router.get("/admin-only")
    async def admin(user = Depends(require_role(UserRole.ADMIN))):
        ...
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional

import redis.asyncio as aioredis
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.session import get_db
from app.models.user import User
from app.models.enums import UserRole

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Sabitler
# ---------------------------------------------------------------------------

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60          # 1 saat
REFRESH_TOKEN_EXPIRE_DAYS = 30            # 30 gün
BRUTE_FORCE_MAX_ATTEMPTS = 5             # Maks başarısız giriş
BRUTE_FORCE_LOCKOUT_MINUTES = 15         # Kilitleme süresi (dakika)

# Token prefix'leri — Redis key'lerinde kullanılır
TOKEN_BLACKLIST_PREFIX = "token:blacklist:"
BRUTE_FORCE_PREFIX = "auth:bruteforce:"

# ---------------------------------------------------------------------------
# Şifre Hashing (bcrypt)
# ---------------------------------------------------------------------------

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ---------------------------------------------------------------------------
# OAuth2 şeması — Swagger UI ile uyumlu
# ---------------------------------------------------------------------------

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/api/v1/auth/login",
    auto_error=True,
)

# İsteğe bağlı OAuth2 — korumasız endpoint'lerde kullanıcı bilgisi almak için
oauth2_scheme_optional = OAuth2PasswordBearer(
    tokenUrl="/api/v1/auth/login",
    auto_error=False,
)


# ---------------------------------------------------------------------------
# Redis Yardımcıları
# ---------------------------------------------------------------------------


async def _get_redis() -> aioredis.Redis:
    """Async Redis client döndürür."""
    return aioredis.from_url(settings.REDIS_URL, decode_responses=True)


# ---------------------------------------------------------------------------
# AuthService Sınıfı
# ---------------------------------------------------------------------------


class AuthService:
    """
    JWT tabanlı kimlik doğrulama servisi.

    Şifre hashing, token oluşturma/doğrulama, brute-force koruması
    ve token blacklist yönetimi sağlar.
    """

    # ===================================================================
    # Şifre İşlemleri
    # ===================================================================

    @staticmethod
    def hash_password(password: str) -> str:
        """
        Düz metin şifreyi bcrypt ile hash'ler.

        Args:
            password: Düz metin şifre.

        Returns:
            Bcrypt hash string'i.
        """
        return pwd_context.hash(password)

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """
        Düz metin şifreyi hash ile karşılaştırır.

        Args:
            plain_password: Kullanıcının girdiği şifre.
            hashed_password: Veritabanındaki hash.

        Returns:
            Eşleşme durumu.
        """
        return pwd_context.verify(plain_password, hashed_password)

    # ===================================================================
    # Şifre Doğrulama Kuralları
    # ===================================================================

    @staticmethod
    def validate_password(password: str) -> None:
        """
        Şifre güvenlik kurallarını doğrular.

        Kurallar:
        - Minimum 8 karakter
        - En az 1 büyük harf
        - En az 1 rakam

        Args:
            password: Kontrol edilecek şifre.

        Raises:
            HTTPException: Kural ihlali durumunda (422).
        """
        errors: list[str] = []

        if len(password) < 8:
            errors.append("Şifre en az 8 karakter olmalıdır.")
        if not re.search(r"[A-Z]", password):
            errors.append("Şifre en az 1 büyük harf içermelidir.")
        if not re.search(r"\d", password):
            errors.append("Şifre en az 1 rakam içermelidir.")

        if errors:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "error": "password_validation_failed",
                    "messages": errors,
                },
            )

    # ===================================================================
    # JWT Token Oluşturma
    # ===================================================================

    @staticmethod
    def create_access_token(
        user_id: str,
        role: str = UserRole.USER.value,
        *,
        extra_claims: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        JWT access token oluşturur (1 saat geçerli).

        Args:
            user_id: Kullanıcı UUID string.
            role: Kullanıcı rolü.
            extra_claims: Ek JWT payload verileri.

        Returns:
            Encoded JWT string.
        """
        now = datetime.now(timezone.utc)
        payload = {
            "sub": str(user_id),
            "role": role,
            "type": "access",
            "iat": now,
            "exp": now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
            "jti": str(uuid.uuid4()),
        }
        if extra_claims:
            payload.update(extra_claims)

        return jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)

    @staticmethod
    def create_refresh_token(user_id: str) -> str:
        """
        JWT refresh token oluşturur (30 gün geçerli).

        Args:
            user_id: Kullanıcı UUID string.

        Returns:
            Encoded JWT string.
        """
        now = datetime.now(timezone.utc)
        payload = {
            "sub": str(user_id),
            "type": "refresh",
            "iat": now,
            "exp": now + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
            "jti": str(uuid.uuid4()),
        }
        return jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)

    # ===================================================================
    # JWT Token Doğrulama
    # ===================================================================

    @staticmethod
    def decode_token(token: str) -> Dict[str, Any]:
        """
        JWT token'ı decode eder ve payload döndürür.

        Args:
            token: Encoded JWT string.

        Returns:
            Token payload sözlüğü.

        Raises:
            HTTPException: Geçersiz veya süresi dolmuş token (401).
        """
        try:
            payload = jwt.decode(
                token, settings.SECRET_KEY, algorithms=[ALGORITHM]
            )
            return payload
        except JWTError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "error": "invalid_token",
                    "message": "Token geçersiz veya süresi dolmuş.",
                },
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc

    # ===================================================================
    # Token Blacklist (Logout)
    # ===================================================================

    @staticmethod
    async def blacklist_token(token: str) -> None:
        """
        Token'ı Redis blacklist'e ekler.

        Token'ın kalan TTL'i kadar Redis'te tutulur,
        böylece süresi dolan token'lar otomatik temizlenir.

        Args:
            token: Blacklist'e eklenecek JWT string.
        """
        try:
            payload = jwt.decode(
                token, settings.SECRET_KEY, algorithms=[ALGORITHM]
            )
            jti = payload.get("jti", "")
            exp = payload.get("exp", 0)

            # Kalan süre hesapla
            now = datetime.now(timezone.utc).timestamp()
            ttl = max(int(exp - now), 1)

            r = await _get_redis()
            await r.set(f"{TOKEN_BLACKLIST_PREFIX}{jti}", "1", ex=ttl)
            await r.aclose()

            logger.info("Token blacklist'e eklendi: jti=%s ttl=%ds", jti, ttl)

        except JWTError:
            # Geçersiz token — blacklist'e eklemeye gerek yok
            pass
        except Exception as exc:
            logger.warning("Token blacklist hatası: %s", exc)

    @staticmethod
    async def is_token_blacklisted(token: str) -> bool:
        """
        Token'ın blacklist'te olup olmadığını kontrol eder.

        Args:
            token: Kontrol edilecek JWT string.

        Returns:
            True ise token geçersiz kılınmış.
        """
        try:
            payload = jwt.decode(
                token, settings.SECRET_KEY, algorithms=[ALGORITHM]
            )
            jti = payload.get("jti", "")

            r = await _get_redis()
            result = await r.get(f"{TOKEN_BLACKLIST_PREFIX}{jti}")
            await r.aclose()

            return result is not None

        except JWTError:
            return True
        except Exception as exc:
            logger.warning("Token blacklist kontrol hatası: %s", exc)
            return False

    # ===================================================================
    # Brute Force Koruması
    # ===================================================================

    @staticmethod
    async def check_brute_force(email: str) -> None:
        """
        Brute force saldırı kontrolü yapar.

        5 başarısız giriş denemesinden sonra hesabı 15 dakika kilitler.

        Args:
            email: Kontrol edilecek email adresi.

        Raises:
            HTTPException: Hesap kilitli (429).
        """
        key = f"{BRUTE_FORCE_PREFIX}{email.lower()}"

        try:
            r = await _get_redis()
            attempts_raw = await r.get(key)
            await r.aclose()

            if attempts_raw is not None and int(attempts_raw) >= BRUTE_FORCE_MAX_ATTEMPTS:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail={
                        "error": "account_locked",
                        "message": (
                            f"Çok fazla başarısız giriş denemesi. "
                            f"Hesabınız {BRUTE_FORCE_LOCKOUT_MINUTES} dakika kilitlendi."
                        ),
                        "lockout_minutes": BRUTE_FORCE_LOCKOUT_MINUTES,
                    },
                )
        except HTTPException:
            raise
        except Exception as exc:
            logger.warning("Brute force kontrolü hatası (grace): %s", exc)

    @staticmethod
    async def record_failed_attempt(email: str) -> None:
        """
        Başarısız giriş denemesini Redis'te kaydeder.

        Args:
            email: Başarısız giriş yapan email.
        """
        key = f"{BRUTE_FORCE_PREFIX}{email.lower()}"

        try:
            r = await _get_redis()
            pipe = r.pipeline()
            pipe.incr(key)
            pipe.expire(key, BRUTE_FORCE_LOCKOUT_MINUTES * 60)
            await pipe.execute()
            await r.aclose()
        except Exception as exc:
            logger.warning("Brute force kayıt hatası: %s", exc)

    @staticmethod
    async def clear_failed_attempts(email: str) -> None:
        """
        Başarılı giriş sonrası başarısız deneme sayacını sıfırlar.

        Args:
            email: Temizlenecek email.
        """
        key = f"{BRUTE_FORCE_PREFIX}{email.lower()}"

        try:
            r = await _get_redis()
            await r.delete(key)
            await r.aclose()
        except Exception as exc:
            logger.warning("Brute force temizleme hatası: %s", exc)

    # ===================================================================
    # Email Doğrulama (placeholder — SMTP sonra eklenecek)
    # ===================================================================

    @staticmethod
    async def send_verification_email(email: str, user_id: str) -> None:
        """
        Email doğrulama mesajı gönderir.

        Şimdilik sadece log'a yazar. SMTP entegrasyonu
        ileride eklenecektir.

        Args:
            email: Hedef email adresi.
            user_id: Kullanıcı UUID string.
        """
        # Doğrulama token'ı oluştur
        verification_token = str(uuid.uuid4())

        # Redis'te 24 saat sakla
        try:
            r = await _get_redis()
            await r.set(
                f"email:verify:{verification_token}",
                str(user_id),
                ex=86400,  # 24 saat
            )
            await r.aclose()
        except Exception as exc:
            logger.warning("Email doğrulama token kayıt hatası: %s", exc)

        # TODO: SMTP entegrasyonu
        verification_url = f"{settings.APP_NAME}/verify?token={verification_token}"
        logger.info(
            "📧 Email doğrulama gönderildi (LOG): "
            "email=%s user_id=%s url=%s",
            email,
            user_id,
            verification_url,
        )


# ---------------------------------------------------------------------------
# FastAPI Dependency: get_current_user
# ---------------------------------------------------------------------------

auth_service = AuthService()


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    JWT token'dan mevcut kullanıcıyı çözer.

    FastAPI Depends() ile tüm korumalı endpoint'lere
    enjekte edilebilir.

    Args:
        token: Bearer token (OAuth2 header'dan otomatik alınır).
        db: Async veritabanı oturumu.

    Returns:
        User ORM nesnesi.

    Raises:
        HTTPException: Geçersiz token, blacklist'teki token veya
                       kullanıcı bulunamadı (401).
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={
            "error": "authentication_required",
            "message": "Geçersiz kimlik bilgileri.",
        },
        headers={"WWW-Authenticate": "Bearer"},
    )

    # Token decode
    payload = auth_service.decode_token(token)

    # Token tipi kontrolü
    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "invalid_token_type",
                "message": "Bu endpoint için access token gereklidir.",
            },
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Blacklist kontrolü
    if await auth_service.is_token_blacklisted(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "token_revoked",
                "message": "Bu token iptal edilmiş.",
            },
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Kullanıcı ID çek
    user_id = payload.get("sub")
    if user_id is None:
        raise credentials_exception

    # Kullanıcıyı DB'den getir
    stmt = select(User).where(User.id == user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if user is None:
        raise credentials_exception

    # Aktiflik kontrolü
    if hasattr(user, "is_active") and not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "account_disabled",
                "message": "Hesabınız devre dışı bırakılmış.",
            },
        )

    return user


async def get_current_user_optional(
    token: Optional[str] = Depends(oauth2_scheme_optional),
    db: AsyncSession = Depends(get_db),
) -> Optional[User]:
    """
    Opsiyonel kullanıcı çözümleme.

    Token yoksa None döndürür, varsa doğrular.
    Hem anonim hem de kimliği doğrulanmış erişime izin
    veren endpoint'ler için kullanılır.
    """
    if token is None:
        return None

    try:
        return await get_current_user(token=token, db=db)
    except HTTPException:
        return None


# ---------------------------------------------------------------------------
# Rol Tabanlı Yetkilendirme
# ---------------------------------------------------------------------------


def require_role(*allowed_roles: UserRole):
    """
    Belirtilen rollere sahip kullanıcıları gerektiren dependency factory.

    Kullanım:
        @router.get("/admin-panel")
        async def admin_panel(user = Depends(require_role(UserRole.ADMIN))):
            ...

        @router.patch("/moderate")
        async def moderate(
            user = Depends(require_role(UserRole.MODERATOR, UserRole.ADMIN))
        ):
            ...

    Args:
        *allowed_roles: İzin verilen UserRole enum değerleri.

    Returns:
        FastAPI dependency fonksiyonu.
    """

    async def _role_checker(
        current_user: User = Depends(get_current_user),
    ) -> User:
        user_role = current_user.role

        # String → enum dönüşümü
        try:
            user_role_enum = UserRole(user_role)
        except ValueError:
            user_role_enum = None

        # ADMIN her zaman erişebilir
        if user_role_enum == UserRole.ADMIN:
            return current_user

        # İzin kontrolü
        allowed_values = {r.value for r in allowed_roles}
        if user_role not in allowed_values:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": "insufficient_permissions",
                    "message": (
                        f"Bu işlem için gereken roller: "
                        f"{', '.join(r.value for r in allowed_roles)}. "
                        f"Mevcut rolünüz: {user_role}."
                    ),
                    "required_roles": [r.value for r in allowed_roles],
                    "current_role": user_role,
                },
            )

        return current_user

    return _role_checker
