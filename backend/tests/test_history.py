"""
test_history.py — Esri Wayback zaman serisi: seçim, kanıt üretimi ve bulgu ucu.

Tarihsel skor puana girmez (ayırt edici değil, docs/calibration-history-z16.json); burada
zaman serisinin gerçekten üretildiği ve bulgu sayfasına ulaştığı sınanır.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from httpx import AsyncClient
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.analyzers.time_series import (
    Timeline,
    TimelineEntry,
    TimeSeriesAnalyzer,
)
from app.services.history_service import build_history
from tests.conftest import TestAnomaly


# ═══════════════════════════════════════════════════════════════════════════
# Yılın karesi seçimi — Esri Wayback ISO tarih verir
# ═══════════════════════════════════════════════════════════════════════════


def test_select_best_per_year_accepts_iso_dates():
    """Eskiden int("2016-01-") hatası tüm zaman serisini sessizce boşaltıyordu (20/20 konum 0 kare)."""
    snaps = [
        {"timestamp": "2016-01-15T00:00:00", "wayback_url": "a"},
        {"timestamp": "2016-06-20T00:00:00", "wayback_url": "b"},
        {"timestamp": "2016-12-30T00:00:00", "wayback_url": "c"},
        {"timestamp": "2019-03-01T00:00:00", "wayback_url": "d"},
    ]
    best = TimeSeriesAnalyzer._select_best_per_year(snaps)
    assert [s["wayback_url"] for s in best] == ["b", "d"]


def test_select_best_per_year_still_accepts_cdx_dates():
    snaps = [
        {"timestamp": "20160115120000", "wayback_url": "a"},
        {"timestamp": "20160705120000", "wayback_url": "b"},
    ]
    assert [s["wayback_url"] for s in TimeSeriesAnalyzer._select_best_per_year(snaps)] == ["b"]


# ═══════════════════════════════════════════════════════════════════════════
# build_history — kareleri kaydeder, değişimleri etiketler
# ═══════════════════════════════════════════════════════════════════════════


def _entry(date: str, shade: int) -> TimelineEntry:
    return TimelineEntry(date=date, year=int(date[:4]), image=Image.new("RGB", (256, 256), (shade, shade, shade)))


class _FakeAnalyzer(TimeSeriesAnalyzer):
    def __init__(self, entries):
        super().__init__()
        self._entries = entries

    async def fetch_timeline(self, lat, lng, zoom, **_):  # type: ignore[override]
        return Timeline(entries=self._entries, lat=lat, lng=lng, zoom=zoom)


@pytest.mark.asyncio
async def test_build_history_saves_frames_and_skips_no_change(tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.history_service.settings.STORAGE_ROOT", str(tmp_path))
    analyzer = _FakeAnalyzer([
        _entry("2016-07-01T00:00:00", 40),
        _entry("2018-07-01T00:00:00", 40),   # aynı görüntü → NO_CHANGE, listelenmez
        _entry("2022-07-01T00:00:00", 220),  # belirgin değişim
    ])

    history = await build_history(37.24, -115.79, 16, analyzer=analyzer)

    assert history["status"] == "ready"
    assert [s["date"] for s in history["snapshots"]] == ["2016-07-01", "2018-07-01", "2022-07-01"]
    for snap in history["snapshots"]:
        assert snap["image_url"].startswith("/media/anomaly_images/wayback_")
        assert (tmp_path / "anomaly_images" / snap["image_url"].rsplit("/", 1)[1]).exists()
    assert len(history["changes"]) == 1
    change = history["changes"][0]
    assert change["date_before"] == "2018-07-01" and change["date"] == "2022-07-01"
    assert change["label"]  # Türkçe etiket


@pytest.mark.asyncio
async def test_build_history_reports_empty_when_no_imagery(tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.history_service.settings.STORAGE_ROOT", str(tmp_path))
    history = await build_history(0.0, 0.0, 16, analyzer=_FakeAnalyzer([]))
    assert history["status"] == "empty"
    assert history["snapshots"] == [] and history["changes"] == []


# ═══════════════════════════════════════════════════════════════════════════
# GET /anomalies/{id}/history
# ═══════════════════════════════════════════════════════════════════════════


async def _anomaly(db: AsyncSession, meta: dict) -> TestAnomaly:
    anomaly = TestAnomaly(
        id=str(uuid.uuid4()), lat=37.2431, lng=-115.793, category="CENSORED_AREA",
        confidence_score=61.0, title="Zaman serisi testi", status="PENDING",
        source_providers=["esri", "maptiler"], detection_methods=["blur_detection"], meta_data=meta,
    )
    db.add(anomaly)
    await db.commit()
    return anomaly


@pytest.mark.asyncio
async def test_history_endpoint_queues_once_then_reports_pending(client: AsyncClient, db_session: AsyncSession):
    anomaly = await _anomaly(db_session, {})
    task = MagicMock()
    with patch("app.tasks.scan_tasks.build_anomaly_history", task):
        first = await client.get(f"/api/v1/anomalies/{anomaly.id}/history")
        second = await client.get(f"/api/v1/anomalies/{anomaly.id}/history")

    assert first.status_code == 200 and first.json()["status"] == "pending"
    assert second.json()["status"] == "pending"
    task.delay.assert_called_once_with(str(anomaly.id))


@pytest.mark.asyncio
async def test_history_endpoint_returns_ready_history_without_queueing(client: AsyncClient, db_session: AsyncSession):
    ready = {
        "status": "ready", "source": "Esri World Imagery Wayback", "zoom": 16,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "snapshots": [{"date": "2016-07-01", "year": 2016, "image_url": "/media/anomaly_images/wayback_x.png"}],
        "changes": [],
    }
    anomaly = await _anomaly(db_session, {"history": ready})
    task = MagicMock()
    with patch("app.tasks.scan_tasks.build_anomaly_history", task):
        response = await client.get(f"/api/v1/anomalies/{anomaly.id}/history")

    assert response.json()["status"] == "ready"
    assert response.json()["snapshots"][0]["year"] == 2016
    task.delay.assert_not_called()


@pytest.mark.asyncio
async def test_history_endpoint_requeues_a_stuck_job(client: AsyncClient, db_session: AsyncSession):
    stale = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    anomaly = await _anomaly(db_session, {"history": {"status": "pending", "queued_at": stale}})
    task = MagicMock()
    with patch("app.tasks.scan_tasks.build_anomaly_history", task):
        await client.get(f"/api/v1/anomalies/{anomaly.id}/history")
    task.delay.assert_called_once()


@pytest.mark.asyncio
async def test_history_endpoint_404(client: AsyncClient):
    response = await client.get(f"/api/v1/anomalies/{uuid.uuid4()}/history")
    assert response.status_code == 404
