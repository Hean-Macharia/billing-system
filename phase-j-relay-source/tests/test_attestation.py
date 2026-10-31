import asyncio
import http.client
import io
import json
import sys
from pathlib import Path
from threading import Thread
from http.server import ThreadingHTTPServer

import pytest


SOURCE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE))

import routeros  # noqa: E402
import server  # noqa: E402


TOKEN = "local-test-relay-shared-token-with-more-than-32-characters"
ROUTER = {"router_id": "65ab00000000000000000001", "site_id": "65ab00000000000000000002"}
REQUEST = {
    "router_id": ROUTER["router_id"],
    "site_id": ROUTER["site_id"],
    "client_ip": "192.168.89.100",
    "client_mac": "aa-bb-cc-dd-ee-ff",
    "nonce": "R5XoV1gN6qaJzHykbv3d5abCdefGHIjkLmnoPQRsTuv",
    "requested_at": 1_800_000_000,
}


def test_positive_attestation_matches_fastapi_verifier(monkeypatch):
    from app.core.config import settings
    from app.services.hotspot_attestation_service import (
        HotspotAttestationService,
        verify_attestation_signature,
    )

    now = 1_800_000_000
    monkeypatch.setattr(server.time, "time", lambda: now)
    monkeypatch.setattr(server, "load_router_password", lambda: "test-router-password")
    observation = {
        "client_ip": REQUEST["client_ip"],
        "observed": True,
        "evidence": {
            "dhcp_lease_match": True,
            "dhcp_lease_status": "bound",
            "hotspot_host_match": True,
            "observation_age_seconds": 0,
        },
    }
    reply = server.handle_attestation(
        dict(REQUEST), TOKEN, router=ROUTER, observer=lambda *_: observation
    )

    assert set(reply) == {"attestation", "signature"}
    assert verify_attestation_signature(reply["attestation"], reply["signature"], TOKEN)
    assert reply["attestation"]["nonce"] == REQUEST["nonce"]
    assert reply["attestation"]["issued_at"] == now
    assert reply["attestation"]["expires_at"] - now <= 60

    monkeypatch.setattr(settings, "router_relay_token", TOKEN)
    fake_db = _NonceDB(REQUEST["nonce"], now)
    service = HotspotAttestationService(fake_db, relay_client=object(), clock=lambda: now)
    candidate = {"router_id": ROUTER["router_id"], "site_id": ROUTER["site_id"]}
    challenge = {"client_ip": REQUEST["client_ip"], "client_mac": "AA:BB:CC:DD:EE:FF"}
    verified = asyncio.run(service._verify_relay_reply(candidate, REQUEST["nonce"], challenge, reply))
    assert verified["observed"] is True
    assert verified["router_id"] == ROUTER["router_id"]
    assert verified["site_id"] == ROUTER["site_id"]

    altered = json.loads(json.dumps(reply))
    altered["attestation"]["site_id"] = "65ab00000000000000000003"
    with pytest.raises(Exception):
        asyncio.run(service._verify_relay_reply(candidate, REQUEST["nonce"], challenge, altered))


class _NonceDB:
    def __init__(self, nonce, now):
        self.router_attestation_nonces = _NonceCollection(nonce, now)


class _NonceCollection:
    def __init__(self, nonce, now):
        from datetime import datetime, timedelta, timezone

        self.record = {
            "nonce": nonce,
            "state": "pending",
            "expires_at": datetime.fromtimestamp(now, timezone.utc) + timedelta(seconds=50),
        }

    async def find_one_and_update(self, query, update, return_document=None):
        if query["nonce"] != self.record["nonce"] or self.record["state"] != "pending":
            return None
        self.record.update(update["$set"])
        return self.record


def test_negative_observation_is_signed_and_not_positive():
    result = server.create_attestation(
        dict(REQUEST),
        ROUTER,
        {
            "client_ip": REQUEST["client_ip"],
            "observed": False,
            "evidence": {
                "dhcp_lease_match": False,
                "dhcp_lease_status": "missing",
                "hotspot_host_match": False,
                "observation_age_seconds": 0,
            },
        },
        TOKEN,
        now=1_800_000_000,
    )
    assert result["attestation"]["observed"] is False
    assert len(result["signature"]) == 64


def test_stale_router_observation_is_never_signed():
    with pytest.raises(RuntimeError, match="stale"):
        server.create_attestation(
            dict(REQUEST), ROUTER,
            {"client_ip": REQUEST["client_ip"], "observed": True, "evidence": {
                "dhcp_lease_match": True, "dhcp_lease_status": "bound",
                "hotspot_host_match": True, "observation_age_seconds": 16,
            }}, TOKEN, now=1_800_000_000,
        )


def test_routeros_failure_does_not_become_signed_negative(monkeypatch):
    monkeypatch.setattr(server.time, "time", lambda: REQUEST["requested_at"])
    monkeypatch.setattr(server, "load_router_password", lambda: "mock-only")
    def unavailable(*_args):
        raise OSError("mock router unavailable")
    with pytest.raises(OSError, match="unavailable"):
        server.handle_attestation(dict(REQUEST), TOKEN, router=ROUTER, observer=unavailable)


@pytest.mark.parametrize("field,value", [
    ("router_id", "65ab00000000000000000009"),
    ("site_id", "65ab00000000000000000009"),
    ("client_mac", "not-a-mac"),
    ("client_ip", "8.8.8.8"),
    ("nonce", "short"),
    ("requested_at", 1),
    ("requested_at", 1_800_000_010),
])
def test_rejects_wrong_identity_or_malformed_request(field, value, monkeypatch):
    now = 1_800_000_000
    monkeypatch.setattr(server.time, "time", lambda: now)
    body = dict(REQUEST)
    body[field] = value
    with pytest.raises((ValueError, PermissionError)):
        server._validate_attestation_request(body, ROUTER)


def test_rejects_extra_router_target_fields(monkeypatch):
    monkeypatch.setattr(server.time, "time", lambda: REQUEST["requested_at"])
    body = {**REQUEST, "host": "127.0.0.1", "username": "attacker", "password": "bad"}
    with pytest.raises(ValueError, match="fields"):
        server._validate_attestation_request(body, ROUTER)


def test_unavailable_router_configuration_fails_closed(monkeypatch):
    monkeypatch.setattr(server, "load_attestation_router", lambda: (_ for _ in ()).throw(RuntimeError("mapping missing")))
    with pytest.raises(RuntimeError, match="mapping"):
        server.handle_attestation(dict(REQUEST), TOKEN, observer=lambda *_: None)


def test_router_allowlist_requires_explicit_enabled_router_and_active_site(monkeypatch):
    settings = {
        "ATTESTATION_ROUTER_ID": ROUTER["router_id"],
        "ATTESTATION_SITE_ID": ROUTER["site_id"],
        "ATTESTATION_ROUTER_ENABLED": "true",
        "ATTESTATION_SITE_ACTIVE": "true",
    }
    monkeypatch.setattr(server, "_relay_env_value", lambda key: settings.get(key, ""))
    assert server.load_attestation_router() == ROUTER
    settings["ATTESTATION_ROUTER_ENABLED"] = "false"
    with pytest.raises(RuntimeError, match="disabled or inactive"):
        server.load_attestation_router()
    settings["ATTESTATION_ROUTER_ENABLED"] = "true"
    settings["ATTESTATION_SITE_ACTIVE"] = "false"
    with pytest.raises(RuntimeError, match="disabled or inactive"):
        server.load_attestation_router()


def test_hmac_tampering_is_detected_by_fastapi():
    from app.services.hotspot_attestation_service import verify_attestation_signature

    result = server.create_attestation(
        dict(REQUEST), ROUTER,
        {"client_ip": REQUEST["client_ip"], "observed": False, "evidence": {
            "dhcp_lease_match": False, "dhcp_lease_status": "missing",
            "hotspot_host_match": False, "observation_age_seconds": 0,
        }}, TOKEN, now=1_800_000_000,
    )
    assert verify_attestation_signature(result["attestation"], result["signature"], TOKEN)
    result["attestation"]["nonce"] = "tampered"
    assert not verify_attestation_signature(result["attestation"], result["signature"], TOKEN)


def test_routeros_observation_reads_only_dhcp_and_hotspot_tables(monkeypatch):
    commands = []

    class FakeRouterOS:
        def __init__(self, password, timeout):
            assert password == "mock-only"
            assert timeout <= routeros.TIMEOUT

        def connect(self):
            return None

        def query(self, command, attributes=None):
            commands.append(command)
            if command == "/ip/dhcp-server/lease/print":
                return [{"address": REQUEST["client_ip"], "mac-address": "AA:BB:CC:DD:EE:FF", "status": "bound"}]
            if command == "/ip/hotspot/host/print":
                return [{"address": REQUEST["client_ip"], "mac-address": "AA:BB:CC:DD:EE:FF"}]
            raise AssertionError("Attestation must use read-only table queries")

        def close(self):
            return None

    monkeypatch.setattr(routeros, "RouterOS", FakeRouterOS)
    observed = routeros.observe_hotspot_client(REQUEST["client_ip"], REQUEST["client_mac"], "mock-only")
    assert observed["observed"] is True
    assert observed["evidence"]["dhcp_lease_status"] == "bound"
    assert observed["evidence"]["hotspot_host_match"] is True
    assert commands == ["/ip/dhcp-server/lease/print", "/ip/hotspot/host/print"]


@pytest.mark.parametrize("kind", ["unbound", "expired", "missing-host", "mismatched-host", "duplicate-lease", "duplicate-host"])
def test_routeros_observation_is_negative_or_fails_closed(kind, monkeypatch):
    class FakeRouterOS:
        def __init__(self, password, timeout):
            pass

        def connect(self):
            return None

        def query(self, command, attributes=None):
            if command == "/ip/dhcp-server/lease/print":
                lease = {"address": REQUEST["client_ip"], "mac-address": "AA:BB:CC:DD:EE:FF", "status": "bound"}
                if kind == "unbound": lease["status"] = "offered"
                if kind == "expired": lease["status"] = "waiting"
                if kind == "duplicate-lease": return [lease, dict(lease)]
                return [lease]
            if command == "/ip/hotspot/host/print":
                if kind in {"missing-host", "unbound", "expired"}: return []
                mac = "AA:BB:CC:DD:EE:00" if kind == "mismatched-host" else "AA:BB:CC:DD:EE:FF"
                row = {"address": REQUEST["client_ip"], "mac-address": mac}
                return [row, dict(row)] if kind == "duplicate-host" else [row]

        def close(self):
            pass

    monkeypatch.setattr(routeros, "RouterOS", FakeRouterOS)
    if kind in {"mismatched-host", "duplicate-lease", "duplicate-host"}:
        with pytest.raises(RuntimeError):
            routeros.observe_hotspot_client(REQUEST["client_ip"], REQUEST["client_mac"], "mock")
    else:
        observed = routeros.observe_hotspot_client(REQUEST["client_ip"], REQUEST["client_mac"], "mock")
        assert observed["observed"] is False


@pytest.fixture
def relay_http(monkeypatch):
    monkeypatch.setattr(server, "load_token", lambda: TOKEN)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.RelayHandler)
    thread = Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield httpd.server_address
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=2)


def _post(address, path, token=None, payload=None):
    connection = http.client.HTTPConnection(*address, timeout=2)
    headers = {"Content-Type": "application/json"}
    if token is not None:
        headers["Authorization"] = token
    body = json.dumps(payload or {"probe": True})
    connection.request("POST", path, body=body, headers=headers)
    response = connection.getresponse()
    data = json.loads(response.read())
    connection.close()
    return response.status, data


@pytest.mark.parametrize("authorization", [None, "Basic malformed", "Bearer wrong-token"])
def test_attestation_route_rejects_missing_or_invalid_bearer(relay_http, authorization):
    status, body = _post(relay_http, "/api/v1/router/attest", authorization)
    assert status == 401
    assert body["message"] == "Unauthorized"


def test_attestation_route_uses_existing_auth_and_returns_safe_mapping_error(relay_http, monkeypatch):
    monkeypatch.setattr(server, "load_attestation_router", lambda: (_ for _ in ()).throw(RuntimeError("Attestation router/site mapping is not configured")))
    status, body = _post(relay_http, "/api/v1/router/attest", "Bearer " + TOKEN, REQUEST)
    assert status == 503
    assert body["message"] == "Router attestation could not be verified"
    assert TOKEN not in json.dumps(body)


def test_existing_health_and_router_relay_routes_remain_available(relay_http, monkeypatch):
    import builtins

    import routeros as routeros_module

    health = http.client.HTTPConnection(*relay_http, timeout=2)
    health.request("GET", "/health")
    response = health.getresponse()
    payload = json.loads(response.read())
    health.close()
    assert response.status == 200
    assert payload["status"] == "running"

    original_open = builtins.open
    def fake_open(path, *args, **kwargs):
        if str(path).endswith("relay.env"):
            return io.StringIO("MIKROTIK_API_PASSWORD=mock-only-password\n")
        return original_open(path, *args, **kwargs)
    monkeypatch.setattr(builtins, "open", fake_open)
    monkeypatch.setattr(routeros_module, "run_action", lambda action, payload: {"action": action})
    status, body = _post(relay_http, "/api/v1/router/relay", "Bearer " + TOKEN, {"action": "system.identity"})
    assert status == 200
    assert body == {"success": True, "data": {"action": "system.identity"}}


