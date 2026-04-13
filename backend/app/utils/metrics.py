"""
metrics.py — GhostBuilding Prometheus Metrikleri.

Tanımlanan metrikler:
- HTTP istek sayısı ve latency histogram (endpoint bazında)
- Anomali tespit sayısı (kategori bazında)
- Celery görev başarı/hata oranı
- Cache hit/miss oranı

Kullanım:
    from app.utils.metrics import (
        http_requests_total,
        http_request_duration_seconds,
        anomaly_detections_total,
        celery_task_total,
        cache_operations_total,
        metrics_endpoint,
    )

Prometheus scraping:
    GET /metrics
"""

from __future__ import annotations

from prometheus_client import (
    Counter,
    Histogram,
    Gauge,
    Info,
    generate_latest,
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    REGISTRY,
)
from starlette.requests import Request
from starlette.responses import Response


# ═══════════════════════════════════════════════════════════════════════════════
# HTTP Metrikleri
# ═══════════════════════════════════════════════════════════════════════════════

http_requests_total = Counter(
    "ghostbuilding_http_requests_total",
    "Toplam HTTP istek sayısı",
    ["method", "endpoint", "status_code"],
)

http_request_duration_seconds = Histogram(
    "ghostbuilding_http_request_duration_seconds",
    "HTTP istek süresi (saniye)",
    ["method", "endpoint"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0),
)

http_requests_in_progress = Gauge(
    "ghostbuilding_http_requests_in_progress",
    "Şu an işlenen HTTP istek sayısı",
    ["method"],
)


# ═══════════════════════════════════════════════════════════════════════════════
# Anomali Tespit Metrikleri
# ═══════════════════════════════════════════════════════════════════════════════

anomaly_detections_total = Counter(
    "ghostbuilding_anomaly_detections_total",
    "Tespit edilen anomali sayısı (kategori bazında)",
    ["category", "severity"],
)

anomaly_scan_duration_seconds = Histogram(
    "ghostbuilding_anomaly_scan_duration_seconds",
    "Anomali tarama süresi (saniye)",
    ["scan_type"],
    buckets=(0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0),
)

active_scans = Gauge(
    "ghostbuilding_active_scans",
    "Aktif tarama sayısı",
)


# ═══════════════════════════════════════════════════════════════════════════════
# Celery Görev Metrikleri
# ═══════════════════════════════════════════════════════════════════════════════

celery_task_total = Counter(
    "ghostbuilding_celery_task_total",
    "Celery görev sayısı",
    ["task_name", "status"],  # status: success, failure, retry
)

celery_task_duration_seconds = Histogram(
    "ghostbuilding_celery_task_duration_seconds",
    "Celery görev süresi (saniye)",
    ["task_name"],
    buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 300.0, 600.0),
)


# ═══════════════════════════════════════════════════════════════════════════════
# Cache Metrikleri
# ═══════════════════════════════════════════════════════════════════════════════

cache_operations_total = Counter(
    "ghostbuilding_cache_operations_total",
    "Cache operasyon sayısı",
    ["operation"],  # operation: hit, miss, set, delete
)


# ═══════════════════════════════════════════════════════════════════════════════
# Sistem Bilgisi
# ═══════════════════════════════════════════════════════════════════════════════

app_info = Info(
    "ghostbuilding_app",
    "GhostBuilding uygulama bilgileri",
)


def set_app_info(version: str, environment: str) -> None:
    """Uygulama bilgilerini ayarlar (startup'ta bir kez çağrılır)."""
    app_info.info({
        "version": version,
        "environment": environment,
        "service": "ghostbuilding-api",
    })


# ═══════════════════════════════════════════════════════════════════════════════
# Metrics Endpoint
# ═══════════════════════════════════════════════════════════════════════════════

async def metrics_endpoint(request: Request) -> Response:
    """
    Prometheus scraping endpoint'i.

    GET /metrics → Prometheus metrikleri (text/plain)
    """
    return Response(
        content=generate_latest(REGISTRY),
        media_type=CONTENT_TYPE_LATEST,
    )
