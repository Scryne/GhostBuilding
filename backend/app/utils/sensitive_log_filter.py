"""
sensitive_log_filter.py — Hassas bilgileri log'lardan filtreleyen handler.

API key'ler, şifreler, token'lar ve diğer hassas verilerin
günlük kayıtlarına düşmesini engeller.

Kullanım:
    import logging
    from app.utils.sensitive_log_filter import SensitiveDataFilter

    logger = logging.getLogger()
    logger.addFilter(SensitiveDataFilter())
"""

from __future__ import annotations

import logging
import re
from typing import Pattern


class SensitiveDataFilter(logging.Filter):
    """
    Log mesajlarından hassas verileri maskeleyen filter.

    Maskelenen veri tipleri:
    - API key'ler (Google, Bing, Sentinel Hub, OpenAI, vb.)
    - JWT token'lar
    - Şifreler
    - Database connection string'lerindeki şifreler
    - Redis URL'lerindeki şifreler
    """

    # (pattern, replacement) çiftleri
    PATTERNS: list[tuple[Pattern, str]] = [
        # API key pattern'leri — ortam değişkeni değerleri
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
        # API key değerleri — yaygın formatlar
        (
            re.compile(
                r"(AIza[A-Za-z0-9_-]{35})"        # Google API Key
                r"|(sk-[A-Za-z0-9]{20,})"         # OpenAI API Key
                r"|(key-[A-Za-z0-9]{20,})",        # Generic API Key
                re.IGNORECASE,
            ),
            "***API_KEY_REDACTED***",
        ),
        # JWT Token'lar
        (
            re.compile(
                r"(eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)",
            ),
            "***JWT_REDACTED***",
        ),
        # Bearer token header'ı
        (
            re.compile(
                r"(Bearer\s+)\S+",
                re.IGNORECASE,
            ),
            r"\1***TOKEN_REDACTED***",
        ),
        # Şifre alanları
        (
            re.compile(
                r"(password|passwd|pwd|secret)\s*[=:]\s*\S+",
                re.IGNORECASE,
            ),
            r"\1=***REDACTED***",
        ),
        # Database URL'leri — şifre kısmı
        (
            re.compile(
                r"(postgresql|mysql|redis|mongodb)(\+\w+)?://"
                r"([^:]+):([^@]+)@",
                re.IGNORECASE,
            ),
            r"\1\2://\3:***REDACTED***@",
        ),
    ]

    def filter(self, record: logging.LogRecord) -> bool:
        """
        Log kaydındaki hassas verileri maskeler.

        Returns:
            Her zaman True — kayıt düşürülmez, sadece maskelenir.
        """
        if record.msg and isinstance(record.msg, str):
            record.msg = self._redact(record.msg)

        if record.args:
            if isinstance(record.args, dict):
                record.args = {
                    k: self._redact(str(v)) if isinstance(v, str) else v
                    for k, v in record.args.items()
                }
            elif isinstance(record.args, tuple):
                record.args = tuple(
                    self._redact(str(a)) if isinstance(a, str) else a
                    for a in record.args
                )

        return True

    def _redact(self, text: str) -> str:
        """Metindeki hassas verileri maskeler."""
        for pattern, replacement in self.PATTERNS:
            text = pattern.sub(replacement, text)
        return text
