import pytest
from httpx import AsyncClient
from fastapi import status

class TestDiscussionsPublic:

    @pytest.mark.asyncio
    async def test_get_empty_threads(self, async_client: AsyncClient):
        response = await async_client.get("/api/discussions/")

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_get_threads_with_pagination(self, async_client: AsyncClient):
        response = await async_client.get("/api/discussions/?skip=0&limit=10")

        assert response.status_code == status.HTTP_200_OK
        assert isinstance(response.json(), list)

    @pytest.mark.asyncio
    async def test_get_threads_pinned_first(self, async_client: AsyncClient):
        response = await async_client.get("/api/discussions/?pinned_first=true")

        assert response.status_code == status.HTTP_200_OK

    @pytest.mark.asyncio
    async def test_get_nonexistent_thread(self, async_client: AsyncClient):
        response = await async_client.get("/api/discussions/999")

        assert response.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_get_posts_nonexistent_thread(self, async_client: AsyncClient):
        response = await async_client.get("/api/discussions/999/posts")

        assert response.status_code == status.HTTP_404_NOT_FOUND

class TestDiscussionsAuth:

    async def _get_auth_headers(self, async_client: AsyncClient, user_data):
        await async_client.post("/api/auth/register", json=user_data)

        login_response = await async_client.post("/api/auth/login", json={
            "email": user_data["email"],
            "password": user_data["password"]
        })
        tokens = login_response.json()

        return {"Authorization": f"Bearer {tokens['access_token']}"}

    @pytest.mark.asyncio
    async def test_create_thread_without_auth(self, async_client: AsyncClient, test_thread_data):
        response = await async_client.post("/api/discussions/", json=test_thread_data)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.asyncio
    async def test_create_thread_success(self, async_client: AsyncClient, test_user_data, test_thread_data):
        headers = await self._get_auth_headers(async_client, test_user_data)

        response = await async_client.post("/api/discussions/", json=test_thread_data, headers=headers)

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["title"] == test_thread_data["title"]
        assert "creator" in data
        assert "id" in data

    @pytest.mark.asyncio
    async def test_create_thread_invalid_data(self, async_client: AsyncClient, test_user_data):
        headers = await self._get_auth_headers(async_client, test_user_data)

        invalid_data = {}

        response = await async_client.post("/api/discussions/", json=invalid_data, headers=headers)

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    @pytest.mark.asyncio
    async def test_update_thread_without_auth(self, async_client: AsyncClient):
        update_data = {"title": "Updated Title"}
        response = await async_client.put("/api/discussions/1", json=update_data)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.asyncio
    async def test_update_nonexistent_thread(self, async_client: AsyncClient, test_user_data):
        headers = await self._get_auth_headers(async_client, test_user_data)

        update_data = {"title": "Updated Title"}
        response = await async_client.put("/api/discussions/999", json=update_data, headers=headers)

        assert response.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_delete_thread_without_auth(self, async_client: AsyncClient):
        response = await async_client.delete("/api/discussions/1")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.asyncio
    async def test_delete_nonexistent_thread(self, async_client: AsyncClient, test_user_data):
        headers = await self._get_auth_headers(async_client, test_user_data)

        response = await async_client.delete("/api/discussions/999", headers=headers)

        assert response.status_code == status.HTTP_404_NOT_FOUND

class TestDiscussionPosts:

    async def _get_auth_headers(self, async_client: AsyncClient, user_data):
        await async_client.post("/api/auth/register", json=user_data)

        login_response = await async_client.post("/api/auth/login", json={
            "email": user_data["email"],
            "password": user_data["password"]
        })
        tokens = login_response.json()

        return {"Authorization": f"Bearer {tokens['access_token']}"}

    @pytest.mark.asyncio
    async def test_create_post_without_auth(self, async_client: AsyncClient, test_post_data):
        response = await async_client.post("/api/discussions/1/posts", json=test_post_data)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.asyncio
    async def test_create_post_nonexistent_thread(self, async_client: AsyncClient, test_user_data, test_post_data):
        headers = await self._get_auth_headers(async_client, test_user_data)

        response = await async_client.post("/api/discussions/999/posts", json=test_post_data, headers=headers)

        assert response.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_update_post_without_auth(self, async_client: AsyncClient, test_post_data):
        response = await async_client.put("/api/discussions/posts/1", json=test_post_data)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.asyncio
    async def test_update_nonexistent_post(self, async_client: AsyncClient, test_user_data, test_post_data):
        headers = await self._get_auth_headers(async_client, test_user_data)

        response = await async_client.put("/api/discussions/posts/999", json=test_post_data, headers=headers)

        assert response.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_delete_post_without_auth(self, async_client: AsyncClient):
        response = await async_client.delete("/api/discussions/posts/1")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.asyncio
    async def test_delete_nonexistent_post(self, async_client: AsyncClient, test_user_data):
        headers = await self._get_auth_headers(async_client, test_user_data)

        response = await async_client.delete("/api/discussions/posts/999", headers=headers)

        assert response.status_code == status.HTTP_404_NOT_FOUND

class TestUserDiscussions:

    @pytest.mark.asyncio
    async def test_get_my_threads_without_auth(self, async_client: AsyncClient):
        response = await async_client.get("/api/discussions/my/threads")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.asyncio
    async def test_get_my_posts_without_auth(self, async_client: AsyncClient):
        response = await async_client.get("/api/discussions/my/posts")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.asyncio
    async def test_get_my_content_empty(self, async_client: AsyncClient, test_user_data):
        await async_client.post("/api/auth/register", json=test_user_data)
        login_response = await async_client.post("/api/auth/login", json={
            "email": test_user_data["email"],
            "password": test_user_data["password"]
        })
        tokens = login_response.json()
        headers = {"Authorization": f"Bearer {tokens['access_token']}"}

        threads_response = await async_client.get("/api/discussions/my/threads", headers=headers)
        posts_response = await async_client.get("/api/discussions/my/posts", headers=headers)

        assert threads_response.status_code == status.HTTP_200_OK
        assert posts_response.status_code == status.HTTP_200_OK
        assert threads_response.json() == []
        assert posts_response.json() == []
