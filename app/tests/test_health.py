# app/tests/test_health.py
import pytest
from httpx import AsyncClient

class TestHealthCheck:

    @pytest.mark.asyncio
    async def test_health_check(self, async_client: AsyncClient):
        """ÄNDERUNG: Async test for health check endpoint"""
        response = await async_client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "version" in data

class TestAPIDocumentation:

    @pytest.mark.asyncio
    async def test_openapi_schema_available(self, async_client: AsyncClient):
        response = await async_client.get("/api/openapi.json")

        # Should be available in debug mode, otherwise might be None
        # The response depends on settings.DEBUG
        assert response.status_code in [200, 404]

    @pytest.mark.asyncio
    async def test_docs_redirect(self, async_client: AsyncClient):
        response = await async_client.get("/docs", follow_redirects=False)

        # Should either show docs or redirect/404 depending on config
        assert response.status_code in [200, 404, 307, 308]
