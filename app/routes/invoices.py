"""Invoice API routes."""
from typing import Optional

from fastapi import APIRouter, Depends, Request, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.dependencies import get_db, require_permission
from app.core.logging import get_logger
from app.models.user import Permission, UserInDB
from app.schemas.invoice import InvoiceCreate, InvoiceUpdate
from app.services.invoice_service import InvoiceService
from app.utils.helpers import paginated_response, success_response

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1/invoices", tags=["Invoices"])


def _to_response(inv):
    return {
        "_id": str(inv.id),
        "invoice_number": inv.invoice_number,
        "customer_id": inv.customer_id,
        "customer_code": inv.customer_code,
        "customer_name": inv.customer_name,
        "subscription_id": inv.subscription_id,
        "invoice_date": inv.invoice_date.isoformat() if inv.invoice_date else None,
        "due_date": inv.due_date.isoformat() if inv.due_date else None,
        "paid_date": inv.paid_date.isoformat() if inv.paid_date else None,
        "sent_date": inv.sent_date.isoformat() if inv.sent_date else None,
        "status": inv.status.value,
        "line_items": [item.model_dump() for item in inv.line_items] if inv.line_items else [],
        "subtotal_kes": inv.subtotal_kes,
        "tax_rate_percent": inv.tax_rate_percent,
        "tax_amount_kes": inv.tax_amount_kes,
        "discount_kes": inv.discount_kes,
        "total_kes": inv.total_kes,
        "amount_paid_kes": inv.amount_paid_kes,
        "balance_due_kes": inv.balance_due_kes,
        "payment_ids": inv.payment_ids,
        "notes": inv.notes,
        "terms": inv.terms,
        "created_by": inv.created_by,
        "created_at": inv.created_at.isoformat() if inv.created_at else None,
        "updated_at": inv.updated_at.isoformat() if inv.updated_at else None,
        "email_sent": inv.email_sent,
        "sms_sent": inv.sms_sent,
    }


@router.post("", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_invoice(
    request: Request, data: InvoiceCreate,
    current_user: UserInDB = Depends(require_permission(Permission.INVOICES_CREATE)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    service = InvoiceService(db)
    invoice = await service.create(data, created_by=str(current_user.id))
    return success_response(message="Invoice created successfully", data=_to_response(invoice))


@router.get("", response_model=dict)
async def list_invoices(
    request: Request, customer_id: Optional[str] = None, status: Optional[str] = None,
    overdue_only: bool = False, page: int = 1, limit: int = 20,
    current_user: UserInDB = Depends(require_permission(Permission.INVOICES_READ)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    service = InvoiceService(db)
    invoices, total = await service.list_invoices(customer_id=customer_id, status=status, overdue_only=overdue_only, page=page, limit=limit)
    return paginated_response(data=[_to_response(i) for i in invoices], total=total, page=page, limit=limit, message="Invoices retrieved")


@router.get("/overdue", response_model=dict)
async def get_overdue_invoices(
    request: Request,
    current_user: UserInDB = Depends(require_permission(Permission.INVOICES_READ)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    service = InvoiceService(db)
    invoices = await service.get_overdue_invoices()
    return success_response(message="Overdue invoices retrieved", data=[_to_response(i) for i in invoices])


@router.get("/{invoice_id}", response_model=dict)
async def get_invoice(
    request: Request, invoice_id: str,
    current_user: UserInDB = Depends(require_permission(Permission.INVOICES_READ)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    service = InvoiceService(db)
    invoice = await service.get_by_id(invoice_id)
    return success_response(message="Invoice retrieved", data=_to_response(invoice))


@router.patch("/{invoice_id}", response_model=dict)
async def update_invoice(
    request: Request, invoice_id: str, data: InvoiceUpdate,
    current_user: UserInDB = Depends(require_permission(Permission.INVOICES_UPDATE)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    service = InvoiceService(db)
    invoice = await service.update(invoice_id, data)
    return success_response(message="Invoice updated", data=_to_response(invoice))


@router.post("/{invoice_id}/send", response_model=dict)
async def send_invoice(
    request: Request, invoice_id: str,
    current_user: UserInDB = Depends(require_permission(Permission.INVOICES_UPDATE)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    service = InvoiceService(db)
    invoice = await service.mark_sent(invoice_id, sent_by=str(current_user.id))
    return success_response(message="Invoice marked as sent", data=_to_response(invoice))