"""M-Pesa Pydantic schemas for API requests/responses."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, ConfigDict


class StkPushRequest(BaseModel):
    """Request body to initiate STK Push."""
    phone_number: str = Field(..., pattern=r"^254[0-9]{9}$", description="2547XXXXXXXX format")
    amount: float = Field(..., gt=0, description="Amount in KES")
    account_reference: str = Field(..., max_length=20, description="Invoice number or customer code")
    transaction_desc: str = Field(default="ISP Billing Payment", max_length=50)
    customer_id: str
    invoice_id: Optional[str] = None
    subscription_id: Optional[str] = None


class StkCallbackMetadataItem(BaseModel):
    Name: str
    Value: Optional[str] = None


class StkCallbackBody(BaseModel):
    """Safaricom callback body wrapper."""
    stkCallback: dict


class StkQueryRequest(BaseModel):
    """Manual query for a pending STK transaction."""
    checkout_request_id: str


class MpesaTransactionResponse(BaseModel):
    """Clean response for M-Pesa transactions."""
    model_config = ConfigDict(from_attributes=True)

    _id: str
    transaction_type: str
    merchant_request_id: Optional[str]
    checkout_request_id: Optional[str]
    customer_id: str
    invoice_id: Optional[str]
    subscription_id: Optional[str]
    amount: float
    phone_number: str
    account_reference: str
    status: str
    result_code: Optional[int]
    result_desc: Optional[str]
    mpesa_receipt_number: Optional[str]
    callback_received: bool
    payment_id: Optional[str]
    settled: bool
    settlement_error: Optional[str]
    created_at: datetime
    updated_at: datetime