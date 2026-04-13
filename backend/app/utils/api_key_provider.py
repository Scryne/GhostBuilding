"""
api_key_provider.py — Abstract API key yönetimi ve rotation pattern.

Tüm harici API key'leri environment variable üzerinden yönetilir.
Key rotation için abstract provider pattern kullanılır.

Kullanım:
    from app.utils.api_key_provider import get_api_key_provider

    provider = get_api_key_provider("google_maps")
    key = provider.get_key()
"""

from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)


class APIKeyProvider(ABC):
    """
    API key yönetimi için abstract base class.

    Alt sınıflar key rotation, caching veya vault
    entegrasyonu implementasyonu sağlayabilir.
    """

    @abstractmethod
    def get_key(self) -> Optional[str]:
        """Mevcut aktif API key'i döndürür."""
        ...

    @abstractmethod
    def rotate_key(self) -> Optional[str]:
        """Sonraki key'e geçiş yapar (rotation destekleniyorsa)."""
        ...

    @abstractmethod
    def is_configured(self) -> bool:
        """Key'in yapılandırılmış olup olmadığını kontrol eder."""
        ...

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Sağlayıcı adını döndürür."""
        ...


class EnvironmentKeyProvider(APIKeyProvider):
    """
    Environment variable tabanlı API key provider.

    Key rotation: Birden fazla env var tanımlarak sıralı rotation
    desteklenir (örn: GOOGLE_MAPS_API_KEY, GOOGLE_MAPS_API_KEY_2).
    """

    def __init__(
        self,
        name: str,
        env_var: str,
        rotation_env_vars: Optional[list[str]] = None,
    ) -> None:
        self._name = name
        self._primary_env_var = env_var
        self._rotation_vars = rotation_env_vars or []
        self._current_index = 0
        self._all_vars = [env_var] + self._rotation_vars

    @property
    def provider_name(self) -> str:
        return self._name

    def get_key(self) -> Optional[str]:
        """Mevcut aktif key'i döndürür."""
        var = self._all_vars[self._current_index]
        key = os.getenv(var) or getattr(settings, var, None)

        if not key:
            logger.debug(
                "API key mevcut değil: provider=%s env_var=%s",
                self._name,
                var,
            )
            return None

        return key

    def rotate_key(self) -> Optional[str]:
        """
        Sonraki key'e geçiş yapar.

        Rotation env var'ları tanımlıysa sıradaki key'e geçer.
        Tanımlı değilse veya son key'deyse ilk key'e döner.
        """
        if len(self._all_vars) <= 1:
            logger.info(
                "Key rotation: tek key tanımlı, rotation yapılamıyor: provider=%s",
                self._name,
            )
            return self.get_key()

        self._current_index = (self._current_index + 1) % len(self._all_vars)
        new_key = self.get_key()

        logger.info(
            "Key rotation yapıldı: provider=%s index=%d/%d",
            self._name,
            self._current_index + 1,
            len(self._all_vars),
        )

        return new_key

    def is_configured(self) -> bool:
        """En az bir key tanımlı mı kontrol eder."""
        for var in self._all_vars:
            val = os.getenv(var) or getattr(settings, var, None)
            if val:
                return True
        return False


# ═══════════════════════════════════════════════════════════════════════════
# Provider Registry
# ═══════════════════════════════════════════════════════════════════════════

_PROVIDERS: dict[str, APIKeyProvider] = {
    "google_maps": EnvironmentKeyProvider(
        name="Google Maps",
        env_var="GOOGLE_MAPS_API_KEY",
    ),
    "bing_maps": EnvironmentKeyProvider(
        name="Bing Maps",
        env_var="BING_MAPS_API_KEY",
    ),
    "sentinel_hub": EnvironmentKeyProvider(
        name="Sentinel Hub",
        env_var="SENTINEL_HUB_CLIENT_ID",
    ),
    "openai": EnvironmentKeyProvider(
        name="OpenAI",
        env_var="OPENAI_API_KEY",
    ),
}


def get_api_key_provider(name: str) -> APIKeyProvider:
    """
    İsme göre API key provider döndürür.

    Args:
        name: Provider adı (google_maps, bing_maps, sentinel_hub, openai).

    Returns:
        APIKeyProvider instance.

    Raises:
        KeyError: Tanımsız provider adı.
    """
    if name not in _PROVIDERS:
        raise KeyError(
            f"Tanımsız API key provider: {name}. "
            f"Mevcut provider'lar: {list(_PROVIDERS.keys())}"
        )
    return _PROVIDERS[name]


def register_provider(name: str, provider: APIKeyProvider) -> None:
    """Yeni bir API key provider kaydeder."""
    _PROVIDERS[name] = provider
    logger.info("API key provider kaydedildi: %s", name)
