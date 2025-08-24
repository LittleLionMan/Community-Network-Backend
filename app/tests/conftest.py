import pytest
import pytest_asyncio
import uuid
import os
from typing import AsyncGenerator
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

# ✅ Environment setup
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test.db")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-testing-only")
os.environ.setdefault("DEBUG", "true")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("RATE_LIMIT_PER_MINUTE", "1000")  # ✅ Disable rate limiting for tests
os.environ["CONTENT_MODERATION_ENABLED"] = "true"

import sys
from pathlib import Path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from app.main import app
from app.database import get_db  # ✅ No more Base import here
from app.models.base import Base  # ✅ Import Base directly from models
# ✅ Import ALL models to ensure tables are created
from app import models  # This imports all models from __init__.py
from app.models import *  # Import everything explicitly

TEST_DATABASE_URL = "sqlite+aiosqlite:///./test.db"

@pytest_asyncio.fixture  # ✅ Default function scope
async def async_engine():
    """Create test database engine"""
    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
        connect_args={"check_same_thread": False}
    )

    # ✅ Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    # ✅ Cleanup
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()
    except:
        pass  # Ignore cleanup errors

@pytest_asyncio.fixture
async def async_session(async_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create isolated test session"""
    async_session_maker = async_sessionmaker(
        bind=async_engine,
        class_=AsyncSession,
        expire_on_commit=False
    )

    async with async_session_maker() as session:
        yield session
        await session.rollback()  # ✅ Always rollback test changes

@pytest_asyncio.fixture
async def async_client(async_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Create test client with database override"""
    async def override_get_db():
        yield async_session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as ac:
        yield ac

    app.dependency_overrides.clear()

# ✅ Simplified test data fixtures
def _get_unique_user_data(base_name: str = "testuser"):
    unique_id = str(uuid.uuid4())[:8]
    return {
        "display_name": f"{base_name}_{unique_id}",
        "email": f"{base_name}_{unique_id}@example.com",
        "password": "TestPass123!",
        "first_name": "Test",
        "last_name": "User"
    }

@pytest_asyncio.fixture
async def test_user_data():
    return _get_unique_user_data("testuser")

@pytest_asyncio.fixture
async def admin_user_data():
    return _get_unique_user_data("admin")

@pytest_asyncio.fixture
async def second_user_data():
    return _get_unique_user_data("seconduser")

@pytest_asyncio.fixture
async def test_category_data():
    unique_id = str(uuid.uuid4())[:8]
    return {
        "name": f"Test Category {unique_id}",
        "description": "A test event category"
    }

@pytest_asyncio.fixture
async def test_event_data():
    from datetime import datetime, timedelta
    unique_id = str(uuid.uuid4())[:8]
    return {
        "title": f"Test Event {unique_id}",
        "description": "A test event description",
        "start_datetime": (datetime.now() + timedelta(days=1)).isoformat(),
        "location": "Test Location",
        "max_participants": 10,
        "category_id": 1
    }

@pytest_asyncio.fixture
async def test_service_data():
    unique_id = str(uuid.uuid4())[:8]
    return {
        "title": f"Test Service {unique_id}",
        "description": "A test service description",
        "is_offering": True
    }

@pytest_asyncio.fixture
async def test_thread_data():
    unique_id = str(uuid.uuid4())[:8]
    return {
        "title": f"Test Thread {unique_id}"
    }

@pytest_asyncio.fixture
async def test_post_data():
    return {"content": "This is a test post content."}

@pytest_asyncio.fixture
async def test_poll_data():
    unique_id = str(uuid.uuid4())[:8]
    return {
        "question": f"What is your favorite color? {unique_id}",
        "poll_type": "thread",
        "options": [
            {"text": "Red", "order_index": 1},
            {"text": "Blue", "order_index": 2},
            {"text": "Green", "order_index": 3}
        ]
    }
