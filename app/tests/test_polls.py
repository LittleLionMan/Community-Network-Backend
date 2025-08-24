import pytest
from httpx import AsyncClient
from fastapi import status
from .test_utils import get_auth_headers

class TestPollsPublic:

    @pytest.mark.asyncio
    async def test_get_empty_polls(self, async_client: AsyncClient):
        """Test getting polls when none exist"""
        response = await async_client.get("/api/polls/")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "at least 2 options" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_create_poll_too_many_options(self, async_client: AsyncClient, test_user_data):
        headers = await get_auth_headers(async_client, test_user_data)

        options = [{"text": f"Option {i}", "order_index": i} for i in range(1, 12)]
        poll_data = {
            "question": "Poll with too many options?",
            "poll_type": "thread",
            "options": options
        }

        response = await async_client.post("/api/polls/", json=poll_data, headers=headers)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "more than 10 options" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_create_admin_poll_with_thread(self, async_client: AsyncClient, test_user_data):
        headers = await get_auth_headers(async_client, test_user_data)

        poll_data = {
            "question": "Admin poll with thread?",
            "poll_type": "admin",
            "thread_id": 1,
            "options": [
                {"text": "Yes", "order_index": 1},
                {"text": "No", "order_index": 2}
            ]
        }

        response = await async_client.post("/api/polls/", json=poll_data, headers=headers)

        assert response.status_code in [status.HTTP_400_BAD_REQUEST, status.HTTP_403_FORBIDDEN]

    @pytest.mark.asyncio
    async def test_update_poll_without_auth(self, async_client: AsyncClient):
        update_data = {"question": "Updated question?"}
        response = await async_client.put("/api/polls/1", json=update_data)

        assert response.status_code in [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN]

    @pytest.mark.asyncio
    async def test_update_nonexistent_poll(self, async_client: AsyncClient, test_user_data):
        headers = await get_auth_headers(async_client, test_user_data)

        update_data = {"question": "Updated question?"}
        response = await async_client.put("/api/polls/999", json=update_data, headers=headers)

        assert response.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_delete_poll_without_auth(self, async_client: AsyncClient):
        response = await async_client.delete("/api/polls/1")

        assert response.status_code in [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN]

    @pytest.mark.asyncio
    async def test_delete_nonexistent_poll(self, async_client: AsyncClient, test_user_data):
        headers = await get_auth_headers(async_client, test_user_data)

        response = await async_client.delete("/api/polls/999", headers=headers)

        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestPollVoting:

    @pytest.mark.asyncio
    async def test_vote_without_auth(self, async_client: AsyncClient):
        vote_data = {"option_id": 1}
        response = await async_client.post("/api/polls/1/vote", json=vote_data)

        assert response.status_code in [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN]

    @pytest.mark.asyncio
    async def test_vote_nonexistent_poll(self, async_client: AsyncClient, test_user_data):
        headers = await get_auth_headers(async_client, test_user_data)

        vote_data = {"option_id": 1}
        response = await async_client.post("/api/polls/999/vote", json=vote_data, headers=headers)

        assert response.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_remove_vote_without_auth(self, async_client: AsyncClient):
        response = await async_client.delete("/api/polls/1/vote")

        assert response.status_code in [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN]

    @pytest.mark.asyncio
    async def test_remove_vote_nonexistent_poll(self, async_client: AsyncClient, test_user_data):
        headers = await get_auth_headers(async_client, test_user_data)

        response = await async_client.delete("/api/polls/999/vote", headers=headers)

        assert response.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_remove_nonexistent_vote(self, async_client: AsyncClient, test_user_data):
        headers = await get_auth_headers(async_client, test_user_data)

        response = await async_client.delete("/api/polls/1/vote", headers=headers)

        assert response.status_code in [status.HTTP_400_BAD_REQUEST, status.HTTP_404_NOT_FOUND]


class TestUserPolls:

    @pytest.mark.asyncio
    async def test_get_my_polls_without_auth(self, async_client: AsyncClient):
        response = await async_client.get("/api/polls/my/created")

        assert response.status_code in [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN]

    @pytest.mark.asyncio
    async def test_get_my_votes_without_auth(self, async_client: AsyncClient):
        response = await async_client.get("/api/polls/my/votes")

        assert response.status_code in [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN]

    @pytest.mark.asyncio
    async def test_get_my_polls_empty(self, async_client: AsyncClient, test_user_data):
        headers = await get_auth_headers(async_client, test_user_data)

        response = await async_client.get("/api/polls/my/created", headers=headers)

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_get_my_votes_empty(self, async_client: AsyncClient, test_user_data):
        headers = await get_auth_headers(async_client, test_user_data)

        response = await async_client.get("/api/polls/my/votes", headers=headers)

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_get_my_content_with_pagination(self, async_client: AsyncClient, test_user_data):
        headers = await get_auth_headers(async_client, test_user_data)

        polls_response = await async_client.get("/api/polls/my/created?skip=0&limit=10", headers=headers)
        votes_response = await async_client.get("/api/polls/my/votes?skip=0&limit=10", headers=headers)

        assert polls_response.status_code == status.HTTP_200_OK
        assert votes_response.status_code == status.HTTP_200_OK
        assert polls_response.json() == []  # vermutlich leer

    @pytest.mark.asyncio
    async def test_get_polls_with_filters(self, async_client: AsyncClient):
        response = await async_client.get("/api/polls/?poll_type=thread")
        assert response.status_code == status.HTTP_200_OK

        response = await async_client.get("/api/polls/?active_only=true")
        assert response.status_code == status.HTTP_200_OK

        response = await async_client.get("/api/polls/?thread_id=1")
        assert response.status_code == status.HTTP_200_OK

        response = await async_client.get("/api/polls/?skip=0&limit=10")
        assert response.status_code == status.HTTP_200_OK

    @pytest.mark.asyncio
    async def test_get_nonexistent_poll(self, async_client: AsyncClient):
        response = await async_client.get("/api/polls/999")

        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestPollsAuth:

    @pytest.mark.asyncio
    async def test_create_poll_without_auth(self, async_client: AsyncClient, test_poll_data):
        response = await async_client.post("/api/polls/", json=test_poll_data)

        assert response.status_code in [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN]

    @pytest.mark.asyncio
    async def test_create_admin_poll_non_admin(self, async_client: AsyncClient, test_user_data):
        headers = await get_auth_headers(async_client, test_user_data)

        admin_poll_data = {
            "question": "Administrative poll question?",
            "poll_type": "admin",
            "options": [
                {"text": "Yes", "order_index": 1},
                {"text": "No", "order_index": 2}
            ]
        }

        response = await async_client.post("/api/polls/", json=admin_poll_data, headers=headers)

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "only admins" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_create_poll_nonexistent_thread(self, async_client: AsyncClient, test_user_data):
        headers = await get_auth_headers(async_client, test_user_data)

        poll_data = {
            "question": "Thread poll question?",
            "poll_type": "thread",
            "thread_id": 999,
            "options": [
                {"text": "Yes", "order_index": 1},
                {"text": "No", "order_index": 2}
            ]
        }

        response = await async_client.post("/api/polls/", json=poll_data, headers=headers)

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "thread not found" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_create_poll_too_few_options(self, async_client: AsyncClient, test_user_data):
        headers = await get_auth_headers(async_client, test_user_data)

        poll_data = {
            "question": "Poll with one option?",
            "poll_type": "thread",
            "options": [
                {"text": "Only option", "order_index": 1}
            ]
        }

        response = await async_client.post("/api/polls/", json=poll_data, headers=headers)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "at least 2 options" in response.json()["detail"].lower()
