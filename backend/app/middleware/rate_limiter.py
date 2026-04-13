"""
rate_limiter.py — Redis tabanlı sliding window rate limiting middleware.

Her endpoint grubu için farklı limit kuralları uygular:
- /api/v1/anomalies/scan: IP başına saatte 10 istek
- /api/v1/auth/login: IP başına dakikada 5 istek
- /api/v1/ genel: IP başına dakikada 60 istek

Limit aşılınca HTTP 429 Too Many Requests + Retry-After header döner.

Algoritma: Redis ZSET tabanlı sliding window — her istek UNIX timestamp
ile scored member olarak eklenir, pencere dışı girişler temizlenir,
kalan girişler sayılır.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Optional

import redis.asyncio as aioredis
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.types import ASGIApp

from app.config import settings

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# Rate Limit Kuralları
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class RateLimitRule:
    """Tek bir rate limit kuralı."""

    max_requests: int       # Pencere içinde izin verilen maks istek
    window_seconds: int     # Sliding window süresi (saniye)
    key_prefix: str         # Redis key prefix'i


# Endpoint grubu → kural eşleşmesi (en spesifik önce)
RATE_LIMIT_RULES: list[tuple[str, str, RateLimitRule]] = [
    # (path_prefix, http_method_or_"*", RateLimitRule)
    (
        "/api/v1/anomalies/scan",
        "POST",
        RateLimitRule(
            max_requests=settings.RATE_LIMIT_SCAN_PER_HOUR,
            window_seconds=3600,
            key_prefix="rl:scan",
        ),
    ),
    (
        "/api/v1/auth/login",
        "POST",
        RateLimitRule(
            max_requests=5,
            window_seconds=60,
            key_prefix="rl:login",
        ),
    ),
    (
        "/api/v1/",
        "*",
        RateLimitRule(
            max_requests=settings.RATE_LIMIT_PER_MINUTE,
            window_seconds=60,
            key_prefix="rl:api",
        ),
    ),
]

# Sağlık kontrolü gibi rate limit dışı yollar
EXEMPT_PATHS = {"/api/v1/health", "/docs", "/redoc", "/openapi.json", "/"}


# ═══════════════════════════════════════════════════════════════════════════
# Sliding Window Yardımcı Fonksiyonları
# ═══════════════════════════════════════════════════════════════════════════


async def _get_redis() -> Optional[aioredis.Redis]:
    """Rate limiter için async Redis client döndürür."""
    try:
        return aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    except Exception as exc:
        logger.warning("Rate limiter Redis bağlantı hatası: %s", exc)
        return None


def _resolve_client_ip(request: Request) -> str:
    """
    İstemcinin gerçek IP adresini çözer.

    Proxy arkasında çalışırken X-Forwarded-For header'ından alır,
    yoksa doğrudan client IP kullanır.
    """
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # İlk IP gerçek istemci IP'sidir
        return forwarded_for.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _match_rule(path: str, method: str) -> Optional[RateLimitRule]:
    """Verilen path ve HTTP method için eşleşen en spesifik kuralı bulur."""
    for rule_path, rule_method, rule in RATE_LIMIT_RULES:
        if path.startswith(rule_path):
            if rule_method == "*" or rule_method.upper() == method.upper():
                return rule
    return None


async def check_rate_limit(
    client_ip: str,
    rule: RateLimitRule,
) -> tuple[bool, int, int, int]:
    """
    Sliding window rate limit kontrolü yapar.

    Args:
        client_ip: İstemci IP adresi.
        rule: Uygulanacak rate limit kuralı.

    Returns:
        (is_allowed, remaining, limit, retry_after_seconds)
    """
    r = await _get_redis()
    if r is None:
        # Redis yoksa grace mode — isteği geçir
        return True, rule.max_requests, rule.max_requests, 0

    try:
        now = time.time()
        window_start = now - rule.window_seconds
        key = f"{rule.key_prefix}:{client_ip}"

        pipe = r.pipeline()
        # 1. Pencere dışı girişleri temizle
        pipe.zremrangebyscore(key, 0, window_start)
        # 2. Mevcut istek sayısını al
        pipe.zcard(key)
        # 3. Bu isteği ekle (score = timestamp, member = unique)
        pipe.zadd(key, {f"{now}": now})
        # 4. Key'in TTL'ini pencere süresiyle güncelle
        pipe.expire(key, rule.window_seconds)
        results = await pipe.execute()

        current_count = results[1]  # zcard sonucu (eklenmeden önceki sayı)

        if current_count >= rule.max_requests:
            # Limiti aşmış — eklenen member'ı geri al
            await r.zrem(key, f"{now}")

            # Retry-After: en eski girişin pencere dışına çıkma süresi
            oldest = await r.zrange(key, 0, 0, withscores=True)
            retry_after = 0
            if oldest:
                oldest_ts = oldest[0][1]
                retry_after = max(int(oldest_ts + rule.window_seconds - now), 1)

            await r.aclose()
            return False, 0, rule.max_requests, retry_after

        remaining = max(rule.max_requests - current_count - 1, 0)
        await r.aclose()
        return True, remaining, rule.max_requests, 0

    except Exception as exc:
        logger.warning("Rate limit kontrolü hatası (grace): %s", exc)
        try:
            await r.aclose()
        except Exception:
            pass
        return True, rule.max_requests, rule.max_requests, 0


# ═══════════════════════════════════════════════════════════════════════════
# FastAPI Middleware
# ═══════════════════════════════════════════════════════════════════════════


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Redis tabanlı sliding window rate limiting middleware.

    Her isteğin IP adresine ve eşleşen endpoint kuralına göre
    rate limit kontrolü yapar. Aşılırsa 429 döner.
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        path = request.url.path
        method = request.method

        # Muaf yolları atla
        if path in EXEMPT_PATHS:
            return await call_next(request)

        # Eşleşen kural bul
        rule = _match_rule(path, method)
        if rule is None:
            return await call_next(request)

        # IP çöz ve rate limit kontrol et
        client_ip = _resolve_client_ip(request)
        is_allowed, remaining, limit, retry_after = await check_rate_limit(
            client_ip, rule
        )

        if not is_allowed:
            logger.warning(
                "Rate limit aşıldı: ip=%s path=%s rule=%s retry_after=%d",
                client_ip,
                path,
                rule.key_prefix,
                retry_after,
            )
            return JSONResponse(
                status_code=429,
                content={
                    "error": "rate_limit_exceeded",
                    "message": "Çok fazla istek gönderdiniz. Lütfen bekleyin.",
                    "retry_after_seconds": retry_after,
                },
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(time.time()) + retry_after),
                },
            )

        # İstek geçti — rate limit header'larını ekle
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response
