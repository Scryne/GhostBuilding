"""
security_headers.py — Güvenlik HTTP başlıkları middleware'i.

OWASP güvenlik önerilerine uygun HTTP başlıklarını tüm yanıtlara ekler:
- Content-Security-Policy
- X-Frame-Options: DENY
- X-Content-Type-Options: nosniff
- Referrer-Policy: strict-origin-when-cross-origin
- Strict-Transport-Security (HSTS — prod ortamında)
- Permissions-Policy
"""

from __future__ import annotations

import logging

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.types import ASGIApp

from app.config import settings

logger = logging.getLogger(__name__)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Tüm HTTP yanıtlarına güvenlik başlıklarını ekler.

    Ortam (ENVIRONMENT) ayarına göre HSTS ve CSP kuralları değişir.
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)
        self.is_production = settings.ENVIRONMENT.lower() in ("production", "prod")

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        response = await call_next(request)

        # ── Clickjacking koruması ──
        response.headers["X-Frame-Options"] = "DENY"

        # ── MIME tipi sniffing koruması ──
        response.headers["X-Content-Type-Options"] = "nosniff"

        # ── XSS koruması (legacy tarayıcılar için) ──
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # ── Referrer politikası ──
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # ── İzin politikası — gereksiz API'leri kapat ──
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(self), "
            "payment=(), usb=(), magnetometer=()"
        )

        # ── Content Security Policy ──
        if self.is_production:
            csp = (
                "default-src 'self'; "
                "script-src 'self'; "
                "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
                "font-src 'self' https://fonts.gstatic.com; "
                "img-src 'self' data: https://*.openstreetmap.org https://*.google.com "
                "https://*.bing.com https://*.virtualearth.net blob:; "
                "connect-src 'self'; "
                "frame-ancestors 'none'; "
                "base-uri 'self'; "
                "form-action 'self';"
            )
        else:
            # Dev modunda daha esnek CSP
            csp = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
                "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
                "font-src 'self' https://fonts.gstatic.com; "
                "img-src * data: blob:; "
                "connect-src *; "
                "frame-ancestors 'none'; "
                "base-uri 'self';"
            )
        response.headers["Content-Security-Policy"] = csp

        # ── HSTS — Sadece production'da ──
        if self.is_production:
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains; preload"
            )

        return response
