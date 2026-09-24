"""Router (MikroTik) management service.

Handles CRUD for managed routers plus live operations (connectivity
tests, health refresh, active sessions, DHCP leases, queues, PPPoE
provisioning). Transparently picks the legacy binary API (RouterOS 6.x,
e.g. RB951Ui-2HnD on 6.49.21) or the REST API (RouterOS 7+) based on the
router's stored api_type.
"""
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any, Tuple

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.crypto import decrypt_value, encrypt_value
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.logging import get_logger
from app.integrations.mikrotik.legacy_client import AsyncMikroTikLegacyClient, MikroTikLegacyError
from app.integrations.mikrotik.rest_client import AsyncMikroTikRestClient, MikroTikRestError
from app.integrations.mikrotik.parsers import (
    normalize_active_hotspot,
    normalize_active_pppoe,
    normalize_dhcp_lease,
    normalize_health,
    normalize_interface,
    normalize_queue,
    normalize_system_resource,
)
from app.models.router import Router, RouterApiType, RouterStatus, default_port_for
from app.schemas.router import RouterCreate, RouterUpdate

logger = get_logger(__name__)


class RouterService:
    """Administrative and live operations for managed MikroTik routers."""

    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.collection = db.routers

    # ------------------------------------------------------------------ #
    # Serialization helpers
    # ------------------------------------------------------------------ #
    def _serialize_router(self, doc: dict) -> Dict[str, Any]:
        """Convert MongoDB document to JSON-serializable dict."""
        if not doc:
            return None

        if "_id" in doc and isinstance(doc["_id"], ObjectId):
            doc["_id"] = str(doc["_id"])

        for key, value in list(doc.items()):
            if isinstance(value, ObjectId):
                doc[key] = str(value)
            elif isinstance(value, datetime):
                doc[key] = value.isoformat()

        return doc

    def _router_to_dict(self, router: Router) -> Dict[str, Any]:
        """Convert Router model to serializable dict."""
        if not router:
            return None

        router_dict = router.model_dump(by_alias=True)
        if "_id" in router_dict and isinstance(router_dict["_id"], ObjectId):
            router_dict["_id"] = str(router_dict["_id"])
        if "id" in router_dict and isinstance(router_dict["id"], ObjectId):
            router_dict["id"] = str(router_dict["id"])

        for key, value in router_dict.items():
            if isinstance(value, datetime):
                router_dict[key] = value.isoformat()

        return router_dict

    # ------------------------------------------------------------------ #
    # CRUD
    # ------------------------------------------------------------------ #
    async def create_router(self, data: RouterCreate) -> Dict[str, Any]:
        """Create a new router and return serializable dict."""
        existing = await self.collection.find_one({"ip_address": data.ip_address})
        if existing:
            raise ConflictError(f"Router with IP {data.ip_address} already exists")

        doc = data.model_dump(exclude={"password", "radius_secret"})
        doc["port"] = data.port or default_port_for(data.api_type, data.use_ssl)
        doc["password"] = encrypt_value(data.password)
        doc["radius_secret"] = encrypt_value(data.radius_secret) if data.radius_secret else None
        doc["status"] = RouterStatus.UNKNOWN.value
        doc["last_health"] = None
        doc["last_checked_at"] = None
        doc["routeros_version"] = None
        doc["created_at"] = datetime.now(timezone.utc)
        doc["updated_at"] = datetime.now(timezone.utc)

        result = await self.collection.insert_one(doc)
        doc["_id"] = str(result.inserted_id)
        logger.info(f"Router registered: {data.name} @ {data.ip_address} ({data.api_type.value})")

        return self._serialize_router(doc)

    async def get_router(self, router_id: str) -> Dict[str, Any]:
        """Get router by ID as serializable dict."""
        doc = await self._get_raw(router_id)
        return self._serialize_router(doc)

    async def _get_raw(self, router_id: str) -> dict:
        try:
            oid = ObjectId(router_id)
        except Exception as exc:
            raise NotFoundError("Router not found") from exc
        doc = await self.collection.find_one({"_id": oid})
        if not doc:
            raise NotFoundError("Router not found")
        return doc

    async def list_routers(
        self,
        site_id: Optional[str] = None,
        status: Optional[str] = None,
        page: int = 1,
        limit: int = 20,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """List routers with pagination, returning serializable dicts."""
        query = {}
        if site_id:
            query["site_id"] = site_id
        if status:
            query["status"] = status

        skip = (page - 1) * limit
        total = await self.collection.count_documents(query)
        cursor = self.collection.find(query).skip(skip).limit(limit).sort("created_at", -1)
        routers = []
        async for doc in cursor:
            routers.append(self._serialize_router(doc))
        return routers, total

    async def update_router(self, router_id: str, data: RouterUpdate) -> Dict[str, Any]:
        """Update a router and return serializable dict."""
        update_data = {k: v for k, v in data.model_dump(exclude_unset=True).items() if v is not None}
        if not update_data:
            raise ValidationError("No fields to update")

        if "password" in update_data:
            update_data["password"] = encrypt_value(update_data["password"])
        if "radius_secret" in update_data:
            update_data["radius_secret"] = encrypt_value(update_data["radius_secret"])
        if "api_type" in update_data and isinstance(update_data["api_type"], RouterApiType):
            update_data["api_type"] = update_data["api_type"].value
        if "status" in update_data and isinstance(update_data["status"], RouterStatus):
            update_data["status"] = update_data["status"].value

        update_data["updated_at"] = datetime.now(timezone.utc)

        try:
            oid = ObjectId(router_id)
        except Exception as exc:
            raise NotFoundError("Router not found") from exc

        result = await self.collection.update_one({"_id": oid}, {"$set": update_data})
        if result.matched_count == 0:
            raise NotFoundError("Router not found")

        doc = await self.collection.find_one({"_id": oid})
        return self._serialize_router(doc)

    async def delete_router(self, router_id: str) -> bool:
        """Delete a router."""
        try:
            oid = ObjectId(router_id)
        except Exception as exc:
            raise NotFoundError("Router not found") from exc
        result = await self.collection.delete_one({"_id": oid})
        if result.deleted_count == 0:
            raise NotFoundError("Router not found")
        return True

    # ------------------------------------------------------------------ #
    # Client factory
    # ------------------------------------------------------------------ #
    def _is_legacy(self, router: dict) -> bool:
        """Return True if the router is configured for the legacy API."""
        api_type = router.get("api_type")
        if hasattr(api_type, "value"):
            api_type = api_type.value
        return api_type == RouterApiType.LEGACY.value

    def _legacy_client(self, router: dict) -> AsyncMikroTikLegacyClient:
        return AsyncMikroTikLegacyClient(
            host=router["ip_address"],
            username=router["username"],
            password=decrypt_value(router["password"]),
            port=router.get("port") or 8728,
            use_ssl=bool(router.get("use_ssl")),
            ssl_verify=bool(router.get("ssl_verify")),
        )

    def _rest_client(self, router: dict) -> AsyncMikroTikRestClient:
        return AsyncMikroTikRestClient(
            host=router["ip_address"],
            username=router["username"],
            password=decrypt_value(router["password"]),
            port=router.get("port") or 443,
            use_ssl=bool(router.get("use_ssl", True)),
            ssl_verify=bool(router.get("ssl_verify", False)),
        )

    async def _resolve_client(self, router: dict) -> Tuple[Any, str]:
        """
        Return the correct MikroTik client for this router.

        IMPORTANT: This function does NOT probe the connection. It picks the
        client purely based on the router's stored `api_type`. If we probed
        here, the probe would open and close the HTTP session on the REST
        client, leaving it unusable for the actual call that follows
        (`RuntimeError: Cannot send a request, as the client has been closed`).

        Failure handling is done by the caller, which catches
        MikroTikLegacyError / MikroTikRestError and returns a clean
        {"reachable": False, ...} response.
        """
        api_type = router.get("api_type")
        if hasattr(api_type, "value"):
            api_type = api_type.value

        if api_type == RouterApiType.LEGACY.value:
            return self._legacy_client(router), RouterApiType.LEGACY.value

        return self._rest_client(router), RouterApiType.REST.value

    async def _close_client(self, client: Any, api_type: str) -> None:
        """Close a client regardless of type."""
        if api_type == RouterApiType.LEGACY.value:
            if hasattr(client, "disconnect"):
                try:
                    await client.disconnect()
                except Exception:
                    pass
            return
        if hasattr(client, "close"):
            try:
                await client.close()
            except Exception:
                pass

    # ------------------------------------------------------------------ #
    # Connectivity
    # ------------------------------------------------------------------ #
    async def test_connectivity(self, router_id: str) -> Dict[str, Any]:
        """Test connectivity to a router (legacy or REST, based on api_type)."""
        router = await self._get_raw(router_id)
        checked_at = datetime.now(timezone.utc)

        client, used_api = await self._resolve_client(router)
        try:
            if used_api == RouterApiType.LEGACY.value:
                reachable = await client.test_connection()
            else:
                reachable = await client.test_connection()
        except (MikroTikLegacyError, MikroTikRestError) as exc:
            logger.warning(f"Connectivity test failed for {router['ip_address']}: {exc}")
            reachable = False
        finally:
            await self._close_client(client, used_api)

        new_status = RouterStatus.ONLINE.value if reachable else RouterStatus.OFFLINE.value
        await self.collection.update_one(
            {"_id": ObjectId(router_id)},
            {"$set": {"status": new_status, "last_checked_at": checked_at}},
        )
        return {
            "router_id": router_id,
            "reachable": reachable,
            "api_type": used_api,
            "configured_api_type": router.get("api_type"),
            "checked_at": checked_at.isoformat(),
        }

    # ------------------------------------------------------------------ #
    # Health
    # ------------------------------------------------------------------ #
    async def refresh_health(self, router_id: str) -> Dict[str, Any]:
        """Refresh router health metrics (legacy or REST, based on api_type)."""
        router = await self._get_raw(router_id)

        if self._is_legacy(router):
            health = await self._refresh_health_legacy(router)
        else:
            health = await self._refresh_health_rest(router)

        health["checked_at"] = datetime.now(timezone.utc).isoformat()

        await self.collection.update_one(
            {"_id": ObjectId(router_id)},
            {
                "$set": {
                    "last_health": health,
                    "last_checked_at": datetime.now(timezone.utc),
                    "status": RouterStatus.ONLINE.value if health.get("reachable") else RouterStatus.OFFLINE.value,
                    "routeros_version": health.get("version") or router.get("routeros_version"),
                }
            },
        )
        return health

    async def refresh_all_health(self) -> Dict[str, Any]:
        """Refresh health for all routers."""
        cursor = self.collection.find({"status": {"$ne": RouterStatus.DISABLED.value}})
        checked, online, offline = 0, 0, 0
        results = []
        async for doc in cursor:
            router_id = str(doc["_id"])
            try:
                result = await self.refresh_health(router_id)
                checked += 1
                if result.get("reachable"):
                    online += 1
                else:
                    offline += 1
                results.append({
                    "router_id": router_id,
                    "name": doc.get("name"),
                    "online": result.get("reachable", False),
                    "error": result.get("error") if not result.get("reachable") else None,
                })
            except Exception as exc:
                logger.warning(f"Health refresh failed for router {router_id}: {exc}")
                offline += 1
                checked += 1
                results.append({
                    "router_id": router_id,
                    "name": doc.get("name"),
                    "online": False,
                    "error": str(exc),
                })
        return {
            "checked": checked,
            "online": online,
            "offline": offline,
            "details": results,
        }

    async def _refresh_health_legacy(self, router: dict) -> dict:
        client = self._legacy_client(router)
        try:
            await client.connect()
            raw_resource = await client.get_system_resource()
            raw_health_rows = await client.get_system_health()

            resource = normalize_system_resource(raw_resource)
            metrics = normalize_health(raw_health_rows)

            return {
                "reachable": True,
                "api_type": "legacy",
                "cpu_load_percent": resource["cpu_load_percent"],
                "free_memory_bytes": resource["free_memory_bytes"],
                "total_memory_bytes": resource["total_memory_bytes"],
                "free_hdd_bytes": resource["free_hdd_bytes"],
                "total_hdd_bytes": resource["total_hdd_bytes"],
                "uptime_seconds": resource["uptime_seconds"],
                "board_name": resource["board_name"],
                "version": resource["version"],
                "voltage": metrics.get("voltage"),
                "temperature": metrics.get("temperature"),
            }
        except MikroTikLegacyError as exc:
            logger.warning(f"Legacy health check failed for {router['ip_address']}: {exc}")
            return {"reachable": False, "api_type": "legacy", "error": str(exc)}
        finally:
            await self._close_client(client, RouterApiType.LEGACY.value)

    async def _refresh_health_rest(self, router: dict) -> dict:
        client = self._rest_client(router)
        try:
            resource = await client.get_system_resource()
            return {
                "reachable": True,
                "api_type": "rest",
                "cpu_load_percent": resource.get("cpu-load"),
                "free_memory_bytes": resource.get("free-memory"),
                "total_memory_bytes": resource.get("total-memory"),
                "uptime_seconds": resource.get("uptime"),
                "board_name": resource.get("board-name"),
                "version": resource.get("version"),
            }
        except MikroTikRestError as exc:
            logger.warning(f"REST health check failed for {router['ip_address']}: {exc}")
            return {"reachable": False, "api_type": "rest", "error": str(exc)}
        finally:
            await self._close_client(client, RouterApiType.REST.value)

    # ------------------------------------------------------------------ #
    # Live data
    # ------------------------------------------------------------------ #
    async def get_interfaces(self, router_id: str) -> List[Dict[str, Any]]:
        """Get router interfaces (legacy or REST)."""
        router = await self._get_raw(router_id)
        client, api_type = await self._resolve_client(router)
        try:
            if api_type == RouterApiType.LEGACY.value:
                await client.connect()
                raw = await client.get_interfaces()
                return [normalize_interface(row) for row in raw]
            return await client.get_interfaces()
        finally:
            await self._close_client(client, api_type)

    async def get_active_users(self, router_id: str) -> Dict[str, Any]:
        """Get active PPPoE and HotSpot users (legacy or REST)."""
        router = await self._get_raw(router_id)
        client, api_type = await self._resolve_client(router)
        try:
            if api_type == RouterApiType.LEGACY.value:
                await client.connect()
                pppoe_raw = await client.get_active_pppoe()
                hotspot_raw = await client.get_active_hotspot()
                return {
                    "api_type": "legacy",
                    "pppoe": normalize_active_pppoe(pppoe_raw),
                    "hotspot": normalize_active_hotspot(hotspot_raw),
                }

            return {
                "api_type": "rest",
                "pppoe": await client.get_active_pppoe(),
                "hotspot": await client.get_active_hotspot(),
            }
        finally:
            await self._close_client(client, api_type)

    async def get_active_hotspot_sessions(self, router_id: str) -> Dict[str, Any]:
        """
        Get ONLY active HotSpot sessions.
        Used by /hotspot/routers/{router_id}/active-sessions.
        """
        router = await self._get_raw(router_id)
        client, api_type = await self._resolve_client(router)
        try:
            if api_type == RouterApiType.LEGACY.value:
                await client.connect()
                hotspot_raw = await client.get_active_hotspot()
                sessions = normalize_active_hotspot(hotspot_raw)
                return {
                    "api_type": "legacy",
                    "router_id": router_id,
                    "count": len(sessions),
                    "sessions": sessions,
                }

            hotspot_raw = await client.get_active_hotspot()
            sessions = hotspot_raw if isinstance(hotspot_raw, list) else []
            return {
                "api_type": "rest",
                "router_id": router_id,
                "count": len(sessions),
                "sessions": sessions,
            }
        finally:
            await self._close_client(client, api_type)

    async def get_dhcp_leases(self, router_id: str) -> List[Dict[str, Any]]:
        """Get DHCP leases (legacy or REST)."""
        router = await self._get_raw(router_id)
        client, api_type = await self._resolve_client(router)
        try:
            if api_type == RouterApiType.LEGACY.value:
                await client.connect()
                raw = await client.get_dhcp_leases()
                return [normalize_dhcp_lease(row) for row in raw]
            return await client.get_dhcp_leases()
        finally:
            await self._close_client(client, api_type)

    async def get_queues(self, router_id: str) -> List[Dict[str, Any]]:
        """Get simple queues (legacy or REST)."""
        router = await self._get_raw(router_id)
        client, api_type = await self._resolve_client(router)
        try:
            if api_type == RouterApiType.LEGACY.value:
                await client.connect()
                raw = await client.get_queues()
                return [normalize_queue(row) for row in raw]
            return await client.get_queues()
        finally:
            await self._close_client(client, api_type)

    # ------------------------------------------------------------------ #
    # PPPoE provisioning
    # ------------------------------------------------------------------ #
    async def push_pppoe_user(
        self,
        router_id: str,
        username: str,
        password: str,
        profile: str = "default",
    ) -> Dict[str, Any]:
        """Push PPPoE user to router (legacy or REST)."""
        router = await self._get_raw(router_id)
        client, api_type = await self._resolve_client(router)
        try:
            if api_type == RouterApiType.LEGACY.value:
                await client.connect()
            await client.add_pppoe_user(username, password, profile)
            return {
                "success": True,
                "username": username,
                "profile": profile,
                "api_type": api_type,
            }
        finally:
            await self._close_client(client, api_type)

    async def disconnect_pppoe_user(self, router_id: str, username: str) -> Dict[str, Any]:
        """Disconnect PPPoE user session (legacy or REST)."""
        router = await self._get_raw(router_id)
        client, api_type = await self._resolve_client(router)
        try:
            if api_type == RouterApiType.LEGACY.value:
                await client.connect()
            result = await client.disconnect_pppoe_session(username)
            return {
                "username": username,
                "disconnected": result,
                "api_type": api_type,
            }
        finally:
            await self._close_client(client, api_type)