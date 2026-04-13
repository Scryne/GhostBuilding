"""
logging_middleware.py — Request/Response Logging Middleware.

Her HTTP isteğinde:
- Benzersiz request_id oluşturur (veya X-Request-ID header'ından alır)
- user_id'yi JWT token'dan çıkarır
- İstek ve yanıt bilgilerini structlog ile loglar
- Tüm context'i structlog contextvars'a bağlar (downstream logger'lar otomatik görür)

Kullanım:
    app.add_middleware(RequestLoggingMiddleware)
"""

from __future__ import annotations

import time
import uuid
from typing import Optional

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.utils.logger import get_logger

logger = get_logger(__name__)


def _extract_user_id(request: Request) -> Optional[str]:
    """
    Authorization header'ından user_id çıkarmaya çalışır.
    JWT decode etmeden sadece claim'den alır (lightweight).
    """
    try:
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            import json
            import base64

            token = auth_header.split(" ", 1)[1]
            # JWT payload kısmını decode et (imza doğrulaması yapmıyoruz — sadece log)
            payload_b64 = token.split(".")[1]
            # Base64 padding düzelt
            padding = 4 - len(payload_b64) % 4
            if padding != 4:
                payload_b64 += "=" * padding
            payload = json.loads(base64.urlsafe_b64decode(payload_b64))
            return str(payload.get("sub", payload.get("user_id", "anonymous")))
    except Exception:
        pass
    return None


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Her HTTP isteğini ve yanıtını structlog ile loglar.

    Bağlam bilgileri:
    - request_id: Benzersiz istek tanımlayıcı
    - user_id: JWT token'dan çıkarılan kullanıcı kimliği
    - method, path, status_code, duration_ms
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # Request ID: header'dan al veya yeni oluştur
        request_id = request.headers.get("x-request-id", str(uuid.uuid4()))

        # User ID: JWT'den çıkar
        user_id = _extract_user_id(request) or "anonymous"

        # structlog context'e bağla — bu isteğin tüm loglarında görünür
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            user_id=user_id,
        )

        # Başlangıç zamanı
        start_time = time.perf_counter()

        # İsteği logla
        logger.info(
            "request_started",
            method=request.method,
            path=str(request.url.path),
            query=str(request.url.query) if request.url.query else None,
            client_ip=request.client.host if request.client else None,
        )

        try:
            response = await call_next(request)
        except Exception as exc:
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            logger.error(
                "request_failed",
                method=request.method,
                path=str(request.url.path),
                duration_ms=duration_ms,
                error=str(exc),
                exc_info=True,
            )
            raise

        # Süre hesapla
        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)

        # Yanıtı logla
        log_method = logger.warning if response.status_code >= 400 else logger.info
        log_method(
            "request_completed",
            method=request.method,
            path=str(request.url.path),
            status_code=response.status_code,
            duration_ms=duration_ms,
        )

        # Response header'a request_id ekle
        response.headers["X-Request-ID"] = request_id

        return response
