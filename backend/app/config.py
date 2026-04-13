from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List, Optional

class Settings(BaseSettings):
    # APP Configuration
    APP_NAME: str = "GhostBuilding"
    VERSION: str = "0.1.0"
    DEBUG: bool = False
    ENVIRONMENT: str = "dev"
    SECRET_KEY: str = "supersecretkey_change_in_production"
    ALLOWED_ORIGINS: List[str] = ["*"]
    MAX_SCAN_RADIUS_KM: int = 50
    ANOMALY_CONFIDENCE_THRESHOLD: float = 60.0

    # DATABASE Configuration
    DATABASE_URL: str
    DATABASE_POOL_SIZE: int = 20
    MAX_OVERFLOW: int = 10

    # REDIS Configuration
    REDIS_URL: str
    CACHE_TTL_SECONDS: int = 3600

    # API KEYS (Optional)
    GOOGLE_MAPS_API_KEY: Optional[str] = None
    BING_MAPS_API_KEY: Optional[str] = None
    SENTINEL_HUB_CLIENT_ID: Optional[str] = None
    SENTINEL_HUB_CLIENT_SECRET: Optional[str] = None
    OPENAI_API_KEY: Optional[str] = None

    # STORAGE Configuration (MinIO / Local)
    MINIO_ENDPOINT: str = "minio:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_SECURE: bool = False
    MINIO_BUCKET: str = "satellite-images"
    STORAGE_ROOT: str = "data"

    # RATE LIMITING Configuration
    RATE_LIMIT_PER_MINUTE: int = 60
    RATE_LIMIT_SCAN_PER_HOUR: int = 10
    RATE_LIMIT_LOGIN_PER_MINUTE: int = 5

    # SENTRY Configuration
    SENTRY_DSN: Optional[str] = None
    SENTRY_TRACES_SAMPLE_RATE: float = 0.2
    SENTRY_PROFILES_SAMPLE_RATE: float = 0.1

    # MONITORING Configuration
    ENABLE_PROMETHEUS: bool = True

    model_config = SettingsConfigDict(
        env_file=".env", 
        env_file_encoding="utf-8", 
        extra="ignore"
    )

settings = Settings()
