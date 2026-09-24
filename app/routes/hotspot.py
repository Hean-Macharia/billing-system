"""HotSpot plan (profile) API routes."""
from typing import Optional

from fastapi import APIRouter, Depends, Request
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.dependencies import get_db, require_permission
from app.core.logging import get_logger
from app.models.user import Permission, UserInDB
from app.schemas.hotspot import HotspotPlanCreate, HotspotPlanUpdate
from app.services.hotspot_service import HotspotService
from app.utils.helpers import success_response

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1/hotspot", tags=["HotSpot"])


def _plan_to_response(p) -> dict:
    return {
        "_id": str(p.id),
        "name": p.name,
        "site_id": p.site_id,
        "duration_hours": p.duration_hours,
        "data_allowance_mb": p.data_allowance_mb,
        "rate_limit": p.rate_limit,
        "price": p.price,
        "currency": p.currency,
        "description": p.description,
        "is_active": p.is_active,
        "sort_order": p.sort_order,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


# ── Plans ──

@router.post("/plans", response_model=dict, status_code=201)
async def create_hotspot_plan(
    request: Request,
    data: HotspotPlanCreate,
    current_user: UserInDB = Depends(require_permission(Permission.VOUCHERS_CREATE)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    service = HotspotService(db)
    plan = await service.create_plan(data)
    return success_response(message="HotSpot plan created", data=_plan_to_response(plan), status_code=201)


@router.get("/plans", response_model=dict)
async def list_hotspot_plans(
    request: Request,
    site_id: Optional[str] = None,
    active_only: bool = False,
    current_user: UserInDB = Depends(require_permission(Permission.VOUCHERS_READ)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    service = HotspotService(db)
    plans = await service.list_plans(site_id=site_id, active_only=active_only)
    return success_response(message="HotSpot plans retrieved", data=[_plan_to_response(p) for p in plans])


@router.get("/plans/public", response_model=dict)
async def list_public_hotspot_plans(
    request: Request,
    site_id: Optional[str] = None,
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """No-auth listing of active plans - what a captive-portal splash page
    shows a guest before they buy/redeem a voucher."""
    service = HotspotService(db)
    plans = await service.list_plans(site_id=site_id, active_only=True)
    return success_response(
        message="Available HotSpot plans",
        data=[
            {
                "name": p.name,
                "duration_hours": p.duration_hours,
                "data_allowance_mb": p.data_allowance_mb,
                "price": p.price,
                "currency": p.currency,
                "description": p.description,
            }
            for p in plans
        ],
    )


@router.get("/plans/{plan_id}", response_model=dict)
async def get_hotspot_plan(
    request: Request,
    plan_id: str,
    current_user: UserInDB = Depends(require_permission(Permission.VOUCHERS_READ)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    service = HotspotService(db)
    plan = await service.get_plan(plan_id)
    return success_response(message="HotSpot plan retrieved", data=_plan_to_response(plan))


@router.patch("/plans/{plan_id}", response_model=dict)
async def update_hotspot_plan(
    request: Request,
    plan_id: str,
    data: HotspotPlanUpdate,
    current_user: UserInDB = Depends(require_permission(Permission.VOUCHERS_UPDATE)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    service = HotspotService(db)
    plan = await service.update_plan(plan_id, data)
    return success_response(message="HotSpot plan updated", data=_plan_to_response(plan))


@router.delete("/plans/{plan_id}", response_model=dict)
async def delete_hotspot_plan(
    request: Request,
    plan_id: str,
    current_user: UserInDB = Depends(require_permission(Permission.VOUCHERS_DELETE)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    service = HotspotService(db)
    await service.delete_plan(plan_id)
    return success_response(message="HotSpot plan deleted")


# ── Live sessions enriched with voucher info ──

@router.get("/routers/{router_id}/active-sessions", response_model=dict)
async def get_hotspot_active_sessions(
    request: Request,
    router_id: str,
    current_user: UserInDB = Depends(require_permission(Permission.ROUTERS_READ)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Live /ip/hotspot/active sessions from the router (Phase 7), each
    enriched with the voucher record behind it (status, expiry, data cap)."""
    service = HotspotService(db)
    sessions = await service.get_active_sessions_with_vouchers(router_id)
    return success_response(message="Active HotSpot sessions retrieved", data=sessions)
