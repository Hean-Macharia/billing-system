import pytest

from app.core.exceptions import ServiceUnavailableError
from app.routes.portal import portal_register
from app.schemas.portal import PortalRegisterRequest


@pytest.mark.asyncio
async def test_public_portal_registration_is_disabled_until_secure_verification():
    request = PortalRegisterRequest(
        customer_code="CUST-0001",
        phone="254712345678",
        email="customer@example.com",
        password="secure-password",
    )

    with pytest.raises(ServiceUnavailableError) as error:
        await portal_register(request)

    assert error.value.status_code == 503
    assert "secure verification" in error.value.message
