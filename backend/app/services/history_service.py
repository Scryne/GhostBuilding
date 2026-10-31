"""
history_service.py — Bir bulgunun konumu için Esri Wayback zaman serisi (kanıt, puan değil).

Tarihsel değişim puanı ölçüldü ve anomali sinyali olarak kullanılamaz (docs/algorithms.md,
docs/calibration-history-z16.json): Esri sıradan şehirleri sık yeniler, her yeni çekim "yapı
belirdi/kayboldu" sayılır; 60 sıradan konumun ham skor medyanı 95/100, p90'ı 100. Referans
tesislerin çoğu kontrol şehirlerinden düşük çıktı (Groom Lake 3, Kadıköy 100). Bu yüzden zaman
serisi bulgu sayfasında insan incelemesi için gösterilir: konumun yıllar içindeki görüntüleri ve
görüntünün değiştiği tarihler.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import settings
from app.services.analyzers.time_series import ChangeType, TimeSeriesAnalyzer

logger = logging.getLogger(__name__)

HISTORY_SOURCE = "Esri World Imagery Wayback"
# Bulgu karoları da bu klasörden servis edilir (main.py: /media/anomaly_images).
HISTORY_MEDIA_SUBDIR = "anomaly_images"

CHANGE_LABELS: Dict[str, str] = {
    ChangeType.STRUCTURE_APPEARED.value: "Yeni yapı ya da yüzey",
    ChangeType.STRUCTURE_DISAPPEARED.value: "Yapı ya da yüzey kayboldu",
    ChangeType.BLUR_APPLIED.value: "Görüntü bulanıklaştı",
    ChangeType.BLUR_REMOVED.value: "Bulanıklık kalktı",
    ChangeType.RESOLUTION_CHANGED.value: "Çözünürlük değişti",
    ChangeType.SIGNIFICANT_CHANGE.value: "Belirgin değişim",
    ChangeType.MINOR_CHANGE.value: "Küçük değişim",
    ChangeType.NO_CHANGE.value: "Kayda değer değişim yok",
}


def _save_snapshot(image: Any, lat: float, lng: float, date: str) -> str:
    root = Path(getattr(settings, "STORAGE_ROOT", "data")) / HISTORY_MEDIA_SUBDIR
    root.mkdir(parents=True, exist_ok=True)
    filename = f"wayback_{lat:.4f}_{lng:.4f}_{date[:10]}_{uuid.uuid4().hex[:8]}.png"
    image.convert("RGB").save(str(root / filename), "PNG", optimize=True)
    return f"/media/{HISTORY_MEDIA_SUBDIR}/{filename}"


async def build_history(
    lat: float,
    lng: float,
    zoom: int,
    *,
    analyzer: Optional[TimeSeriesAnalyzer] = None,
) -> Dict[str, Any]:
    """Konumun Wayback zaman serisini toplar, görüntüleri kaydeder, gösterime hazır döndürür.

    Dönen sözlük ``Anomaly.meta_data["history"]`` alanına yazılır:
    ``status`` ("ready" | "empty"), ``source``, ``zoom``, ``generated_at``,
    ``snapshots`` [{date, year, image_url}], ``changes`` [{date, date_before, change_type,
    label, diff_score, ssim}]. Görüntü gelmezse ``status="empty"`` (ağ ya da kapsama yok).
    """
    analyzer = analyzer or TimeSeriesAnalyzer()
    timeline = await analyzer.fetch_timeline(lat, lng, zoom)
    changes = analyzer.detect_changes(timeline)

    snapshots: List[Dict[str, Any]] = []
    for entry in timeline.entries:
        try:
            url = _save_snapshot(entry.image, lat, lng, entry.date)
        except Exception as exc:  # disk dolu vb.: o kare atlanır, seri gösterilir
            logger.warning("Wayback karesi kaydedilemedi (%s): %s", entry.date, exc)
            continue
        snapshots.append({"date": entry.date[:10], "year": entry.year, "image_url": url})

    return {
        "status": "ready" if snapshots else "empty",
        "source": HISTORY_SOURCE,
        "zoom": zoom,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "snapshots": snapshots,
        "changes": [
            {
                "date": c.date[:10],
                "date_before": c.date_before[:10],
                "change_type": c.change_type.value,
                "label": CHANGE_LABELS.get(c.change_type.value, c.change_type.value),
                "diff_score": round(c.diff_score, 1),
                "ssim": round(c.ssim_score, 3),
            }
            for c in changes
            if c.change_type is not ChangeType.NO_CHANGE
        ],
    }


async def store_anomaly_history(anomaly_id: str) -> Dict[str, Any]:
    """Bulgunun zaman serisini üretip ``meta_data["history"]``'ye yazar (Celery görevi çağırır)."""
    from sqlalchemy import select

    from app.db.session import AsyncSessionLocal
    from app.models.anomaly import Anomaly

    async with AsyncSessionLocal() as session:
        anomaly = (await session.execute(select(Anomaly).where(Anomaly.id == anomaly_id))).scalar_one_or_none()
        if anomaly is None:
            return {"status": "missing"}
        lat, lng = anomaly.lat, anomaly.lng

    try:
        history = await build_history(lat, lng, settings.ANALYSIS_ZOOM)
    except Exception as exc:
        logger.exception("Zaman serisi üretilemedi (%s): %s", anomaly_id, exc)
        history = {"status": "failed", "generated_at": datetime.now(timezone.utc).isoformat()}

    async with AsyncSessionLocal() as session:
        anomaly = (await session.execute(select(Anomaly).where(Anomaly.id == anomaly_id))).scalar_one_or_none()
        if anomaly is None:
            return {"status": "missing"}
        # JSONB değişikliği yeni sözlükle atanır; yerinde değiştirmeyi SQLAlchemy görmez.
        anomaly.meta_data = {**(anomaly.meta_data or {}), "history": history}
        await session.commit()
    return history
