import pytest
from httpx import AsyncClient
from fastapi import status
from datetime import datetime, timedelta

class TestEventsPublic:

    @pytest.mark.asyncio
    async def test_get_empty_events(self, async_client: AsyncClient):
        response = await async_client.get("/api/events/")

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_get_events_with_pagination(self, async_client: AsyncClient):
        response = await async_client.get("/api/events/?skip=0&limit=10")

        assert response.status_code == status.HTTP_200_OK
        assert isinstance(response.json(), list)

    @pytest.mark.asyncio
    async def test_get_nonexistent_event(self, async_client: AsyncClient):
        response = await async_client.get("/api/events/999")

        assert response.status_code == status.HTTP_404_NOT_FOUND

class TestEventsAuth:

    async def _get_auth_headers(self, async_client: AsyncClient, user_data):
        await async_client.post("/api/auth/register", json=user_data)

        login_response = await async_client.post("/api/auth/login", json={
            "email": user_data["email"],
            "password": user_data["password"]
        })
        tokens = login_response.json()

        return {"Authorization": f"Bearer {tokens['access_token']}"}

    @pytest.mark.asyncio
    async def test_create_event_without_auth(self, async_client: AsyncClient, test_event_data):
        response = await async_client.post("/api/events/", json=test_event_data)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.asyncio
    async def test_create_event_invalid_category(self, async_client: AsyncClient, test_user_data, test_event_data):
        headers = await self._get_auth_headers(async_client, test_user_data)

        # Use non-existent category
        event_data = test_event_data.copy()
        event_data["category_id"] = 999

        response = await async_client.post("/api/events/", json=event_data, headers=headers)

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "category not found" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_create_event_past_date(self, async_client: AsyncClient, test_user_data, test_event_data):
        headers = await self._get_auth_headers(async_client, test_user_data)

        # Use past date
        event_data = test_event_data.copy()
        event_data["start_datetime"] = (datetime.now() - timedelta(days=1)).isoformat()

        response = await async_client.post("/api/events/", json=event_data, headers=headers)

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

class TestEventParticipation:

    async def _get_auth_headers(self, async_client: AsyncClient, user_data):
        await async_client.post("/api/auth/register", json=user_data)

        login_response = await async_client.post("/api/auth/login", json={
            "email": user_data["email"],
            "password": user_data["password"]
        })
        tokens = login_response.json()

        return {"Authorization": f"Bearer {tokens['access_token']}"}

    @pytest.mark.asyncio
    async def test_join_nonexistent_event(self, async_client: AsyncClient, test_user_data):
        headers = await self._get_auth_headers(async_client, test_user_data)

        response = await async_client.post("/api/events/999/join", headers=headers)

        assert response.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_join_event_without_auth(self, async_client: AsyncClient):
        response = await async_client.post("/api/events/1/join")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.asyncio
    async def test_leave_event_without_auth(self, async_client: AsyncClient):
        response = await async_client.delete("/api/events/1/join")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.asyncio
    async def test_get_event_participants(self, async_client: AsyncClient):
        response = await async_client.get("/api/events/999/participants")

        assert response.status_code == status.HTTP_404_NOT_FOUND

class TestUserEvents:

    @pytest.mark.asyncio
    async def test_get_my_created_events_without_auth(self, async_client: AsyncClient):
        response = await async_client.get("/api/events/my/created")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.asyncio
    async def test_get_my_joined_events_without_auth(self, async_client: AsyncClient):
        response = await async_client.get("/api/events/my/joined")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.asyncio
    async def test_get_my_events_empty(self, async_client: AsyncClient, test_user_data):
        await async_client.post("/api/auth/register", json=test_user_data)
        login_response = await async_client.post("/api/auth/login", json={
            "email": test_user_data["email"],
            "password": test_user_data["password"]
        })
        tokens = login_response.json()
        headers = {"Authorization": f"Bearer {tokens['access_token']}"}

        created_response = await async_client.get("/api/events/my/created", headers=headers)
        joined_response = await async_client.get("/api/events/my/joined", headers=headers)

        assert created_response.status_code == status.HTTP_200_OK
        assert joined_response.status_code == status.HTTP_200_OK
        assert created_response.json() == []
        assert joined_response.json() == []
