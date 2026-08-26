"""Service Plan API routes."""
from typing import Optional

from fastapi import APIRouter, Depends, Request, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.dependencies import get_db, require_permission
from app.core.logging import get_logger
from app.models.user import Permission, UserInDB
from app.schemas.service import ServicePlanCreate, ServicePlanUpdate
from app.services.service_plan_service import ServicePlanService
from app.utils.helpers import paginated_response, success_response

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1/services", tags=["Service Plans"])


def _to_response(plan):
    return {
        "_id": str(plan.id),
        "plan_code": plan.plan_code,
        "name": plan.name,
        "description": plan.description,
        "service_type": plan.service_type.value,
        "status": plan.status.value,
        "download_speed_mbps": plan.download_speed_mbps,
        "upload_speed_mbps": plan.upload_speed_mbps,
        "burst_speed_mbps": plan.burst_speed_mbps,
        "base_price_kes": plan.base_price_kes,
        "setup_fee_kes": plan.setup_fee_kes,
        "equipment_fee_kes": plan.equipment_fee_kes,
        "billing_cycle": plan.billing_cycle.value,
        "features": [f.model_dump() for f in plan.features] if plan.features else [],
        "fair_usage_policy": plan.fair_usage_policy,
        "data_cap_gb": plan.data_cap_gb,
        "minimum_contract_months": plan.minimum_contract_months,
        "early_termination_fee_kes": plan.early_termination_fee_kes,
        "grace_period_days": plan.grace_period_days,
        "target_customer_types": plan.target_customer_types,
        "tags": plan.tags,
        "popularity_score": plan.popularity_score,
        "created_at": plan.created_at.isoformat() if plan.created_at else None,
        "updated_at": plan.updated_at.isoformat() if plan.updated_at else None,
        "created_by": plan.created_by,
    }


@router.post("", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_plan(
    request: Request, data: ServicePlanCreate,
    current_user: UserInDB = Depends(require_permission(Permission.SERVICES_CREATE)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    service = ServicePlanService(db)
    plan = await service.create(data, created_by=str(current_user.id))
    return success_response(message="Service plan created successfully", data=_to_response(plan))


@router.get("", response_model=dict)
async def list_plans(
    request: Request, status: Optional[str] = None, service_type: Optional[str] = None,
    search: Optional[str] = None, page: int = 1, limit: int = 20,
    current_user: UserInDB = Depends(require_permission(Permission.SERVICES_READ)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    service = ServicePlanService(db)
    plans, total = await service.list_plans(status=status, service_type=service_type, search=search, page=page, limit=limit)
    return paginated_response(data=[_to_response(p) for p in plans], total=total, page=page, limit=limit, message="Service plans retrieved")


@router.get("/{plan_id}", response_model=dict)
async def get_plan(
    request: Request, plan_id: str,
    current_user: UserInDB = Depends(require_permission(Permission.SERVICES_READ)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    service = ServicePlanService(db)
    plan = await service.get_by_id(plan_id)
    return success_response(message="Service plan retrieved", data=_to_response(plan))


@router.patch("/{plan_id}", response_model=dict)
async def update_plan(
    request: Request, plan_id: str, data: ServicePlanUpdate,
    current_user: UserInDB = Depends(require_permission(Permission.SERVICES_UPDATE)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    service = ServicePlanService(db)
    plan = await service.update(plan_id, data)
    return success_response(message="Service plan updated", data=_to_response(plan))


@router.delete("/{plan_id}", response_model=dict)
async def delete_plan(
    request: Request, plan_id: str,
    current_user: UserInDB = Depends(require_permission(Permission.SERVICES_DELETE)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    service = ServicePlanService(db)
    await service.delete(plan_id)
    return success_response(message="Service plan deprecated")