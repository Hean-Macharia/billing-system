"""M-Pesa API routes.

Phase 5 endpoints:
- POST /api/v1/mpesa/stk-push      -> Initiate payment (protected)
- POST /api/v1/mpesa/callback      -> Safaricom callback (public, no auth)
- POST /api/v1/mpesa/query         -> Query pending transaction (protected)
- POST /api/v1/mpesa/reconcile     -> Batch reconcile pending (protected)
- GET  /api/v1/mpesa/transactions  -> List transactions (protected)
"""
from typing import Optional

from fastapi import APIRouter, Depends, Request, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.dependencies import get_db, require_permission
from app.core.logging import get_logger
from app.models.user import Permission, UserInDB
from app.schemas.mpesa import StkPushRequest, StkQueryRequest
from app.services.mpesa_service import MpesaService
from app.utils.helpers import paginated_response, success_response

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1/mpesa", tags=["M-Pesa"])


def _tx_to_response(tx):
    return {
        "_id": str(tx.id),
        "transaction_type": tx.transaction_type,
        "merchant_request_id": tx.merchant_request_id,
        "checkout_request_id": tx.checkout_request_id,
        "customer_id": tx.customer_id,
        "invoice_id": tx.invoice_id,
        "subscription_id": tx.subscription_id,
        "amount": tx.amount,
        "phone_number": tx.phone_number,
        "account_reference": tx.account_reference,
        "status": tx.status.value,
        "result_code": tx.result_code,
        "result_desc": tx.result_desc,
        "mpesa_receipt_number": tx.mpesa_receipt_number,
        "mpesa_transaction_date": tx.mpesa_transaction_date,
        "callback_received": tx.callback_received,
        "payment_id": tx.payment_id,
        "settled": tx.settled,
        "settlement_error": tx.settlement_error,
        "created_at": tx.created_at.isoformat() if tx.created_at else None,
        "updated_at": tx.updated_at.isoformat() if tx.updated_at else None,
    }


@router.post("/stk-push", response_model=dict, status_code=status.HTTP_201_CREATED)
async def initiate_stk_push(
    request: Request,
    data: StkPushRequest,
    current_user: UserInDB = Depends(require_permission(Permission.MPESA_MANAGE)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Initiate M-Pesa STK Push to customer phone."""
    service = MpesaService(db)
    tx = await service.initiate_stk_push(data, created_by=str(current_user.id))
    return success_response(
        message="STK Push initiated successfully",
        data=_tx_to_response(tx),
        status_code=201,
    )


@router.post("/callback", response_model=dict)
async def mpesa_callback(
    request: Request,
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Safaricom STK Push callback endpoint.

    This endpoint is PUBLIC — Safaricom calls it directly.
    Idempotency is handled internally to prevent duplicate processing.
    """
    body = await request.json()
    logger.info(f"M-Pesa callback received: {body}")

    service = MpesaService(db)
    tx = await service.process_callback(body)
    return success_response(
        message=f"Callback processed: {tx.status.value}",
        data=_tx_to_response(tx),
    )


@router.post("/query", response_model=dict)
async def query_stk_status(
    request: Request,
    data: StkQueryRequest,
    current_user: UserInDB = Depends(require_permission(Permission.MPESA_MANAGE)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Manually query Safaricom for a pending STK transaction status.
    Useful when callback was not received (network issues).
    """
    service = MpesaService(db)
    tx = await service.query_stk_status(data.checkout_request_id)
    return success_response(
        message="STK status queried",
        data=_tx_to_response(tx),
    )


@router.post("/reconcile", response_model=dict)
async def reconcile_pending(
    request: Request,
    max_age_hours: int = 24,
    current_user: UserInDB = Depends(require_permission(Permission.MPESA_MANAGE)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Batch reconcile all pending STK transactions older than N hours.
    Queries Safaricom for each and processes the result.
    """
    service = MpesaService(db)
    updated = await service.reconcile_pending(max_age_hours=max_age_hours)
    return success_response(
        message=f"Reconciled {len(updated)} pending transaction(s)",
        data=[_tx_to_response(tx) for tx in updated],
    )


@router.get("/transactions", response_model=dict)
async def list_transactions(
    request: Request,
    customer_id: Optional[str] = None,
    status: Optional[str] = None,
    invoice_id: Optional[str] = None,
    page: int = 1,
    limit: int = 20,
    current_user: UserInDB = Depends(require_permission(Permission.PAYMENTS_READ)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """List M-Pesa transactions with filters."""
    service = MpesaService(db)
    transactions, total = await service.list_transactions(
        customer_id=customer_id, status=status, invoice_id=invoice_id, page=page, limit=limit
    )
    return paginated_response(
        data=[_tx_to_response(tx) for tx in transactions],
        total=total,
        page=page,
        limit=limit,
        message="M-Pesa transactions retrieved",
    )


@router.get("/transactions/{tx_id}", response_model=dict)
async def get_transaction(
    request: Request,
    tx_id: str,
    current_user: UserInDB = Depends(require_permission(Permission.PAYMENTS_READ)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Get a single M-Pesa transaction by ID."""
    service = MpesaService(db)
    tx = await service.get_by_id(tx_id)
    return success_response(message="Transaction retrieved", data=_tx_to_response(tx))