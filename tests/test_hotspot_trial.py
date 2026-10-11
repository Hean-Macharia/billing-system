import pytest
from mongomock_motor import AsyncMongoMockClient
from pydantic import ValidationError as PydanticValidationError

from app.core.exceptions import ConflictError
from app.schemas.portal import HotspotPurchaseRequest
from app.services.hotspot_service import HotspotService
from app.services.radius_auth_service import RadiusAuthService


def test_hotspot_purchase_requires_device_type_and_mac():
    purchase = HotspotPurchaseRequest(
        plan_id="plan-id",
        phone_number="254791196121",
        device_type="tv",
        device_mac="aa-bb-cc-dd-ee-ff",
    )

    assert purchase.device_type == "tv"
    with pytest.raises(PydanticValidationError):
        HotspotPurchaseRequest(
            plan_id="plan-id",
            phone_number="254791196121",
            device_type="tv",
            device_mac="not-a-mac",
        )


@pytest.mark.asyncio
async def test_free_trial_is_three_minutes_and_bound_to_one_device():
    client = AsyncMongoMockClient(tz_aware=True)
    db = client["hotspot_trial_test"]
    await db.hotspot_trial_claims.create_index("client_mac", unique=True)
    await db.vouchers.create_index("voucher_code", unique=True)
    service = HotspotService(db)

    trial = await service.request_free_trial("aa-bb-cc-dd-ee-ff")
    voucher = await db.vouchers.find_one({"voucher_code": trial["voucher_code"]})
    radius = RadiusAuthService(db)

    assert trial["duration_seconds"] == 180
    assert voucher["duration_hours"] == pytest.approx(0.05)
    assert voucher["price"] == 0
    assert voucher["trial_mac"] == "AA:BB:CC:DD:EE:FF"
    assert await radius._check_voucher(trial["voucher_code"], "AA:BB:CC:DD:EE:FF")
    assert await radius._check_voucher(trial["voucher_code"], "11:22:33:44:55:66") is None

    with pytest.raises(ConflictError, match="already claimed"):
        await service.request_free_trial("AA:BB:CC:DD:EE:FF")

    client.close()
