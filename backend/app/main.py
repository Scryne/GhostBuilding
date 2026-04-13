from contextlib import asynccontextmanager
from fastapi import FastAPI, APIRouter
from fastapi.middleware.cors import CORSMiddleware
import redis.asyncio as redis

# Import configs and DB settings
from app.config import settings
from app.db.session import engine
from app.routers import map_routes, anomalies, auth, verifications
from app.routers import health as health_router

# Structured logging (replaces stdlib logging)
from app.utils.logger import configure_logging, get_logger

# Monitoring & Observability
from app.utils.sentry import init_sentry
from app.utils.metrics import metrics_endpoint, set_app_info

# Security middleware
from app.middleware.rate_limiter import RateLimitMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware

# Observability middleware
from app.middleware.logging_middleware import RequestLoggingMiddleware
from app.middleware.metrics_middleware import PrometheusMiddleware

# ─── Configure structured logging BEFORE anything else ───────────────────────
configure_logging(
    environment=settings.ENVIRONMENT,
    log_level="DEBUG" if settings.DEBUG else "INFO",
)
logger = get_logger(__name__)

# ─── Initialize Sentry error tracking ────────────────────────────────────────
init_sentry()

# Global redis client variable to cleanly close later
redis_client = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup and Shutdown events for FastAPI lifecycle.
    """
    # ====== STARTUP ====== #
    logger.info(
        "app_starting",
        app_name=settings.APP_NAME,
        environment=settings.ENVIRONMENT,
        version=settings.VERSION,
    )

    # Set Prometheus app info
    set_app_info(version=settings.VERSION, environment=settings.ENVIRONMENT)

    global redis_client
    try:
        redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
        # Verify redis connection
        await redis_client.ping()
        logger.info("redis_connected")
    except Exception as e:
        logger.error("redis_connection_failed", error=str(e))

    # Yield control to the application
    yield

    # ====== SHUTDOWN ====== #
    logger.info("app_shutting_down")

    # Close Redis Connection
    if redis_client:
        await redis_client.aclose()
        logger.info("redis_disconnected")

    # Dispose SQLAlchemy Async Engine
    logger.info("db_pool_disposing")
    await engine.dispose()
    logger.info("app_shutdown_complete")

# Create FastAPI application instance with custom branding
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.VERSION,
    description="OSINT platform designed to identify and highlight geographical discrepancies between various maps providers.",
    lifespan=lifespan,
    # OWASP A05: Disable debug docs in production
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    openapi_tags=[
        {"name": "system", "description": "System health and status endpoints."},
        {"name": "auth", "description": "Authentication, authorization and user management."},
        {"name": "maps", "description": "Map intel operations and OSINT analytics."},
        {"name": "anomalies", "description": "Anomaly detection, scanning, comparison and statistics."},
        {"name": "verifications", "description": "Community verification voting and trust scoring."},
    ]
)

# ═══════════════════════════════════════════════════════════════════════════
# Middleware Stack (reverse order — last added = first executed)
# ═══════════════════════════════════════════════════════════════════════════

# 1. CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    expose_headers=["X-RateLimit-Limit", "X-RateLimit-Remaining", "X-RateLimit-Reset", "Retry-After", "X-Request-ID"],
)

# 2. Security Headers Middleware
app.add_middleware(SecurityHeadersMiddleware)

# 3. Rate Limiting Middleware
app.add_middleware(RateLimitMiddleware)

# 4. Request Logging Middleware (structlog — request_id, user_id binding)
app.add_middleware(RequestLoggingMiddleware)

# 5. Prometheus Metrics Middleware
app.add_middleware(PrometheusMiddleware)

# ═══════════════════════════════════════════════════════════════════════════
# Prometheus /metrics endpoint (outside API versioning)
# ═══════════════════════════════════════════════════════════════════════════
app.add_route("/metrics", metrics_endpoint, methods=["GET"])

# Main API Version 1 Router
api_v1_router = APIRouter(prefix="/api/v1")

# Include nested domain routers to v1 Router
api_v1_router.include_router(health_router.router, tags=["system"])
api_v1_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_v1_router.include_router(map_routes.router, prefix="/maps", tags=["maps"])
api_v1_router.include_router(anomalies.router, prefix="/anomalies", tags=["anomalies"])
api_v1_router.include_router(verifications.router, prefix="/anomalies", tags=["verifications"])

# Finalize the inclusion into the main app object
app.include_router(api_v1_router)

@app.get("/", include_in_schema=False)
def read_root():
    return {"message": f"Welcome to {settings.APP_NAME} API. Please navigate to /docs for OpenAPI specifications."}
