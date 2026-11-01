from bson import ObjectId
from mongomock_motor import AsyncMongoMockClient
import pytest

from app.core.exceptions import ConflictError, ValidationError
from app.models.router import RouterCreate
from app.services.router_service import RouterService


@pytest.fixture
def relationship_db():
    client = AsyncMongoMockClient(tz_aware=True)
    db = client["router_relationship_test"]
    yield db
    client.close()


def router_payload(site_id=None, nas_client_id=None):
    return RouterCreate(
        name="Test router",
        site_id=site_id,
        nas_client_id=nas_client_id,
        ip_address="192.0.2.10",
        username="api-user",
        password="local-only-test-password",
    )


@pytest.mark.asyncio
async def test_router_assignment_rejects_missing_site(relationship_db):
    with pytest.raises(ValidationError, match="site does not exist"):
        await RouterService(relationship_db).create_router(
            router_payload(site_id=str(ObjectId()))
        )


@pytest.mark.asyncio
async def test_router_accepts_objectid_site_with_string_reference(relationship_db):
    site_id = ObjectId()
    await relationship_db.sites.insert_one({"_id": site_id, "status": "active"})
    service = RouterService(relationship_db)

    await service._validate_site_and_nas(str(site_id), None)
    await service._validate_site_and_nas(site_id, None)


@pytest.mark.asyncio
async def test_linked_nas_must_be_active_and_on_the_router_site(relationship_db):
    site_id, other_site_id = ObjectId(), ObjectId()
    nas_id = ObjectId()
    await relationship_db.sites.insert_many([
        {"_id": site_id, "status": "active"},
        {"_id": other_site_id, "status": "active"},
    ])
    await relationship_db.nas_clients.insert_one({
        "_id": nas_id, "site_id": str(other_site_id), "status": "active",
    })

    with pytest.raises(ConflictError, match="same site"):
        await RouterService(relationship_db)._validate_site_and_nas(
            str(site_id), str(nas_id)
        )


@pytest.mark.asyncio
async def test_router_assignment_rejects_inactive_site(relationship_db):
    site_id = ObjectId()
    await relationship_db.sites.insert_one({"_id": site_id, "status": "inactive"})
    with pytest.raises(ValidationError, match="not active"):
        await RouterService(relationship_db)._validate_site_and_nas(str(site_id), None)
