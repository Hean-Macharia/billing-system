"""Authentication endpoint tests."""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.database import database

client = TestClient(app)


@pytest.fixture(scope="module", autouse=True)
def setup_db():
    """Ensure DB connection for tests."""
    import asyncio
    asyncio.run(database.connect())
    yield
    asyncio.run(database.disconnect())


@pytest.fixture(autouse=True)
async def clean_users():
    """Clean users collection before each test."""
    await database.db.users.delete_many({})
    yield
    await database.db.users.delete_many({})


class TestAuthPublic:
    """Tests for public (no auth required) endpoints."""

    def test_register_customer_success(self):
        response = client.post("/api/v1/auth/register", json={
            "email": "customer@test.com",
            "username": "testcustomer",
            "full_name": "Test Customer",
            "password": "Password123",
            "role": "customer",
        })
        assert response.status_code == 201
        data = response.json()
        assert data["success"] is True
        assert data["data"]["email"] == "customer@test.com"
        assert data["data"]["role"] == "customer"

    def test_register_duplicate_email(self):
        # First registration
        client.post("/api/v1/auth/register", json={
            "email": "dup@test.com",
            "username": "unique1",
            "full_name": "Dup User",
            "password": "Password123",
            "role": "customer",
        })
        # Duplicate email
        response = client.post("/api/v1/auth/register", json={
            "email": "dup@test.com",
            "username": "unique2",
            "full_name": "Dup User 2",
            "password": "Password123",
            "role": "customer",
        })
        assert response.status_code == 409
        assert response.json()["error_code"] == "CONFLICT"

    def test_register_weak_password(self):
        response = client.post("/api/v1/auth/register", json={
            "email": "weak@test.com",
            "username": "weakuser",
            "full_name": "Weak User",
            "password": "weak",
            "role": "customer",
        })
        assert response.status_code == 422

    def test_register_unauthorized_role_without_auth(self):
        response = client.post("/api/v1/auth/register", json={
            "email": "admin@test.com",
            "username": "adminuser",
            "full_name": "Admin User",
            "password": "Password123",
            "role": "admin",
        })
        assert response.status_code == 401

    def test_login_success(self):
        # Register first
        client.post("/api/v1/auth/register", json={
            "email": "login@test.com",
            "username": "loginuser",
            "full_name": "Login User",
            "password": "Password123",
            "role": "customer",
        })
        # Login
        response = client.post("/api/v1/auth/login", json={
            "email": "login@test.com",
            "password": "Password123",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "access_token" in data["data"]["tokens"]
        assert "refresh_token" in data["data"]["tokens"]

    def test_login_invalid_credentials(self):
        response = client.post("/api/v1/auth/login", json={
            "email": "nonexistent@test.com",
            "password": "Password123",
        })
        assert response.status_code == 401

    def test_refresh_token(self):
        # Register and login
        client.post("/api/v1/auth/register", json={
            "email": "refresh@test.com",
            "username": "refreshuser",
            "full_name": "Refresh User",
            "password": "Password123",
            "role": "customer",
        })
        login_resp = client.post("/api/v1/auth/login", json={
            "email": "refresh@test.com",
            "password": "Password123",
        })
        refresh_token = login_resp.json()["data"]["tokens"]["refresh_token"]

        response = client.post("/api/v1/auth/refresh", json={
            "refresh_token": refresh_token,
        })
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data["data"]

    def test_refresh_invalid_token(self):
        response = client.post("/api/v1/auth/refresh", json={
            "refresh_token": "invalid.token.here",
        })
        assert response.status_code == 401


class TestAuthProtected:
    """Tests for protected (auth required) endpoints."""

    @pytest.fixture
    def customer_token(self):
        client.post("/api/v1/auth/register", json={
            "email": "protected@test.com",
            "username": "protecteduser",
            "full_name": "Protected User",
            "password": "Password123",
            "role": "customer",
        })
        resp = client.post("/api/v1/auth/login", json={
            "email": "protected@test.com",
            "password": "Password123",
        })
        return resp.json()["data"]["tokens"]["access_token"]

    def test_get_me(self, customer_token):
        response = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {customer_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["email"] == "protected@test.com"

    def test_get_me_no_token(self):
        response = client.get("/api/v1/auth/me")
        assert response.status_code == 401

    def test_update_me(self, customer_token):
        response = client.patch(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {customer_token}"},
            json={"full_name": "Updated Name"},
        )
        assert response.status_code == 200
        assert response.json()["data"]["full_name"] == "Updated Name"

    def test_logout(self, customer_token):
        response = client.post(
            "/api/v1/auth/logout",
            headers={"Authorization": f"Bearer {customer_token}"},
        )
        assert response.status_code == 200

    def test_change_password(self, customer_token):
        response = client.post(
            "/api/v1/auth/change-password",
            headers={"Authorization": f"Bearer {customer_token}"},
            json={
                "current_password": "Password123",
                "new_password": "NewPassword456",
            },
        )
        assert response.status_code == 200

        # Verify old password no longer works
        login_resp = client.post("/api/v1/auth/login", json={
            "email": "protected@test.com",
            "password": "Password123",
        })
        assert login_resp.status_code == 401

        # Verify new password works
        login_resp = client.post("/api/v1/auth/login", json={
            "email": "protected@test.com",
            "password": "NewPassword456",
        })
        assert login_resp.status_code == 200


class TestAuthAdmin:
    """Tests for admin-only endpoints."""

    @pytest.fixture
    def admin_token(self):
        # Register admin
        client.post("/api/v1/auth/register", json={
            "email": "adminonly@test.com",
            "username": "adminonly",
            "full_name": "Admin Only",
            "password": "Password123",
            "role": "admin",
        })
        resp = client.post("/api/v1/auth/login", json={
            "email": "adminonly@test.com",
            "password": "Password123",
        })
        return resp.json()["data"]["tokens"]["access_token"]

    @pytest.fixture
    def customer_token(self):
        client.post("/api/v1/auth/register", json={
            "email": "custadmin@test.com",
            "username": "custadmin",
            "full_name": "Cust Admin",
            "password": "Password123",
            "role": "customer",
        })
        resp = client.post("/api/v1/auth/login", json={
            "email": "custadmin@test.com",
            "password": "Password123",
        })
        return resp.json()["data"]["tokens"]["access_token"]

    def test_list_users_as_admin(self, admin_token):
        response = client.get(
            "/api/v1/auth/users",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert "meta" in data

    def test_list_users_as_customer(self, customer_token):
        response = client.get(
            "/api/v1/auth/users",
            headers={"Authorization": f"Bearer {customer_token}"},
        )
        assert response.status_code == 403

    def test_create_staff_by_admin(self, admin_token):
        response = client.post(
            "/api/v1/auth/register",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "email": "newtech@test.com",
                "username": "newtech",
                "full_name": "New Tech",
                "password": "Password123",
                "role": "technician",
            },
        )
        assert response.status_code == 201
        assert response.json()["data"]["role"] == "technician"