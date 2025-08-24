import pytest
from httpx import AsyncClient
from fastapi import status
from .test_utils import get_auth_headers

class TestCommentsPublic:

    @pytest.mark.asyncio
    async def test_get_comments_without_filter(self, async_client: AsyncClient):
        response = await async_client.get("/api/comments/")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "must specify" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_get_comments_with_event_filter(self, async_client: AsyncClient):
        response = await async_client.get("/api/comments/?event_id=1")

        assert response.status_code == status.HTTP_200_OK
        assert isinstance(response.json(), list)

    @pytest.mark.asyncio
    async def test_get_comments_with_service_filter(self, async_client: AsyncClient):
        response = await async_client.get("/api/comments/?service_id=1")

        assert response.status_code == status.HTTP_200_OK
        assert isinstance(response.json(), list)

    @pytest.mark.asyncio
    async def test_get_comments_with_parent_filter(self, async_client: AsyncClient):
        response = await async_client.get("/api/comments/?event_id=1&parent_id=1")

        assert response.status_code == status.HTTP_200_OK
        assert isinstance(response.json(), list)

    @pytest.mark.asyncio
    async def test_get_comments_with_pagination(self, async_client: AsyncClient):
        response = await async_client.get("/api/comments/?event_id=1&skip=0&limit=10")

        assert response.status_code == status.HTTP_200_OK

    @pytest.mark.asyncio
    async def test_get_nonexistent_comment(self, async_client: AsyncClient):
        response = await async_client.get("/api/comments/999")

        assert response.status_code == status.HTTP_404_NOT_FOUND

class TestCommentsAuth:

    @pytest.mark.asyncio
    async def test_create_comment_without_auth(self, async_client: AsyncClient):
        comment_data = {
            "content": "Test comment",
            "event_id": 1
        }

        response = await async_client.post("/api/comments/", json=comment_data)

        assert response.status_code in [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN]

    @pytest.mark.asyncio
    async def test_create_comment_invalid_data(self, async_client: AsyncClient, test_user_data):
        headers = await get_auth_headers(async_client, test_user_data)

        invalid_data = {"content": "Test comment"}

        response = await async_client.post("/api/comments/", json=invalid_data, headers=headers)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "must specify exactly one" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_create_comment_multiple_parents(self, async_client: AsyncClient, test_user_data):
        headers = await get_auth_headers(async_client, test_user_data)

        invalid_data = {
            "content": "Test comment",
            "event_id": 1,
            "service_id": 1
        }

        response = await async_client.post("/api/comments/", json=invalid_data, headers=headers)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "must specify exactly one" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_create_comment_nonexistent_event(self, async_client: AsyncClient, test_user_data):
        headers = await get_auth_headers(async_client, test_user_data)

        comment_data = {
            "content": "Test comment",
            "event_id": 999
        }

        response = await async_client.post("/api/comments/", json=comment_data, headers=headers)

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "event not found" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_create_comment_nonexistent_service(self, async_client: AsyncClient, test_user_data):
        headers = await get_auth_headers(async_client, test_user_data)

        comment_data = {
            "content": "Test comment",
            "service_id": 999
        }

        response = await async_client.post("/api/comments/", json=comment_data, headers=headers)

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "service not found" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_create_comment_nonexistent_parent(self, async_client: AsyncClient, test_user_data):
        headers = await get_auth_headers(async_client, test_user_data)

        comment_data = {
            "content": "Test reply",
            "event_id": 1,
            "parent_id": 999
        }

        response = await async_client.post("/api/comments/", json=comment_data, headers=headers)

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "parent comment not found" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_update_comment_without_auth(self, async_client: AsyncClient):
        update_data = {"content": "Updated comment"}
        response = await async_client.put("/api/comments/1", json=update_data)

        assert response.status_code in [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN]

    @pytest.mark.asyncio
    async def test_update_nonexistent_comment(self, async_client: AsyncClient, test_user_data):
        headers = await get_auth_headers(async_client, test_user_data)

        update_data = {"content": "Updated comment"}
        response = await async_client.put("/api/comments/999", json=update_data, headers=headers)

        assert response.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_delete_comment_without_auth(self, async_client: AsyncClient):
        response = await async_client.delete("/api/comments/1")

        assert response.status_code in [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN]

    @pytest.mark.asyncio
    async def test_delete_nonexistent_comment(self, async_client: AsyncClient, test_user_data):
        headers = await get_auth_headers(async_client, test_user_data)

        response = await async_client.delete("/api/comments/999", headers=headers)

        assert response.status_code == status.HTTP_404_NOT_FOUND

class TestUserComments:

    @pytest.mark.asyncio
    async def test_get_my_comments_without_auth(self, async_client: AsyncClient):
        response = await async_client.get("/api/comments/my/")

        assert response.status_code in [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN]

    @pytest.mark.asyncio
    async def test_get_my_comments_empty(self, async_client: AsyncClient, test_user_data):
        await async_client.post("/api/auth/register", json=test_user_data)
        login_response = await async_client.post("/api/auth/login", json={
            "email": test_user_data["email"],
            "password": test_user_data["password"]
        })
        tokens = login_response.json()
        headers = {"Authorization": f"Bearer {tokens['access_token']}"}

        response = await async_client.get("/api/comments/my/", headers=headers)

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_get_my_comments_with_pagination(self, async_client: AsyncClient, test_user_data):
        await async_client.post("/api/auth/register", json=test_user_data)
        login_response = await async_client.post("/api/auth/login", json={
            "email": test_user_data["email"],
            "password": test_user_data["password"]
        })
        tokens = login_response.json()
        headers = {"Authorization": f"Bearer {tokens['access_token']}"}

        response = await async_client.get("/api/comments/my/?skip=0&limit=10", headers=headers)

        assert response.status_code == status.HTTP_200_OK
