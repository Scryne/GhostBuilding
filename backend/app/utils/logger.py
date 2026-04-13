"""
logger.py — GhostBuilding Structured Logging Sistemi.

structlog ile JSON (production) ve renkli konsol (development) çıktısı üretir.
Her log kaydında: timestamp, level, service, request_id, user_id bulunur.

Kullanım:
    from app.utils.logger import get_logger
    logger = get_logger(__name__)
    logger.info("scan_started", lat=41.01, lon=28.97)
"""

from __future__ import annotations

import logging
import re
import sys
from typing import Any

import structlog


# ─── Hassas Veri Maskeleme Processor ─────────────────────────────────────────

_SENSITIVE_PATTERNS: list[tuple[re.Pattern, str]] = [
    # API Key ortam değişkenleri
    (
        re.compile(
            r"(GOOGLE_MAPS_API_KEY|BING_MAPS_API_KEY|OPENAI_API_KEY|"
            r"SENTINEL_HUB_CLIENT_ID|SENTINEL_HUB_CLIENT_SECRET|"
            r"MINIO_ACCESS_KEY|MINIO_SECRET_KEY|SECRET_KEY)"
            r"\s*[=:]\s*\S+",
            re.IGNORECASE,
        ),
        r"\1=***REDACTED***",
    ),
    # Google / OpenAI / Generic API key değerleri
    (
        re.compile(
            r"(AIza[A-Za-z0-9_-]{35})"
            r"|(sk-[A-Za-z0-9]{20,})"
            r"|(key-[A-Za-z0-9]{20,})",
            re.IGNORECASE,
        ),
        "***API_KEY_REDACTED***",
    ),
    # JWT Token
    (
        re.compile(r"(eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)"),
        "***JWT_REDACTED***",
    ),
    # Bearer token
    (re.compile(r"(Bearer\s+)\S+", re.IGNORECASE), r"\1***TOKEN_REDACTED***"),
    # Password alanları
    (
        re.compile(r"(password|passwd|pwd|secret)\s*[=:]\s*\S+", re.IGNORECASE),
        r"\1=***REDACTED***",
    ),
    # Database / Redis URL — şifre kısmı
    (
        re.compile(
            r"(postgresql|mysql|redis|mongodb)(\+\w+)?://"
            r"([^:]+):([^@]+)@",
            re.IGNORECASE,
        ),
        r"\1\2://\3:***REDACTED***@",
    ),
]


def _redact_value(value: str) -> str:
    """Metindeki hassas verileri maskeler."""
    for pattern, replacement in _SENSITIVE_PATTERNS:
        value = pattern.sub(replacement, value)
    return value


def sensitive_data_masker(
    logger: Any, method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """structlog processor: log event dict içindeki hassas verileri maskeler."""
    for key, value in event_dict.items():
        if isinstance(value, str):
            event_dict[key] = _redact_value(value)
    return event_dict


# ─── Service Context Processor ───────────────────────────────────────────────

def add_service_context(
    logger: Any, method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """Her log kaydına service adı ekler."""
    event_dict.setdefault("service", "ghostbuilding")
    return event_dict


# ─── structlog Konfigürasyonu ─────────────────────────────────────────────────

def configure_logging(*, environment: str = "dev", log_level: str = "INFO") -> None:
    """
    structlog ve stdlib logging altyapısını yapılandırır.

    Args:
        environment: "dev" veya "production"
        log_level: Log seviyesi (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """
    is_production = environment.lower() in ("production", "prod", "staging")

    # Timestamp formatı
    timestamper = structlog.processors.TimeStamper(fmt="iso")

    # Shared processors — hem structlog hem stdlib tarafından kullanılır
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        add_service_context,
        sensitive_data_masker,
        timestamper,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    if is_production:
        # Production: JSON çıktısı
        renderer = structlog.processors.JSONRenderer()
    else:
        # Development: Renkli konsol çıktısı
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # stdlib logging handler'ı da structlog formatına yönlendir
    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    root_logger = logging.getLogger()
    root_logger.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    root_logger.addHandler(handler)
    root_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # Gürültücü kütüphaneleri sustur
    for noisy in ("uvicorn.access", "uvicorn.error", "sqlalchemy.engine"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """
    Bağlamsal (context-bound) structlog logger döndürür.

    Kullanım:
        logger = get_logger(__name__)
        logger.info("event_name", key="value")
    """
    return structlog.get_logger(name)
