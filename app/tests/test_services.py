import pytest
from httpx import AsyncClient
from fastapi import status
from .test_utils import get_auth_headers

class TestServicesPublic:

    @pytest.mark.asyncio
    async def test_get_empty_services(self, async_client: AsyncClient):
        response = await async_client.get("/api/services/")

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_get_services_with_filters(self, async_client: AsyncClient):
        response = await async_client.get("/api/services/?is_offering=true")
        assert response.status_code == status.HTTP_200_OK

        response = await async_client.get("/api/services/?search=test")
        assert response.status_code == status.HTTP_200_OK

        response = await async_client.get("/api/services/?skip=0&limit=10")
        assert response.status_code == status.HTTP_200_OK

    @pytest.mark.asyncio
    async def test_get_nonexistent_service(self, async_client: AsyncClient):
        response = await async_client.get("/api/services/999")

        assert response.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_get_service_stats(self, async_client: AsyncClient):
        response = await async_client.get("/api/services/stats")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "total_active_services" in data
        assert "services_offered" in data
        assert "services_requested" in data
        assert isinstance(data["total_active_services"], int)

class TestServicesAuth:

    @pytest.mark.asyncio
    async def test_create_service_without_auth(self, async_client: AsyncClient, test_service_data):
        response = await async_client.post("/api/services/", json=test_service_data)

        assert response.status_code in [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN]

    @pytest.mark.asyncio
    async def test_create_service_success(self, async_client: AsyncClient, test_user_data, test_service_data):
        headers = await get_auth_headers(async_client, test_user_data)

        response = await async_client.post("/api/services/", json=test_service_data, headers=headers)

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["title"] == test_service_data["title"]
        assert data["description"] == test_service_data["description"]
        assert data["is_offering"] == test_service_data["is_offering"]
        assert "user" in data
        assert "id" in data

    @pytest.mark.asyncio
    async def test_create_service_invalid_data(self, async_client: AsyncClient, test_user_data):
        headers = await get_auth_headers(async_client, test_user_data)

        invalid_data = {"title": "Test Service"}

        response = await async_client.post("/api/services/", json=invalid_data, headers=headers)

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    @pytest.mark.asyncio
    async def test_update_nonexistent_service(self, async_client: AsyncClient, test_user_data):
        headers = await get_auth_headers(async_client, test_user_data)

        update_data = {"title": "Updated Title"}
        response = await async_client.put("/api/services/999", json=update_data, headers=headers)

        assert response.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_update_service_without_auth(self, async_client: AsyncClient):
        update_data = {"title": "Updated Title"}
        response = await async_client.put("/api/services/1", json=update_data)

        assert response.status_code in [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN]

    @pytest.mark.asyncio
    async def test_delete_service_without_auth(self, async_client: AsyncClient):
        response = await async_client.delete("/api/services/1")

        assert response.status_code in [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN]

    @pytest.mark.asyncio
    async def test_delete_nonexistent_service(self, async_client: AsyncClient, test_user_data):
        headers = await get_auth_headers(async_client, test_user_data)

        response = await async_client.delete("/api/services/999", headers=headers)

        assert response.status_code == status.HTTP_404_NOT_FOUND

class TestUserServices:

    @pytest.mark.asyncio
    async def test_get_my_services_without_auth(self, async_client: AsyncClient):
        response = await async_client.get("/api/services/my/")

        assert response.status_code in [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN]

    @pytest.mark.asyncio
    async def test_get_my_services_empty(self, async_client: AsyncClient, test_user_data):
        await async_client.post("/api/auth/register", json=test_user_data)
        login_response = await async_client.post("/api/auth/login", json={
            "email": test_user_data["email"],
            "password": test_user_data["password"]
        })
        tokens = login_response.json()
        headers = {"Authorization": f"Bearer {tokens['access_token']}"}

        response = await async_client.get("/api/services/my/", headers=headers)

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_get_my_services_with_filters(self, async_client: AsyncClient, test_user_data):
        await async_client.post("/api/auth/register", json=test_user_data)
        login_response = await async_client.post("/api/auth/login", json={
            "email": test_user_data["email"],
            "password": test_user_data["password"]
        })
        tokens = login_response.json()
        headers = {"Authorization": f"Bearer {tokens['access_token']}"}

        response = await async_client.get("/api/services/my/?is_offering=true", headers=headers)
        assert response.status_code == status.HTTP_200_OK

        response = await async_client.get("/api/services/my/?skip=0&limit=10", headers=headers)
        assert response.status_code == status.HTTP_200_OK
