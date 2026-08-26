"""Pydantic schemas for payment endpoints."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.models.payment import PaymentMethod, PaymentStatus


class PaymentCreate(BaseModel):
    customer_id: str
    invoice_id: Optional[str] = None
    subscription_id: Optional[str] = None
    amount_kes: float = Field(..., gt=0)
    payment_method: PaymentMethod
    payment_method_details: Optional[dict] = None
    payment_date: Optional[datetime] = None
    notes: Optional[str] = None
    transaction_id: Optional[str] = None
    mpesa_phone_number: Optional[str] = None
    bank_reference: Optional[str] = None
    bank_name: Optional[str] = None
    received_by: Optional[str] = None
    receipt_number: Optional[str] = None


class PaymentUpdate(BaseModel):
    status: Optional[PaymentStatus] = None
    notes: Optional[str] = None
    mpesa_receipt_number: Optional[str] = None
    mpesa_result_code: Optional[int] = None
    mpesa_result_desc: Optional[str] = None
    bank_reference: Optional[str] = None
    reconciled: Optional[bool] = None


class PaymentResponse(BaseModel):
    id: str = Field(..., alias="_id")
    transaction_id: str
    customer_id: str
    customer_code: Optional[str] = None
    customer_name: Optional[str] = None
    invoice_id: Optional[str] = None
    invoice_number: Optional[str] = None
    subscription_id: Optional[str] = None
    amount_kes: float
    currency: str
    payment_method: str
    payment_method_details: Optional[dict] = None
    status: str
    mpesa_receipt_number: Optional[str] = None
    mpesa_phone_number: Optional[str] = None
    bank_reference: Optional[str] = None
    bank_name: Optional[str] = None
    received_by: Optional[str] = None
    receipt_number: Optional[str] = None
    payment_date: datetime
    processed_date: Optional[datetime] = None
    confirmed_date: Optional[datetime] = None
    reconciled: bool
    reconciled_by: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    created_by: Optional[str] = None

    class Config:
        populate_by_name = True