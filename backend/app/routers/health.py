"""
health.py — GhostBuilding Health Check Router.

Detaylı sistem sağlık kontrolü:
- Database bağlantısı
- Redis bağlantısı
- Celery worker durumu
- Uygulama sürümü ve uptime

Kullanım:
    GET /api/v1/health → Detaylı sağlık raporu
    GET /health → Basit liveness check
"""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.session import get_db
from app.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter()

# Uygulama başlangıç zamanı
_app_start_time: float = time.time()


async def _check_database(db: AsyncSession) -> dict[str, Any]:
    """PostgreSQL bağlantı kontrolü."""
    try:
        result = await db.execute(text("SELECT 1"))
        result.scalar()
        return {"status": "connected", "latency_ms": None}
    except Exception as e:
        logger.error("health_check_db_failed", error=str(e))
        return {"status": "disconnected", "error": str(e)}


async def _check_redis() -> dict[str, Any]:
    """Redis bağlantı kontrolü."""
    try:
        import redis.asyncio as aioredis

        client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        start = time.perf_counter()
        await client.ping()
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        await client.aclose()
        return {"status": "connected", "latency_ms": latency_ms}
    except Exception as e:
        logger.error("health_check_redis_failed", error=str(e))
        return {"status": "disconnected", "error": str(e)}


async def _check_celery() -> dict[str, Any]:
    """Celery worker durumunu kontrol eder."""
    try:
        from app.tasks.celery_app import celery_app

        # Inspect ile aktif worker'ları sorgula (timeout: 2 saniye)
        inspector = celery_app.control.inspect(timeout=2.0)
        active_workers = inspector.ping()

        if active_workers:
            worker_names = list(active_workers.keys())
            return {
                "status": "running",
                "workers": len(worker_names),
                "worker_names": worker_names,
            }
        else:
            return {"status": "no_workers", "workers": 0}
    except Exception as e:
        logger.error("health_check_celery_failed", error=str(e))
        return {"status": "error", "error": str(e)}


@router.get("/health", tags=["system"])
async def detailed_health_check(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """
    Detaylı sistem sağlık kontrolü.

    Returns:
        {
            "status": "healthy" | "degraded" | "unhealthy",
            "database": "connected" | "disconnected",
            "redis": "connected" | "disconnected",
            "celery": "running" | "no_workers" | "error",
            "version": "0.1.0",
            "environment": "dev",
            "uptime_seconds": 3600
        }
    """
    # Paralel olmayan ama güvenli kontroller
    db_status = await _check_database(db)
    redis_status = await _check_redis()
    celery_status = await _check_celery()

    uptime_seconds = round(time.time() - _app_start_time, 2)

    # Genel durum belirleme
    checks = {
        "database": db_status["status"],
        "redis": redis_status["status"],
        "celery": celery_status["status"],
    }

    if all(v in ("connected", "running") for v in checks.values()):
        overall = "healthy"
    elif checks["database"] == "disconnected":
        overall = "unhealthy"
    else:
        overall = "degraded"

    response = {
        "status": overall,
        "database": db_status["status"],
        "redis": redis_status["status"],
        "celery": celery_status["status"],
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
        "uptime_seconds": uptime_seconds,
        "details": {
            "database": db_status,
            "redis": redis_status,
            "celery": celery_status,
        },
    }

    log_method = logger.info if overall == "healthy" else logger.warning
    log_method("health_check", **{k: v for k, v in response.items() if k != "details"})

    return response


@router.get("/health/liveness", tags=["system"])
async def liveness_check() -> dict[str, str]:
    """Basit liveness check — K8s/Docker için."""
    return {"status": "alive"}


@router.get("/health/readiness", tags=["system"])
async def readiness_check(db: AsyncSession = Depends(get_db)) -> dict[str, str]:
    """Readiness check — DB bağlantısı doğrular."""
    db_check = await _check_database(db)
    if db_check["status"] == "connected":
        return {"status": "ready"}
    return {"status": "not_ready", "reason": "database_disconnected"}
