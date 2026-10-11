from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.customer_service import CustomerService


@pytest.mark.asyncio
async def test_assign_package_uses_customer_id_and_does_not_mutate_payload():
    db = SimpleNamespace()
    db.customers = SimpleNamespace(update_one=AsyncMock(return_value=SimpleNamespace(matched_count=1)))

    service = CustomerService(db)
    service.get_by_id = AsyncMock(return_value=SimpleNamespace(current_package=None))

    payload = {"package_id": "pkg-123", "package_name": "Fiber 50"}
    result = await service.assign_package("64e26b3fe4a7b5f0d0d0d0d0", payload)

    assert result is not None
    assert payload == {"package_id": "pkg-123", "package_name": "Fiber 50"}
    assert db.customers.update_one.await_count == 1
    assert service.get_by_id.await_count == 2
    service.get_by_id.assert_any_await("64e26b3fe4a7b5f0d0d0d0d0")
