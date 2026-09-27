"""Anomali motoru puanlaması — 2026-09-27 denetimi regresyonları.

- Ham piksel farkı doğrudan puan değildir: sıradan bir konum (~%70 fark) puan almaz.
- Genel COCO modeli bina tanımadığı için bina dedektörü tanımlı değilse mekânsal
  karşılaştırma hiç çalışmaz ve bu durum puan dökümünde görünür.
- Motor adayları bir kez yazar; tarama görevi ikinci kez yazmaz.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.services import anomaly_engine
from app.services.analyzers.pixel_diff import (
    ANOMALY_HIGH_DIFF,
    ANOMALY_MEDIUM_DIFF,
    diff_to_score,
)
from app.services.anomaly_engine import AnomalyEngine
from app.tasks import scan_tasks


def test_taban_icindeki_fark_puan_almaz() -> None:
    assert diff_to_score(0.0) == 0.0
    assert diff_to_score(71.5) == 0.0  # sıradan konum ortancası
    assert diff_to_score(ANOMALY_MEDIUM_DIFF) == 0.0


def test_fark_puani_esikler_arasinda_monoton_artar() -> None:
    assert diff_to_score(ANOMALY_HIGH_DIFF) == pytest.approx(50.0)
    assert diff_to_score(100.0) == pytest.approx(100.0)
    samples = [ANOMALY_MEDIUM_DIFF + i for i in range(0, 20)]
    scores = [diff_to_score(x) for x in samples]
    assert scores == sorted(scores)


def test_uc_kaynakta_fark_esigi_kendi_tabanini_kullanir() -> None:
    """Üç kaynakta ölçü en farklı çifttir; iki kaynaklı eşik sıradan Fransız konumlarını işaretlerdi."""
    assert diff_to_score(92.0, provider_count=2) > 50.0
    assert diff_to_score(92.0, provider_count=3) < 50.0
    assert diff_to_score(99.5, provider_count=3) > 50.0


def _score(engine: AnomalyEngine, max_diff: float) -> Any:
    return engine._compute_confidence_score(
        pixel_diff_result={"max_diff_score": max_diff, "disagreeing_count": 0},
        blur_result={"censorship_score": 0.0},
        geospatial_result=None,
        provider_count=2,
    )


def test_siradan_konum_aday_uretmez(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(anomaly_engine.settings, "BUILDING_DETECTOR_WEIGHTS", None)
    engine = AnomalyEngine(min_confidence=60.0)
    breakdown = _score(engine, 74.0)
    assert breakdown.pixel_diff_score == 0.0
    assert breakdown.raw_max_diff == 74.0
    candidates = engine._build_candidates(
        lat=41.0, lng=29.0, score_breakdown=breakdown,
        pixel_diff_result={"max_diff_score": 74.0, "disagreeing_count": 0},
        blur_result={"censorship_score": 0.0}, geospatial_result=None,
        provider_tiles={},
    )
    assert candidates == []


def test_dedektor_yoksa_mekansal_sinyal_etkisiz_gorunur(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(anomaly_engine.settings, "BUILDING_DETECTOR_WEIGHTS", None)
    breakdown = _score(AnomalyEngine(), 90.0)
    assert anomaly_engine.INACTIVE_GEOSPATIAL in breakdown.inactive_signals
    assert breakdown.to_dict()["inactive_signals"]


async def test_dedektor_yoksa_mekansal_analiz_calismaz(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(anomaly_engine.settings, "BUILDING_DETECTOR_WEIGHTS", None)
    engine = AnomalyEngine()

    async def tiles(*_: Any) -> dict[str, Any]:
        return {}

    async def buildings(*_: Any) -> list[Any]:
        return []

    async def geospatial(*_: Any) -> None:
        raise AssertionError("bina dedektörü yokken mekânsal analiz çağrıldı")

    monkeypatch.setattr(engine, "_fetch_provider_tiles", tiles)
    monkeypatch.setattr(engine, "_fetch_osm_buildings", buildings)
    monkeypatch.setattr(engine, "_run_geospatial_analysis", geospatial)
    assert await engine.analyze(41.0, 29.0, 16) == []
    assert engine.last_run["tile_count"] == 0


def test_tarama_gorevi_adaylari_ikinci_kez_yazmaz() -> None:
    assert not hasattr(scan_tasks, "_write_anomalies_to_db")


def test_sansur_puani_tabana_gore_olceklenir() -> None:
    from app.services.analyzers.blur_detector import censorship_to_score

    assert censorship_to_score(0.0) == 0.0
    assert censorship_to_score(15.0) == 0.0  # sıradan konumların %90'ı bu kadar
    assert censorship_to_score(20.0) == pytest.approx(50.0)  # taban p99
    assert censorship_to_score(25.0) > 50.0


def test_taban_ustu_bulaniklik_sansurlu_bolge_adayi_uretir(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(anomaly_engine.settings, "BUILDING_DETECTOR_WEIGHTS", None)
    engine = AnomalyEngine(min_confidence=50.0)
    blur = {"censorship_score": 25.0, "most_blurred": "esri", "sharpest": "maptiler"}
    pixel = {"max_diff_score": 30.0, "disagreeing_count": 0}
    breakdown = engine._compute_confidence_score(
        pixel_diff_result=pixel, blur_result=blur, geospatial_result=None, provider_count=2,
    )
    candidates = engine._build_candidates(
        lat=48.3, lng=-4.5, score_breakdown=breakdown, pixel_diff_result=pixel,
        blur_result=blur, geospatial_result=None, provider_tiles={},
    )
    assert [c.category for c in candidates] == ["CENSORED_AREA"]
    assert candidates[0].confidence_score == pytest.approx(breakdown.blur_censorship_score)
    assert candidates[0].confidence_score > 50.0
