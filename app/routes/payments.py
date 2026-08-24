from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.database import get_database
from app.core.security import get_current_user
from app.schemas.payment import (
    PaymentCreate,
    PaymentResponse,
)


router = APIRouter(
    prefix="/api/v1/payments",
    tags=["Payments"],
)


@router.post(
    "",
    response_model=PaymentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_payment(
    payment: PaymentCreate,
    current_user=Depends(get_current_user),
):
    """
    Create a payment record.

    This endpoint currently records payments only.
    M-PESA integration will be connected later.
    """

    database = get_database()

    now = datetime.now(timezone.utc)

    payment_document = {
        "payment_id": str(ObjectId()),
        "customer_id": payment.customer_id,
        "invoice_id": payment.invoice_id,
        "amount": payment.amount,
        "currency": payment.currency,
        "payment_method": payment.payment_method,
        "transaction_reference": payment.transaction_reference,
        "phone_number": payment.phone_number,
        "status": "completed",
        "created_at": now,
        "updated_at": now,
        "created_by": current_user.get("user_id"),
    }

    await database.payments.insert_one(payment_document)

    return payment_document


@router.get(
    "",
    response_model=list[PaymentResponse],
)
async def list_payments(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    customer_id: Optional[str] = None,
    current_user=Depends(get_current_user),
):
    database = get_database()

    query = {}

    if customer_id:
        query["customer_id"] = customer_id

    payments = (
        await database.payments
        .find(query)
        .sort("created_at", -1)
        .skip(skip)
        .limit(limit)
        .to_list(length=limit)
    )

    for payment in payments:
        payment.pop("_id", None)

    return payments


@router.get(
    "/{payment_id}",
    response_model=PaymentResponse,
)
async def get_payment(
    payment_id: str,
    current_user=Depends(get_current_user),
):
    database = get_database()

    payment = await database.payments.find_one(
        {
            "payment_id": payment_id
        }
    )

    if not payment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment not found",
        )

    payment.pop("_id", None)

    return payment