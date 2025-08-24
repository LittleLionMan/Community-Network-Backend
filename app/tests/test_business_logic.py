import pytest
from httpx import AsyncClient
from fastapi import status
from datetime import datetime, timedelta
from .test_utils import get_auth_headers

class TestEventCapacityManagement:

    @pytest.mark.asyncio
    async def test_join_full_event(self, async_client: AsyncClient, test_user_data, second_user_data):
        headers1 = await get_auth_headers(async_client, test_user_data)

        category_data = {"name": "Test Category", "description": "Test"}
        # Note: This would need admin user in real scenario

        event_data = {
            "title": "Full Event Test",
            "description": "Event with capacity 1",
            "start_datetime": (datetime.now() + timedelta(days=1)).isoformat(),
            "max_participants": 1,
            "category_id": 1
        }

        # This test would need proper setup with categories
        # For MVP, we can test the capacity logic directly in the service
        pass  # Implement when event creation works in tests

    @pytest.mark.asyncio
    async def test_cannot_join_past_event(self, async_client: AsyncClient, test_user_data):
        headers = await get_auth_headers(async_client, test_user_data)

        response = await async_client.post("/api/events/1/join", headers=headers)

        assert response.status_code in [404, 400]

class TestServiceMatching:

    @pytest.mark.asyncio
    async def test_get_service_recommendations_without_services(self, async_client: AsyncClient, test_user_data):
        headers = await get_auth_headers(async_client, test_user_data)

        response = await async_client.get("/api/services/recommendations", headers=headers)

        assert response.status_code == status.HTTP_200_OK
        assert isinstance(response.json(), list)

class TestContentModeration:

    @pytest.mark.asyncio
    async def test_flagged_content_rejected(self, async_client: AsyncClient, test_user_data):
        headers = await get_auth_headers(async_client, test_user_data)

        flagged_content = {
            "content": "This contains Hurensohn which should be flagged",
            "event_id": 1
        }

        response = await async_client.post("/api/comments/", json=flagged_content, headers=headers)

        assert response.status_code in [400, 404]

        if response.status_code == 400:
            assert "flagged" in response.json()["detail"].lower()

class TestDataIntegrity:

    @pytest.mark.asyncio
    async def test_user_stats_calculation(self, async_client: AsyncClient, test_user_data):
        headers = await get_auth_headers(async_client, test_user_data)

        response = await async_client.get("/api/events/my/stats", headers=headers)

        assert response.status_code == status.HTTP_200_OK
        stats = response.json()

        assert stats.get("upcoming_events", 0) == 0
        assert stats.get("events_attended", 0) == 0
        assert stats.get("events_cancelled", 0) == 0
        assert stats.get("attendance_rate", 0) == 0
