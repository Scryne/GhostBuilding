"""
worker.py — Celery app backward-compat re-export.

Eski import yolunu koruyor: celery_app.tasks.celery_app'a yönlendirir.
Docker Compose komutlarında bu modül referans edilebilir.

Kullanım:
    celery -A app.worker.celery_app worker --loglevel=info
    celery -A app.worker.celery_app beat --loglevel=info
"""

# Yeni modülden re-export
from app.tasks.celery_app import celery_app  # noqa: F401

# Görev modüllerini import et (keşif için)
import app.tasks.scan_tasks  # noqa: F401
import app.tasks.maintenance_tasks  # noqa: F401
