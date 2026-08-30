"""RADIUS admin API routes.

Manage NAS clients, RADIUS users, and view sessions.
"""
from typing import Optional
from app.core.dependencies import get_db

from fastapi import APIRouter, Depends, Request, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.dependencies import get_db, require_permission
from app.core.logging import get_logger
from app.models.user import Permission, UserInDB
from app.schemas.radius import (
    NasClientCreate, NasClientUpdate, NasClientResponse,
    RadiusUserCreate, RadiusUserUpdate, RadiusUserResponse,
    RadiusSessionResponse, RadiusAccountingResponse,
)
from app.services.radius_admin_service import RadiusAdminService
from app.utils.helpers import paginated_response, success_response

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1/radius", tags=["RADIUS Admin"])


def _nas_to_response(nas) -> dict:
    return {
        "_id": str(nas.id),
        "name": nas.name,
        "site_id": nas.site_id,
        "ip_address": nas.ip_address,
        "description": nas.description,
        "location": nas.location,
        "nas_type": nas.nas_type.value,
        "status": nas.status,
        "coa_port": nas.coa_port,
        "last_seen": nas.last_seen.isoformat() if nas.last_seen else None,
        "created_at": nas.created_at.isoformat() if nas.created_at else None,
        "updated_at": nas.updated_at.isoformat() if nas.updated_at else None,
    }


def _user_to_response(user) -> dict:
    return {
        "_id": str(user.id),
        "username": user.username,
        "user_type": user.user_type.value,
        "customer_id": user.customer_id,
        "service_id": user.service_id,
        "subscription_id": user.subscription_id,
        "site_id": user.site_id,
        "package_id": user.package_id,
        "framed_ip_address": user.framed_ip_address,
        "framed_ip_pool": user.framed_ip_pool,
        "session_timeout": user.session_timeout,
        "idle_timeout": user.idle_timeout,
        "simultaneous_use": user.simultaneous_use,
        "rate_limit": user.rate_limit,
        "status": user.status,
        "last_login": user.last_login.isoformat() if user.last_login else None,
        "total_sessions": user.total_sessions,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "updated_at": user.updated_at.isoformat() if user.updated_at else None,
    }


# ── NAS Clients ──

@router.post("/nas", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_nas(
    request: Request,
    data: NasClientCreate,
    current_user: UserInDB = Depends(require_permission(Permission.RADIUS_MANAGE)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    service = RadiusAdminService(db)
    nas = await service.create_nas(data)
    return success_response(message="NAS client created", data=_nas_to_response(nas), status_code=201)


@router.get("/nas", response_model=dict)
async def list_nas(
    request: Request,
    site_id: Optional[str] = None,
    status: Optional[str] = None,
    page: int = 1,
    limit: int = 20,
    current_user: UserInDB = Depends(require_permission(Permission.RADIUS_READ)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    service = RadiusAdminService(db)
    clients, total = await service.list_nas(site_id=site_id, status=status, page=page, limit=limit)
    return paginated_response(data=[_nas_to_response(c) for c in clients], total=total, page=page, limit=limit)


@router.get("/nas/{nas_id}", response_model=dict)
async def get_nas(
    request: Request,
    nas_id: str,
    current_user: UserInDB = Depends(require_permission(Permission.RADIUS_READ)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    service = RadiusAdminService(db)
    nas = await service.get_nas(nas_id)
    return success_response(message="NAS client retrieved", data=_nas_to_response(nas))


@router.patch("/nas/{nas_id}", response_model=dict)
async def update_nas(
    request: Request,
    nas_id: str,
    data: NasClientUpdate,
    current_user: UserInDB = Depends(require_permission(Permission.RADIUS_MANAGE)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    service = RadiusAdminService(db)
    nas = await service.update_nas(nas_id, data)
    return success_response(message="NAS client updated", data=_nas_to_response(nas))


@router.delete("/nas/{nas_id}", response_model=dict)
async def delete_nas(
    request: Request,
    nas_id: str,
    current_user: UserInDB = Depends(require_permission(Permission.RADIUS_MANAGE)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    service = RadiusAdminService(db)
    await service.delete_nas(nas_id)
    return success_response(message="NAS client deleted")


# ── RADIUS Users ──

@router.post("/users", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_radius_user(
    request: Request,
    data: RadiusUserCreate,
    current_user: UserInDB = Depends(require_permission(Permission.RADIUS_MANAGE)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    service = RadiusAdminService(db)
    user = await service.create_user(data)
    return success_response(message="RADIUS user created", data=_user_to_response(user), status_code=201)


@router.get("/users", response_model=dict)
async def list_radius_users(
    request: Request,
    customer_id: Optional[str] = None,
    site_id: Optional[str] = None,
    user_type: Optional[str] = None,
    status: Optional[str] = None,
    page: int = 1,
    limit: int = 20,
    current_user: UserInDB = Depends(require_permission(Permission.RADIUS_READ)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    service = RadiusAdminService(db)
    users, total = await service.list_users(
        customer_id=customer_id, site_id=site_id, user_type=user_type, status=status, page=page, limit=limit
    )
    return paginated_response(data=[_user_to_response(u) for u in users], total=total, page=page, limit=limit)


@router.get("/users/{user_id}", response_model=dict)
async def get_radius_user(
    request: Request,
    user_id: str,
    current_user: UserInDB = Depends(require_permission(Permission.RADIUS_READ)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    service = RadiusAdminService(db)
    user = await service.get_user(user_id)
    return success_response(message="RADIUS user retrieved", data=_user_to_response(user))


@router.patch("/users/{user_id}", response_model=dict)
async def update_radius_user(
    request: Request,
    user_id: str,
    data: RadiusUserUpdate,
    current_user: UserInDB = Depends(require_permission(Permission.RADIUS_MANAGE)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    service = RadiusAdminService(db)
    user = await service.update_user(user_id, data)
    return success_response(message="RADIUS user updated", data=_user_to_response(user))


@router.delete("/users/{user_id}", response_model=dict)
async def delete_radius_user(
    request: Request,
    user_id: str,
    current_user: UserInDB = Depends(require_permission(Permission.RADIUS_MANAGE)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    service = RadiusAdminService(db)
    await service.delete_user(user_id)
    return success_response(message="RADIUS user deleted")


@router.post("/users/sync/{subscription_id}", response_model=dict)
async def sync_user_from_subscription(
    request: Request,
    subscription_id: str,
    current_user: UserInDB = Depends(require_permission(Permission.RADIUS_MANAGE)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Auto-create RADIUS user from an active subscription."""
    service = RadiusAdminService(db)
    user = await service.sync_user_from_subscription(subscription_id)
    return success_response(message="RADIUS user synced from subscription", data=_user_to_response(user))