"""Payment API routes."""
from typing import Optional

from fastapi import APIRouter, Depends, Request, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.dependencies import get_db, require_permission
from app.core.logging import get_logger
from app.models.user import Permission, UserInDB
from app.schemas.payment import PaymentCreate, PaymentUpdate
from app.services.payment_service import PaymentService
from app.utils.helpers import paginated_response, success_response

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1/payments", tags=["Payments"])


def _to_response(pay):
    return {
        "_id": str(pay.id),
        "transaction_id": pay.transaction_id,
        "customer_id": pay.customer_id,
        "customer_code": pay.customer_code,
        "customer_name": pay.customer_name,
        "invoice_id": pay.invoice_id,
        "invoice_number": pay.invoice_number,
        "subscription_id": pay.subscription_id,
        "amount_kes": pay.amount_kes,
        "currency": pay.currency,
        "payment_method": pay.payment_method.value,
        "payment_method_details": pay.payment_method_details,
        "status": pay.status.value,
        "mpesa_receipt_number": pay.mpesa_receipt_number,
        "mpesa_phone_number": pay.mpesa_phone_number,
        "bank_reference": pay.bank_reference,
        "bank_name": pay.bank_name,
        "received_by": pay.received_by,
        "receipt_number": pay.receipt_number,
        "payment_date": pay.payment_date.isoformat() if pay.payment_date else None,
        "processed_date": pay.processed_date.isoformat() if pay.processed_date else None,
        "confirmed_date": pay.confirmed_date.isoformat() if pay.confirmed_date else None,
        "reconciled": pay.reconciled,
        "reconciled_by": pay.reconciled_by,
        "notes": pay.notes,
        "created_at": pay.created_at.isoformat() if pay.created_at else None,
        "updated_at": pay.updated_at.isoformat() if pay.updated_at else None,
        "created_by": pay.created_by,
    }


@router.post("", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_payment(
    request: Request, data: PaymentCreate,
    current_user: UserInDB = Depends(require_permission(Permission.PAYMENTS_CREATE)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    service = PaymentService(db)
    payment = await service.create(data, created_by=str(current_user.id))
    return success_response(message="Payment recorded successfully", data=_to_response(payment))


@router.get("", response_model=dict)
async def list_payments(
    request: Request, customer_id: Optional[str] = None, invoice_id: Optional[str] = None,
    status: Optional[str] = None, payment_method: Optional[str] = None,
    page: int = 1, limit: int = 20,
    current_user: UserInDB = Depends(require_permission(Permission.PAYMENTS_READ)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    service = PaymentService(db)
    payments, total = await service.list_payments(customer_id=customer_id, invoice_id=invoice_id, status=status, payment_method=payment_method, page=page, limit=limit)
    return paginated_response(data=[_to_response(p) for p in payments], total=total, page=page, limit=limit, message="Payments retrieved")


@router.get("/{payment_id}", response_model=dict)
async def get_payment(
    request: Request, payment_id: str,
    current_user: UserInDB = Depends(require_permission(Permission.PAYMENTS_READ)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    service = PaymentService(db)
    payment = await service.get_by_id(payment_id)
    return success_response(message="Payment retrieved", data=_to_response(payment))


@router.patch("/{payment_id}", response_model=dict)
async def update_payment(
    request: Request, payment_id: str, data: PaymentUpdate,
    current_user: UserInDB = Depends(require_permission(Permission.PAYMENTS_UPDATE)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    service = PaymentService(db)
    payment = await service.update(payment_id, data)
    return success_response(message="Payment updated", data=_to_response(payment))


@router.post("/{payment_id}/confirm", response_model=dict)
async def confirm_payment(
    request: Request, payment_id: str,
    current_user: UserInDB = Depends(require_permission(Permission.PAYMENTS_UPDATE)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    service = PaymentService(db)
    payment = await service.confirm_payment(payment_id)
    return success_response(message="Payment confirmed", data=_to_response(payment))


@router.post("/mpesa/callback", response_model=dict)
async def mpesa_callback(
    request: Request,
    current_user: UserInDB = Depends(require_permission(Permission.MPESA_MANAGE)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    body = await request.json()
    checkout_request_id = body.get("CheckoutRequestID")
    result_code = body.get("ResultCode")
    result_desc = body.get("ResultDesc")
    receipt_number = None
    if result_code == 0 and body.get("CallbackMetadata"):
        items = body["CallbackMetadata"].get("Item", [])
        for item in items:
            if item.get("Name") == "MpesaReceiptNumber":
                receipt_number = item.get("Value")

    service = PaymentService(db)
    payment = await service.process_mpesa_callback(checkout_request_id, result_code, result_desc, receipt_number)
    return success_response(message="M-Pesa callback processed", data=_to_response(payment))