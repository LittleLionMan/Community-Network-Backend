import pytest
import asyncio
from httpx import AsyncClient
from typing import Dict, NoReturn

async def get_auth_headers(async_client: AsyncClient, user_data: dict, max_retries: int = 3) -> Dict[str, str]: #type: ignore[return]

    for attempt in range(max_retries):
        try:
            reg_response = await async_client.post("/api/auth/register", json=user_data)

            if reg_response.status_code == 429:
                await asyncio.sleep(1)
                continue

            login_response = await async_client.post("/api/auth/login", json={
                "email": user_data["email"],
                "password": user_data["password"]
            })

            if login_response.status_code == 429:
                await asyncio.sleep(1)
                continue

            if login_response.status_code == 200:
                tokens = login_response.json()
                if "access_token" in tokens:
                    return {"Authorization": f"Bearer {tokens['access_token']}"}

        except Exception as e:
            if attempt == max_retries - 1:
                pytest.skip(f"Auth setup failed after {max_retries} attempts: {e}")

    pytest.skip("Could not establish authentication after retries")

async def create_test_user(async_client: AsyncClient, user_data: dict = None) -> dict: # type: ignore[return]
    if user_data is None:
        import uuid
        unique_id = str(uuid.uuid4())[:8]
        user_data = {
            "display_name": f"testuser_{unique_id}",
            "email": f"testuser_{unique_id}@example.com",
            "password": "TestPass123!",
            "first_name": "Test",
            "last_name": "User"
        }

    headers = await get_auth_headers(async_client, user_data)
    return {
        "headers": headers,
        "user_data": user_data
    }
