"""Secure relay client for Render -> Oracle VPS -> MikroTik communication.

This client is intentionally limited: it can only talk to the VPS relay using a
shared token and never exposes the MikroTik API port to the public internet.
The relay itself is expected to validate the token, payload shape, and allowed
RouterOS operations before forwarding request data to the private VPN address.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

import httpx

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class RouterRelayError(Exception):
    """Raised for relayed API failures or invalid relay responses."""


class RouterRelayClient:
    """Client for the VPS relay that sits between Render and the MikroTik router."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        token: Optional[str] = None,
        timeout: int = 10,
    ):
        self.base_url = (base_url or settings.router_relay_url or "").rstrip("/")
        self.token = token or settings.router_relay_token or ""
        self.timeout = timeout

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    async def ping(self) -> Dict[str, Any]:
        return await self._request("GET", "/health")

    async def test_connection(self) -> bool:
        try:
            payload = await self.ping()
            return bool(payload.get("success"))
        except Exception:
            return False

    async def get_system_identity(self) -> Dict[str, Any]:
        return await self._request("POST", "/api/v1/router/relay", {"action": "system.identity"})

    async def get_system_resource(self) -> Dict[str, Any]:
        return await self._request("POST", "/api/v1/router/relay", {"action": "system.resource"})

    async def get_system_health(self) -> list:
        payload = await self._request("POST", "/api/v1/router/relay", {"action": "system.health"})
        rows = payload.get("data") if isinstance(payload, dict) else payload
        return rows if isinstance(rows, list) else []

    async def get_interfaces(self) -> list:
        payload = await self._request("POST", "/api/v1/router/relay", {"action": "interface.list"})
        rows = payload.get("data") if isinstance(payload, dict) else payload
        return rows if isinstance(rows, list) else []

    async def get_active_pppoe(self) -> list:
        payload = await self._request("POST", "/api/v1/router/relay", {"action": "pppoe.active"})
        rows = payload.get("data") if isinstance(payload, dict) else payload
        return rows if isinstance(rows, list) else []

    async def get_pppoe_secrets(self) -> list:
        payload = await self._request("POST", "/api/v1/router/relay", {"action": "pppoe.secrets"})
        rows = payload.get("data") if isinstance(payload, dict) else payload
        return rows if isinstance(rows, list) else []

    async def add_pppoe_user(self, name: str, password: str, profile: str = "default") -> Dict[str, Any]:
        return await self._request(
            "POST",
            "/api/v1/router/relay",
            {"action": "pppoe.add", "payload": {"name": name, "password": password, "profile": profile}},
        )

    async def disconnect_pppoe_session(self, name: str) -> bool:
        payload = await self._request("POST", "/api/v1/router/relay", {"action": "pppoe.disconnect", "payload": {"name": name}})
        data = payload.get("data") if isinstance(payload, dict) else payload
        return bool(data)

    async def get_active_hotspot(self) -> list:
        payload = await self._request("POST", "/api/v1/router/relay", {"action": "hotspot.active"})
        rows = payload.get("data") if isinstance(payload, dict) else payload
        return rows if isinstance(rows, list) else []

    async def get_hotspot_users(self) -> list:
        payload = await self._request("POST", "/api/v1/router/relay", {"action": "hotspot.users"})
        rows = payload.get("data") if isinstance(payload, dict) else payload
        return rows if isinstance(rows, list) else []

    async def add_hotspot_user(self, name: str, password: str, profile: str = "default", comment: Optional[str] = None) -> Dict[str, Any]:
        payload = {"name": name, "password": password, "profile": profile}
        if comment:
            payload["comment"] = comment
        return await self._request("POST", "/api/v1/router/relay", {"action": "hotspot.add", "payload": payload})

    async def disconnect_hotspot_session(self, mac_address: str) -> bool:
        payload = await self._request("POST", "/api/v1/router/relay", {"action": "hotspot.disconnect", "payload": {"mac_address": mac_address}})
        data = payload.get("data") if isinstance(payload, dict) else payload
        return bool(data)

    async def get_dhcp_leases(self) -> list:
        payload = await self._request("POST", "/api/v1/router/relay", {"action": "dhcp.leases"})
        rows = payload.get("data") if isinstance(payload, dict) else payload
        return rows if isinstance(rows, list) else []

    async def get_queues(self) -> list:
        payload = await self._request("POST", "/api/v1/router/relay", {"action": "queue.list"})
        rows = payload.get("data") if isinstance(payload, dict) else payload
        return rows if isinstance(rows, list) else []

    async def close(self) -> None:
        return None

    async def _request(self, method: str, path: str, json_body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if not self.base_url:
            raise RouterRelayError("ROUTER_RELAY_URL is not configured")
        if not self.token:
            raise RouterRelayError("ROUTER_RELAY_TOKEN is not configured")

        try:
            async with httpx.AsyncClient(timeout=self.timeout, headers=self._headers()) as client:
                response = await client.request(method, f"{self.base_url}{path}", json=json_body)
                if response.status_code == 401:
                    raise RouterRelayError("Relay authentication failed")
                if response.status_code >= 400:
                    raise RouterRelayError(f"Relay returned HTTP {response.status_code}")
                body = response.json()
        except httpx.HTTPError as exc:
            raise RouterRelayError(f"Relay connection failed: {exc}") from exc

        if not isinstance(body, dict):
            raise RouterRelayError("Relay returned an invalid payload")
        if body.get("success") is False:
            raise RouterRelayError(body.get("message") or "Relay rejected the request")
        return body
