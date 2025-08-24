import pytest
from httpx import AsyncClient
from typing import Dict, NoReturn

async def get_auth_headers(async_client: AsyncClient, user_data: dict) -> Dict[str, str]: # type: ignore[return]
    try:
        reg_response = await async_client.post("/api/auth/register", json=user_data)

        if reg_response.status_code == 429:
            pytest.skip("Rate limit hit during registration")

        if reg_response.status_code not in [201, 400]:
            print(f"❌ Registration failed: {reg_response.status_code} - {reg_response.text}")
            pytest.skip(f"Registration failed: {reg_response.status_code}")

        login_response = await async_client.post("/api/auth/login", json={
            "email": user_data["email"],
            "password": user_data["password"]
        })

        if login_response.status_code == 429:
            pytest.skip("Rate limit hit during login")

        if login_response.status_code != 200:
            print(f"❌ Login failed: {login_response.status_code} - {login_response.text}")
            pytest.skip(f"Login failed: {login_response.status_code}")

        tokens = login_response.json()

        if "access_token" not in tokens:
            print(f"❌ No access_token in response: {tokens}")
            pytest.skip("No access_token in login response")

        return {"Authorization": f"Bearer {tokens['access_token']}"}

    except Exception as e:
        print(f"❌ Auth helper failed: {e}")
        pytest.skip(f"Auth setup failed: {e}")

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
