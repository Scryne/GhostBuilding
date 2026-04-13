"""
sanitizer.py — XSS ve injection koruması için input temizleme araçları.

Pydantic model'larda kullanılmak üzere string temizleme fonksiyonları
ve reusable validator'lar sağlar.

Önemli: SQL injection koruması SQLAlchemy ORM tarafından otomatik
olarak sağlanır. Bu modül uygulama katmanı XSS temizliğini kapsar.
"""

from __future__ import annotations

import html
import re
from typing import Optional


# XSS saldırılarında yaygın kullanılan tehlikeli pattern'ler
_XSS_PATTERNS = [
    re.compile(r"<\s*script", re.IGNORECASE),
    re.compile(r"javascript\s*:", re.IGNORECASE),
    re.compile(r"on\w+\s*=", re.IGNORECASE),       # onclick=, onload=, etc.
    re.compile(r"<\s*iframe", re.IGNORECASE),
    re.compile(r"<\s*object", re.IGNORECASE),
    re.compile(r"<\s*embed", re.IGNORECASE),
    re.compile(r"<\s*form", re.IGNORECASE),
    re.compile(r"<\s*img[^>]+onerror", re.IGNORECASE),
    re.compile(r"data\s*:\s*text/html", re.IGNORECASE),
    re.compile(r"vbscript\s*:", re.IGNORECASE),
    re.compile(r"expression\s*\(", re.IGNORECASE),   # CSS expression attack
]

# SQL injection işaretçileri (ek katman — ORM zaten korur)
_SQL_PATTERNS = [
    re.compile(r";\s*DROP\s+TABLE", re.IGNORECASE),
    re.compile(r";\s*DELETE\s+FROM", re.IGNORECASE),
    re.compile(r"UNION\s+SELECT", re.IGNORECASE),
    re.compile(r"'\s*OR\s+'1'\s*=\s*'1", re.IGNORECASE),
    re.compile(r"--\s*$", re.MULTILINE),
]


def sanitize_string(value: str) -> str:
    """
    String değeri XSS karakterlerinden temizler.

    1. HTML özel karakterlerini escape eder (&, <, >, ", ')
    2. Null byte'ları temizler
    3. Başta/sondaki boşlukları kırpar

    Args:
        value: Temizlenecek string.

    Returns:
        Temizlenmiş string.
    """
    if not value:
        return value

    # Null byte'ları temizle
    value = value.replace("\x00", "")

    # HTML escape
    value = html.escape(value, quote=True)

    # Başta/sonda boşlukları kırp
    return value.strip()


def contains_xss(value: str) -> bool:
    """
    String'de XSS saldırı pattern'i olup olmadığını kontrol eder.

    Args:
        value: Kontrol edilecek string.

    Returns:
        True ise tehlikeli pattern tespit edildi.
    """
    if not value:
        return False

    for pattern in _XSS_PATTERNS:
        if pattern.search(value):
            return True
    return False


def contains_sql_injection(value: str) -> bool:
    """
    String'de SQL injection pattern'i olup olmadığını kontrol eder.

    Not: Bu ek bir güvenlik katmanıdır. Asıl koruma
    SQLAlchemy ORM parametrize sorgularla sağlanır.

    Args:
        value: Kontrol edilecek string.

    Returns:
        True ise tehlikeli pattern tespit edildi.
    """
    if not value:
        return False

    for pattern in _SQL_PATTERNS:
        if pattern.search(value):
            return True
    return False


def validate_safe_string(value: Optional[str], field_name: str = "alan") -> Optional[str]:
    """
    Pydantic validator'larda kullanılmak üzere güvenlik kontrolü.

    XSS veya SQL injection tespit edilirse ValueError fırlatır.
    Aksi halde sanitize edilmiş string'i döndürür.

    Args:
        value: Doğrulanacak string.
        field_name: Hata mesajında kullanılacak alan adı.

    Returns:
        Sanitize edilmiş string veya None.

    Raises:
        ValueError: Tehlikeli içerik tespit edildiğinde.
    """
    if value is None:
        return None

    if contains_xss(value):
        raise ValueError(
            f"{field_name} alanında güvenlik açığı tespit edildi: "
            f"HTML/JavaScript içerik yasaktır."
        )

    if contains_sql_injection(value):
        raise ValueError(
            f"{field_name} alanında güvenlik açığı tespit edildi: "
            f"Yapısal sorgu işaretçileri yasaktır."
        )

    return sanitize_string(value)
