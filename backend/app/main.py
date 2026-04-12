import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, APIRouter
from fastapi.middleware.cors import CORSMiddleware
import redis.asyncio as redis

# Import configs and DB settings
from app.config import settings
from app.db.session import engine
from app.routers import map_routes, anomalies, auth, verifications

# Configure basic logging level
logging.basicConfig(level=logging.INFO if not settings.DEBUG else logging.DEBUG)
logger = logging.getLogger(__name__)

# Global redis client variable to cleanly close later
redis_client = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup and Shutdown events for FastAPI lifecycle.
    """
    # ====== STARTUP ====== #
    logger.info(f"Starting {settings.APP_NAME} in {settings.ENVIRONMENT} mode...")
    
    global redis_client
    try:
        redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
        # Verify redis connection
        await redis_client.ping()
        logger.info("Redis connection established successfully.")
    except Exception as e:
        logger.error(f"Redis configuration failed: {e}")

    # Yield control to the application
    yield
    
    # ====== SHUTDOWN ====== #
    logger.info("Initiating shutdown sequences...")
    
    # Close Redis Connection
    if redis_client:
        await redis_client.aclose()
        logger.info("Redis connection closed.")
        
    # Dispose SQLAlchemy Async Engine
    logger.info("Disposing async DB connection pool...")
    await engine.dispose()
    logger.info("Application shutdown complete.")

# Create FastAPI application instance with custom branding
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.VERSION,
    description="OSINT platform designed to identify and highlight geographical discrepancies between various maps providers.",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_tags=[
        {"name": "system", "description": "System health and status endpoints."},
        {"name": "auth", "description": "Authentication, authorization and user management."},
        {"name": "maps", "description": "Map intel operations and OSINT analytics."},
        {"name": "anomalies", "description": "Anomaly detection, scanning, comparison and statistics."},
        {"name": "verifications", "description": "Community verification voting and trust scoring."},
    ]
)

# Set up CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Main API Version 1 Router
api_v1_router = APIRouter(prefix="/api/v1")

@api_v1_router.get("/health", tags=["system"])
async def health_check():
    """
    Healthcheck endpoint for Kubernetes, Docker, and system administrators.
    Verifies that the backend is alive.
    """
    return {
        "status": "healthy",
        "app_name": settings.APP_NAME,
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT
    }

# Include nested domain routers to v1 Router
api_v1_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_v1_router.include_router(map_routes.router, prefix="/maps", tags=["maps"])
api_v1_router.include_router(anomalies.router, prefix="/anomalies", tags=["anomalies"])
api_v1_router.include_router(verifications.router, prefix="/anomalies", tags=["verifications"])

# Finalize the inclusion into the main app object
app.include_router(api_v1_router)

@app.get("/", include_in_schema=False)
def read_root():
    return {"message": f"Welcome to {settings.APP_NAME} API. Please navigate to /docs for OpenAPI specifications."}
