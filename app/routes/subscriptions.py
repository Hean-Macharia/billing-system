"""Subscription API routes."""
from typing import Optional

from fastapi import APIRouter, Depends, Request, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.dependencies import get_db, require_permission
from app.core.logging import get_logger
from app.models.user import Permission, UserInDB
from app.schemas.subscription import SubscriptionCreate, SubscriptionUpdate
from app.services.subscription_service import SubscriptionService
from app.utils.helpers import paginated_response, success_response

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1/subscriptions", tags=["Subscriptions"])


def _to_response(sub):
    return {
        "_id": str(sub.id),
        "customer_id": sub.customer_id,
        "customer_code": sub.customer_code,
        "customer_name": sub.customer_name,
        "plan_id": sub.plan_id,
        "plan_code": sub.plan_code,
        "plan_name": sub.plan_name,
        "status": sub.status.value,
        "start_date": sub.start_date.isoformat() if sub.start_date else None,
        "end_date": sub.end_date.isoformat() if sub.end_date else None,
        "next_billing_date": sub.next_billing_date.isoformat() if sub.next_billing_date else None,
        "last_billed_date": sub.last_billed_date.isoformat() if sub.last_billed_date else None,
        "monthly_price_kes": sub.monthly_price_kes,
        "setup_fee_kes": sub.setup_fee_kes,
        "equipment_fee_kes": sub.equipment_fee_kes,
        "discount_kes": sub.discount_kes,
        "contract_months": sub.contract_months,
        "auto_renew": sub.auto_renew,
        "installation_completed": sub.installation_completed,
        "installation_date": sub.installation_date.isoformat() if sub.installation_date else None,
        "ip_address": sub.ip_address,
        "pppoe_username": sub.pppoe_username,
        "data_used_gb": sub.data_used_gb,
        "data_cap_gb": sub.data_cap_gb,
        "total_billed_kes": sub.total_billed_kes,
        "total_paid_kes": sub.total_paid_kes,
        "notes": sub.notes,
        "tags": sub.tags,
        "created_at": sub.created_at.isoformat() if sub.created_at else None,
        "updated_at": sub.updated_at.isoformat() if sub.updated_at else None,
        "created_by": sub.created_by,
        "cancelled_at": sub.cancelled_at.isoformat() if sub.cancelled_at else None,
        "cancellation_reason": sub.cancellation_reason,
    }


@router.post("", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_subscription(
    request: Request, data: SubscriptionCreate,
    current_user: UserInDB = Depends(require_permission(Permission.SUBSCRIPTIONS_CREATE)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    service = SubscriptionService(db)
    sub = await service.create(data, created_by=str(current_user.id))
    return success_response(message="Subscription created successfully", data=_to_response(sub))


@router.get("", response_model=dict)
async def list_subscriptions(
    request: Request, customer_id: Optional[str] = None, plan_id: Optional[str] = None,
    status: Optional[str] = None, page: int = 1, limit: int = 20,
    current_user: UserInDB = Depends(require_permission(Permission.SUBSCRIPTIONS_READ)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    service = SubscriptionService(db)
    subs, total = await service.list_subscriptions(customer_id=customer_id, plan_id=plan_id, status=status, page=page, limit=limit)
    return paginated_response(data=[_to_response(s) for s in subs], total=total, page=page, limit=limit, message="Subscriptions retrieved")


@router.get("/{sub_id}", response_model=dict)
async def get_subscription(
    request: Request, sub_id: str,
    current_user: UserInDB = Depends(require_permission(Permission.SUBSCRIPTIONS_READ)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    service = SubscriptionService(db)
    sub = await service.get_by_id(sub_id)
    return success_response(message="Subscription retrieved", data=_to_response(sub))


@router.patch("/{sub_id}", response_model=dict)
async def update_subscription(
    request: Request, sub_id: str, data: SubscriptionUpdate,
    current_user: UserInDB = Depends(require_permission(Permission.SUBSCRIPTIONS_UPDATE)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    service = SubscriptionService(db)
    sub = await service.update(sub_id, data)
    return success_response(message="Subscription updated", data=_to_response(sub))


@router.post("/{sub_id}/cancel", response_model=dict)
async def cancel_subscription(
    request: Request, sub_id: str, reason: Optional[str] = None,
    current_user: UserInDB = Depends(require_permission(Permission.SUBSCRIPTIONS_UPDATE)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    service = SubscriptionService(db)
    sub = await service.cancel(sub_id, reason=reason)
    return success_response(message="Subscription cancelled", data=_to_response(sub))


@router.post("/{sub_id}/install", response_model=dict)
async def mark_installed(
    request: Request, sub_id: str,
    current_user: UserInDB = Depends(require_permission(Permission.SUBSCRIPTIONS_UPDATE)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    service = SubscriptionService(db)
    sub = await service.mark_installed(sub_id, technician_id=str(current_user.id))
    return success_response(message="Installation completed", data=_to_response(sub))


@router.post("/{sub_id}/invoice", response_model=dict)
async def generate_invoice(
    request: Request, sub_id: str,
    current_user: UserInDB = Depends(require_permission(Permission.INVOICES_CREATE)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    from app.services.invoice_service import InvoiceService
    invoice_service = InvoiceService(db)
    invoice = await invoice_service.generate_from_subscription(sub_id, created_by=str(current_user.id))
    return success_response(
        message="Invoice generated successfully",
        data={"_id": str(invoice.id), "invoice_number": invoice.invoice_number, "total_kes": invoice.total_kes, "status": invoice.status.value},
    )