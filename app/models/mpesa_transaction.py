"""M-Pesa transaction model for idempotency and reconciliation."""
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field
from bson import ObjectId


class MpesaTransactionStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


class MpesaTransaction(BaseModel):
    """Stores every M-Pesa STK Push request and callback for audit & idempotency."""
    model_config = ConfigDict(populate_by_name=True, json_encoders={ObjectId: str})

    id: Optional[str] = Field(alias="_id", default=None)
    transaction_type: str = "stk_push"  # Future: c2b, b2c, etc.
    merchant_request_id: Optional[str] = None
    checkout_request_id: Optional[str] = None
    customer_id: str
    invoice_id: Optional[str] = None
    subscription_id: Optional[str] = None
    amount: float = Field(..., gt=0)
    phone_number: str
    account_reference: str
    transaction_desc: str
    status: MpesaTransactionStatus = MpesaTransactionStatus.PENDING
    result_code: Optional[int] = None
    result_desc: Optional[str] = None
    mpesa_receipt_number: Optional[str] = None
    mpesa_transaction_date: Optional[str] = None  # YYYYMMDDHHMMSS from Safaricom
    callback_received: bool = False
    callback_payload: Optional[dict] = None
    payment_id: Optional[str] = None  # Links to app.models.payment.Payment
    settled: bool = False  # True once invoice+subscription fully processed
    settlement_error: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class MpesaTransactionInDB(MpesaTransaction):
    """Transaction as stored in MongoDB."""
    model_config = ConfigDict(populate_by_name=True)
    id: str = Field(alias="_id")