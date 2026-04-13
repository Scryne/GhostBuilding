"""
conftest.py — Test konfigürasyonu ve fixture'ları.

SQLite in-memory veritabanı, AsyncClient, test kullanıcıları
ve mock Celery ile CI-uyumlu test ortamı sağlar.

PostGIS bağımlılıkları kaldırılmış test modelleri kullanılır.
"""

from __future__ import annotations

import os
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["REDIS_URL"] = "redis://localhost:6379/0"

import asyncio
import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import Column, String, Float, Text, Integer, Boolean, DateTime, event, ForeignKey
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, relationship

# ---------------------------------------------------------------------------
# Test Base — PostGIS olmadan
# ---------------------------------------------------------------------------


class TestBase(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Test Modelleri — SQLite uyumlu (PostGIS/Geometry kaldırıldı)
# ---------------------------------------------------------------------------


class TestUser(TestBase):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String, unique=True, index=True, nullable=False)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=True)
    role = Column(String, default="USER", nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)
    trust_score = Column(Float, default=50.0)
    verified_count = Column(Integer, default=0)
    submitted_count = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    verifications = relationship("TestVerification", back_populates="user")


class TestAnomaly(TestBase):
    __tablename__ = "anomalies"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    lat = Column(Float, nullable=False)
    lng = Column(Float, nullable=False)
    # geom sütunu yok — PostGIS gerektirdiği için test'lerde kaldırıldı
    category = Column(String, nullable=False)
    confidence_score = Column(Float, default=0.0)
    title = Column(String)
    description = Column(Text)
    status = Column(String, default="PENDING")
    detected_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    verified_at = Column(DateTime(timezone=True), nullable=True)
    source_providers = Column(JSON, default=list)
    detection_methods = Column(JSON, default=list)
    meta_data = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    images = relationship("TestAnomalyImage", back_populates="anomaly", cascade="all, delete-orphan")
    verifications = relationship("TestVerification", back_populates="anomaly", cascade="all, delete-orphan")

    @property
    def is_highly_confident(self):
        return self.confidence_score >= 85.0


class TestAnomalyImage(TestBase):
    __tablename__ = "anomaly_images"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    anomaly_id = Column(String, ForeignKey("anomalies.id"), nullable=False)
    provider = Column(String, nullable=False)
    image_url = Column(String, nullable=False)
    captured_at = Column(DateTime(timezone=True), nullable=True)
    zoom_level = Column(Integer, nullable=True)
    tile_x = Column(Integer, nullable=True)
    tile_y = Column(Integer, nullable=True)
    tile_z = Column(Integer, nullable=True)
    diff_score = Column(Float, nullable=True)
    is_blurred = Column(Boolean, default=False)

    anomaly = relationship("TestAnomaly", back_populates="images")


class TestVerification(TestBase):
    __tablename__ = "verifications"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    anomaly_id = Column(String, ForeignKey("anomalies.id"), nullable=False)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    vote = Column(String, nullable=False)
    comment = Column(Text)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    anomaly = relationship("TestAnomaly", back_populates="verifications")
    user = relationship("TestUser", back_populates="verifications")


# ---------------------------------------------------------------------------
# Async Engine & Session
# ---------------------------------------------------------------------------

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="session")
def event_loop() -> Generator:
    """Session-scoped event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def test_engine():
    """Session-scoped async engine (SQLite in-memory)."""
    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
        future=True,
    )

    async with engine.begin() as conn:
        await conn.run_sync(TestBase.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(TestBase.metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Per-test async DB session with automatic rollback."""
    session_factory = async_sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )

    async with session_factory() as session:
        yield session
        await session.rollback()


# ---------------------------------------------------------------------------
# Model Patching — ORM sınıflarını test modelleriyle değiştir
# ---------------------------------------------------------------------------


def _patch_models():
    """
    app.models.* modüllerindeki sınıfları test modelleriyle değiştirir.
    Bu sayede router/service kodları PostGIS olmadan SQLite'ta çalışır.
    """
    patches = [
        patch("app.models.user.User", TestUser),
        patch("app.models.anomaly.Anomaly", TestAnomaly),
        patch("app.models.anomaly_image.AnomalyImage", TestAnomalyImage),
        patch("app.models.verification.Verification", TestVerification),
    ]
    return patches


# ---------------------------------------------------------------------------
# FastAPI Test Client
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """
    Async HTTP test client.

    - app.db.session.get_db → test session ile override
    - Redis bağımlılıkları mock'lanır
    - Celery task'lar eager mode'da çalışır
    """
    # Model patching
    model_patches = _patch_models()
    for p in model_patches:
        p.start()

    # Lazy import — patchler aktifken
    from app.main import app
    from app.db.session import get_db

    # DB override
    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db

    # Redis mock
    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.set = AsyncMock(return_value=True)
    mock_redis.incr = AsyncMock(return_value=1)
    mock_redis.expire = AsyncMock(return_value=True)
    mock_redis.ttl = AsyncMock(return_value=3600)
    mock_redis.delete = AsyncMock(return_value=1)
    mock_redis.aclose = AsyncMock()
    mock_redis.pipeline = MagicMock(return_value=mock_redis)
    mock_redis.execute = AsyncMock(return_value=[1, True])

    redis_patch = patch(
        "app.services.auth_service._get_redis",
        return_value=mock_redis,
    )
    redis_patch.start()

    # Anomaly router'daki Redis de mock'la
    redis_patch2 = patch(
        "app.routers.anomalies._get_redis_client",
        return_value=mock_redis,
    )
    redis_patch2.start()

    # Rate limiter Redis mock
    redis_patch3 = patch(
        "app.middleware.rate_limiter._get_redis",
        return_value=None,  # Grace mode — rate limit kontrolü atlanır
    )
    redis_patch3.start()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    # Temizlik
    app.dependency_overrides.clear()
    redis_patch.stop()
    redis_patch2.stop()
    redis_patch3.stop()
    for p in model_patches:
        p.stop()


# ---------------------------------------------------------------------------
# Test Kullanıcıları
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession) -> TestUser:
    """Standart USER rolünde test kullanıcısı."""
    from app.services.auth_service import AuthService

    user = TestUser(
        id=str(uuid.uuid4()),
        email="testuser@ghostbuilding.io",
        username="test_user",
        hashed_password=AuthService.hash_password("TestPass1"),
        role="USER",
        is_active=True,
        is_verified=True,
        trust_score=50.0,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def test_moderator(db_session: AsyncSession) -> TestUser:
    """MODERATOR rolünde test kullanıcısı."""
    from app.services.auth_service import AuthService

    user = TestUser(
        id=str(uuid.uuid4()),
        email="moderator@ghostbuilding.io",
        username="test_moderator",
        hashed_password=AuthService.hash_password("ModPass1"),
        role="MODERATOR",
        is_active=True,
        is_verified=True,
        trust_score=60.0,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def test_admin(db_session: AsyncSession) -> TestUser:
    """ADMIN rolünde test kullanıcısı."""
    from app.services.auth_service import AuthService

    user = TestUser(
        id=str(uuid.uuid4()),
        email="admin@ghostbuilding.io",
        username="test_admin",
        hashed_password=AuthService.hash_password("AdminPass1"),
        role="ADMIN",
        is_active=True,
        is_verified=True,
        trust_score=80.0,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


# ---------------------------------------------------------------------------
# Auth Token Helpers
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def user_token(test_user: TestUser) -> str:
    """USER rolünde access token."""
    from app.services.auth_service import AuthService

    return AuthService.create_access_token(
        user_id=str(test_user.id),
        role=test_user.role,
    )


@pytest_asyncio.fixture
async def moderator_token(test_moderator: TestUser) -> str:
    """MODERATOR rolünde access token."""
    from app.services.auth_service import AuthService

    return AuthService.create_access_token(
        user_id=str(test_moderator.id),
        role=test_moderator.role,
    )


@pytest_asyncio.fixture
async def admin_token(test_admin: TestUser) -> str:
    """ADMIN rolünde access token."""
    from app.services.auth_service import AuthService

    return AuthService.create_access_token(
        user_id=str(test_admin.id),
        role=test_admin.role,
    )


def auth_header(token: str) -> dict:
    """Bearer token ile Authorization header oluşturur."""
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Test Anomalisi
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def test_anomaly(db_session: AsyncSession) -> TestAnomaly:
    """Test anomalisi (PENDING durumunda)."""
    anomaly = TestAnomaly(
        id=str(uuid.uuid4()),
        lat=41.0082,
        lng=28.9784,
        category="GHOST_BUILDING",
        confidence_score=72.5,
        title="Test Anomaly — İstanbul",
        description="Test amaçlı oluşturulmuş anomali.",
        status="PENDING",
        source_providers=["GOOGLE", "OSM"],
        detection_methods=["pixel_diff"],
        meta_data={"base_confidence": 72.5},
    )
    db_session.add(anomaly)
    await db_session.commit()
    await db_session.refresh(anomaly)
    return anomaly


# ---------------------------------------------------------------------------
# Celery Mock
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_celery():
    """Celery task'ları mock'lar — eager mode simülasyonu."""
    mock_task = MagicMock()
    mock_task.id = str(uuid.uuid4())
    mock_task.delay = MagicMock(return_value=mock_task)
    mock_task.apply_async = MagicMock(return_value=mock_task)

    with patch(
        "app.tasks.scan_tasks.scan_coordinate",
        mock_task,
    ) as mocked:
        yield mocked
