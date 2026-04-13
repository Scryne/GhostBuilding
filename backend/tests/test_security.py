"""
test_security.py — GhostBuilding güvenlik katmanı testleri.

OWASP Top 10 kontrol listesine göre kapsamlı güvenlik testleri:
- A01 Broken Access Control: role check decorator
- A02 Cryptographic Failures: bcrypt + token güvenliği
- A03 Injection: ORM + Pydantic + XSS koruması
- A05 Security Misconfiguration: DEBUG, security headers
- A07 Authentication Failures: brute force koruması
- Rate Limiting: sliding window kontrolü
- Input Validation: koordinat, string, XSS
- API Key Management: provider pattern
- Sensitive Log Filtering: API key/token maskeleme
"""

from __future__ import annotations

import os
import sys

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["REDIS_URL"] = "redis://localhost:6379/0"

import logging
import time
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

# ═══════════════════════════════════════════════════════════════════════════
# Import helpers — db session'ı SQLite uyumlu hale getiren mock
# ═══════════════════════════════════════════════════════════════════════════


def _mock_db_session_module():
    """
    app.db.session modülünü SQLite-uyumlu mock ile değiştirir.
    Bu sayede testlerde pool_size/max_overflow hatası oluşmaz.
    """
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
    from sqlalchemy.pool import StaticPool

    mock_engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        future=True,
        poolclass=StaticPool,
    )
    mock_session_factory = async_sessionmaker(
        bind=mock_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )

    # app.db.session modülünü mock'la
    mock_module = MagicMock()
    mock_module.engine = mock_engine
    mock_module.AsyncSessionLocal = mock_session_factory
    mock_module.get_db = AsyncMock()
    sys.modules["app.db.session"] = mock_module


# DB session modülünü test başlamadan önce mock'la
_mock_db_session_module()


# ═══════════════════════════════════════════════════════════════════════════
# 1. Rate Limiter Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestRateLimiter:
    """Rate limiting middleware testleri."""

    def test_resolve_client_ip_direct(self):
        """Doğrudan bağlantıda IP çözme."""
        from app.middleware.rate_limiter import _resolve_client_ip

        request = MagicMock()
        request.headers = {}
        request.client.host = "192.168.1.100"
        assert _resolve_client_ip(request) == "192.168.1.100"

    def test_resolve_client_ip_forwarded(self):
        """X-Forwarded-For header'ından IP çözme."""
        from app.middleware.rate_limiter import _resolve_client_ip

        request = MagicMock()
        request.headers = {"X-Forwarded-For": "10.0.0.1, 172.16.0.1"}
        request.client.host = "127.0.0.1"
        assert _resolve_client_ip(request) == "10.0.0.1"

    def test_match_rule_scan(self):
        """Scan endpoint kuralı eşleşmesi."""
        from app.middleware.rate_limiter import _match_rule

        rule = _match_rule("/api/v1/anomalies/scan", "POST")
        assert rule is not None
        assert rule.key_prefix == "rl:scan"
        assert rule.window_seconds == 3600  # 1 saat

    def test_match_rule_login(self):
        """Login endpoint kuralı eşleşmesi."""
        from app.middleware.rate_limiter import _match_rule

        rule = _match_rule("/api/v1/auth/login", "POST")
        assert rule is not None
        assert rule.key_prefix == "rl:login"
        assert rule.window_seconds == 60

    def test_match_rule_general_api(self):
        """Genel API kuralı eşleşmesi."""
        from app.middleware.rate_limiter import _match_rule

        rule = _match_rule("/api/v1/anomalies", "GET")
        assert rule is not None
        assert rule.key_prefix == "rl:api"
        assert rule.max_requests == 60

    def test_match_rule_exempt_path(self):
        """Muaf yollar için kural eşleşmemesi."""
        from app.middleware.rate_limiter import EXEMPT_PATHS

        assert "/api/v1/health" in EXEMPT_PATHS
        assert "/" in EXEMPT_PATHS

    @pytest.mark.asyncio
    async def test_check_rate_limit_allowed_grace(self):
        """Redis yoksa grace mode — izin ver."""
        from app.middleware.rate_limiter import check_rate_limit, RateLimitRule

        rule = RateLimitRule(max_requests=10, window_seconds=60, key_prefix="rl:test")

        with patch("app.middleware.rate_limiter._get_redis", return_value=None):
            is_allowed, remaining, limit, retry_after = await check_rate_limit(
                "127.0.0.1", rule
            )
            assert is_allowed is True
            assert remaining == 10
            assert retry_after == 0

    @pytest.mark.asyncio
    async def test_check_rate_limit_exceeded(self):
        """Limit aşıldığında izin verilmemesi."""
        from app.middleware.rate_limiter import check_rate_limit, RateLimitRule

        rule = RateLimitRule(max_requests=2, window_seconds=60, key_prefix="rl:test")

        mock_redis = AsyncMock()
        mock_pipe = AsyncMock()
        mock_pipe.execute = AsyncMock(return_value=[0, 3, True, True])  # zcard=3 > max=2
        mock_redis.pipeline = MagicMock(return_value=mock_pipe)
        mock_redis.zrem = AsyncMock()
        mock_redis.zrange = AsyncMock(return_value=[("ts1", time.time() - 30)])
        mock_redis.aclose = AsyncMock()

        with patch("app.middleware.rate_limiter._get_redis", return_value=mock_redis):
            is_allowed, remaining, limit, retry_after = await check_rate_limit(
                "127.0.0.1", rule
            )
            assert is_allowed is False
            assert remaining == 0

    @pytest.mark.asyncio
    async def test_check_rate_limit_within_limit(self):
        """Limit içindeyken izin verilmesi."""
        from app.middleware.rate_limiter import check_rate_limit, RateLimitRule

        rule = RateLimitRule(max_requests=10, window_seconds=60, key_prefix="rl:test")

        mock_redis = AsyncMock()
        mock_pipe = AsyncMock()
        mock_pipe.execute = AsyncMock(return_value=[0, 3, True, True])  # zcard=3 < max=10
        mock_redis.pipeline = MagicMock(return_value=mock_pipe)
        mock_redis.aclose = AsyncMock()

        with patch("app.middleware.rate_limiter._get_redis", return_value=mock_redis):
            is_allowed, remaining, limit, retry_after = await check_rate_limit(
                "127.0.0.1", rule
            )
            assert is_allowed is True
            assert remaining == 6  # 10 - 3 - 1 = 6

    def test_rate_limit_rules_scan_limits(self):
        """Scan rate limit: saatte 10."""
        from app.middleware.rate_limiter import _match_rule

        rule = _match_rule("/api/v1/anomalies/scan", "POST")
        assert rule.max_requests == 10
        assert rule.window_seconds == 3600

    def test_rate_limit_rules_login_limits(self):
        """Login rate limit: dakikada 5."""
        from app.middleware.rate_limiter import _match_rule

        rule = _match_rule("/api/v1/auth/login", "POST")
        assert rule.max_requests == 5
        assert rule.window_seconds == 60

    def test_rate_limit_rules_general_limits(self):
        """Genel API rate limit: dakikada 60."""
        from app.middleware.rate_limiter import _match_rule

        rule = _match_rule("/api/v1/anomalies/stats", "GET")
        assert rule.max_requests == 60
        assert rule.window_seconds == 60


# ═══════════════════════════════════════════════════════════════════════════
# 2. Input Validation Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestInputValidation:
    """Input validation testleri — koordinat, string, XSS."""

    def test_scan_request_valid(self):
        """Geçerli tarama isteği."""
        from app.routers.anomalies import ScanRequest

        req = ScanRequest(lat=41.0082, lng=28.9784, zoom=15, radius_km=5.0)
        assert req.lat == 41.0082
        assert req.lng == 28.9784
        assert req.radius_km == 5.0

    def test_scan_request_lat_out_of_range(self):
        """Enlem sınır dışı."""
        from app.routers.anomalies import ScanRequest

        with pytest.raises(Exception):
            ScanRequest(lat=91.0, lng=28.0)

    def test_scan_request_lat_negative_out_of_range(self):
        """Negatif enlem sınır dışı."""
        from app.routers.anomalies import ScanRequest

        with pytest.raises(Exception):
            ScanRequest(lat=-91.0, lng=28.0)

    def test_scan_request_lng_out_of_range(self):
        """Boylam sınır dışı."""
        from app.routers.anomalies import ScanRequest

        with pytest.raises(Exception):
            ScanRequest(lat=41.0, lng=181.0)

    def test_scan_request_radius_too_small(self):
        """radius_km çok küçük."""
        from app.routers.anomalies import ScanRequest

        with pytest.raises(Exception):
            ScanRequest(lat=41.0, lng=28.0, radius_km=0.01)

    def test_scan_request_radius_too_large(self):
        """radius_km çok büyük."""
        from app.routers.anomalies import ScanRequest

        with pytest.raises(Exception):
            ScanRequest(lat=41.0, lng=28.0, radius_km=51.0)

    def test_scan_request_boundary_lat(self):
        """Sınır değerleri: -90 ve 90."""
        from app.routers.anomalies import ScanRequest

        req_min = ScanRequest(lat=-90.0, lng=0.0)
        req_max = ScanRequest(lat=90.0, lng=0.0)
        assert req_min.lat == -90.0
        assert req_max.lat == 90.0

    def test_scan_request_radius_boundary_min(self):
        """radius_km alt sınır: 0.1"""
        from app.routers.anomalies import ScanRequest

        req = ScanRequest(lat=41.0, lng=28.0, radius_km=0.1)
        assert req.radius_km == 0.1

    def test_scan_request_radius_boundary_max(self):
        """radius_km üst sınır: 50.0"""
        from app.routers.anomalies import ScanRequest

        req = ScanRequest(lat=41.0, lng=28.0, radius_km=50.0)
        assert req.radius_km == 50.0

    def test_register_username_xss_rejected(self):
        """XSS içeren kullanıcı adı reddedilmeli (alphanumeric regex tarafından)."""
        from app.routers.auth import RegisterRequest

        with pytest.raises(Exception):
            RegisterRequest(
                email="test@test.com",
                username="<script>alert(1)</script>",
                password="SecurePass1",
            )

    def test_register_username_valid(self):
        """Geçerli kullanıcı adı."""
        from app.routers.auth import RegisterRequest

        req = RegisterRequest(
            email="test@test.com",
            username="ghost_hunter_42",
            password="SecurePass1",
        )
        assert req.username == "ghost_hunter_42"

    def test_register_password_min_length(self):
        """Şifre minimum uzunluk kontrolü."""
        from app.routers.auth import RegisterRequest

        with pytest.raises(Exception):
            RegisterRequest(
                email="test@test.com",
                username="valid_user",
                password="Short1",  # 6 chars < 8
            )

    def test_register_password_max_length(self):
        """Şifre maximum uzunluk kontrolü."""
        from app.routers.auth import RegisterRequest

        with pytest.raises(Exception):
            RegisterRequest(
                email="test@test.com",
                username="valid_user",
                password="A1" + "a" * 127,  # 129 chars > 128
            )

    def test_register_username_sql_injection(self):
        """SQL injection atasını yapm kullanıcı adı reddedilmeli."""
        from app.routers.auth import RegisterRequest

        with pytest.raises(Exception):
            RegisterRequest(
                email="test@test.com",
                username="a'; DROP TABLE users--",
                password="SecurePass1",
            )


# ═══════════════════════════════════════════════════════════════════════════
# 3. XSS Sanitizer Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestSanitizer:
    """XSS/SQL injection temizleme testleri."""

    def test_sanitize_string_html_escape(self):
        """HTML karakter escape."""
        from app.utils.sanitizer import sanitize_string

        assert sanitize_string("<script>") == "&lt;script&gt;"
        assert sanitize_string('"><img onerror=x>') == "&quot;&gt;&lt;img onerror=x&gt;"

    def test_sanitize_string_null_bytes(self):
        """Null byte temizliği."""
        from app.utils.sanitizer import sanitize_string

        assert "\x00" not in sanitize_string("test\x00string")

    def test_sanitize_string_trim(self):
        """Baştaki/sondaki boşluk kırpma."""
        from app.utils.sanitizer import sanitize_string

        assert sanitize_string("  hello  ") == "hello"

    def test_contains_xss_script_tag(self):
        """<script> tag tespiti."""
        from app.utils.sanitizer import contains_xss

        assert contains_xss("<script>alert(1)</script>") is True
        assert contains_xss("< SCRIPT >alert(1)") is True

    def test_contains_xss_javascript_protocol(self):
        """javascript: protocol tespiti."""
        from app.utils.sanitizer import contains_xss

        assert contains_xss("javascript:alert(1)") is True

    def test_contains_xss_event_handler(self):
        """Olay işleyici tespiti (onerror, onclick, vb.)."""
        from app.utils.sanitizer import contains_xss

        assert contains_xss('<img onerror="alert(1)">') is True
        assert contains_xss("onclick=steal()") is True

    def test_contains_xss_iframe(self):
        """<iframe> tespiti."""
        from app.utils.sanitizer import contains_xss

        assert contains_xss("<iframe src='evil.com'>") is True

    def test_contains_xss_data_uri(self):
        """data:text/html tespiti."""
        from app.utils.sanitizer import contains_xss

        assert contains_xss("data:text/html,<script>alert(1)</script>") is True

    def test_contains_xss_vbscript(self):
        """vbscript: tespiti."""
        from app.utils.sanitizer import contains_xss

        assert contains_xss("vbscript:msgbox") is True

    def test_contains_xss_clean_text(self):
        """Temiz metin geçmeli."""
        from app.utils.sanitizer import contains_xss

        assert contains_xss("Normal yorum metni") is False
        assert contains_xss("Bu bir test mesajıdır.") is False
        assert contains_xss("41.0082, 28.9784") is False

    def test_contains_sql_injection(self):
        """SQL injection pattern tespiti."""
        from app.utils.sanitizer import contains_sql_injection

        assert contains_sql_injection("; DROP TABLE users") is True
        assert contains_sql_injection("UNION SELECT * FROM passwords") is True
        assert contains_sql_injection("' OR '1'='1") is True

    def test_contains_sql_injection_delete(self):
        """SQL DELETE injection tespiti."""
        from app.utils.sanitizer import contains_sql_injection

        assert contains_sql_injection("; DELETE FROM users") is True

    def test_contains_sql_injection_clean(self):
        """Normal metin SQL injection olarak algılanmamalı."""
        from app.utils.sanitizer import contains_sql_injection

        assert contains_sql_injection("Normal metin") is False
        assert contains_sql_injection("User registered successfully") is False

    def test_validate_safe_string_xss(self):
        """XSS içeren string ValueError fırlatmalı."""
        from app.utils.sanitizer import validate_safe_string

        with pytest.raises(ValueError, match="güvenlik açığı"):
            validate_safe_string("<script>alert(1)</script>", "test")

    def test_validate_safe_string_sql_injection(self):
        """SQL injection içeren string ValueError fırlatmalı."""
        from app.utils.sanitizer import validate_safe_string

        with pytest.raises(ValueError, match="güvenlik açığı"):
            validate_safe_string("'; DROP TABLE users--", "test")

    def test_validate_safe_string_clean(self):
        """Temiz string geçmeli."""
        from app.utils.sanitizer import validate_safe_string

        result = validate_safe_string("Temiz metin", "test")
        assert result == "Temiz metin"

    def test_validate_safe_string_none(self):
        """None değer None döndürmeli."""
        from app.utils.sanitizer import validate_safe_string

        assert validate_safe_string(None, "test") is None

    def test_validate_safe_string_empty(self):
        """Boş string geçmeli."""
        from app.utils.sanitizer import validate_safe_string

        result = validate_safe_string("", "test")
        assert result == ""


# ═══════════════════════════════════════════════════════════════════════════
# 4. Security Headers Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestSecurityHeaders:
    """Güvenlik HTTP başlıkları testleri."""

    @pytest.mark.asyncio
    async def test_security_headers_present_dev(self):
        """Dev modunda güvenlik başlıklarının mevcut olduğu kontrol edilir."""
        from app.middleware.security_headers import SecurityHeadersMiddleware

        mock_app = AsyncMock()
        mock_request = MagicMock()
        mock_response = MagicMock()
        mock_response.headers = {}

        async def mock_call_next(request):
            return mock_response

        with patch("app.middleware.security_headers.settings") as mock_settings:
            mock_settings.ENVIRONMENT = "dev"
            middleware = SecurityHeadersMiddleware(mock_app)
            response = await middleware.dispatch(mock_request, mock_call_next)

        assert response.headers["X-Frame-Options"] == "DENY"
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-XSS-Protection"] == "1; mode=block"
        assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
        assert "Content-Security-Policy" in response.headers
        assert "Permissions-Policy" in response.headers

    @pytest.mark.asyncio
    async def test_hsts_absent_in_dev(self):
        """HSTS dev modunda olmamalı."""
        from app.middleware.security_headers import SecurityHeadersMiddleware

        mock_app = AsyncMock()
        mock_request = MagicMock()
        mock_response = MagicMock()
        mock_response.headers = {}

        async def mock_call_next(request):
            return mock_response

        with patch("app.middleware.security_headers.settings") as mock_settings:
            mock_settings.ENVIRONMENT = "dev"
            middleware = SecurityHeadersMiddleware(mock_app)
            response = await middleware.dispatch(mock_request, mock_call_next)
            assert "Strict-Transport-Security" not in response.headers

    @pytest.mark.asyncio
    async def test_hsts_present_in_production(self):
        """HSTS production'da aktif olmalı."""
        from app.middleware.security_headers import SecurityHeadersMiddleware

        mock_app = AsyncMock()
        mock_request = MagicMock()
        mock_response = MagicMock()
        mock_response.headers = {}

        async def mock_call_next(request):
            return mock_response

        with patch("app.middleware.security_headers.settings") as mock_settings:
            mock_settings.ENVIRONMENT = "production"
            middleware = SecurityHeadersMiddleware(mock_app)
            response = await middleware.dispatch(mock_request, mock_call_next)
            assert "Strict-Transport-Security" in response.headers
            assert "31536000" in response.headers["Strict-Transport-Security"]
            assert "includeSubDomains" in response.headers["Strict-Transport-Security"]

    @pytest.mark.asyncio
    async def test_csp_strict_in_production(self):
        """Production CSP'de unsafe-eval olmamalı."""
        from app.middleware.security_headers import SecurityHeadersMiddleware

        mock_app = AsyncMock()
        mock_request = MagicMock()
        mock_response = MagicMock()
        mock_response.headers = {}

        async def mock_call_next(request):
            return mock_response

        with patch("app.middleware.security_headers.settings") as mock_settings:
            mock_settings.ENVIRONMENT = "prod"
            middleware = SecurityHeadersMiddleware(mock_app)
            response = await middleware.dispatch(mock_request, mock_call_next)
            csp = response.headers["Content-Security-Policy"]
            assert "unsafe-eval" not in csp
            assert "frame-ancestors 'none'" in csp


# ═══════════════════════════════════════════════════════════════════════════
# 5. Sensitive Log Filter Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestSensitiveLogFilter:
    """Hassas veri log filtreleme testleri."""

    def test_redact_api_key_env_var(self):
        """API key environment variable maskeleme."""
        from app.utils.sensitive_log_filter import SensitiveDataFilter

        f = SensitiveDataFilter()
        result = f._redact("GOOGLE_MAPS_API_KEY=AIzaSyBxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx")
        assert "AIzaSyB" not in result
        assert "REDACTED" in result

    def test_redact_openai_key(self):
        """OpenAI API key maskeleme."""
        from app.utils.sensitive_log_filter import SensitiveDataFilter

        f = SensitiveDataFilter()
        result = f._redact("OPENAI_API_KEY=sk-abcdefghijklmnopqrstuvwxyz1234567890")
        assert "sk-abcdefghijklmnopqrst" not in result
        assert "REDACTED" in result

    def test_redact_jwt_token(self):
        """JWT token maskeleme."""
        from app.utils.sensitive_log_filter import SensitiveDataFilter

        f = SensitiveDataFilter()
        token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
        result = f._redact(f"Token: {token}")
        assert token not in result
        assert "REDACTED" in result

    def test_redact_bearer_token(self):
        """Bearer token header maskeleme."""
        from app.utils.sensitive_log_filter import SensitiveDataFilter

        f = SensitiveDataFilter()
        result = f._redact("Authorization: Bearer some_secret_token_here")
        assert "some_secret_token_here" not in result
        assert "REDACTED" in result

    def test_redact_password(self):
        """Şifre maskeleme."""
        from app.utils.sensitive_log_filter import SensitiveDataFilter

        f = SensitiveDataFilter()
        result = f._redact("password=supersecret123")
        assert "supersecret123" not in result
        assert "REDACTED" in result

    def test_redact_secret_key(self):
        """SECRET_KEY maskeleme."""
        from app.utils.sensitive_log_filter import SensitiveDataFilter

        f = SensitiveDataFilter()
        result = f._redact("SECRET_KEY=my-ultra-secret-key")
        assert "my-ultra-secret-key" not in result
        assert "REDACTED" in result

    def test_redact_database_url(self):
        """Database URL şifre maskeleme."""
        from app.utils.sensitive_log_filter import SensitiveDataFilter

        f = SensitiveDataFilter()
        result = f._redact("postgresql+asyncpg://user:secretpass@localhost/db")
        assert "secretpass" not in result
        assert "REDACTED" in result

    def test_redact_redis_url(self):
        """Redis URL şifre maskeleme."""
        from app.utils.sensitive_log_filter import SensitiveDataFilter

        f = SensitiveDataFilter()
        result = f._redact("redis://default:mypassword@redis-host:6379/0")
        assert "mypassword" not in result
        assert "REDACTED" in result

    def test_clean_text_not_redacted(self):
        """Temiz metin maskelenmemeli."""
        from app.utils.sensitive_log_filter import SensitiveDataFilter

        f = SensitiveDataFilter()
        result = f._redact("Normal log message about anomaly detection")
        assert result == "Normal log message about anomaly detection"

    def test_log_record_filter_msg(self):
        """Log kaydı msg alanı filtreleme."""
        from app.utils.sensitive_log_filter import SensitiveDataFilter

        f = SensitiveDataFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="OPENAI_API_KEY=sk-1234567890abcdefghijklmn",
            args=None,
            exc_info=None,
        )

        assert f.filter(record) is True  # Kayıt düşürülmemeli
        assert "sk-1234567890abcdef" not in record.msg

    def test_log_record_filter_args_tuple(self):
        """Log kaydı args (tuple) filtreleme."""
        from app.utils.sensitive_log_filter import SensitiveDataFilter

        f = SensitiveDataFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Connecting to %s",
            args=("postgresql://user:secretpass@localhost/db",),
            exc_info=None,
        )

        assert f.filter(record) is True
        # Tuple arg'ları maskelenmiş olmalı
        assert "secretpass" not in str(record.args)


# ═══════════════════════════════════════════════════════════════════════════
# 6. API Key Provider Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestAPIKeyProvider:
    """API key yönetimi testleri."""

    def test_get_provider(self):
        """Tanımlı provider'ı almak."""
        from app.utils.api_key_provider import get_api_key_provider

        provider = get_api_key_provider("google_maps")
        assert provider.provider_name == "Google Maps"

    def test_get_provider_bing(self):
        """Bing maps provider."""
        from app.utils.api_key_provider import get_api_key_provider

        provider = get_api_key_provider("bing_maps")
        assert provider.provider_name == "Bing Maps"

    def test_get_provider_sentinel(self):
        """Sentinel Hub provider."""
        from app.utils.api_key_provider import get_api_key_provider

        provider = get_api_key_provider("sentinel_hub")
        assert provider.provider_name == "Sentinel Hub"

    def test_get_provider_openai(self):
        """OpenAI provider."""
        from app.utils.api_key_provider import get_api_key_provider

        provider = get_api_key_provider("openai")
        assert provider.provider_name == "OpenAI"

    def test_get_provider_unknown(self):
        """Tanımsız provider KeyError fırlatmalı."""
        from app.utils.api_key_provider import get_api_key_provider

        with pytest.raises(KeyError, match="Tanımsız"):
            get_api_key_provider("nonexistent_provider")

    def test_environment_key_provider_not_configured(self):
        """Environment variable tanımlı değil → False."""
        from app.utils.api_key_provider import EnvironmentKeyProvider

        provider = EnvironmentKeyProvider(
            name="Test",
            env_var="DEFINITELY_NOT_SET_ENV_VAR_XYZ",
        )
        assert provider.is_configured() is False

    def test_environment_key_provider_get_key_none(self):
        """Tanımlı olmayan key → None."""
        from app.utils.api_key_provider import EnvironmentKeyProvider

        provider = EnvironmentKeyProvider(
            name="Test",
            env_var="DEFINITELY_NOT_SET_ENV_VAR_XYZ",
        )
        assert provider.get_key() is None

    def test_environment_key_provider_get_key(self):
        """Environment variable'dan key okuma."""
        from app.utils.api_key_provider import EnvironmentKeyProvider

        os.environ["TEST_PROVIDER_KEY_SEC"] = "test-key-value-123"
        provider = EnvironmentKeyProvider(
            name="Test",
            env_var="TEST_PROVIDER_KEY_SEC",
        )

        assert provider.get_key() == "test-key-value-123"
        assert provider.is_configured() is True

        del os.environ["TEST_PROVIDER_KEY_SEC"]

    def test_key_rotation(self):
        """Key rotation mekanizması."""
        from app.utils.api_key_provider import EnvironmentKeyProvider

        os.environ["ROT_KEY_1"] = "key-1"
        os.environ["ROT_KEY_2"] = "key-2"

        provider = EnvironmentKeyProvider(
            name="RotationTest",
            env_var="ROT_KEY_1",
            rotation_env_vars=["ROT_KEY_2"],
        )

        assert provider.get_key() == "key-1"

        rotated = provider.rotate_key()
        assert rotated == "key-2"

        # Tekrar rotate edince ilk key'e dönmeli
        rotated2 = provider.rotate_key()
        assert rotated2 == "key-1"

        del os.environ["ROT_KEY_1"]
        del os.environ["ROT_KEY_2"]

    def test_single_key_rotation_noop(self):
        """Tek key'de rotation → aynı key döner."""
        from app.utils.api_key_provider import EnvironmentKeyProvider

        os.environ["SINGLE_ROT_KEY"] = "only-key"
        provider = EnvironmentKeyProvider(
            name="SingleRotTest",
            env_var="SINGLE_ROT_KEY",
        )

        rotated = provider.rotate_key()
        assert rotated == "only-key"

        del os.environ["SINGLE_ROT_KEY"]

    def test_register_custom_provider(self):
        """Özel provider kaydı."""
        from app.utils.api_key_provider import (
            EnvironmentKeyProvider,
            register_provider,
            get_api_key_provider,
        )

        custom = EnvironmentKeyProvider(
            name="Custom",
            env_var="CUSTOM_KEY_SEC_TEST",
        )
        register_provider("custom_sec_test", custom)

        fetched = get_api_key_provider("custom_sec_test")
        assert fetched.provider_name == "Custom"


# ═══════════════════════════════════════════════════════════════════════════
# 7. OWASP A01 — Broken Access Control Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestAccessControl:
    """Rol tabanlı erişim kontrolü testleri."""

    def test_require_role_factory(self):
        """require_role dependency factory oluşturma."""
        from app.services.auth_service import require_role
        from app.models.enums import UserRole

        checker = require_role(UserRole.ADMIN)
        assert callable(checker)

    def test_require_role_multiple_roles(self):
        """Birden fazla rol ile require_role."""
        from app.services.auth_service import require_role
        from app.models.enums import UserRole

        checker = require_role(UserRole.MODERATOR, UserRole.ADMIN)
        assert callable(checker)

    def test_user_roles_enum(self):
        """UserRole enum değerleri doğrulaması."""
        from app.models.enums import UserRole

        assert UserRole.USER.value == "USER"
        assert UserRole.MODERATOR.value == "MODERATOR"
        assert UserRole.ADMIN.value == "ADMIN"


# ═══════════════════════════════════════════════════════════════════════════
# 8. OWASP A02 — Cryptographic Failures Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestCryptography:
    """Kriptografik güvenlik testleri."""

    def test_bcrypt_hash_and_verify(self):
        """Bcrypt hash/verify döngüsü."""
        from app.services.auth_service import AuthService

        password = "TestPassword123"
        hashed = AuthService.hash_password(password)

        assert hashed != password
        assert hashed.startswith("$2b$") or hashed.startswith("$2a$")
        assert AuthService.verify_password(password, hashed) is True
        assert AuthService.verify_password("wrong", hashed) is False

    def test_bcrypt_unique_hashes(self):
        """Aynı şifre farklı hash'ler üretmeli (salt)."""
        from app.services.auth_service import AuthService

        password = "SamePass123"
        hash1 = AuthService.hash_password(password)
        hash2 = AuthService.hash_password(password)
        assert hash1 != hash2  # Salt farklı olacağından hash'ler farklı olmalı

    def test_jwt_access_token_creation(self):
        """JWT access token oluşturma ve doğrulama."""
        from app.services.auth_service import AuthService

        token = AuthService.create_access_token(
            user_id="test-uuid-1234",
            role="USER",
        )
        payload = AuthService.decode_token(token)

        assert payload["sub"] == "test-uuid-1234"
        assert payload["role"] == "USER"
        assert payload["type"] == "access"
        assert "jti" in payload
        assert "exp" in payload
        assert "iat" in payload

    def test_jwt_refresh_token_type(self):
        """Refresh token doğru tip içermeli."""
        from app.services.auth_service import AuthService

        token = AuthService.create_refresh_token(user_id="test-uuid-5678")
        payload = AuthService.decode_token(token)

        assert payload["type"] == "refresh"
        assert payload["sub"] == "test-uuid-5678"

    def test_invalid_token_rejected(self):
        """Geçersiz token reddedilmeli."""
        from app.services.auth_service import AuthService
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            AuthService.decode_token("invalid.token.here")
        assert exc_info.value.status_code == 401

    def test_tampered_token_rejected(self):
        """Değiştirilmiş token reddedilmeli."""
        from app.services.auth_service import AuthService
        from fastapi import HTTPException

        token = AuthService.create_access_token(
            user_id="test-uuid", role="USER"
        )
        # Token'ı boz
        tampered = token[:-5] + "XXXXX"
        with pytest.raises(HTTPException) as exc_info:
            AuthService.decode_token(tampered)
        assert exc_info.value.status_code == 401


# ═══════════════════════════════════════════════════════════════════════════
# 9. OWASP A07 — Brute Force Protection Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestBruteForceProtection:
    """Brute force koruması testleri."""

    @pytest.mark.asyncio
    async def test_check_brute_force_unlocked(self):
        """Kilitli olmayan hesap geçmeli."""
        from app.services.auth_service import AuthService

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value="2")  # 2 < 5 maks
        mock_redis.aclose = AsyncMock()

        with patch("app.services.auth_service._get_redis", return_value=mock_redis):
            # Hata fırlatmamalı
            await AuthService.check_brute_force("test@test.com")

    @pytest.mark.asyncio
    async def test_check_brute_force_locked(self):
        """5 başarısız denemeden sonra hesap kilitlenmeli."""
        from app.services.auth_service import AuthService
        from fastapi import HTTPException

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value="5")  # 5 >= 5 maks
        mock_redis.aclose = AsyncMock()

        with patch("app.services.auth_service._get_redis", return_value=mock_redis):
            with pytest.raises(HTTPException) as exc_info:
                await AuthService.check_brute_force("test@test.com")
            assert exc_info.value.status_code == 429
            assert "account_locked" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_check_brute_force_above_limit(self):
        """5'ten fazla başarısız deneme → kilitli."""
        from app.services.auth_service import AuthService
        from fastapi import HTTPException

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value="10")
        mock_redis.aclose = AsyncMock()

        with patch("app.services.auth_service._get_redis", return_value=mock_redis):
            with pytest.raises(HTTPException):
                await AuthService.check_brute_force("hacker@evil.com")

    @pytest.mark.asyncio
    async def test_record_failed_attempt(self):
        """Başarısız deneme kaydı."""
        from app.services.auth_service import AuthService

        mock_redis = AsyncMock()
        mock_pipe = AsyncMock()
        mock_pipe.execute = AsyncMock()
        mock_redis.pipeline = MagicMock(return_value=mock_pipe)
        mock_redis.aclose = AsyncMock()

        with patch("app.services.auth_service._get_redis", return_value=mock_redis):
            await AuthService.record_failed_attempt("test@test.com")
            mock_pipe.incr.assert_called_once()
            mock_pipe.expire.assert_called_once()

    @pytest.mark.asyncio
    async def test_clear_failed_attempts(self):
        """Başarılı giriş sonrası sayaç temizleme."""
        from app.services.auth_service import AuthService

        mock_redis = AsyncMock()
        mock_redis.delete = AsyncMock()
        mock_redis.aclose = AsyncMock()

        with patch("app.services.auth_service._get_redis", return_value=mock_redis):
            await AuthService.clear_failed_attempts("test@test.com")
            mock_redis.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_token_blacklist_add(self):
        """Token blacklist'e ekleme."""
        from app.services.auth_service import AuthService

        token = AuthService.create_access_token(
            user_id="test-uuid", role="USER"
        )

        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock()
        mock_redis.aclose = AsyncMock()

        with patch("app.services.auth_service._get_redis", return_value=mock_redis):
            await AuthService.blacklist_token(token)
            mock_redis.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_token_blacklist_check(self):
        """Blacklist'teki token True döndürmeli."""
        from app.services.auth_service import AuthService

        token = AuthService.create_access_token(
            user_id="test-uuid", role="USER"
        )

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value="1")  # Blacklist'te var
        mock_redis.aclose = AsyncMock()

        with patch("app.services.auth_service._get_redis", return_value=mock_redis):
            is_blacklisted = await AuthService.is_token_blacklisted(token)
            assert is_blacklisted is True

    @pytest.mark.asyncio
    async def test_token_not_blacklisted(self):
        """Blacklist'te olmayan token False döndürmeli."""
        from app.services.auth_service import AuthService

        token = AuthService.create_access_token(
            user_id="test-uuid", role="USER"
        )

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)  # Blacklist'te yok
        mock_redis.aclose = AsyncMock()

        with patch("app.services.auth_service._get_redis", return_value=mock_redis):
            is_blacklisted = await AuthService.is_token_blacklisted(token)
            assert is_blacklisted is False


# ═══════════════════════════════════════════════════════════════════════════
# 10. OWASP A05 — Security Misconfiguration Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestSecurityMisconfiguration:
    """Güvenlik yapılandırma testleri."""

    def test_debug_default_false(self):
        """DEBUG varsayılan olarak False olmalı."""
        from app.config import Settings

        assert Settings.model_fields["DEBUG"].default is False

    def test_password_validation_uppercase_required(self):
        """Şifre büyük harf gereksinimi."""
        from app.services.auth_service import AuthService
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            AuthService.validate_password("alllowercase1")
        assert exc_info.value.status_code == 422

    def test_password_validation_digit_required(self):
        """Şifre rakam gereksinimi."""
        from app.services.auth_service import AuthService
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            AuthService.validate_password("NoDigitsHere")
        assert exc_info.value.status_code == 422

    def test_password_validation_min_length(self):
        """Şifre minimum uzunluk gereksinimi."""
        from app.services.auth_service import AuthService
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            AuthService.validate_password("Sh0rt")
        assert exc_info.value.status_code == 422

    def test_password_validation_passes(self):
        """Geçerli şifre doğrulama."""
        from app.services.auth_service import AuthService

        # Hata fırlatmamalı
        AuthService.validate_password("ValidPass123")

    def test_password_validation_multiple_rules(self):
        """Birden fazla kural ihlali."""
        from app.services.auth_service import AuthService
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            AuthService.validate_password("short")  # kısa + büyük harf yok + rakam yok
        assert exc_info.value.status_code == 422


# ═══════════════════════════════════════════════════════════════════════════
# 11. Verification Comment XSS Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestVerificationCommentSanitization:
    """Doğrulama yorum alanı XSS temizleme testleri."""

    def test_comment_xss_rejected(self):
        """XSS içeren yorum reddedilmeli."""
        from app.routers.verifications import VerifyRequest
        from app.models.enums import VerificationVote

        with pytest.raises(Exception):
            VerifyRequest(
                vote=VerificationVote.CONFIRM,
                comment="<script>alert('xss')</script>",
            )

    def test_comment_iframe_rejected(self):
        """iframe içeren yorum reddedilmeli."""
        from app.routers.verifications import VerifyRequest
        from app.models.enums import VerificationVote

        with pytest.raises(Exception):
            VerifyRequest(
                vote=VerificationVote.CONFIRM,
                comment="<iframe src='http://evil.com'></iframe>",
            )

    def test_comment_clean_accepted(self):
        """Temiz yorum kabul edilmeli."""
        from app.routers.verifications import VerifyRequest
        from app.models.enums import VerificationVote

        req = VerifyRequest(
            vote=VerificationVote.CONFIRM,
            comment="Google uydu görüntüsünde yapı net görünüyor.",
        )
        assert req.comment is not None

    def test_comment_none_accepted(self):
        """None yorum kabul edilmeli."""
        from app.routers.verifications import VerifyRequest
        from app.models.enums import VerificationVote

        req = VerifyRequest(
            vote=VerificationVote.DENY,
            comment=None,
        )
        assert req.comment is None

    def test_comment_max_length(self):
        """Yorum max uzunluk kontrolü (2000 karakter)."""
        from app.routers.verifications import VerifyRequest
        from app.models.enums import VerificationVote

        with pytest.raises(Exception):
            VerifyRequest(
                vote=VerificationVote.UNCERTAIN,
                comment="X" * 2001,
            )

    def test_comment_within_max_length(self):
        """2000 karakter sınırında yorum kabul edilmeli."""
        from app.routers.verifications import VerifyRequest
        from app.models.enums import VerificationVote

        req = VerifyRequest(
            vote=VerificationVote.CONFIRM,
            comment="A" * 2000,
        )
        assert len(req.comment) == 2000
