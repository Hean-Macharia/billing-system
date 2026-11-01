"""
Phase 1 tests: Health endpoints, security headers, CORS, response format.
"""
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestRootEndpoint:
    @pytest.mark.asyncio
    async def test_root_redirects_to_documented_hotspot_entry(self, client):
        response = await client.get("/")
        assert response.status_code == 307
        assert response.headers["location"] == "/hotspot/"

    @pytest.mark.asyncio
    async def test_frontend_routes_serve_static_apps(self, client):
        for path, marker in (
            ("/hotspot/", "DEVZEN CREATIONS"),
            ("/admin/", "DevZen Creations"),
            ("/portal/", "DevZen Creations"),
        ):
            response = await client.get(path)
            assert response.status_code == 200
            assert marker in response.text
            assert "content-security-policy" not in response.headers

        secondary_portal = await client.get("/index.html")
        assert secondary_portal.status_code == 200
        assert "DEVZEN CREATIONS" in secondary_portal.text

    @pytest.mark.asyncio
    async def test_shared_theme_is_served_without_exposing_repository_files(self, client):
        theme = await client.get("/frontend/shared/css/modern-theme.css")
        assert theme.status_code == 200
        assert "--dz-bg: #0f1629" in theme.text

        # The shared asset allowlist must not turn the repository root into a
        # general-purpose file server.
        private_file = await client.get("/frontend/shared/../../.env")
        assert private_file.status_code == 404

    @pytest.mark.asyncio
    async def test_hotspot_static_entry_serves_direct_and_routeros_redirect_urls(self, client):
        captive_query = (
            "?link-login-only=http%3A%2F%2Flogin.hean.local%2Flogin"
            "&link-orig=http%253A%252F%252Fconnectivitycheck.gstatic.com%252Fgenerate%255F204"
            "&chap-id=%5C213"
            "&chap-challenge=%5C277%5C154%5C110%5C145%5C127%5C347%5C223%5C373%5C157%5C252%5C232%5C270%5C110%5C011%5C006%5C314"
        )
        direct = await client.get("/hotspot/")
        redirected = await client.get(f"/hotspot/{captive_query}")

        assert direct.status_code == 200
        assert redirected.status_code == 200
        assert redirected.headers["content-type"].startswith("text/html")
        assert "mikrotik-login.js" in redirected.text
        assert "js/app.js" in redirected.text


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
        response = await client.get("/health")
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
