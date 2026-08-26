"""Customer endpoint tests."""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.database import database

client = TestClient(app)


@pytest.fixture(scope="module", autouse=True)
def setup_db():
    import asyncio
    asyncio.run(database.connect())
    yield
    asyncio.run(database.disconnect())


@pytest.fixture(autouse=True)
async def clean_collections():
    await database.db.users.delete_many({})
    await database.db.customers.delete_many({})
    yield
    await database.db.users.delete_many({})
    await database.db.customers.delete_many({})


@pytest.fixture
def admin_token():
    # Register admin
    client.post("/api/v1/auth/register", json={
        "email": "admin@isp.com",
        "username": "adminuser",
        "full_name": "Admin User",
        "password": "Password123",
        "role": "admin",
    })
    resp = client.post("/api/v1/auth/login", json={
        "email": "admin@isp.com",
        "password": "Password123",
    })
    return resp.json()["data"]["tokens"]["access_token"]


@pytest.fixture
def customer_token():
    client.post("/api/v1/auth/register", json={
        "email": "customer@isp.com",
        "username": "customeruser",
        "full_name": "Customer User",
        "password": "Password123",
        "role": "customer",
    })
    resp = client.post("/api/v1/auth/login", json={
        "email": "customer@isp.com",
        "password": "Password123",
    })
    return resp.json()["data"]["tokens"]["access_token"]


class TestCustomerCreate:
    def test_create_customer_as_admin(self, admin_token):
        response = client.post(
            "/api/v1/customers",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "customer_code": "CUST-0001",
                "full_name": "John Doe",
                "email": "john@example.com",
                "phone": "+254712345678",
                "customer_type": "residential",
                "address": {
                    "street": "123 Main St",
                    "city": "Nairobi",
                    "country": "Kenya",
                },
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["customer_code"] == "CUST-0001"
        assert data["data"]["full_name"] == "John Doe"

    def test_create_customer_duplicate_code(self, admin_token):
        # Create first
        client.post(
            "/api/v1/customers",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "customer_code": "CUST-DUP",
                "full_name": "First",
                "phone": "+254700000001",
                "address": {"street": "St", "city": "Nairobi", "country": "Kenya"},
            },
        )
        # Try duplicate
        response = client.post(
            "/api/v1/customers",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "customer_code": "CUST-DUP",
                "full_name": "Second",
                "phone": "+254700000002",
                "address": {"street": "St2", "city": "Nairobi", "country": "Kenya"},
            },
        )
        assert response.status_code == 409

    def test_create_customer_as_customer_role(self, customer_token):
        response = client.post(
            "/api/v1/customers",
            headers={"Authorization": f"Bearer {customer_token}"},
            json={
                "customer_code": "CUST-0002",
                "full_name": "Jane Doe",
                "phone": "+254712345679",
                "address": {"street": "456 Oak St", "city": "Mombasa", "country": "Kenya"},
            },
        )
        assert response.status_code == 403

    def test_create_customer_no_auth(self):
        response = client.post(
            "/api/v1/customers",
            json={
                "customer_code": "CUST-0003",
                "full_name": "No Auth",
                "phone": "+254712345680",
                "address": {"street": "St", "city": "City", "country": "Kenya"},
            },
        )
        assert response.status_code == 401


class TestCustomerRead:
    def test_list_customers(self, admin_token):
        # Create a customer first
        client.post(
            "/api/v1/customers",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "customer_code": "CUST-LIST1",
                "full_name": "List Test",
                "phone": "+254700000003",
                "address": {"street": "St", "city": "Nairobi", "country": "Kenya"},
            },
        )
        response = client.get(
            "/api/v1/customers",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "meta" in data
        assert len(data["data"]) >= 1

    def test_get_customer_by_id(self, admin_token):
        create_resp = client.post(
            "/api/v1/customers",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "customer_code": "CUST-GET1",
                "full_name": "Get Test",
                "phone": "+254700000004",
                "address": {"street": "St", "city": "Nairobi", "country": "Kenya"},
            },
        )
        customer_id = create_resp.json()["data"]["_id"]
        response = client.get(
            f"/api/v1/customers/{customer_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        assert response.json()["data"]["customer_code"] == "CUST-GET1"

    def test_get_customer_by_code(self, admin_token):
        client.post(
            "/api/v1/customers",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "customer_code": "CUST-CODE1",
                "full_name": "Code Test",
                "phone": "+254700000005",
                "address": {"street": "St", "city": "Nairobi", "country": "Kenya"},
            },
        )
        response = client.get(
            "/api/v1/customers/code/CUST-CODE1",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        assert response.json()["data"]["customer_code"] == "CUST-CODE1"

    def test_search_customers(self, admin_token):
        client.post(
            "/api/v1/customers",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "customer_code": "CUST-SEARCH",
                "full_name": "Searchable Name",
                "phone": "+254700000006",
                "address": {"street": "St", "city": "Nairobi", "country": "Kenya"},
            },
        )
        response = client.get(
            "/api/v1/customers?search=Searchable",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        assert len(response.json()["data"]) >= 1


class TestCustomerUpdate:
    def test_update_customer(self, admin_token):
        create_resp = client.post(
            "/api/v1/customers",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "customer_code": "CUST-UPD",
                "full_name": "Before Update",
                "phone": "+254700000007",
                "address": {"street": "St", "city": "Nairobi", "country": "Kenya"},
            },
        )
        customer_id = create_resp.json()["data"]["_id"]
        response = client.patch(
            f"/api/v1/customers/{customer_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"full_name": "After Update"},
        )
        assert response.status_code == 200
        assert response.json()["data"]["full_name"] == "After Update"

    def test_update_status(self, admin_token):
        create_resp = client.post(
            "/api/v1/customers",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "customer_code": "CUST-STAT",
                "full_name": "Status Test",
                "phone": "+254700000008",
                "address": {"street": "St", "city": "Nairobi", "country": "Kenya"},
            },
        )
        customer_id = create_resp.json()["data"]["_id"]
        response = client.patch(
            f"/api/v1/customers/{customer_id}/status?status=active",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        assert response.json()["data"]["status"] == "active"


class TestCustomerDelete:
    def test_delete_customer(self, admin_token):
        create_resp = client.post(
            "/api/v1/customers",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "customer_code": "CUST-DEL",
                "full_name": "Delete Test",
                "phone": "+254700000009",
                "address": {"street": "St", "city": "Nairobi", "country": "Kenya"},
            },
        )
        customer_id = create_resp.json()["data"]["_id"]
        response = client.delete(
            f"/api/v1/customers/{customer_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        assert "deactivated" in response.json()["message"].lower()