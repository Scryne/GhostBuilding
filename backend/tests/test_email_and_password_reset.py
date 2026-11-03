"""
test_email_and_password_reset.py — SMTP gönderimi, e-posta doğrulama ve şifre sıfırlama.

Gönderim gerçek bir SMTP konuşmasıyla sınanır: ``aiosmtpd`` ile yerel bir sahte sunucu açılır,
uygulama ``smtplib`` ile ona bağlanır, ileti sunucuda yakalanır ve içindeki bağlantı
izlenerek akış uçtan uca yürütülür. STARTTLS ve SMTPS yolları ``trustme`` ile üretilen
test sertifikasıyla, sertifika doğrulaması KAPATILMADAN sınanır.
"""

from __future__ import annotations

import email
import logging
import re
import socket
import uuid
from datetime import timedelta
from email.message import Message
from email.policy import default as default_policy
from typing import Any
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import jwt
import pytest
import pytest_asyncio
from aiosmtpd.controller import Controller
from aiosmtpd.smtp import AuthResult
from fastapi import HTTPException
from httpx import AsyncClient
from sqlalchemy import select

from app.config import settings
from app.services import email_service
from tests.conftest import TestUser, auth_header


# auth_service modül düzeyinde İÇE AKTARILMAZ: conftest, ``app.models.user.User``'ı test
# modeliyle ilk içe aktarmadan önce yamalar; toplama anında içe aktarmak gerçek (PostGIS'li)
# modeli bağlar ve tüm test oturumunu bozar. Diğer test dosyaları da aynı deseni izler.
def _svc():
    import sys

    if "app.main" not in sys.modules:
        # İlk içe aktarma, ``client`` fikstürünün yaptığı gibi model yaması altında olmalı;
        # bu dosya tek başına (ya da ilk sırada) koşarken de modüller test modellerini bağlasın.
        from tests.conftest import _patch_models

        patches = _patch_models()
        for p in patches:
            p.start()
        try:
            import app.main  # noqa: F401
        finally:
            for p in patches:
                p.stop()

    from app.services import auth_service

    return auth_service


class _Lazy:
    def __init__(self, name: str) -> None:
        self._name = name

    def __getattr__(self, attr: str) -> Any:
        # pytest toplarken ``__test__`` gibi özellikleri sorar; onlar içe aktarmayı tetiklemesin
        if attr.startswith("_"):
            raise AttributeError(attr)
        return getattr(getattr(_svc(), self._name), attr)


AuthService: Any = _Lazy("AuthService")
ALGORITHM = "HS256"
EMAIL_VERIFY_AUDIENCE = "ghostbuilding:email-verify"
PASSWORD_RESET_AUDIENCE = "ghostbuilding:password-reset"


def session_revoked(payload, user):
    return _svc().session_revoked(payload, user)

FRONTEND = "https://app.ghostbuilding.test"
SENDER = "GhostBuilding <noreply@ghostbuilding.test>"


# ═══════════════════════════════════════════════════════════════════════════
# Yardımcılar: sahte SMTP sunucusu, durumlu sahte Redis
# ═══════════════════════════════════════════════════════════════════════════


class _Inbox:
    """aiosmtpd handler'ı — gelen her iletiyi zarfıyla saklar."""

    def __init__(self) -> None:
        self.envelopes: list[Any] = []

    async def handle_DATA(self, server, session, envelope):  # noqa: N802 (aiosmtpd arayüzü)
        self.envelopes.append(envelope)
        return "250 Message accepted for delivery"

    @property
    def messages(self) -> list[Message]:
        return [email.message_from_bytes(e.original_content, policy=default_policy) for e in self.envelopes]

    def recipients(self) -> list[str]:
        return [rcpt for e in self.envelopes for rcpt in e.rcpt_tos]


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _start_server(**kwargs: Any) -> tuple[Controller, _Inbox]:
    inbox = _Inbox()
    controller = Controller(inbox, hostname="127.0.0.1", port=_free_port(), **kwargs)
    controller.start()
    return controller, inbox


@pytest.fixture
def smtp_server(monkeypatch):
    """Düz SMTP (security=none) sahte sunucu + uygulama ayarları."""
    controller, inbox = _start_server()
    monkeypatch.setattr(settings, "SMTP_HOST", "127.0.0.1")
    monkeypatch.setattr(settings, "SMTP_PORT", controller.port)
    monkeypatch.setattr(settings, "SMTP_SECURITY", "none")
    monkeypatch.setattr(settings, "SMTP_FROM", SENDER)
    monkeypatch.setattr(settings, "SMTP_USERNAME", None)
    monkeypatch.setattr(settings, "SMTP_PASSWORD", None)
    monkeypatch.setattr(settings, "FRONTEND_URL", FRONTEND + "/")
    yield inbox
    controller.stop()


@pytest.fixture
def email_disabled(monkeypatch):
    monkeypatch.setattr(settings, "SMTP_HOST", None)


@pytest.fixture
def tls_ca():
    trustme = pytest.importorskip("trustme")
    ca = trustme.CA()
    server_cert = ca.issue_cert("127.0.0.1", "localhost")
    return ca, server_cert


def _client_context_trusting(ca):
    import ssl

    ctx = ssl.create_default_context()  # hostname + sertifika doğrulaması AÇIK
    ca.configure_trust(ctx)
    return ctx


def _server_context(server_cert):
    import ssl

    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_cert.configure_cert(ctx)
    return ctx


class FakeRedis:
    """auth_service'in kullandığı Redis alt kümesinin durumlu taklidi (TTL yok sayılır)."""

    def __init__(self) -> None:
        self.data: dict[str, Any] = {}

    async def get(self, key):
        return self.data.get(key)

    async def set(self, key, value, ex=None):
        self.data[key] = value
        return True

    async def delete(self, *keys):
        return sum(1 for k in keys if self.data.pop(k, None) is not None)

    async def incr(self, key):
        self.data[key] = int(self.data.get(key, 0)) + 1
        return self.data[key]

    async def expire(self, key, ttl, nx=False):
        return True

    async def aclose(self):
        return None

    def pipeline(self):
        return _FakePipeline(self)


class _FakePipeline:
    def __init__(self, redis: FakeRedis) -> None:
        self.redis = redis
        self.ops: list[tuple[str, tuple, dict]] = []

    def __getattr__(self, name):
        def _queue(*args, **kwargs):
            self.ops.append((name, args, kwargs))
            return self

        return _queue

    async def execute(self):
        results = [await getattr(self.redis, name)(*a, **kw) for name, a, kw in self.ops]
        self.ops = []
        return results


@pytest.fixture
def fake_redis():
    fake = FakeRedis()

    async def _get():
        return fake

    with patch("app.services.auth_service._get_redis", side_effect=_get):
        yield fake


async def _make_user(db_session, *, password: str = "OldPass12", verified: bool = False) -> TestUser:
    suffix = uuid.uuid4().hex[:10]
    user = TestUser(
        id=str(uuid.uuid4()),
        email=f"kisi_{suffix}@ghostbuilding.io",
        username=f"kisi_{suffix}",
        hashed_password=AuthService.hash_password(password),
        role="USER",
        is_active=True,
        is_verified=verified,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


def _text_body(msg: Message) -> str:
    return msg.get_body(preferencelist=("plain",)).get_content()


def _html_body(msg: Message) -> str:
    return msg.get_body(preferencelist=("html",)).get_content()


def _link_from(msg: Message) -> str:
    match = re.search(r"https?://\S+", _text_body(msg))
    assert match, "iletide bağlantı yok"
    return match.group(0)


def _token_from(msg: Message) -> str:
    return parse_qs(urlparse(_link_from(msg)).fragment)["token"][0]


def _app_log_text(caplog) -> str:
    return "\n".join(r.getMessage() for r in caplog.records if r.name.startswith("app"))


# ═══════════════════════════════════════════════════════════════════════════
# Birim: email_service
# ═══════════════════════════════════════════════════════════════════════════


class TestEmailServiceUnit:
    def test_disabled_without_smtp_host(self, email_disabled):
        assert email_service.email_enabled() is False
        status = email_service.email_status()
        assert status["status"] == "disabled"
        assert "kapalı" in status["reason"]

    def test_enabled_status_does_not_expose_host_or_credentials(self, monkeypatch):
        monkeypatch.setattr(settings, "SMTP_HOST", "smtp.gizli-sunucu.test")
        monkeypatch.setattr(settings, "SMTP_PASSWORD", "cok-gizli")
        status = email_service.email_status()
        assert status["status"] == "enabled"
        assert "smtp.gizli-sunucu.test" not in str(status)
        assert "cok-gizli" not in str(status)

    def test_links_use_frontend_url_not_app_name(self, monkeypatch):
        monkeypatch.setattr(settings, "FRONTEND_URL", "https://ornek.test/")
        link = email_service.verification_link("a.b-c_d")
        assert link == "https://ornek.test/auth/verify-email#token=a.b-c_d"
        assert settings.APP_NAME not in link
        assert email_service.password_reset_link("x") == "https://ornek.test/auth/reset-password#token=x"

    def test_token_lives_in_fragment_not_query(self, monkeypatch):
        # Parça sunucuya gönderilmez: nginx/Next erişim log'ları ve Referer token görmez
        monkeypatch.setattr(settings, "FRONTEND_URL", "https://ornek.test")
        parsed = urlparse(email_service.password_reset_link("gizli"))
        assert parsed.query == ""
        assert parse_qs(parsed.fragment) == {"token": ["gizli"]}

    def test_link_query_is_encoded(self, monkeypatch):
        monkeypatch.setattr(settings, "FRONTEND_URL", "https://ornek.test")
        link = email_service.frontend_link("/a", token="x&y=z")
        assert link == "https://ornek.test/a?token=x%26y%3Dz"

    def test_compose_verification_email(self, monkeypatch):
        monkeypatch.setattr(settings, "SMTP_FROM", SENDER)
        msg = email_service.compose_verification_email("alici@ghostbuilding.io", "https://ornek.test/v?token=t")
        assert msg["To"] == "alici@ghostbuilding.io"
        assert "doğrulayın" in msg["Subject"]
        assert "https://ornek.test/v?token=t" in _text_body(msg)
        assert 'href="https://ornek.test/v?token=t"' in _html_body(msg)

    def test_compose_reset_email_escapes_link_in_html(self, monkeypatch):
        monkeypatch.setattr(settings, "SMTP_FROM", SENDER)
        msg = email_service.compose_password_reset_email("a@ghostbuilding.io", 'https://x.test/?a="><b>')
        html = _html_body(msg)
        assert "<b>" not in html
        assert "&quot;&gt;&lt;b&gt;" in html
        assert "Şifre sıfırlama" in msg["Subject"]

    async def test_send_when_disabled_returns_false(self, email_disabled, monkeypatch):
        monkeypatch.setattr(settings, "SMTP_FROM", SENDER)
        msg = email_service.compose_verification_email("a@ghostbuilding.io", "https://x.test")
        assert await email_service.send_email(msg, kind="verification") is False
        assert await email_service.send_password_reset_email("a@ghostbuilding.io", "t") is False

    async def test_missing_sender_fails_softly(self, monkeypatch, caplog):
        monkeypatch.setattr(settings, "SMTP_HOST", "127.0.0.1")
        monkeypatch.setattr(settings, "SMTP_FROM", None)
        monkeypatch.setattr(settings, "SMTP_USERNAME", None)
        caplog.set_level(logging.INFO)
        assert await email_service.send_verification_email("a@ghostbuilding.io", "t") is False
        assert "SMTP_FROM" in _app_log_text(caplog)


# ═══════════════════════════════════════════════════════════════════════════
# Entegrasyon: sahte SMTP sunucusuna gerçek gönderim
# ═══════════════════════════════════════════════════════════════════════════


class TestSmtpDelivery:
    async def test_plain_smtp_delivery(self, smtp_server):
        msg = email_service.compose_verification_email("alici@ghostbuilding.io", f"{FRONTEND}/auth/verify-email?token=t")
        assert await email_service.send_email(msg, kind="verification") is True

        assert smtp_server.recipients() == ["alici@ghostbuilding.io"]
        received = smtp_server.messages[0]
        assert received["From"] == SENDER
        assert received["Subject"] == "GhostBuilding — E-posta adresinizi doğrulayın"
        assert "doğrulayın" in _text_body(received)  # UTF-8 kayıpsız

    async def test_smtp_auth_login(self, monkeypatch):
        seen: list[tuple[bytes, bytes]] = []

        def authenticator(server, session, envelope, mechanism, auth_data):
            seen.append((auth_data.login, auth_data.password))
            return AuthResult(success=auth_data.password == b"dogru-parola")

        controller, inbox = _start_server(authenticator=authenticator, auth_require_tls=False, auth_required=True)
        try:
            monkeypatch.setattr(settings, "SMTP_HOST", "127.0.0.1")
            monkeypatch.setattr(settings, "SMTP_PORT", controller.port)
            monkeypatch.setattr(settings, "SMTP_SECURITY", "none")
            monkeypatch.setattr(settings, "SMTP_FROM", None)
            monkeypatch.setattr(settings, "SMTP_USERNAME", "gonderen@ghostbuilding.io")
            monkeypatch.setattr(settings, "SMTP_PASSWORD", "dogru-parola")

            msg = email_service.compose_password_reset_email("a@ghostbuilding.io", "https://x.test")
            assert msg["From"] == "gonderen@ghostbuilding.io"  # SMTP_FROM yoksa kullanıcı adı
            assert await email_service.send_email(msg, kind="password_reset") is True
            assert seen == [(b"gonderen@ghostbuilding.io", b"dogru-parola")]
            assert len(inbox.envelopes) == 1

            monkeypatch.setattr(settings, "SMTP_PASSWORD", "yanlis")
            msg = email_service.compose_password_reset_email("a@ghostbuilding.io", "https://x.test")
            assert await email_service.send_email(msg, kind="password_reset") is False
            assert len(inbox.envelopes) == 1
        finally:
            controller.stop()

    async def test_starttls_with_certificate_verification(self, monkeypatch, tls_ca):
        ca, server_cert = tls_ca
        controller, inbox = _start_server(tls_context=_server_context(server_cert), require_starttls=True)
        try:
            monkeypatch.setattr(settings, "SMTP_HOST", "127.0.0.1")
            monkeypatch.setattr(settings, "SMTP_PORT", controller.port)
            monkeypatch.setattr(settings, "SMTP_SECURITY", "starttls")
            monkeypatch.setattr(settings, "SMTP_FROM", SENDER)
            monkeypatch.setattr(settings, "SMTP_USERNAME", None)

            msg = email_service.compose_verification_email("a@ghostbuilding.io", "https://x.test")
            # Güvenilmeyen sertifika: varsayılan bağlam reddeder, e-posta GİTMEZ
            assert await email_service.send_email(msg, kind="verification") is False
            assert inbox.envelopes == []

            monkeypatch.setattr(email_service, "_tls_context", lambda: _client_context_trusting(ca))
            msg = email_service.compose_verification_email("a@ghostbuilding.io", "https://x.test")
            assert await email_service.send_email(msg, kind="verification") is True
            assert len(inbox.envelopes) == 1
        finally:
            controller.stop()

    async def test_implicit_tls_smtps(self, monkeypatch, tls_ca):
        ca, server_cert = tls_ca
        controller, inbox = _start_server(
            ssl_context=_server_context(server_cert),
            server_hostname="127.0.0.1",
        )
        try:
            monkeypatch.setattr(settings, "SMTP_HOST", "127.0.0.1")
            monkeypatch.setattr(settings, "SMTP_PORT", controller.port)
            monkeypatch.setattr(settings, "SMTP_SECURITY", "ssl")
            monkeypatch.setattr(settings, "SMTP_FROM", SENDER)
            monkeypatch.setattr(settings, "SMTP_USERNAME", None)
            monkeypatch.setattr(email_service, "_tls_context", lambda: _client_context_trusting(ca))

            msg = email_service.compose_verification_email("a@ghostbuilding.io", "https://x.test")
            assert await email_service.send_email(msg, kind="verification") is True
            assert len(inbox.envelopes) == 1
        finally:
            controller.stop()

    async def test_unreachable_server_fails_softly_without_logging_address(self, monkeypatch, caplog):
        monkeypatch.setattr(settings, "SMTP_HOST", "127.0.0.1")
        monkeypatch.setattr(settings, "SMTP_PORT", _free_port())  # dinleyen yok
        monkeypatch.setattr(settings, "SMTP_SECURITY", "none")
        monkeypatch.setattr(settings, "SMTP_FROM", SENDER)
        monkeypatch.setattr(settings, "SMTP_TIMEOUT_SECONDS", 2.0)

        caplog.set_level(logging.INFO)
        msg = email_service.compose_verification_email("gizli.alici@ghostbuilding.io", "https://x.test/?token=GIZLI")
        assert await email_service.send_email(msg, kind="verification") is False

        logs = _app_log_text(caplog)
        assert "E-posta gönderilemedi" in logs
        assert "gizli.alici@ghostbuilding.io" not in logs
        assert "GIZLI" not in logs


# ═══════════════════════════════════════════════════════════════════════════
# Birim: amaçlı token'lar ve oturum sürümü
# ═══════════════════════════════════════════════════════════════════════════


class _U:
    def __init__(self, hashed="h", version=0):
        self.id = str(uuid.uuid4())
        self.hashed_password = hashed
        self.session_version = version


class TestPurposeTokens:
    def test_constants_match_service(self):
        svc = _svc()
        assert (svc.ALGORITHM, svc.EMAIL_VERIFY_AUDIENCE, svc.PASSWORD_RESET_AUDIENCE) == (
            ALGORITHM,
            EMAIL_VERIFY_AUDIENCE,
            PASSWORD_RESET_AUDIENCE,
        )

    def test_verification_roundtrip(self):
        token = AuthService.create_email_verification_token("u-1")
        payload = AuthService.decode_purpose_token(token, EMAIL_VERIFY_AUDIENCE)
        assert payload["sub"] == "u-1"

    def test_expired_is_distinguished_from_invalid(self):
        token = _svc().AuthService._purpose_token("u-1", EMAIL_VERIFY_AUDIENCE, timedelta(seconds=-5))
        with pytest.raises(_svc().PurposeTokenError) as exc:
            AuthService.decode_purpose_token(token, EMAIL_VERIFY_AUDIENCE)
        assert exc.value.reason == "expired"

        with pytest.raises(_svc().PurposeTokenError) as exc:
            AuthService.decode_purpose_token(token[:-3] + "abc", EMAIL_VERIFY_AUDIENCE)
        assert exc.value.reason == "invalid"

        # Süresi dolmuş ama imzası sağlam token yeniden gönderim için okunabilir
        assert AuthService.decode_purpose_token(token, EMAIL_VERIFY_AUDIENCE, verify_exp=False)["sub"] == "u-1"

    def test_audiences_do_not_cross(self):
        reset = AuthService.create_password_reset_token(_U())
        with pytest.raises(_svc().PurposeTokenError) as exc:
            AuthService.decode_purpose_token(reset, EMAIL_VERIFY_AUDIENCE)
        assert exc.value.reason == "invalid"

    def test_purpose_token_is_not_a_session_token(self):
        reset = AuthService.create_password_reset_token(_U())
        with pytest.raises(HTTPException) as exc:
            AuthService.decode_token(reset)
        assert exc.value.status_code == 401

    def test_session_token_is_not_a_purpose_token(self):
        access = AuthService.create_access_token("u-1")
        with pytest.raises(_svc().PurposeTokenError):
            AuthService.decode_purpose_token(access, PASSWORD_RESET_AUDIENCE)

    def test_reset_token_binds_version_and_password_fingerprint(self):
        user = _U(hashed="$2b$12$abc", version=4)
        payload = jwt.decode(
            AuthService.create_password_reset_token(user),
            settings.SECRET_KEY,
            algorithms=[ALGORITHM],
            audience=PASSWORD_RESET_AUDIENCE,
        )
        assert payload["tv"] == 4
        assert payload["pwf"] == AuthService.password_fingerprint("$2b$12$abc")
        assert "$2b$12$abc" not in str(payload)  # hash'in kendisi token'a girmez
        assert AuthService.password_fingerprint("$2b$12$abd") != payload["pwf"]

    def test_reset_token_lifetime_follows_setting(self, monkeypatch):
        monkeypatch.setattr(settings, "PASSWORD_RESET_TOKEN_MINUTES", 15)
        payload = jwt.decode(
            AuthService.create_password_reset_token(_U()),
            settings.SECRET_KEY,
            algorithms=[ALGORITHM],
            audience=PASSWORD_RESET_AUDIENCE,
        )
        assert payload["exp"] - payload["iat"] == 15 * 60

    def test_session_revoked(self):
        assert session_revoked({"tv": 0}, _U(version=0)) is False
        assert session_revoked({}, _U(version=0)) is False  # tv'siz eski token
        assert session_revoked({"tv": 0}, _U(version=1)) is True
        assert session_revoked({"tv": "bozuk"}, _U(version=0)) is True

    def test_session_tokens_carry_version(self):
        access = AuthService.create_access_token("u", session_version=3)
        refresh = AuthService.create_refresh_token("u", session_version=3)
        assert AuthService.decode_token(access)["tv"] == 3
        assert AuthService.decode_token(refresh)["tv"] == 3

    async def test_address_limit(self, fake_redis, monkeypatch):
        monkeypatch.setattr(settings, "RATE_LIMIT_EMAIL_PER_ADDRESS_PER_HOUR", 2)
        results = [await AuthService.allow_email_to_address("reset", "Kisi@Ornek.test") for _ in range(3)]
        assert results == [True, True, False]
        # Başka amaç ayrı sayılır; Redis anahtarında adresin kendisi yok
        assert await AuthService.allow_email_to_address("verify", "kisi@ghostbuilding.io") is True
        assert all("ornek" not in key for key in fake_redis.data)


class TestRateLimitRules:
    @pytest.mark.parametrize(
        "path,prefix,limit_attr",
        [
            ("/api/v1/auth/forgot-password", "rl:forgot", "RATE_LIMIT_EMAIL_ACTIONS_PER_HOUR"),
            ("/api/v1/auth/resend-verification", "rl:resend", "RATE_LIMIT_EMAIL_ACTIONS_PER_HOUR"),
            ("/api/v1/auth/reset-password", "rl:reset", "RATE_LIMIT_RESET_SUBMIT_PER_HOUR"),
        ],
    )
    def test_email_endpoints_have_hourly_ip_limit(self, path, prefix, limit_attr):
        from app.middleware.rate_limiter import _match_rule

        rule = _match_rule(path, "POST")
        assert rule is not None
        assert rule.key_prefix == prefix
        assert rule.window_seconds == 3600
        assert rule.max_requests == getattr(settings, limit_attr)


# ═══════════════════════════════════════════════════════════════════════════
# Entegrasyon: API akışları (sahte SMTP üzerinden)
# ═══════════════════════════════════════════════════════════════════════════


@pytest_asyncio.fixture
async def unverified_user(db_session):
    return await _make_user(db_session, verified=False)


class TestEmailVerificationFlow:
    async def test_register_when_email_disabled_says_so(self, client: AsyncClient, email_disabled):
        suffix = uuid.uuid4().hex[:8]
        response = await client.post(
            "/api/v1/auth/register",
            json={"email": f"kapali_{suffix}@ghostbuilding.io", "username": f"kapali_{suffix}", "password": "SecurePass1"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["email_delivery"] == "disabled"
        assert "kapalı" in data["message"]

    async def test_register_sends_mail_and_link_verifies(self, client: AsyncClient, smtp_server, db_session, caplog):
        caplog.set_level(logging.INFO)
        suffix = uuid.uuid4().hex[:8]
        address = f"yeni_{suffix}@ghostbuilding.io"
        response = await client.post(
            "/api/v1/auth/register",
            json={"email": address, "username": f"yeni_{suffix}", "password": "SecurePass1"},
        )
        assert response.status_code == 201
        assert response.json()["email_delivery"] == "enabled"

        assert smtp_server.recipients() == [address]
        link = _link_from(smtp_server.messages[0])
        assert link.startswith(f"{FRONTEND}/auth/verify-email#token=")
        token = _token_from(smtp_server.messages[0])

        first = await client.post("/api/v1/auth/verify-email", json={"token": token})
        assert first.status_code == 200
        assert first.json()["status"] == "verified"

        # Eski GET yolu da çalışır (geriye uyumluluk)
        again = await client.get("/api/v1/auth/verify-email", params={"token": token})
        assert again.status_code == 200
        assert again.json()["status"] == "already_verified"

        user = (await db_session.execute(select(TestUser).where(TestUser.email == address))).scalar_one()
        await db_session.refresh(user)
        assert user.is_verified is True

        logs = _app_log_text(caplog)
        assert "Doğrulama e-postası" in logs  # log gerçekten yakalanıyor
        assert address not in logs
        assert token not in logs

    async def test_verify_expired_and_invalid(self, client: AsyncClient, unverified_user):
        expired = _svc().AuthService._purpose_token(str(unverified_user.id), EMAIL_VERIFY_AUDIENCE, timedelta(seconds=-1))
        r = await client.get("/api/v1/auth/verify-email", params={"token": expired})
        assert r.status_code == 400
        assert r.json()["detail"]["error"] == "token_expired"

        r = await client.post("/api/v1/auth/verify-email", json={"token": expired})
        assert r.json()["detail"]["error"] == "token_expired"

        r = await client.get("/api/v1/auth/verify-email", params={"token": "bozuk-token"})
        assert r.status_code == 400
        assert r.json()["detail"]["error"] == "invalid_token"

        # Başka amaçlı (sıfırlama) token doğrulama için geçersiz
        reset = AuthService.create_password_reset_token(unverified_user)
        r = await client.get("/api/v1/auth/verify-email", params={"token": reset})
        assert r.json()["detail"]["error"] == "invalid_token"

        # Var olmayan kullanıcıya ait imzalı token
        ghost = AuthService.create_email_verification_token(str(uuid.uuid4()))
        r = await client.get("/api/v1/auth/verify-email", params={"token": ghost})
        assert r.json()["detail"]["error"] == "invalid_token"

    async def test_resend_does_not_leak_account_state(self, client: AsyncClient, smtp_server, db_session, unverified_user):
        verified = await _make_user(db_session, verified=True)

        responses = []
        for address in (unverified_user.email, "yok_boyle_biri@ghostbuilding.io", verified.email):
            r = await client.post("/api/v1/auth/resend-verification", json={"email": address})
            responses.append((r.status_code, r.json()))

        assert len({str(x) for x in responses}) == 1, "yanıtlar hesap durumuna göre değişmemeli"
        assert responses[0][0] == 202
        assert smtp_server.recipients() == [unverified_user.email]

    async def test_resend_with_expired_link_token(self, client: AsyncClient, smtp_server, unverified_user):
        expired = _svc().AuthService._purpose_token(str(unverified_user.id), EMAIL_VERIFY_AUDIENCE, timedelta(seconds=-1))
        r = await client.post("/api/v1/auth/resend-verification", json={"token": expired})
        assert r.status_code == 202
        assert smtp_server.recipients() == [unverified_user.email]

        fresh = _token_from(smtp_server.messages[0])
        ok = await client.get("/api/v1/auth/verify-email", params={"token": fresh})
        assert ok.json()["status"] == "verified"

    async def test_resend_with_forged_token_sends_nothing(self, client: AsyncClient, smtp_server, unverified_user):
        forged = jwt.encode(
            {"sub": str(unverified_user.id), "aud": EMAIL_VERIFY_AUDIENCE, "exp": 1},
            "baska-anahtar",
            algorithm=ALGORITHM,
        )
        r = await client.post("/api/v1/auth/resend-verification", json={"token": forged})
        assert r.status_code == 202
        assert smtp_server.envelopes == []

    async def test_resend_requires_email_or_token(self, client: AsyncClient, smtp_server):
        r = await client.post("/api/v1/auth/resend-verification", json={})
        assert r.status_code == 422

    @pytest.mark.parametrize(
        "path,body",
        [
            ("/api/v1/auth/resend-verification", {"email": "a@ghostbuilding.io"}),
            ("/api/v1/auth/forgot-password", {"email": "a@ghostbuilding.io"}),
        ],
    )
    async def test_email_actions_report_disabled(self, client: AsyncClient, email_disabled, path, body):
        r = await client.post(path, json=body)
        assert r.status_code == 503
        assert r.json()["detail"]["error"] == "email_disabled"

    async def test_health_reports_email_state(self, client: AsyncClient, email_disabled):
        r = await client.get("/api/v1/health")
        data = r.json()
        assert data["email"] == "disabled"
        assert data["details"]["email"]["status"] == "disabled"


class TestPasswordResetFlow:
    async def test_forgot_does_not_leak_account_existence(self, client: AsyncClient, smtp_server, unverified_user):
        known = await client.post("/api/v1/auth/forgot-password", json={"email": unverified_user.email.upper()})
        unknown = await client.post("/api/v1/auth/forgot-password", json={"email": "hic_yok@ghostbuilding.io"})

        assert known.status_code == unknown.status_code == 202
        assert known.json() == unknown.json()
        assert smtp_server.recipients() == [unverified_user.email]
        link = _link_from(smtp_server.messages[0])
        assert link.startswith(f"{FRONTEND}/auth/reset-password#token=")

    async def test_forgot_per_address_limit_is_silent(
        self, client: AsyncClient, smtp_server, fake_redis, unverified_user, monkeypatch
    ):
        monkeypatch.setattr(settings, "RATE_LIMIT_EMAIL_PER_ADDRESS_PER_HOUR", 2)
        bodies = set()
        for _ in range(4):
            r = await client.post("/api/v1/auth/forgot-password", json={"email": unverified_user.email})
            assert r.status_code == 202
            bodies.add(r.text)
        assert len(bodies) == 1
        assert len(smtp_server.envelopes) == 2

    async def test_forgot_for_disabled_account_sends_nothing(self, client: AsyncClient, smtp_server, db_session):
        user = await _make_user(db_session)
        user.is_active = False
        await db_session.commit()
        r = await client.post("/api/v1/auth/forgot-password", json={"email": user.email})
        assert r.status_code == 202
        assert smtp_server.envelopes == []

    async def test_full_reset_flow_revokes_old_sessions(
        self, client: AsyncClient, smtp_server, fake_redis, db_session, caplog
    ):
        caplog.set_level(logging.INFO)
        user = await _make_user(db_session, password="OldPass12", verified=False)

        login = await client.post("/api/v1/auth/login", json={"email": user.email, "password": "OldPass12"})
        assert login.status_code == 200
        old_access = login.json()["access_token"]
        old_refresh = login.json()["refresh_token"]
        assert (await client.get("/api/v1/auth/me", headers=auth_header(old_access))).status_code == 200

        await client.post("/api/v1/auth/forgot-password", json={"email": user.email})
        token = _token_from(smtp_server.messages[0])

        reset = await client.post("/api/v1/auth/reset-password", json={"token": token, "new_password": "NewPass34"})
        assert reset.status_code == 200, reset.text

        # Eski access ve refresh token'ları artık işe yaramaz
        me = await client.get("/api/v1/auth/me", headers=auth_header(old_access))
        assert me.status_code == 401
        assert me.json()["detail"]["error"] == "session_revoked"
        refreshed = await client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
        assert refreshed.status_code == 401
        assert refreshed.json()["detail"]["error"] == "session_revoked"

        # Eski şifre reddedilir, yenisi çalışır ve yeni oturum geçerlidir
        bad = await client.post("/api/v1/auth/login", json={"email": user.email, "password": "OldPass12"})
        assert bad.status_code == 401
        good = await client.post("/api/v1/auth/login", json={"email": user.email, "password": "NewPass34"})
        assert good.status_code == 200
        new_access = good.json()["access_token"]
        me = await client.get("/api/v1/auth/me", headers=auth_header(new_access))
        assert me.status_code == 200
        assert me.json()["is_verified"] is True  # bağlantıyı açmak adresin sahipliğini kanıtlar
        new_refresh = await client.post("/api/v1/auth/refresh", json={"refresh_token": good.json()["refresh_token"]})
        assert new_refresh.status_code == 200

        # Tek kullanımlık: aynı bağlantı ikinci kez çalışmaz
        reuse = await client.post("/api/v1/auth/reset-password", json={"token": token, "new_password": "Another56"})
        assert reuse.status_code == 400
        assert reuse.json()["detail"]["error"] == "invalid_token"

        logs = _app_log_text(caplog)
        assert "Şifre sıfırlama e-postası" in logs
        assert user.email not in logs
        assert token not in logs

    async def test_old_reset_link_dies_when_a_newer_one_is_used(self, client: AsyncClient, smtp_server, db_session):
        user = await _make_user(db_session)
        await client.post("/api/v1/auth/forgot-password", json={"email": user.email})
        await client.post("/api/v1/auth/forgot-password", json={"email": user.email})
        first, second = (_token_from(m) for m in smtp_server.messages)

        assert (
            await client.post("/api/v1/auth/reset-password", json={"token": second, "new_password": "NewPass34"})
        ).status_code == 200
        r = await client.post("/api/v1/auth/reset-password", json={"token": first, "new_password": "NewPass56"})
        assert r.status_code == 400
        assert r.json()["detail"]["error"] == "invalid_token"

    async def test_reset_expired_and_invalid(self, client: AsyncClient, db_session):
        user = await _make_user(db_session)
        expired = _svc().AuthService._purpose_token(
            str(user.id),
            PASSWORD_RESET_AUDIENCE,
            timedelta(seconds=-1),
            tv=0,
            pwf=AuthService.password_fingerprint(user.hashed_password),
        )
        r = await client.post("/api/v1/auth/reset-password", json={"token": expired, "new_password": "NewPass34"})
        assert r.status_code == 400
        assert r.json()["detail"]["error"] == "token_expired"

        verify_token = AuthService.create_email_verification_token(str(user.id))
        r = await client.post("/api/v1/auth/reset-password", json={"token": verify_token, "new_password": "NewPass34"})
        assert r.json()["detail"]["error"] == "invalid_token"

        access = AuthService.create_access_token(str(user.id))
        r = await client.post("/api/v1/auth/reset-password", json={"token": access, "new_password": "NewPass34"})
        assert r.json()["detail"]["error"] == "invalid_token"

    async def test_weak_password_keeps_token_usable(self, client: AsyncClient, db_session):
        user = await _make_user(db_session)
        token = AuthService.create_password_reset_token(user)

        weak = await client.post("/api/v1/auth/reset-password", json={"token": token, "new_password": "zayifsifre"})
        assert weak.status_code == 422
        assert weak.json()["detail"]["error"] == "password_validation_failed"

        ok = await client.post("/api/v1/auth/reset-password", json={"token": token, "new_password": "Strong123"})
        assert ok.status_code == 200

    async def test_password_change_elsewhere_invalidates_reset_link(self, client: AsyncClient, db_session):
        user = await _make_user(db_session, password="OldPass12")
        token = AuthService.create_password_reset_token(user)

        user.hashed_password = AuthService.hash_password("Changed99")  # ör. profil sayfasından
        await db_session.commit()

        r = await client.post("/api/v1/auth/reset-password", json={"token": token, "new_password": "NewPass34"})
        assert r.status_code == 400
        assert r.json()["detail"]["error"] == "invalid_token"

    async def test_reset_clears_login_lockout(self, client: AsyncClient, fake_redis, db_session):
        BRUTE_FORCE_PREFIX = _svc().BRUTE_FORCE_PREFIX

        user = await _make_user(db_session)
        fake_redis.data[f"{BRUTE_FORCE_PREFIX}{user.email}"] = "5"
        locked = await client.post("/api/v1/auth/login", json={"email": user.email, "password": "OldPass12"})
        assert locked.status_code == 429

        token = AuthService.create_password_reset_token(user)
        await client.post("/api/v1/auth/reset-password", json={"token": token, "new_password": "NewPass34"})
        unlocked = await client.post("/api/v1/auth/login", json={"email": user.email, "password": "NewPass34"})
        assert unlocked.status_code == 200
