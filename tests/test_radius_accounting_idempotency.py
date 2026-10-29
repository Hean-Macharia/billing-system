import pytest
from bson import ObjectId
from mongomock_motor import AsyncMongoMockClient

from app.schemas.radius_auth import RadiusAccountingRequest, RadiusAuthRequest
from app.services.radius_auth_service import RadiusAuthService


@pytest.mark.asyncio
async def test_data_capped_user_is_rejected_with_radius_reply_message():
    client = AsyncMongoMockClient(tz_aware=True)
    db = client["radius_data_cap_test"]
    subscription_id = ObjectId()
    await db.radius_users.insert_one({
        "username": "limited-user",
        "password": "password",
        "user_type": "pppoe",
        "subscription_id": str(subscription_id),
        "data_cap_bytes": 1000,
        "status": "active",
    })
    await db.subscriptions.insert_one({
        "_id": subscription_id,
        "status": "active",
        "data_used_bytes": 1000,
    })

    reply = await RadiusAuthService(db).authenticate(RadiusAuthRequest.model_validate({
        "User-Name": "limited-user",
        "User-Password": "password",
    }))

    assert reply.control_Auth_Type == "Reject"
    assert reply.reply_Reply_Message == "Data limit exceeded"
    client.close()


@pytest.mark.asyncio
async def test_zero_byte_data_cap_rejects_all_usage():
    client = AsyncMongoMockClient(tz_aware=True)
    db = client["radius_zero_data_cap_test"]
    subscription_id = ObjectId()
    await db.radius_users.insert_one({
        "username": "zero-cap-user",
        "password": "password",
        "user_type": "pppoe",
        "subscription_id": str(subscription_id),
        "data_cap_bytes": 0,
        "status": "active",
    })
    await db.subscriptions.insert_one({
        "_id": subscription_id,
        "status": "active",
        "data_used_bytes": 0,
    })

    reply = await RadiusAuthService(db).authenticate(RadiusAuthRequest.model_validate({
        "User-Name": "zero-cap-user",
        "User-Password": "password",
    }))

    assert reply.control_Auth_Type == "Reject"
    assert reply.reply_Reply_Message == "Data limit exceeded"
    client.close()


@pytest.mark.asyncio
async def test_pending_subscription_is_rejected():
    client = AsyncMongoMockClient(tz_aware=True)
    db = client["radius_pending_subscription_test"]
    subscription_id = ObjectId()
    await db.radius_users.insert_one({
        "username": "pending-user",
        "password": "password",
        "user_type": "pppoe",
        "subscription_id": str(subscription_id),
        "status": "active",
    })
    await db.subscriptions.insert_one({
        "_id": subscription_id,
        "status": "pending",
    })

    reply = await RadiusAuthService(db).authenticate(RadiusAuthRequest.model_validate({
        "User-Name": "pending-user",
        "User-Password": "password",
    }))

    assert reply.control_Auth_Type == "Reject"
    assert reply.reply_Reply_Message == "Subscription pending"
    client.close()


@pytest.mark.asyncio
async def test_missing_subscription_is_rejected():
    client = AsyncMongoMockClient(tz_aware=True)
    db = client["radius_missing_subscription_test"]
    await db.radius_users.insert_one({
        "username": "orphaned-user",
        "password": "password",
        "user_type": "pppoe",
        "subscription_id": str(ObjectId()),
        "status": "active",
    })

    reply = await RadiusAuthService(db).authenticate(RadiusAuthRequest.model_validate({
        "User-Name": "orphaned-user",
        "User-Password": "password",
    }))

    assert reply.control_Auth_Type == "Reject"
    assert reply.reply_Reply_Message == "Subscription not found"
    client.close()


@pytest.mark.asyncio
async def test_duplicate_accounting_start_does_not_reset_or_count_session_again():
    client = AsyncMongoMockClient(tz_aware=True)
    db = client["radius_accounting_start_idempotency_test"]
    await db.radius_users.insert_one({"username": "pppoe-user", "total_sessions": 0})
    service = RadiusAuthService(db)
    request = RadiusAccountingRequest.model_validate({
        "Acct-Status-Type": "Start",
        "Acct-Session-Id": "session-start-test",
        "User-Name": "pppoe-user",
        "NAS-IP-Address": "192.0.2.1",
    })

    await service.accounting(request)
    initial = await db.radius_accounting.find_one({"acct_session_id": "session-start-test"})
    await db.radius_accounting.update_one(
        {"acct_session_id": "session-start-test"},
        {"$set": {"acct_session_time": 120, "acct_input_octets": 4096}},
    )
    await service.accounting(request)

    accounting = await db.radius_accounting.find_one({"acct_session_id": "session-start-test"})
    live_session = await db.radius_sessions.find_one({"acct_session_id": "session-start-test"})
    user = await db.radius_users.find_one({"username": "pppoe-user"})
    assert accounting["acct_start_time"] == initial["acct_start_time"]
    assert accounting["acct_session_time"] == 120
    assert accounting["acct_input_octets"] == 4096
    assert live_session["acct_start_time"] == initial["acct_start_time"]
    assert user["total_sessions"] == 1
    client.close()


@pytest.mark.asyncio
async def test_duplicate_accounting_stop_does_not_double_count_usage():
    client = AsyncMongoMockClient(tz_aware=True)
    db = client["radius_accounting_stop_idempotency_test"]
    subscription_id = ObjectId()
    await db.radius_users.insert_one({"username": "pppoe-user"})
    await db.subscriptions.insert_one({
        "_id": subscription_id,
        "data_used_bytes": 0,
        "total_session_time_sec": 0,
    })
    await db.radius_accounting.insert_one({
        "acct_session_id": "session-stop-test",
        "username": "pppoe-user",
        "subscription_id": str(subscription_id),
    })
    await db.radius_sessions.insert_one({
        "acct_session_id": "session-stop-test",
        "status": "online",
    })
    service = RadiusAuthService(db)
    request = RadiusAccountingRequest.model_validate({
        "Acct-Status-Type": "Stop",
        "Acct-Session-Id": "session-stop-test",
        "User-Name": "pppoe-user",
        "Acct-Session-Time": 300,
        "Acct-Input-Octets": 200,
        "Acct-Output-Octets": 300,
        "Acct-Input-Gigawords": 1,
        "Acct-Output-Gigawords": 0,
    })

    await service.accounting(request)
    first_stop = await db.radius_accounting.find_one({"acct_session_id": "session-stop-test"})
    await service.accounting(request)

    user = await db.radius_users.find_one({"username": "pppoe-user"})
    subscription = await db.subscriptions.find_one({"_id": subscription_id})
    live_session = await db.radius_sessions.find_one({"acct_session_id": "session-stop-test"})
    assert first_stop["acct_stop_time"] is not None
    assert user["total_online_time_sec"] == 300
    assert user["total_input_bytes"] == 2**32 + 200
    assert user["total_output_bytes"] == 300
    assert subscription["data_used_bytes"] == 2**32 + 500
    assert subscription["total_session_time_sec"] == 300
    assert live_session["status"] == "offline"
    client.close()
