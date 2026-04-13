"""
metrics_middleware.py — Prometheus HTTP Metrics Middleware.

Her HTTP isteği için otomatik olarak:
- http_requests_total counter
- http_request_duration_seconds histogram
- http_requests_in_progress gauge
metriklerini günceller.

Kullanım:
    app.add_middleware(PrometheusMiddleware)
"""

from __future__ import annotations

import time

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.utils.metrics import (
    http_requests_total,
    http_request_duration_seconds,
    http_requests_in_progress,
)


def _normalize_path(path: str) -> str:
    """
    Endpoint yolunu normalize eder (UUID, ID gibi dinamik segmentleri kaldırır).
    Prometheus kardinalitesini düşük tutar.
    """
    import re

    # UUID pattern
    path = re.sub(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
        "{id}",
        path,
    )
    # Numeric IDs
    path = re.sub(r"/\d+", "/{id}", path)
    return path


class PrometheusMiddleware(BaseHTTPMiddleware):
    """Her HTTP isteği için Prometheus metriklerini otomatik toplar."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        method = request.method
        path = _normalize_path(request.url.path)

        # /metrics endpoint'i metriklerden hariç tut
        if path == "/metrics":
            return await call_next(request)

        http_requests_in_progress.labels(method=method).inc()
        start_time = time.perf_counter()

        try:
            response = await call_next(request)
        except Exception:
            http_requests_total.labels(
                method=method, endpoint=path, status_code="500"
            ).inc()
            http_requests_in_progress.labels(method=method).dec()
            raise

        duration = time.perf_counter() - start_time
        status_code = str(response.status_code)

        http_requests_total.labels(
            method=method, endpoint=path, status_code=status_code
        ).inc()
        http_request_duration_seconds.labels(method=method, endpoint=path).observe(
            duration
        )
        http_requests_in_progress.labels(method=method).dec()

        return response
