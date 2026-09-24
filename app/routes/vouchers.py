"""Voucher (HotSpot prepaid code) API routes."""
from typing import Optional

from fastapi import APIRouter, Depends, Request, Response, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.dependencies import get_db, require_permission
from app.core.logging import get_logger
from app.models.user import Permission, UserInDB
from app.schemas.voucher import VoucherActivateRequest, VoucherBatchCreate, VoucherDisableRequest
from app.services.voucher_service import VoucherService
from app.utils.helpers import paginated_response, success_response

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1/vouchers", tags=["Vouchers"])


def _voucher_to_response(v) -> dict:
    return {
        "_id": str(v.id),
        "batch_id": v.batch_id,
        "voucher_code": v.voucher_code,
        "status": v.status.value if hasattr(v.status, "value") else v.status,
        "site_id": v.site_id,
        "router_id": v.router_id,
        "duration_hours": v.duration_hours,
        "data_allowance_mb": v.data_allowance_mb,
        "rate_limit": v.rate_limit,
        "price": v.price,
        "currency": v.currency,
        "expiry_date": v.expiry_date.isoformat() if v.expiry_date else None,
        "activated_at": v.activated_at.isoformat() if v.activated_at else None,
        "used_at": v.used_at.isoformat() if v.used_at else None,
        "printed": v.printed,
        "created_at": v.created_at.isoformat() if v.created_at else None,
        "updated_at": v.updated_at.isoformat() if v.updated_at else None,
    }


def _batch_to_response(b) -> dict:
    return {
        "_id": str(b.id),
        "batch_name": b.batch_name,
        "site_id": b.site_id,
        "router_id": b.router_id,
        "quantity": b.quantity,
        "duration_hours": b.duration_hours,
        "data_allowance_mb": b.data_allowance_mb,
        "rate_limit": b.rate_limit,
        "price": b.price,
        "currency": b.currency,
        "activate_on_generation": b.activate_on_generation,
        "generated_count": b.generated_count,
        "activated_count": b.activated_count,
        "used_count": b.used_count,
        "created_at": b.created_at.isoformat() if b.created_at else None,
        "updated_at": b.updated_at.isoformat() if b.updated_at else None,
    }


# ── Public (no auth) - for a captive-portal splash page ──

@router.get("/public/check/{code}", response_model=dict)
async def public_check_voucher(
    request: Request,
    code: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Read-only validity check a HotSpot splash page can call before
    submitting the code to the router's login form. Does not consume the
    voucher - only app.services.radius_auth_service marks it 'used', at
    actual RADIUS authentication time."""
    service = VoucherService(db)
    result = await service.check_code(code)
    return success_response(message="Voucher checked", data=result)


# ── Batches ──

@router.post("/batches", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_voucher_batch(
    request: Request,
    data: VoucherBatchCreate,
    current_user: UserInDB = Depends(require_permission(Permission.VOUCHERS_CREATE)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    service = VoucherService(db)
    batch = await service.create_batch(data, created_by=str(current_user.id))
    return success_response(message="Voucher batch generated", data=_batch_to_response(batch), status_code=201)


@router.get("/batches", response_model=dict)
async def list_voucher_batches(
    request: Request,
    site_id: Optional[str] = None,
    page: int = 1,
    limit: int = 20,
    current_user: UserInDB = Depends(require_permission(Permission.VOUCHERS_READ)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    service = VoucherService(db)
    batches, total = await service.list_batches(site_id=site_id, page=page, limit=limit)
    return paginated_response(data=[_batch_to_response(b) for b in batches], total=total, page=page, limit=limit)


@router.get("/batches/{batch_id}", response_model=dict)
async def get_voucher_batch(
    request: Request,
    batch_id: str,
    current_user: UserInDB = Depends(require_permission(Permission.VOUCHERS_READ)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    service = VoucherService(db)
    batch = await service.get_batch(batch_id)
    return success_response(message="Voucher batch retrieved", data=_batch_to_response(batch))


@router.post("/batches/{batch_id}/activate", response_model=dict)
async def activate_voucher_batch(
    request: Request,
    batch_id: str,
    data: VoucherActivateRequest,
    current_user: UserInDB = Depends(require_permission(Permission.VOUCHERS_UPDATE)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Activates every 'generated' voucher in the batch, or only
    data.voucher_ids if provided (e.g. activating a single sold card)."""
    service = VoucherService(db)
    result = await service.activate_batch(batch_id, voucher_ids=data.voucher_ids, activated_by=str(current_user.id))
    return success_response(message="Batch activation complete", data=result)


@router.get("/batches/{batch_id}/export")
async def export_voucher_batch_csv(
    request: Request,
    batch_id: str,
    current_user: UserInDB = Depends(require_permission(Permission.VOUCHERS_READ)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    service = VoucherService(db)
    csv_text = await service.export_batch_csv(batch_id)
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="voucher_batch_{batch_id}.csv"'},
    )


@router.get("/batches/{batch_id}/print")
async def print_voucher_batch_pdf(
    request: Request,
    batch_id: str,
    org_name: str = "ISP Billing",
    current_user: UserInDB = Depends(require_permission(Permission.VOUCHERS_READ)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Printable voucher cards, 3x8 per A4 page, ready to cut and sell."""
    service = VoucherService(db)
    pdf_bytes = await service.generate_batch_pdf(batch_id, org_name=org_name)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="vouchers_{batch_id}.pdf"'},
    )


# ── Individual vouchers ──

@router.get("", response_model=dict)
async def list_vouchers(
    request: Request,
    batch_id: Optional[str] = None,
    status_filter: Optional[str] = None,
    site_id: Optional[str] = None,
    page: int = 1,
    limit: int = 50,
    current_user: UserInDB = Depends(require_permission(Permission.VOUCHERS_READ)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    service = VoucherService(db)
    vouchers, total = await service.list_vouchers(batch_id=batch_id, status=status_filter, site_id=site_id, page=page, limit=limit)
    return paginated_response(data=[_voucher_to_response(v) for v in vouchers], total=total, page=page, limit=limit)


@router.get("/{voucher_id}", response_model=dict)
async def get_voucher(
    request: Request,
    voucher_id: str,
    current_user: UserInDB = Depends(require_permission(Permission.VOUCHERS_READ)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    service = VoucherService(db)
    voucher = await service.get_voucher(voucher_id)
    return success_response(message="Voucher retrieved", data=_voucher_to_response(voucher))


@router.post("/{voucher_id}/activate", response_model=dict)
async def activate_voucher(
    request: Request,
    voucher_id: str,
    current_user: UserInDB = Depends(require_permission(Permission.VOUCHERS_UPDATE)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    service = VoucherService(db)
    voucher = await service.activate_voucher(voucher_id, activated_by=str(current_user.id))
    return success_response(message="Voucher activated", data=_voucher_to_response(voucher))


@router.post("/{voucher_id}/disable", response_model=dict)
async def disable_voucher(
    request: Request,
    voucher_id: str,
    data: VoucherDisableRequest,
    current_user: UserInDB = Depends(require_permission(Permission.VOUCHERS_UPDATE)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    service = VoucherService(db)
    voucher = await service.disable_voucher(voucher_id, reason=data.reason)
    return success_response(message="Voucher disabled", data=_voucher_to_response(voucher))


# ── Expiry ──

@router.post("/expire-sweep", response_model=dict)
async def expire_sweep(
    request: Request,
    current_user: UserInDB = Depends(require_permission(Permission.VOUCHERS_UPDATE)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Marks any ACTIVE/GENERATED voucher past its expiry_date as EXPIRED.
    Intended to be hit by a scheduled job (cron/APScheduler) every few
    minutes, same pattern as Phase 5's /mpesa/reconcile."""
    service = VoucherService(db)
    result = await service.expire_sweep()
    return success_response(message="Expiry sweep complete", data=result)
