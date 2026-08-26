"""Payment model for MongoDB."""
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from bson import ObjectId
from pydantic import BaseModel, BeforeValidator, Field
from typing_extensions import Annotated

ObjectIdStr = Annotated[str, BeforeValidator(lambda v: str(v) if isinstance(v, ObjectId) else v)]


class PaymentStatus(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    REFUNDED = "refunded"
    CANCELLED = "cancelled"


class PaymentMethod(str, Enum):
    MPESA = "mpesa"
    BANK_TRANSFER = "bank_transfer"
    BANK_DEPOSIT = "bank_deposit"
    CASH = "cash"
    CHEQUE = "cheque"
    VOUCHER = "voucher"
    CARD = "card"
    WALLET = "wallet"


class Payment(BaseModel):
    id: Optional[ObjectIdStr] = Field(None, alias="_id")
    transaction_id: str = Field(..., description="Unique transaction reference")
    customer_id: str
    customer_code: Optional[str] = None
    customer_name: Optional[str] = None
    invoice_id: Optional[str] = None
    invoice_number: Optional[str] = None
    subscription_id: Optional[str] = None
    amount_kes: float = Field(..., gt=0)
    currency: str = "KES"
    payment_method: PaymentMethod
    payment_method_details: Optional[dict] = None
    status: PaymentStatus = PaymentStatus.PENDING
    mpesa_receipt_number: Optional[str] = None
    mpesa_phone_number: Optional[str] = None
    mpesa_merchant_request_id: Optional[str] = None
    mpesa_checkout_request_id: Optional[str] = None
    mpesa_result_code: Optional[int] = None
    mpesa_result_desc: Optional[str] = None
    mpesa_callback_received: bool = False
    mpesa_callback_raw: Optional[dict] = None
    bank_reference: Optional[str] = None
    bank_name: Optional[str] = None
    bank_account: Optional[str] = None
    received_by: Optional[str] = None
    receipt_number: Optional[str] = None
    payment_date: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    processed_date: Optional[datetime] = None
    confirmed_date: Optional[datetime] = None
    reconciled: bool = False
    reconciled_by: Optional[str] = None
    reconciled_at: Optional[datetime] = None
    refunded_amount_kes: float = 0.0
    refund_reason: Optional[str] = None
    refund_transaction_id: Optional[str] = None
    notes: Optional[str] = None
    created_by: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Config:
        populate_by_name = True
        json_encoders = {datetime: lambda v: v.isoformat(), ObjectId: lambda v: str(v)}


class PaymentInDB(Payment):
    pass