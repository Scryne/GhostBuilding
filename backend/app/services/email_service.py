"""
email_service.py — SMTP üzerinden işlem e-postası gönderimi.

Yalnızca standart kütüphane (``smtplib`` + ``email``) kullanılır; gönderim bir iş
parçacığında yapılır ki olay döngüsü SMTP sunucusunu beklemesin.

Kurallar:
- ``SMTP_HOST`` tanımsızsa gönderim KAPALIDIR. Uygulama çalışmaya devam eder; bunu açılışta
  log'a, ``/health`` yanıtına ve ilgili uçların yanıtına açıkça yazar. Sessizce "gönderildi"
  demek yerine kullanıcı neyin olmadığını bilir.
- Bağlantılar ``FRONTEND_URL`` üzerinden kurulur (``APP_NAME`` bir ad, adres değildir).
- Log'a ALICI ADRESİ ve TOKEN yazılmaz. smtplib'in istisna metinleri alıcı adresini
  içerebildiği için (ör. ``SMTPRecipientsRefused``) yalnızca istisna türü ve SMTP kodu yazılır.
"""

from __future__ import annotations

import asyncio
import logging
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formatdate, make_msgid, parseaddr
from html import escape
from typing import Optional
from urllib.parse import urlencode

from app.config import settings

logger = logging.getLogger(__name__)

EMAIL_DISABLED_MESSAGE = (
    "E-posta gönderimi bu sunucuda kapalı (SMTP_HOST tanımlı değil)."
)

# ---------------------------------------------------------------------------
# Durum
# ---------------------------------------------------------------------------


def email_enabled() -> bool:
    """SMTP yapılandırılmış mı? (``SMTP_HOST`` boş değilse açık sayılır.)"""
    return bool((settings.SMTP_HOST or "").strip())


def email_status() -> dict[str, object]:
    """``/health`` ve açılış log'u için durum özeti. Sunucu adı ve kimlik bilgisi içermez."""
    if not email_enabled():
        return {"status": "disabled", "reason": EMAIL_DISABLED_MESSAGE}
    return {"status": "enabled", "security": _security_mode()}


def _security_mode() -> str:
    # Değer config'de Literal ile sınırlı; geçersiz değer uygulama açılırken reddedilir.
    return settings.SMTP_SECURITY


def _sender() -> str:
    sender = settings.SMTP_FROM or settings.SMTP_USERNAME
    if not sender:
        raise ValueError("SMTP_FROM (ya da SMTP_USERNAME) tanımlı olmalı.")
    return sender


# ---------------------------------------------------------------------------
# Bağlantılar
# ---------------------------------------------------------------------------


def frontend_link(path: str, **params: str) -> str:
    """``FRONTEND_URL`` + yol + sorgu. Sondaki/baştaki eğik çizgiler birleştirilir."""
    base = settings.FRONTEND_URL.rstrip("/")
    query = f"?{urlencode(params)}" if params else ""
    return f"{base}/{path.lstrip('/')}{query}"


def frontend_secret_link(path: str, **params: str) -> str:
    """
    Token taşıyan bağlantı: değerler URL PARÇASINDA (``#token=…``) durur.

    Parça tarayıcıdan sunucuya hiç gönderilmez; bu yüzden token ön yüz sunucusunun ya da
    nginx'in erişim log'una (``$request`` sorgu dizesini içerir) ve ``Referer`` başlığına düşmez.
    """
    base = settings.FRONTEND_URL.rstrip("/")
    return f"{base}/{path.lstrip('/')}#{urlencode(params)}"


def verification_link(token: str) -> str:
    return frontend_secret_link("/auth/verify-email", token=token)


def password_reset_link(token: str) -> str:
    return frontend_secret_link("/auth/reset-password", token=token)


# ---------------------------------------------------------------------------
# İleti şablonları
# ---------------------------------------------------------------------------


def _build_message(to: str, subject: str, paragraphs: list[str], link: str, button: str) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = _sender()
    msg["To"] = to
    msg["Date"] = formatdate(localtime=False)
    address = parseaddr(_sender())[1]
    msg["Message-ID"] = make_msgid(domain=address.rsplit("@", 1)[1] if "@" in address else None)

    text = "\n\n".join([*paragraphs[:1], f"{button}: {link}", *paragraphs[1:]])
    msg.set_content(text + "\n\n— GhostBuilding\n")

    html_paragraphs = "".join(f"<p>{escape(p)}</p>" for p in paragraphs[1:])
    html = f"""<!doctype html>
<html lang="tr"><body style="font-family:Inter,Arial,sans-serif;background:#0F1117;color:#F0F2F5;padding:24px">
<p>{escape(paragraphs[0])}</p>
<p><a href="{escape(link, quote=True)}" style="display:inline-block;padding:10px 18px;border-radius:12px;background:#4A7CF7;color:#ffffff;text-decoration:none">{escape(button)}</a></p>
<p style="color:#8B8FA3;font-size:13px">Düğme çalışmazsa bu adresi tarayıcınıza yapıştırın:<br>{escape(link)}</p>
{html_paragraphs}
<p style="color:#8B8FA3">— GhostBuilding</p>
</body></html>"""
    msg.add_alternative(html, subtype="html")
    return msg


def compose_verification_email(to: str, link: str) -> EmailMessage:
    hours = settings.EMAIL_VERIFY_TOKEN_HOURS
    return _build_message(
        to,
        "GhostBuilding — E-posta adresinizi doğrulayın",
        [
            "GhostBuilding hesabınızı etkinleştirmek için e-posta adresinizi doğrulayın.",
            f"Bağlantı {hours} saat geçerlidir.",
            "Bu kaydı siz yapmadıysanız bu e-postayı yok sayabilirsiniz.",
        ],
        link,
        "E-postamı doğrula",
    )


def compose_password_reset_email(to: str, link: str) -> EmailMessage:
    minutes = settings.PASSWORD_RESET_TOKEN_MINUTES
    return _build_message(
        to,
        "GhostBuilding — Şifre sıfırlama",
        [
            "Hesabınız için şifre sıfırlama istendi. Yeni şifrenizi belirlemek için bağlantıyı açın.",
            f"Bağlantı {minutes} dakika geçerlidir ve yalnızca bir kez kullanılabilir. "
            "Şifreniz değiştiğinde açık olan tüm oturumlarınız kapanır.",
            "Bu isteği siz yapmadıysanız bu e-postayı yok sayın; şifreniz değişmez.",
        ],
        link,
        "Yeni şifre belirle",
    )


# ---------------------------------------------------------------------------
# Gönderim
# ---------------------------------------------------------------------------


def _tls_context() -> ssl.SSLContext:
    """Sertifika ve ana makine adı doğrulamalı TLS bağlamı (testler kendi CA'sını verir)."""
    return ssl.create_default_context()


def _send_sync(msg: EmailMessage) -> None:
    host = (settings.SMTP_HOST or "").strip()
    port = settings.SMTP_PORT
    timeout = settings.SMTP_TIMEOUT_SECONDS
    mode = _security_mode()

    smtp: smtplib.SMTP
    if mode == "ssl":
        smtp = smtplib.SMTP_SSL(host, port, timeout=timeout, context=_tls_context())
    else:
        smtp = smtplib.SMTP(host, port, timeout=timeout)

    try:
        smtp.ehlo()
        if mode == "starttls":
            smtp.starttls(context=_tls_context())
            smtp.ehlo()
        if settings.SMTP_USERNAME:
            smtp.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD or "")
        smtp.send_message(msg)
    finally:
        try:
            smtp.quit()
        except Exception:
            smtp.close()


async def send_email(msg: EmailMessage, *, kind: str) -> bool:
    """
    İletiyi gönderir. Başarıda ``True``.

    Gönderim kapalıysa ya da başarısızsa ``False`` döner, istisna fırlatmaz: e-posta,
    çağıran isteğin (kayıt, sıfırlama talebi) sonucunu değiştirmemelidir.

    Args:
        msg: Gönderilecek ileti.
        kind: Log için ileti türü (``verification``, ``password_reset``). Adres yazılmaz.
    """
    if not email_enabled():
        logger.warning("E-posta gönderilmedi (kapalı): tür=%s", kind)
        return False

    try:
        await asyncio.to_thread(_send_sync, msg)
    except Exception as exc:
        code: Optional[int] = getattr(exc, "smtp_code", None)
        logger.error(
            "E-posta gönderilemedi: tür=%s hata=%s smtp_kodu=%s",
            kind,
            type(exc).__name__,
            code if code is not None else "-",
        )
        return False

    logger.info("E-posta gönderildi: tür=%s", kind)
    return True


async def _compose_and_send(kind: str, compose, to: str, link: str) -> bool:
    if not email_enabled():
        logger.warning("E-posta gönderilmedi (kapalı): tür=%s", kind)
        return False
    try:
        msg = compose(to, link)
    except ValueError as exc:  # ör. SMTP_FROM / SMTP_USERNAME eksik
        logger.error("E-posta oluşturulamadı: tür=%s neden=%s", kind, exc)
        return False
    return await send_email(msg, kind=kind)


async def send_verification_email(to: str, token: str) -> bool:
    return await _compose_and_send("verification", compose_verification_email, to, verification_link(token))


async def send_password_reset_email(to: str, token: str) -> bool:
    return await _compose_and_send("password_reset", compose_password_reset_email, to, password_reset_link(token))
