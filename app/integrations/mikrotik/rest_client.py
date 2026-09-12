"""
Async REST client for RouterOS 7+ (native REST API over HTTP/HTTPS).

Only used when a router's api_type is "rest". RouterOS 6.x devices
(e.g. RB951Ui-2HnD on 6.49.21) do not have this API - use
app.integrations.mikrotik.legacy_client.AsyncMikroTikLegacyClient instead.
"""
from __future__ import annotations

from typing import Any, Optional

import httpx

from app.core.logging import get_logger

logger = get_logger(__name__)


class MikroTikRestError(Exception):
    """Raised for any REST-API connection or command failure."""


class AsyncMikroTikRestClient:
    def __init__(
        self,
        host: str,
        username: str,
        password: str,
        port: int = 443,
        use_ssl: bool = True,
        ssl_verify: bool = False,
        timeout: int = 10,
    ):
        scheme = "https" if use_ssl else "http"
        self.base_url = f"{scheme}://{host}:{port}/rest"
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            auth=(username, password),
            verify=ssl_verify,
            timeout=timeout,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "AsyncMikroTikRestClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()

    async def _get(self, path: str, params: Optional[dict] = None) -> Any:
        try:
            resp = await self._client.get(path, params=params)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as exc:
            raise MikroTikRestError(f"HTTP {exc.response.status_code} on {path}: {exc.response.text}") from exc
        except httpx.HTTPError as exc:
            raise MikroTikRestError(f"Request to {path} failed: {exc}") from exc

    async def _post(self, path: str, json: dict) -> Any:
        try:
            resp = await self._client.post(path, json=json)
            resp.raise_for_status()
            return resp.json() if resp.content else None
        except httpx.HTTPStatusError as exc:
            raise MikroTikRestError(f"HTTP {exc.response.status_code} on {path}: {exc.response.text}") from exc
        except httpx.HTTPError as exc:
            raise MikroTikRestError(f"Request to {path} failed: {exc}") from exc

    # ------------------------------------------------------------------ #
    async def test_connection(self) -> bool:
        try:
            await self._get("/system/identity")
            return True
        except MikroTikRestError:
            return False

    async def get_system_resource(self) -> dict:
        return await self._get("/system/resource")

    async def get_system_identity(self) -> dict:
        return await self._get("/system/identity")

    async def get_system_health(self) -> list:
        try:
            return await self._get("/system/health")
        except MikroTikRestError:
            return []

    async def get_interfaces(self) -> list:
        return await self._get("/interface")

    async def get_active_pppoe(self) -> list:
        return await self._get("/ppp/active")

    async def get_pppoe_secrets(self) -> list:
        return await self._get("/ppp/secret")

    async def add_pppoe_user(self, name: str, password: str, profile: str = "default") -> None:
        await self._post("/ppp/secret/add", {"name": name, "password": password, "service": "pppoe", "profile": profile})

    async def disconnect_pppoe_session(self, name: str) -> bool:
        sessions = await self.get_active_pppoe()
        matches = [s for s in sessions if s.get("name") == name]
        for s in matches:
            await self._post("/ppp/active/remove", {".id": s[".id"]})
        return bool(matches)

    async def get_active_hotspot(self) -> list:
        return await self._get("/ip/hotspot/active")

    async def disconnect_hotspot_session(self, mac_address: str) -> bool:
        sessions = await self.get_active_hotspot()
        matches = [s for s in sessions if s.get("mac-address") == mac_address]
        for s in matches:
            await self._post("/ip/hotspot/active/remove", {".id": s[".id"]})
        return bool(matches)

    async def get_dhcp_leases(self) -> list:
        return await self._get("/ip/dhcp-server/lease")

    async def get_queues(self) -> list:
        return await self._get("/queue/simple")

    async def set_queue_rate(self, name: str, max_limit: str) -> bool:
        queues = await self.get_queues()
        matches = [q for q in queues if q.get("name") == name]
        for q in matches:
            await self._post("/queue/simple/set", {".id": q[".id"], "max-limit": max_limit})
        return bool(matches)
