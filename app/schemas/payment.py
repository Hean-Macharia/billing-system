from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class PaymentCreate(BaseModel):
    customer_id: str

    invoice_id: Optional[str] = None

    amount: float = Field(
        ...,
        gt=0,
    )

    currency: str = "KES"

    payment_method: str = Field(
        ...,
        description="mpesa, cash, bank, card, etc.",
    )

    transaction_reference: Optional[str] = None

    phone_number: Optional[str] = None


class PaymentResponse(BaseModel):
    payment_id: str

    customer_id: str

    invoice_id: Optional[str] = None

    amount: float

    currency: str

    payment_method: str

    transaction_reference: Optional[str] = None

    phone_number: Optional[str] = None

    status: str

    created_at: datetime

    updated_at: datetime

    created_by: Optional[str] = None