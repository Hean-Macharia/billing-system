"""Router (MikroTik) management API routes."""
from typing import Optional

from fastapi import APIRouter, Depends, Request, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.dependencies import get_db, require_permission
from app.core.logging import get_logger
from app.models.user import Permission, UserInDB
from app.schemas.router import RouterCreate, RouterUpdate
from app.services.router_service import RouterService
from app.utils.helpers import paginated_response, success_response

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1/routers", tags=["Routers"])


def _router_to_response(r: dict) -> dict:
    def _isoformat(value):
        return value.isoformat() if hasattr(value, "isoformat") else value

    return {
        "_id": str(r.get("_id")),
        "name": r.get("name"),
        "site_id": r.get("site_id"),
        "nas_client_id": r.get("nas_client_id"),
        "ip_address": r.get("ip_address"),
        "api_type": r.get("api_type").value if hasattr(r.get("api_type"), "value") else r.get("api_type"),
        "port": r.get("port"),
        "username": r.get("username"),
        "use_ssl": r.get("use_ssl"),
        "ssl_verify": r.get("ssl_verify"),
        "model_name": r.get("model_name"),
        "routeros_version": r.get("routeros_version"),
        "wan_interface": r.get("wan_interface"),
        "lan_interface": r.get("lan_interface"),
        "pppoe_server_interface": r.get("pppoe_server_interface"),
        "hotspot_interface": r.get("hotspot_interface"),
        "ip_pools": r.get("ip_pools"),
        "radius_server_ip": r.get("radius_server_ip"),
        "status": r.get("status").value if hasattr(r.get("status"), "value") else r.get("status"),
        "last_health": r.get("last_health"),
        "last_checked_at": _isoformat(r.get("last_checked_at")),
        "location": r.get("location"),
        "notes": r.get("notes"),
        "created_at": _isoformat(r.get("created_at")),
        "updated_at": _isoformat(r.get("updated_at")),
        # password / radius_secret intentionally never returned
    }


# ── CRUD ──

@router.post("", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_router(
    request: Request,
    data: RouterCreate,
    current_user: UserInDB = Depends(require_permission(Permission.ROUTERS_CREATE)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    service = RouterService(db)
    r = await service.create_router(data)
    return success_response(message="Router registered", data=_router_to_response(r), status_code=201)


@router.get("", response_model=dict)
async def list_routers(
    request: Request,
    site_id: Optional[str] = None,
    status: Optional[str] = None,
    page: int = 1,
    limit: int = 20,
    current_user: UserInDB = Depends(require_permission(Permission.ROUTERS_READ)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    service = RouterService(db)
    items, total = await service.list_routers(site_id=site_id, status=status, page=page, limit=limit)
    return paginated_response(data=[_router_to_response(r) for r in items], total=total, page=page, limit=limit)


@router.get("/{router_id}", response_model=dict)
async def get_router(
    request: Request,
    router_id: str,
    current_user: UserInDB = Depends(require_permission(Permission.ROUTERS_READ)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    service = RouterService(db)
    r = await service.get_router(router_id)
    return success_response(message="Router retrieved", data=_router_to_response(r))


@router.patch("/{router_id}", response_model=dict)
async def update_router(
    request: Request,
    router_id: str,
    data: RouterUpdate,
    current_user: UserInDB = Depends(require_permission(Permission.ROUTERS_UPDATE)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    service = RouterService(db)
    r = await service.update_router(router_id, data)
    return success_response(message="Router updated", data=_router_to_response(r))


@router.delete("/{router_id}", response_model=dict)
async def delete_router(
    request: Request,
    router_id: str,
    current_user: UserInDB = Depends(require_permission(Permission.ROUTERS_DELETE)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    service = RouterService(db)
    await service.delete_router(router_id)
    return success_response(message="Router deleted")


# ── Connectivity & Health ──

@router.post("/{router_id}/test", response_model=dict)
async def test_router_connectivity(
    request: Request,
    router_id: str,
    current_user: UserInDB = Depends(require_permission(Permission.ROUTERS_READ)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    service = RouterService(db)
    result = await service.test_connectivity(router_id)
    return success_response(message="Connectivity test complete", data=result)


@router.post("/{router_id}/health", response_model=dict)
async def refresh_router_health(
    request: Request,
    router_id: str,
    current_user: UserInDB = Depends(require_permission(Permission.ROUTERS_READ)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    service = RouterService(db)
    health = await service.refresh_health(router_id)
    return success_response(message="Health refreshed", data=health)


@router.get("/{router_id}/health", response_model=dict)
async def get_cached_router_health(
    request: Request,
    router_id: str,
    current_user: UserInDB = Depends(require_permission(Permission.ROUTERS_READ)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    service = RouterService(db)
    r = await service.get_router(router_id)
    return success_response(
        message="Cached health retrieved",
        data={"router_id": router_id, "health": r.last_health, "last_checked_at": r.last_checked_at},
    )


@router.post("/health/refresh-all", response_model=dict)
async def refresh_all_routers_health(
    request: Request,
    current_user: UserInDB = Depends(require_permission(Permission.ROUTERS_READ)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    service = RouterService(db)
    summary = await service.refresh_all_health()
    return success_response(message="Bulk health refresh complete", data=summary)


# ── Live data from router ──

@router.get("/{router_id}/interfaces", response_model=dict)
async def get_router_interfaces(
    request: Request,
    router_id: str,
    current_user: UserInDB = Depends(require_permission(Permission.ROUTERS_READ)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    service = RouterService(db)
    interfaces = await service.get_interfaces(router_id)
    return success_response(message="Interfaces retrieved", data=interfaces)


@router.get("/{router_id}/active-users", response_model=dict)
async def get_router_active_users(
    request: Request,
    router_id: str,
    current_user: UserInDB = Depends(require_permission(Permission.ROUTERS_READ)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    service = RouterService(db)
    users = await service.get_active_users(router_id)
    return success_response(message="Active users retrieved", data=users)


@router.get("/{router_id}/dhcp-leases", response_model=dict)
async def get_router_dhcp_leases(
    request: Request,
    router_id: str,
    current_user: UserInDB = Depends(require_permission(Permission.ROUTERS_READ)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    service = RouterService(db)
    leases = await service.get_dhcp_leases(router_id)
    return success_response(message="DHCP leases retrieved", data=leases)


@router.get("/{router_id}/queues", response_model=dict)
async def get_router_queues(
    request: Request,
    router_id: str,
    current_user: UserInDB = Depends(require_permission(Permission.ROUTERS_READ)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    service = RouterService(db)
    queues = await service.get_queues(router_id)
    return success_response(message="Queues retrieved", data=queues)


# ── PPPoE provisioning ──

@router.post("/{router_id}/pppoe-users", response_model=dict, status_code=status.HTTP_201_CREATED)
async def push_pppoe_user(
    request: Request,
    router_id: str,
    username: str,
    password: str,
    profile: str = "default",
    current_user: UserInDB = Depends(require_permission(Permission.ROUTERS_UPDATE)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    service = RouterService(db)
    await service.push_pppoe_user(router_id, username, password, profile)
    return success_response(message="PPPoE user pushed to router", data={"username": username, "profile": profile}, status_code=201)


@router.post("/{router_id}/pppoe-users/{username}/disconnect", response_model=dict)
async def disconnect_pppoe_user(
    request: Request,
    router_id: str,
    username: str,
    current_user: UserInDB = Depends(require_permission(Permission.ROUTERS_UPDATE)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    service = RouterService(db)
    disconnected = await service.disconnect_pppoe_user(router_id, username)
    return success_response(message="Disconnect requested", data={"username": username, "disconnected": disconnected})
