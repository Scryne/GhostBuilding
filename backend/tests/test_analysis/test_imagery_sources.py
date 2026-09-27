"""Görüntü kaynakları ve karşılaştırma ön işlemesi — 2026-09-26 denetimi regresyonları.

- Karşılaştırma yalnız uydu fotoğrafları arasında ve yalnız yapılandırılmış kaynaklarla yapılır.
- İstekler tek, dürüst bir User-Agent ile gider (rastgele tarayıcı kimliği / sahte Referer yok).
- Farklı çözünürlükteki karolar ÖLÇEKLENİR, ortasından kırpılmaz.
- Esri Wayback seçimi tarih aralığına yayılır ve aynı görüntüyü tekrar etmez.
"""

from __future__ import annotations

import io
from datetime import datetime
from typing import Any

import numpy as np
import pytest
from PIL import Image

from app.services import tile_fetcher
from app.services.analyzers.pixel_diff import PixelDiffAnalyzer
from app.services.tile_fetcher import (
    USER_AGENT,
    TileFetcher,
    TileProvider,
    WaybackFetcher,
    imagery_providers,
)


def _noise_image(size: int, seed: int = 7) -> Image.Image:
    rng = np.random.default_rng(seed)
    base = rng.integers(0, 255, (32, 32, 3), dtype=np.uint8)
    return Image.fromarray(base).resize((size, size), Image.NEAREST)


def test_farkli_cozunurlukteki_ayni_karo_neredeyse_ozdes_sayilir() -> None:
    """Eskiden 512'lik karonun ortası kırpılıp 256'lıkla kıyaslanıyordu (başka bir alan)."""
    small = _noise_image(256)
    large = small.resize((512, 512), Image.LANCZOS)
    result = PixelDiffAnalyzer().compute_diff(small, large)
    assert result.diff_score < 5.0
    assert result.structural_similarity > 0.8


def test_maptiler_anahtari_yoksa_karsilastirmaya_girmez(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tile_fetcher.settings, "MAPTILER_API_KEY", None)
    assert imagery_providers() == [TileProvider.ESRI]
    monkeypatch.setattr(tile_fetcher.settings, "MAPTILER_API_KEY", "anahtar")
    assert imagery_providers() == [TileProvider.ESRI, TileProvider.MAPTILER]


def test_osm_cizimi_uydu_karsilastirmasina_girmez(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tile_fetcher.settings, "MAPTILER_API_KEY", "anahtar")
    assert TileProvider.OSM not in imagery_providers()


def test_istek_basliklari_durust_tek_kimlik_tasir() -> None:
    headers = TileFetcher()._build_headers(TileProvider.OSM)
    assert headers["User-Agent"] == USER_AGENT
    assert "GhostBuilding" in headers["User-Agent"]
    assert "Referer" not in headers
    assert not hasattr(tile_fetcher, "USER_AGENTS")


def test_maptiler_adresi_anahtarsiz_kurulmaz(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tile_fetcher.settings, "MAPTILER_API_KEY", None)
    with pytest.raises(RuntimeError, match="MAPTILER_API_KEY"):
        TileFetcher()._build_url(TileProvider.MAPTILER, 16, 1, 1)


def test_esri_adresi_satir_sutun_sirasini_kullanir() -> None:
    url = TileFetcher()._build_url(TileProvider.ESRI, 16, 37932, 25253)
    assert url.endswith("/tile/16/25253/37932")


def test_wayback_secimi_araliga_esit_yayilir() -> None:
    items = [{"release": i} for i in range(100)]
    picked = WaybackFetcher._spread(items, 5)
    assert [p["release"] for p in picked] == [0, 25, 50, 74, 99]
    assert WaybackFetcher._spread(items[:3], 5) == items[:3]


async def test_wayback_ayni_goruntuyu_tekrar_etmez(monkeypatch: pytest.MonkeyPatch) -> None:
    releases = [
        {"release": n, "date": datetime(2014 + n, 1, 1), "url_template": f"https://w/{n}/{{level}}/{{row}}/{{col}}"}
        for n in range(6)
    ]
    # 0-2 aynı görüntü, 3-5 farklı görüntü
    images = {n: _noise_image(64, seed=1 if n < 3 else 100 + n) for n in range(6)}

    async def fake_list(self: Any) -> list[dict[str, object]]:
        return releases

    async def fake_image(self: Any, url: str) -> Image.Image:
        return images[int(url.split("/")[3])]

    monkeypatch.setattr(WaybackFetcher, "list_releases", fake_list)
    monkeypatch.setattr(WaybackFetcher, "fetch_snapshot_image", fake_image)
    async with WaybackFetcher() as wb:
        snaps = await wb.fetch_historical(41.0, 29.0, 15, datetime(2013, 1, 1), datetime(2030, 1, 1))
    assert [s["release"] for s in snaps] == [0, 3, 4, 5]
    assert all(s["provider"] == "esri_wayback" for s in snaps)


def test_goruntu_bayt_donusumu_gecerli() -> None:
    buf = io.BytesIO()
    _noise_image(32).save(buf, format="PNG")
    assert Image.open(io.BytesIO(buf.getvalue())).size == (32, 32)


def test_ign_yalniz_fransa_icinde_karsilastirmaya_girer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tile_fetcher.settings, "MAPTILER_API_KEY", "anahtar")
    assert TileProvider.IGN in imagery_providers(48.30, -4.51)  # Brest
    assert TileProvider.IGN not in imagery_providers(40.99, 29.03)  # İstanbul
    assert TileProvider.IGN not in imagery_providers()  # konum yok → yalnız küresel


def test_kapsama_disi_bos_karo_reddedilir() -> None:
    assert tile_fetcher._is_blank(Image.new("RGB", (256, 256), "white"))
    assert not tile_fetcher._is_blank(_noise_image(256))


async def test_4xx_yeniden_denenmez(monkeypatch: pytest.MonkeyPatch) -> None:
    import httpx

    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(404, text="yok")

    fetcher = TileFetcher(use_cache=False)
    fetcher._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(tile_fetcher.TileUnavailable):
            await fetcher.fetch_tile(TileProvider.IGN, 16, 1, 1)
    finally:
        await fetcher._client.aclose()
    assert calls["n"] == 1
