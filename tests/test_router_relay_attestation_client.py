import pytest

from app.integrations.mikrotik import relay_client


@pytest.mark.asyncio
async def test_attestation_client_uses_existing_bearer_transport_and_new_contract(monkeypatch):
    calls = []

    class FakeResponse:
        status_code = 200

        def json(self):
            return {"success": True, "attestation": {"nonce": "test"}, "signature": "0" * 64}

    class FakeAsyncClient:
        def __init__(self, *, timeout, headers):
            self.timeout = timeout
            self.headers = headers

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def request(self, method, url, json=None):
            calls.append((method, url, self.headers, json))
            return FakeResponse()

    monkeypatch.setattr(relay_client.httpx, "AsyncClient", FakeAsyncClient)
    request = {
        "router_id": "configured-router-id",
        "site_id": "configured-site-id",
        "client_ip": "192.168.89.100",
        "client_mac": "AA:BB:CC:DD:EE:FF",
        "nonce": "one-time-challenge",
        "requested_at": 1_798_000_000,
    }
    client = relay_client.RouterRelayClient(
        base_url="https://relay.example.test", token="local-test-token-not-a-production-secret"
    )

    result = await client.attest_hotspot_client(request)

    assert result["attestation"]["nonce"] == "test"
    method, url, headers, body = calls[0]
    assert method == "POST"
    assert url == "https://relay.example.test/api/v1/router/attest"
    assert headers["Authorization"].startswith("Bearer ")
    assert body == request
