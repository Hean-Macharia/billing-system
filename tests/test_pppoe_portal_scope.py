from datetime import datetime, timezone

import pytest
from bson import ObjectId
from mongomock_motor import AsyncMongoMockClient

from app.routes.portal import portal_subscriptions


@pytest.mark.asyncio
async def test_customer_portal_reads_string_and_objectid_subscription_refs_without_passwords():
    client = AsyncMongoMockClient(tz_aware=True)
    db = client["pppoe_portal_scope_test"]
    customer_id = ObjectId()
    plan_id = ObjectId()
    await db.service_plans.insert_one({"_id": plan_id, "name": "Home 10"})
    common = {
        "plan_id": str(plan_id), "service_type": "pppoe", "status": "active",
        "pppoe_username": "safe-user", "pppoe_password": "never-return-this",
        "start_date": datetime.now(timezone.utc), "created_at": datetime.now(timezone.utc),
    }
    await db.subscriptions.insert_one({**common, "customer_id": str(customer_id)})
    await db.subscriptions.insert_one({**common, "customer_id": customer_id, "pppoe_username": "legacy-user"})

    response = await portal_subscriptions({"_id": customer_id}, db)
    data = response["data"]

    assert len(data) == 2
    assert {row["pppoe_username"] for row in data} == {"safe-user", "legacy-user"}
    assert all("pppoe_password" not in row for row in data)
    client.close()
