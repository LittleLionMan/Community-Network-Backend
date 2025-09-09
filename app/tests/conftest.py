import pytest_asyncio
import uuid
import os
from typing import AsyncGenerator
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test.db")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-testing-only-min-32-chars")
os.environ.setdefault("DEBUG", "true")
os.environ.setdefault("ENVIRONMENT", "testing")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/1")
os.environ.setdefault("SKIP_CONFIG_VALIDATION", "true")

os.environ["RATE_LIMIT_PER_MINUTE"] = "200"
os.environ["CONTENT_MODERATION_ENABLED"] = "true"

os.environ["UPLOAD_DIR"] = "/tmp/test_uploads"

import sys
from pathlib import Path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from app.main import app
from app.database import get_db
from app.models.base import Base

TEST_DATABASE_URL = "sqlite+aiosqlite:///./test.db"

@pytest_asyncio.fixture
async def async_engine():
    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
        connect_args={"check_same_thread": False}
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()

        import os
        db_file = "./test.db"
        if os.path.exists(db_file):
            os.remove(db_file)

    except Exception as e:
        print(f"Test cleanup warning: {e}")

@pytest_asyncio.fixture
async def async_session(async_engine) -> AsyncGenerator[AsyncSession, None]:
    async_session_maker = async_sessionmaker(
        bind=async_engine,
        class_=AsyncSession,
        expire_on_commit=False
    )

    async with async_session_maker() as session:
        yield session
        await session.rollback()

@pytest_asyncio.fixture
async def async_client(async_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_db():
        yield async_session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        timeout=30.0
    ) as ac:
        yield ac

    app.dependency_overrides.clear()

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
