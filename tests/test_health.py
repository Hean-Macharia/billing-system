"""
Phase 1 tests: Health endpoints, security headers, CORS, response format.
"""
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestRootEndpoint:
    @pytest.mark.asyncio
    async def test_root_returns_success(self, client):
        response = await client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "ISP Billing" in data["message"]

    @pytest.mark.asyncio
    async def test_root_has_health_link(self, client):
        response = await client.get("/")
        data = response.json()
        assert "/health" in str(data)


class TestHealthEndpoints:
    @pytest.mark.asyncio
    async def test_health_returns_200(self, client):
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_health_has_timestamp(self, client):
        response = await client.get("/health")
        data = response.json()
        assert "timestamp" in data["data"]
        assert "T" in data["data"]["timestamp"]

    @pytest.mark.asyncio
    async def test_health_live_returns_200(self, client):
        response = await client.get("/health/live")
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["status"] == "alive"

    @pytest.mark.asyncio
    async def test_health_ready_returns_appropriate_status(self, client):
        response = await client.get("/health/ready")
        assert response.status_code in [200, 503]
        data = response.json()
        assert "success" in data


class TestSystemInfo:
    @pytest.mark.asyncio
    async def test_info_returns_metadata(self, client):
        response = await client.get("/api/v1/system/info")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["currency"] == "KES"
        assert data["data"]["timezone"] == "Africa/Nairobi"

    @pytest.mark.asyncio
    async def test_info_no_secrets_leaked(self, client):
        response = await client.get("/api/v1/system/info")
        text = response.text.lower()
        assert "jwt_secret" not in text
        assert "password" not in text
        assert "radius_secret" not in text


class TestSecurityHeaders:
    @pytest.mark.asyncio
    async def test_security_headers_present(self, client):
        response = await client.get("/")
        headers = response.headers
        assert headers.get("x-content-type-options") == "nosniff"
        assert headers.get("x-frame-options") == "DENY"
        assert headers.get("strict-transport-security") is not None

    @pytest.mark.asyncio
    async def test_server_header_hidden(self, client):
        response = await client.get("/")
        server = response.headers.get("server", "").lower()
        assert "uvicorn" not in server


class TestCORS:
    @pytest.mark.asyncio
    async def test_cors_headers_present(self, client):
        response = await client.get("/", headers={"Origin": "http://localhost:3000"})
        assert "access-control-allow-origin" in response.headers

    @pytest.mark.asyncio
    async def test_preflight_request(self, client):
        response = await client.options(
            "/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET"
            }
        )
        assert response.status_code in [200, 204]


class TestResponseFormat:
    @pytest.mark.asyncio
    async def test_standard_response_structure(self, client):
        response = await client.get("/health")
        data = response.json()
        assert "success" in data
        assert "message" in data
        assert "data" in data