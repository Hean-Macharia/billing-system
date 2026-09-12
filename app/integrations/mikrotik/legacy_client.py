"""
Async-safe client for the MikroTik RouterOS 6.x "legacy" API
(binary protocol, port 8728 plaintext / 8729 SSL) - e.g. the
RB951Ui-2HnD running 6.49.21, which has no RouterOS 7 REST API.

`routeros_api` is fully synchronous/blocking. Every call here is pushed
onto a dedicated ThreadPoolExecutor via run_in_executor so it never stalls
the FastAPI event loop.

All returned dict values are raw legacy-API strings; use
app.integrations.mikrotik.parsers to normalize them.
"""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

try:
    import routeros_api
    from routeros_api.exceptions import (
        RouterOsApiCommunicationError,
        RouterOsApiConnectionError,
    )
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    routeros_api = None
    RouterOsApiCommunicationError = RuntimeError
    RouterOsApiConnectionError = RuntimeError

from app.core.logging import get_logger

logger = get_logger(__name__)

# Dedicated executor so blocking RouterOS calls never share the default
# executor with other blocking work.
_EXECUTOR = ThreadPoolExecutor(max_workers=8, thread_name_prefix="mikrotik-legacy")


class MikroTikLegacyError(Exception):
    """Raised for any legacy-API connection or command failure."""


class AsyncMikroTikLegacyClient:
    """
    Usage:
        client = AsyncMikroTikLegacyClient(host, username, password, port=8728)
        async with client:
            resource = await client.get_system_resource()
    """

    def __init__(
        self,
        host: str,
        username: str,
        password: str,
        port: int = 8728,
        use_ssl: bool = False,
        ssl_verify: bool = False,
        timeout: int = 10,
    ):
        self.host = host
        self.username = username
        self.password = password
        self.port = port
        self.use_ssl = use_ssl
        self.ssl_verify = ssl_verify
        self.timeout = timeout

        self._pool: Optional[routeros_api.RouterOsApiPool] = None
        self._api = None

    # ------------------------------------------------------------------ #
    # Connection lifecycle
    # ------------------------------------------------------------------ #
    async def connect(self) -> None:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(_EXECUTOR, self._connect_sync)

    def _connect_sync(self) -> None:
        if routeros_api is None:
            raise MikroTikLegacyError("routeros-api library not installed. Run: pip install routeros-api")
        try:
            self._pool = routeros_api.RouterOsApiPool(
                self.host,
                username=self.username,
                password=self.password,
                port=self.port,
                use_ssl=self.use_ssl,
                ssl_verify=self.ssl_verify,
                plaintext_login=True,
            )
            self._api = self._pool.get_api()
        except RouterOsApiConnectionError as exc:
            raise MikroTikLegacyError(f"Connection failed to {self.host}:{self.port} - {exc}") from exc
        except Exception as exc:  # noqa: BLE001
            raise MikroTikLegacyError(f"Unexpected error connecting to {self.host}: {exc}") from exc

    async def disconnect(self) -> None:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(_EXECUTOR, self._disconnect_sync)

    def _disconnect_sync(self) -> None:
        if self._pool is not None:
            try:
                self._pool.disconnect()
            except Exception:  # noqa: BLE001
                logger.warning(f"Error disconnecting from {self.host}", exc_info=True)
            finally:
                self._pool = None
                self._api = None

    async def __aenter__(self) -> "AsyncMikroTikLegacyClient":
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.disconnect()

    # ------------------------------------------------------------------ #
    # Low-level helpers
    # ------------------------------------------------------------------ #
    def _require_api(self):
        if self._api is None:
            raise MikroTikLegacyError("Client is not connected - call connect() first")
        return self._api

    async def _run(self, func, *args, **kwargs):
        loop = asyncio.get_running_loop()
        try:
            return await loop.run_in_executor(_EXECUTOR, lambda: func(*args, **kwargs))
        except RouterOsApiCommunicationError as exc:
            raise MikroTikLegacyError(f"Command failed on {self.host}: {exc}") from exc
        except MikroTikLegacyError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise MikroTikLegacyError(f"Unexpected error on {self.host}: {exc}") from exc

    def _get_resource_sync(self, path: str, **query) -> list:
        api = self._require_api()
        resource = api.get_resource(path)
        return resource.get(**query) if query else resource.get()

    # ------------------------------------------------------------------ #
    # Connectivity / health
    # ------------------------------------------------------------------ #
    async def test_connection(self) -> bool:
        try:
            await self.connect()
            await self._run(self._get_resource_sync, "/system/identity")
            return True
        except MikroTikLegacyError:
            return False
        finally:
            await self.disconnect()

    async def get_system_resource(self) -> dict:
        rows = await self._run(self._get_resource_sync, "/system/resource")
        return rows[0] if rows else {}

    async def get_system_identity(self) -> dict:
        rows = await self._run(self._get_resource_sync, "/system/identity")
        return rows[0] if rows else {}

    async def get_system_health(self) -> list:
        try:
            return await self._run(self._get_resource_sync, "/system/health")
        except MikroTikLegacyError:
            return []

    # ------------------------------------------------------------------ #
    # Interfaces
    # ------------------------------------------------------------------ #
    async def get_interfaces(self) -> list:
        return await self._run(self._get_resource_sync, "/interface")

    # ------------------------------------------------------------------ #
    # PPPoE
    # ------------------------------------------------------------------ #
    async def get_active_pppoe(self) -> list:
        return await self._run(self._get_resource_sync, "/ppp/active")

    async def get_pppoe_secrets(self) -> list:
        return await self._run(self._get_resource_sync, "/ppp/secret")

    def _add_pppoe_user_sync(self, name: str, password: str, profile: str) -> None:
        resource = self._require_api().get_resource("/ppp/secret")
        resource.add(name=name, password=password, service="pppoe", profile=profile)

    async def add_pppoe_user(self, name: str, password: str, profile: str = "default") -> None:
        await self._run(self._add_pppoe_user_sync, name, password, profile)

    def _remove_pppoe_user_sync(self, name: str) -> None:
        resource = self._require_api().get_resource("/ppp/secret")
        for row in resource.get(name=name):
            resource.remove(id=row["id"])

    async def remove_pppoe_user(self, name: str) -> None:
        await self._run(self._remove_pppoe_user_sync, name)

    def _disconnect_pppoe_session_sync(self, name: str) -> bool:
        resource = self._require_api().get_resource("/ppp/active")
        matches = resource.get(name=name)
        for row in matches:
            resource.remove(id=row["id"])
        return bool(matches)

    async def disconnect_pppoe_session(self, name: str) -> bool:
        return await self._run(self._disconnect_pppoe_session_sync, name)

    # ------------------------------------------------------------------ #
    # HotSpot
    # ------------------------------------------------------------------ #
    async def get_active_hotspot(self) -> list:
        return await self._run(self._get_resource_sync, "/ip/hotspot/active")

    def _disconnect_hotspot_session_sync(self, mac_address: str) -> bool:
        resource = self._require_api().get_resource("/ip/hotspot/active")
        matches = resource.get(**{"mac-address": mac_address})
        for row in matches:
            resource.remove(id=row["id"])
        return bool(matches)

    async def disconnect_hotspot_session(self, mac_address: str) -> bool:
        return await self._run(self._disconnect_hotspot_session_sync, mac_address)

    # ------------------------------------------------------------------ #
    # DHCP / Queues
    # ------------------------------------------------------------------ #
    async def get_dhcp_leases(self) -> list:
        return await self._run(self._get_resource_sync, "/ip/dhcp-server/lease")

    async def get_queues(self) -> list:
        return await self._run(self._get_resource_sync, "/queue/simple")

    def _set_queue_rate_sync(self, name: str, max_limit: str) -> bool:
        resource = self._require_api().get_resource("/queue/simple")
        matches = resource.get(name=name)
        for row in matches:
            resource.set(id=row["id"], **{"max-limit": max_limit})
        return bool(matches)

    async def set_queue_rate(self, name: str, max_limit: str) -> bool:
        """max_limit format: 'upload/download', e.g. '5M/10M'."""
        return await self._run(self._set_queue_rate_sync, name, max_limit)
