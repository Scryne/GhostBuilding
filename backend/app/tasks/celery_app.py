"""
celery_app.py — GhostBuilding Celery uygulama konfigürasyonu.

Redis broker ve result backend kullanır. JSON serializasyon,
UTC timezone ve periyodik görevler (beat schedule) tanımlar.

Kullanım:
    celery -A app.tasks.celery_app worker --loglevel=info
    celery -A app.tasks.celery_app beat --loglevel=info
"""

from celery import Celery
from celery.schedules import crontab
from kombu import Exchange, Queue

from app.config import settings

# ---------------------------------------------------------------------------
# Celery uygulaması
# ---------------------------------------------------------------------------

celery_app = Celery("ghostbuilding")

# ---------------------------------------------------------------------------
# Broker & Backend
# ---------------------------------------------------------------------------

celery_app.conf.broker_url = settings.REDIS_URL
celery_app.conf.result_backend = settings.REDIS_URL

# ---------------------------------------------------------------------------
# Serializasyon
# ---------------------------------------------------------------------------

celery_app.conf.task_serializer = "json"
celery_app.conf.result_serializer = "json"
celery_app.conf.accept_content = ["json"]
celery_app.conf.result_expires = 3600  # Sonuçlar 1 saat sonra temizlensin

# ---------------------------------------------------------------------------
# Timezone
# ---------------------------------------------------------------------------

celery_app.conf.timezone = "UTC"
celery_app.conf.enable_utc = True

# ---------------------------------------------------------------------------
# Görev keşfi — tasks modüllerini otomatik bul
# ---------------------------------------------------------------------------

celery_app.autodiscover_tasks(
    [
        "app.tasks",
    ],
    related_name="scan_tasks",
)
celery_app.autodiscover_tasks(
    [
        "app.tasks",
    ],
    related_name="maintenance_tasks",
)

# ---------------------------------------------------------------------------
# Kuyruk tanımları
# ---------------------------------------------------------------------------

default_exchange = Exchange("default", type="direct")
scan_exchange = Exchange("scan", type="direct")
maintenance_exchange = Exchange("maintenance", type="direct")

celery_app.conf.task_queues = (
    Queue("default", default_exchange, routing_key="default"),
    Queue("scan", scan_exchange, routing_key="scan"),
    Queue("scan_batch", scan_exchange, routing_key="scan.batch"),
    Queue("maintenance", maintenance_exchange, routing_key="maintenance"),
)

celery_app.conf.task_default_queue = "default"
celery_app.conf.task_default_exchange = "default"
celery_app.conf.task_default_routing_key = "default"

# ---------------------------------------------------------------------------
# Görev yönlendirme
# ---------------------------------------------------------------------------

celery_app.conf.task_routes = {
    "app.tasks.scan_tasks.scan_coordinate": {"queue": "scan"},
    "app.tasks.scan_tasks.batch_scan_region": {"queue": "scan_batch"},
    "app.tasks.scan_tasks.scan_high_priority_regions": {"queue": "scan"},
    "app.tasks.maintenance_tasks.*": {"queue": "maintenance"},
}

# ---------------------------------------------------------------------------
# Performans ayarları
# ---------------------------------------------------------------------------

celery_app.conf.worker_prefetch_multiplier = 1  # Adil dağıtım
celery_app.conf.worker_max_tasks_per_child = 100  # Bellek sızıntısını önle
celery_app.conf.worker_concurrency = 4  # Paralel worker sayısı
celery_app.conf.task_acks_late = True  # Görev bitmeden ACK gönderme
celery_app.conf.task_reject_on_worker_lost = True  # Worker ölürse görev geri kuyruğa

# Zaman aşımı (saniye)
celery_app.conf.task_soft_time_limit = 300  # Soft limit: 5 dk
celery_app.conf.task_time_limit = 600  # Hard limit: 10 dk

# ---------------------------------------------------------------------------
# Beat Schedule — Periyodik görevler
# ---------------------------------------------------------------------------

celery_app.conf.beat_schedule = {
    # Her 6 saatte bir: Yüksek öncelikli bölgeleri tara
    "scan-high-priority-regions-every-6h": {
        "task": "app.tasks.scan_tasks.scan_high_priority_regions",
        "schedule": crontab(minute=0, hour="*/6"),
        "options": {"queue": "scan"},
        "kwargs": {},
    },
    # Her gün gece yarısı (UTC): Süresi dolmuş cache'i temizle
    "cleanup-expired-cache-daily": {
        "task": "app.tasks.maintenance_tasks.cleanup_expired_cache",
        "schedule": crontab(minute=0, hour=0),
        "options": {"queue": "maintenance"},
    },
    # Her Pazartesi 03:00 UTC: Haftalık rapor oluştur
    "generate-weekly-report-monday": {
        "task": "app.tasks.maintenance_tasks.generate_weekly_report",
        "schedule": crontab(minute=0, hour=3, day_of_week="monday"),
        "options": {"queue": "maintenance"},
    },
}
