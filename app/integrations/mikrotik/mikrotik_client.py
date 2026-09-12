"""
app/integrations/mikrotik/mikrotik_client.py
Legacy MikroTik API client for RouterOS 6.x (port 8728/8729).
Wrapped with asyncio thread pools so it never blocks the FastAPI event loop.
"""
import asyncio
import logging
from typing import Any, Dict, List, Optional
from concurrent.futures import ThreadPoolExecutor

from app.core.crypto import decrypt_value
from app.core.config import settings

logger = logging.getLogger(__name__)

# Lazy import so the app starts even if routeros-api isn't installed yet
try:
    import routeros_api
except ImportError:  # pragma: no cover
    routeros_api = None  # type: ignore


class MikroTikLegacyClient:
    """
    Thread-safe wrapper around routeros_api for RouterOS 6.x.
    All blocking calls are offloaded to a ThreadPoolExecutor.
    """

    _executor = ThreadPoolExecutor(max_workers=10, thread_name_prefix="mikrotik_")

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
        self.port = port if not use_ssl else 8729
        self.use_ssl = use_ssl
        self.ssl_verify = ssl_verify
        self.timeout = timeout
        self._api = None
        self._connection = None

    # ─── Connection lifecycle ───

    def _connect_sync(self):
        if routeros_api is None:
            raise RuntimeError("routeros-api library not installed. Run: pip install routeros-api")
        self._connection = routeros_api.RouterOsApiPool(
            self.host,
            username=self.username,
            password=self.password,
            port=self.port,
            plaintext_login=True,
            use_ssl=self.use_ssl,
            ssl_verify=self.ssl_verify,
        )
        self._api = self._connection.get_api()
        return self._api

    def _disconnect_sync(self):
        if self._connection:
            try:
                self._connection.disconnect()
            except Exception:
                pass
            finally:
                self._connection = None
                self._api = None

    async def connect(self):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._executor, self._connect_sync)

    async def disconnect(self):
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(self._executor, self._disconnect_sync)

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.disconnect()

    # ─── Helpers ───

    def _get_resource_sync(self, path: str):
        if self._api is None:
            raise RuntimeError("Not connected. Use 'async with' or call connect() first.")
        return self._api.get_resource(path)

    async def _run(self, fn, *args, **kwargs):
        """Run a blocking function in the thread pool."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._executor, fn, *args, **kwargs)

    # ─── System / Health ───

    async def get_system_resource(self) -> Dict[str, Any]:
        def _fetch():
            res = self._get_resource_sync("/system/resource")
            data = res.get()[0]
            # routeros_api returns nested dicts; flatten primitives
            return {k: v for k, v in data.items()}
        return await self._run(_fetch)

    async def get_system_identity(self) -> Dict[str, Any]:
        def _fetch():
            res = self._get_resource_sync("/system/identity")
            return res.get()[0]
        return await self._run(_fetch)

    async def get_system_routerboard(self) -> Dict[str, Any]:
        def _fetch():
            res = self._get_resource_sync("/system/routerboard")
            return res.get()[0]
        return await self._run(_fetch)

    # ─── Interfaces ───

    async def get_interfaces(self) -> List[Dict[str, Any]]:
        def _fetch():
            res = self._get_resource_sync("/interface")
            return res.get()
        return await self._run(_fetch)

    async def get_interface_stats(self, interface_name: str) -> Dict[str, Any]:
        def _fetch():
            res = self._get_resource_sync("/interface")
            items = res.get()
            for item in items:
                if item.get("name") == interface_name:
                    return item
            return {}
        return await self._run(_fetch)

    # ─── PPPoE ───

    async def get_pppoe_secrets(self) -> List[Dict[str, Any]]:
        def _fetch():
            res = self._get_resource_sync("/ppp/secret")
            return res.get()
        return await self._run(_fetch)

    async def add_pppoe_secret(
        self,
        name: str,
        password: str,
        profile: str = "default",
        service: str = "pppoe",
        remote_address: Optional[str] = None,
        comment: Optional[str] = None,
    ) -> Dict[str, Any]:
        def _add():
            res = self._get_resource_sync("/ppp/secret")
            params = {
                "name": name,
                "password": password,
                "profile": profile,
                "service": service,
            }
            if remote_address:
                params["remote-address"] = remote_address
            if comment:
                params["comment"] = comment
            return res.add(**params)
        return await self._run(_add)

    async def remove_pppoe_secret(self, resource_id: str):
        def _remove():
            res = self._get_resource_sync("/ppp/secret")
            res.remove(id=resource_id)
        return await self._run(_remove)

    async def get_pppoe_active(self) -> List[Dict[str, Any]]:
        def _fetch():
            res = self._get_resource_sync("/ppp/active")
            return res.get()
        return await self._run(_fetch)

    # ─── HotSpot ───

    async def get_hotspot_active(self) -> List[Dict[str, Any]]:
        def _fetch():
            res = self._get_resource_sync("/ip/hotspot/active")
            return res.get()
        return await self._run(_fetch)

    async def get_hotspot_users(self) -> List[Dict[str, Any]]:
        def _fetch():
            res = self._get_resource_sync("/ip/hotspot/user")
            return res.get()
        return await self._run(_fetch)

    async def add_hotspot_user(
        self,
        name: str,
        password: str,
        profile: str = "default",
        limit_uptime: Optional[str] = None,
        comment: Optional[str] = None,
    ) -> Dict[str, Any]:
        def _add():
            res = self._get_resource_sync("/ip/hotspot/user")
            params = {"name": name, "password": password, "profile": profile}
            if limit_uptime:
                params["limit-uptime"] = limit_uptime
            if comment:
                params["comment"] = comment
            return res.add(**params)
        return await self._run(_add)

    # ─── DHCP ───

    async def get_dhcp_leases(self) -> List[Dict[str, Any]]:
        def _fetch():
            res = self._get_resource_sync("/ip/dhcp-server/lease")
            return res.get()
        return await self._run(_fetch)

    # ─── Queues ───

    async def get_simple_queues(self) -> List[Dict[str, Any]]:
        def _fetch():
            res = self._get_resource_sync("/queue/simple")
            return res.get()
        return await self._run(_fetch)

    async def add_simple_queue(
        self,
        name: str,
        target: str,
        max_limit: str,
        comment: Optional[str] = None,
    ) -> Dict[str, Any]:
        def _add():
            res = self._get_resource_sync("/queue/simple")
            params = {"name": name, "target": target, "max-limit": max_limit}
            if comment:
                params["comment"] = comment
            return res.add(**params)
        return await self._run(_add)

    # ─── ARP / Neighbors ───

    async def get_arp_table(self) -> List[Dict[str, Any]]:
        def _fetch():
            res = self._get_resource_sync("/ip/arp")
            return res.get()
        return await self._run(_fetch)

    # ─── Health (RouterOS 6 specific) ───

    async def get_health(self) -> Dict[str, Any]:
        def _fetch():
            res = self._get_resource_sync("/system/health")
            return res.get()[0]
        return await self._run(_fetch)


# ─── Factory ───

def get_mikrotik_client(
    host: str,
    username: str,
    encrypted_password: str,
    port: int = 8728,
    use_ssl: bool = False,
    ssl_verify: bool = False,
) -> MikroTikLegacyClient:
    """Decrypt password and return a configured client."""
    password = decrypt_value(encrypted_password)
    return MikroTikLegacyClient(
        host=host,
        username=username,
        password=password,
        port=port,
        use_ssl=use_ssl,
        ssl_verify=ssl_verify,
    )