import pytest
from bson import ObjectId
from mongomock_motor import AsyncMongoMockClient

from app.services.radius_admin_service import RadiusAdminService


@pytest.mark.asyncio
async def test_sync_updates_existing_pppoe_password_without_fallback_overwrite():
    client = AsyncMongoMockClient(tz_aware=True)
    db = client["radius_subscription_sync_test"]
    customer_id = ObjectId()
    subscription_id = ObjectId()
    await db.customers.insert_one({
        "_id": customer_id,
        "customer_code": "customer-code",
        "phone": "254700000000",
    })
    await db.subscriptions.insert_one({
        "_id": subscription_id,
        "customer_id": customer_id,
        "package_id": None,
        "status": "active",
        "pppoe_username": "pppoe-name",
        "pppoe_password": "updated-password",
    })
    await db.radius_users.insert_one({
        "username": "pppoe-name",
        "password": "old-password",
    })

    service = RadiusAdminService(db)
    updated = await service.sync_user_from_subscription(str(subscription_id))

    assert updated.password == "updated-password"
    await db.subscriptions.update_one(
        {"_id": subscription_id},
        {"$unset": {"pppoe_password": ""}},
    )
    resynced = await service.sync_user_from_subscription(str(subscription_id))

    assert resynced.password == "updated-password"
    client.close()
