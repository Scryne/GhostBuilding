"""
sentry.py — GhostBuilding Sentry Entegrasyonu.

Backend Sentry SDK konfigürasyonu:
- FastAPI entegrasyonu
- Performance tracing (slow request'ler)
- User context otomatik ekleme
- Environment bazlı DSN

Kullanım:
    from app.utils.sentry import init_sentry
    init_sentry()  # main.py startup'ında çağrılır
"""

from __future__ import annotations

import os
from typing import Optional

from app.config import settings
from app.utils.logger import get_logger

logger = get_logger(__name__)


def init_sentry() -> None:
    """
    Sentry SDK'yı başlatır. DSN yoksa sessizce geçer.

    Environment Variables:
        SENTRY_DSN: Sentry Data Source Name
        SENTRY_TRACES_SAMPLE_RATE: Performance tracing sample oranı (0.0 - 1.0)
        SENTRY_PROFILES_SAMPLE_RATE: Profiling sample oranı (0.0 - 1.0)
    """
    dsn = os.getenv("SENTRY_DSN", "")
    if not dsn:
        logger.info("sentry_disabled", reason="SENTRY_DSN not configured")
        return

    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.starlette import StarletteIntegration
        from sentry_sdk.integrations.celery import CeleryIntegration
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
        from sentry_sdk.integrations.redis import RedisIntegration
        from sentry_sdk.integrations.logging import LoggingIntegration

        environment = settings.ENVIRONMENT
        traces_sample_rate = float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.2"))
        profiles_sample_rate = float(os.getenv("SENTRY_PROFILES_SAMPLE_RATE", "0.1"))

        sentry_sdk.init(
            dsn=dsn,
            environment=environment,
            release=f"ghostbuilding@{settings.VERSION}",
            # Performance Monitoring
            traces_sample_rate=traces_sample_rate,
            profiles_sample_rate=profiles_sample_rate,
            # Integrations
            integrations=[
                FastApiIntegration(transaction_style="endpoint"),
                StarletteIntegration(transaction_style="endpoint"),
                CeleryIntegration(monitor_beat_tasks=True),
                SqlalchemyIntegration(),
                RedisIntegration(),
                LoggingIntegration(
                    level=None,  # Tüm seviyeleri breadcrumb olarak kaydet
                    event_level="ERROR",  # ERROR ve üstünü Sentry event'i yap
                ),
            ],
            # Hassas verileri gönderme
            send_default_pii=False,
            # Slow request threshold: 2 saniye
            before_send=_before_send,
            before_send_transaction=_before_send_transaction,
            # Ortam bazlı ayarlar
            attach_stacktrace=True,
            # Production'da debug kapalı
            debug=settings.DEBUG,
        )

        logger.info(
            "sentry_initialized",
            environment=environment,
            traces_sample_rate=traces_sample_rate,
        )

    except ImportError:
        logger.warning("sentry_import_error", reason="sentry-sdk not installed")
    except Exception as e:
        logger.error("sentry_init_error", error=str(e))


def set_sentry_user(user_id: Optional[str], username: Optional[str] = None) -> None:
    """
    Sentry user context'ini ayarlar — hatalar kullanıcıyla ilişkilendirilir.

    Args:
        user_id: Kullanıcı kimliği
        username: Kullanıcı adı (opsiyonel)
    """
    try:
        import sentry_sdk
        sentry_sdk.set_user({
            "id": user_id,
            "username": username,
        })
    except ImportError:
        pass


def _before_send(event: dict, hint: dict) -> Optional[dict]:
    """
    Sentry'ye gönderilmeden önce event'i filtreler/zenginleştirir.
    Hassas verileri temizler.
    """
    # Request verilerinden hassas header'ları çıkar
    if "request" in event:
        headers = event["request"].get("headers", {})
        sensitive_headers = {"authorization", "cookie", "x-api-key"}
        for header in sensitive_headers:
            if header in headers:
                headers[header] = "***REDACTED***"

    return event


def _before_send_transaction(event: dict, hint: dict) -> Optional[dict]:
    """
    Slow request'leri işaretler (>2 saniye).
    Health check gibi rutin endpoint'leri filtreler.
    """
    transaction = event.get("transaction", "")

    # Health check ve metrics endpoint'leri transaction'lardan hariç tut
    skip_endpoints = ("/health", "/metrics", "/favicon.ico")
    if any(transaction.endswith(ep) for ep in skip_endpoints):
        return None

    # Slow request'leri tag'le
    start = event.get("start_timestamp")
    end = event.get("timestamp")
    if start and end:
        try:
            from datetime import datetime

            if isinstance(start, str):
                start = datetime.fromisoformat(start.replace("Z", "+00:00"))
            if isinstance(end, str):
                end = datetime.fromisoformat(end.replace("Z", "+00:00"))

            duration = (end - start).total_seconds()
            if duration > 2.0:
                event.setdefault("tags", {})["slow_request"] = "true"
                event["tags"]["duration_seconds"] = str(round(duration, 2))
        except Exception:
            pass

    return event
