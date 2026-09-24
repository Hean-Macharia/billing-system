import pytest

from app.models.router import RouterApiType
from app.services.router_service import RouterService


class DummyLegacyClient:
    def __init__(self, router):
        self.router = router

    async def test_connection(self):
        return True


class DummyRestClient:
    def __init__(self, router):
        self.router = router

    async def test_connection(self):
        return True

    async def close(self):
        return None


class FailingRestClient(DummyRestClient):
    async def test_connection(self):
        return False


@pytest.mark.asyncio
async def test_legacy_router_prefers_legacy_client():
    service = object.__new__(RouterService)
    service._legacy_client = lambda router: DummyLegacyClient(router)
    service._rest_client = lambda router: DummyRestClient(router)

    router = {"api_type": RouterApiType.LEGACY.value, "ip_address": "192.168.88.1", "port": 8728}
    client, api_type = await service._resolve_client(router)

    assert api_type == RouterApiType.LEGACY.value
    assert isinstance(client, DummyLegacyClient)


@pytest.mark.asyncio
async def test_rest_router_falls_back_to_legacy_when_rest_is_unreachable():
    service = object.__new__(RouterService)
    service._legacy_client = lambda router: DummyLegacyClient(router)
    service._rest_client = lambda router: FailingRestClient(router)

    router = {"api_type": RouterApiType.REST.value, "ip_address": "192.168.88.1", "port": 443}
    client, api_type = await service._resolve_client(router)

    assert api_type == RouterApiType.LEGACY.value
    assert isinstance(client, DummyLegacyClient)
