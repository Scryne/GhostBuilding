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

import hashlib
import hmac
import logging
import re
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional

import redis.asyncio as aioredis
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
import jwt
from jwt import PyJWTError as JWTError  # python-jose bakımsız ve düzeltilmemiş açık taşıyor
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.session import get_db
from app.models.user import User
from app.models.enums import UserRole
from app.services import email_service

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
EMAIL_RATE_PREFIX = "auth:mailrate:"

# Amaçlı token'ların audience değerleri — oturum token'larıyla karışmasınlar diye
EMAIL_VERIFY_AUDIENCE = "ghostbuilding:email-verify"
PASSWORD_RESET_AUDIENCE = "ghostbuilding:password-reset"

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
        session_version: int = 0,
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
            "tv": int(session_version or 0),
            "iat": now,
            "exp": now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
            "jti": str(uuid.uuid4()),
        }
        if extra_claims:
            payload.update(extra_claims)

        return jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)

    @staticmethod
    def create_refresh_token(user_id: str, *, session_version: int = 0) -> str:
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
            "tv": int(session_version or 0),
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
    # Amaçlı Tek-Kullanımlık Token'lar (e-posta doğrulama, şifre sıfırlama)
    # ===================================================================
    #
    # İkisi de imzalı JWT'dir ama access/refresh token'larından AYRI bir ``aud`` taşır:
    # ``decode_token`` ``aud`` beklemediği için bu token'lar oturum token'ı olarak
    # kullanılamaz (PyJWT ``aud`` taşıyan token'ı audience verilmeden reddeder), tersi de
    # olmaz. Süre ``exp`` ile imzanın içindedir; bu yüzden "süresi dolmuş" ile "geçersiz"
    # ayrı ayrı söylenebilir.
    #
    # Şifre sıfırlama token'ı ayrıca kullanıcının o anki ``session_version`` değerini ve
    # şifre hash'inin parmak izini taşır. Sıfırlama ikisini de değiştirdiği için token
    # kullanıldığı anda kendiliğinden geçersizleşir (tek kullanımlık) — Redis'e bağlı değil.

    @staticmethod
    def _purpose_token(user_id: str, audience: str, lifetime: timedelta, **claims: Any) -> str:
        now = datetime.now(timezone.utc)
        payload: Dict[str, Any] = {
            "sub": str(user_id),
            "aud": audience,
            "iat": now,
            "exp": now + lifetime,
            "jti": str(uuid.uuid4()),
            **claims,
        }
        return jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)

    @staticmethod
    def decode_purpose_token(token: str, audience: str, *, verify_exp: bool = True) -> Dict[str, Any]:
        """
        Amaçlı token'ı çözer.

        Raises:
            PurposeTokenError: ``reason`` = ``"expired"`` ya da ``"invalid"``.
        """
        try:
            return jwt.decode(
                token,
                settings.SECRET_KEY,
                algorithms=[ALGORITHM],
                audience=audience,
                options={"verify_exp": verify_exp, "require": ["sub", "aud", "exp"]},
            )
        except jwt.ExpiredSignatureError as exc:
            raise PurposeTokenError("expired") from exc
        except JWTError as exc:
            raise PurposeTokenError("invalid") from exc

    @classmethod
    def create_email_verification_token(cls, user_id: str) -> str:
        return cls._purpose_token(
            user_id,
            EMAIL_VERIFY_AUDIENCE,
            timedelta(hours=settings.EMAIL_VERIFY_TOKEN_HOURS),
        )

    @staticmethod
    def password_fingerprint(hashed_password: Optional[str]) -> str:
        """Şifre hash'inin anahtarlı kısa parmak izi (hash'in kendisi token'a girmez)."""
        digest = hmac.new(
            settings.SECRET_KEY.encode(),
            (hashed_password or "").encode(),
            hashlib.sha256,
        )
        return digest.hexdigest()[:24]

    @classmethod
    def create_password_reset_token(cls, user: Any) -> str:
        return cls._purpose_token(
            str(user.id),
            PASSWORD_RESET_AUDIENCE,
            timedelta(minutes=settings.PASSWORD_RESET_TOKEN_MINUTES),
            tv=int(getattr(user, "session_version", 0) or 0),
            pwf=cls.password_fingerprint(getattr(user, "hashed_password", None)),
        )

    # ===================================================================
    # Adres Başına E-posta Sınırı
    # ===================================================================

    @staticmethod
    async def allow_email_to_address(kind: str, email: str) -> bool:
        """
        Aynı adrese saatte en çok ``RATE_LIMIT_EMAIL_PER_ADDRESS_PER_HOUR`` e-posta.

        Çağıran uç, sınır aşılsa da AYNI yanıtı döner — yoksa sınır, hesabın var olup
        olmadığını sızdırırdı. Redis anahtarında adresin kendisi değil anahtarlı hash'i tutulur.
        Redis erişilemezse diğer sınırlayıcılar gibi geçirir (IP sınırı yine geçerlidir).
        """
        digest = hmac.new(settings.SECRET_KEY.encode(), email.lower().encode(), hashlib.sha256).hexdigest()
        key = f"{EMAIL_RATE_PREFIX}{kind}:{digest[:32]}"
        try:
            r = await _get_redis()
            pipe = r.pipeline()
            pipe.incr(key)
            pipe.expire(key, 3600, nx=True)
            results = await pipe.execute()
            await r.aclose()
            count = int(results[0])
        except Exception as exc:
            logger.warning("E-posta adres sınırı kontrol hatası (grace): %s", type(exc).__name__)
            return True
        return count <= settings.RATE_LIMIT_EMAIL_PER_ADDRESS_PER_HOUR

    # ===================================================================
    # E-posta Gönderimi
    # ===================================================================

    @classmethod
    async def send_verification_email(cls, email: str, user_id: str) -> bool:
        """
        Doğrulama bağlantısını e-postayla gönderir (bağlantı ``FRONTEND_URL`` kökünden).

        Log'a adres ve token yazılmaz; yalnızca kullanıcı kimliği ve sonuç.

        Returns:
            Gönderildiyse ``True``; e-posta kapalıysa ya da gönderim başarısızsa ``False``.
        """
        token = cls.create_email_verification_token(user_id)
        sent = await email_service.send_verification_email(email, token)
        logger.info("Doğrulama e-postası: user_id=%s gönderildi=%s", user_id, sent)
        return sent

    @classmethod
    async def send_password_reset_email(cls, user: Any) -> bool:
        """Sıfırlama bağlantısını gönderir. Log'a adres ve token yazılmaz."""
        token = cls.create_password_reset_token(user)
        sent = await email_service.send_password_reset_email(user.email, token)
        logger.info("Şifre sıfırlama e-postası: user_id=%s gönderildi=%s", user.id, sent)
        return sent


class PurposeTokenError(Exception):
    """Amaçlı token çözülemedi. ``reason``: ``"expired"`` | ``"invalid"``."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def session_revoked(payload: Dict[str, Any], user: Any) -> bool:
    """
    Token, kullanıcının şu anki oturum sürümünden eskiyse ``True``.

    Şifre sıfırlama ``session_version``'ı bir artırır; o andan önce verilmiş tüm access ve
    refresh token'ları (``tv`` claim'i eski) reddedilir. ``tv`` taşımayan eski token'lar 0 sayılır.
    """
    try:
        token_version = int(payload.get("tv", 0) or 0)
    except (TypeError, ValueError):
        return True
    return token_version != int(getattr(user, "session_version", 0) or 0)


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

    # Şifre sıfırlandıysa bu token'dan önceki oturumlar geçersizdir
    if session_revoked(payload, user):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "session_revoked",
                "message": "Oturumunuz sona erdi. Lütfen yeniden giriş yapın.",
            },
            headers={"WWW-Authenticate": "Bearer"},
        )

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
