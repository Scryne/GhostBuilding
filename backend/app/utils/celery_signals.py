"""
celery_signals.py — Celery Görev Sinyal Dinleyicileri.

Prometheus metriklerini Celery görev yaşam döngüsü sinyalleri
üzerinden otomatik olarak günceller.

Her görev başladığında, başarıyla tamamlandığında veya hata aldığında
ilgili Prometheus counter ve histogram güncellenir.

Kullanım:
    celery_app.py'de import edin:
        import app.utils.celery_signals  # noqa: F401
"""

from __future__ import annotations

import time
from typing import Any

from celery.signals import (
    task_prerun,
    task_postrun,
    task_failure,
    task_retry,
)


# Görev başlangıç zamanlarını sakla
_task_start_times: dict[str, float] = {}


@task_prerun.connect
def _on_task_prerun(
    sender: Any = None,
    task_id: str = "",
    task: Any = None,
    **kwargs: Any,
) -> None:
    """Görev başlamadan önce: başlangıç zamanını kaydet."""
    _task_start_times[task_id] = time.perf_counter()


@task_postrun.connect
def _on_task_postrun(
    sender: Any = None,
    task_id: str = "",
    task: Any = None,
    state: str = "",
    **kwargs: Any,
) -> None:
    """Görev tamamlandıktan sonra: süre ve başarı metriklerini kaydet."""
    try:
        from app.utils.metrics import celery_task_total, celery_task_duration_seconds

        task_name = task.name if task else "unknown"

        # Başarı counter
        celery_task_total.labels(task_name=task_name, status="success").inc()

        # Süre histogram
        start_time = _task_start_times.pop(task_id, None)
        if start_time is not None:
            duration = time.perf_counter() - start_time
            celery_task_duration_seconds.labels(task_name=task_name).observe(duration)

    except Exception:
        pass


@task_failure.connect
def _on_task_failure(
    sender: Any = None,
    task_id: str = "",
    exception: Exception = None,
    **kwargs: Any,
) -> None:
    """Görev hata aldığında: hata counter'ını güncelle."""
    try:
        from app.utils.metrics import celery_task_total

        task_name = sender.name if sender else "unknown"
        celery_task_total.labels(task_name=task_name, status="failure").inc()

        # Başlangıç zamanını temizle
        _task_start_times.pop(task_id, None)

    except Exception:
        pass


@task_retry.connect
def _on_task_retry(
    sender: Any = None,
    request: Any = None,
    reason: str = "",
    **kwargs: Any,
) -> None:
    """Görev retry durumunda: retry counter'ını güncelle."""
    try:
        from app.utils.metrics import celery_task_total

        task_name = sender.name if sender else "unknown"
        celery_task_total.labels(task_name=task_name, status="retry").inc()

    except Exception:
        pass
