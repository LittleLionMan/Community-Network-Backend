import pytest
import pytest_asyncio
import uuid
import os
from typing import AsyncGenerator
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test.db")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-testing-only")
os.environ.setdefault("DEBUG", "true")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

import sys
from pathlib import Path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from app.main import app
from app.database import get_db, Base
from app import models

TEST_DATABASE_URL = "sqlite+aiosqlite:///./test.db"

@pytest_asyncio.fixture(scope="session")
async def async_engine():
    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
        connect_args={"check_same_thread": False}
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()

@pytest_asyncio.fixture
async def async_session(async_engine) -> AsyncGenerator[AsyncSession, None]:
    async_session_maker = async_sessionmaker(
        bind=async_engine,
        class_=AsyncSession,
        expire_on_commit=False
    )
    async with async_engine.connect() as conn:
        trans = await conn.begin()
        async with async_session_maker(bind=conn) as session:
            try:
                yield session
            finally:
                await session.rollback()
                await session.close()
        await trans.rollback()

@pytest_asyncio.fixture
async def async_client(async_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_db():
        yield async_session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as ac:
        yield ac

    app.dependency_overrides.clear()

async def get_auth_headers(async_client: AsyncClient, user_data):
    await async_client.post("/api/auth/register", json=user_data)
    login_response = await async_client.post("/api/auth/login", json={
        "email": user_data["email"],
        "password": user_data["password"]
    })
    tokens = login_response.json()
    return {"Authorization": f"Bearer {tokens['access_token']}"}

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
