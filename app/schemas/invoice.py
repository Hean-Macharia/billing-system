"""Pydantic schemas for invoice endpoints."""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from app.models.invoice import InvoiceLineItem, InvoiceStatus


class InvoiceCreate(BaseModel):
    customer_id: str
    subscription_id: Optional[str] = None
    invoice_date: datetime
    due_date: datetime
    line_items: List[InvoiceLineItem] = Field(default_factory=list)
    tax_rate_percent: float = 0.0
    discount_kes: float = 0.0
    notes: Optional[str] = None
    terms: Optional[str] = None


class InvoiceUpdate(BaseModel):
    status: Optional[InvoiceStatus] = None
    due_date: Optional[datetime] = None
    notes: Optional[str] = None
    terms: Optional[str] = None
    footer_message: Optional[str] = None


class InvoiceResponse(BaseModel):
    id: str = Field(..., alias="_id")
    invoice_number: str
    customer_id: str
    customer_code: Optional[str] = None
    customer_name: Optional[str] = None
    subscription_id: Optional[str] = None
    invoice_date: datetime
    due_date: datetime
    paid_date: Optional[datetime] = None
    sent_date: Optional[datetime] = None
    status: str
    line_items: List[dict]
    subtotal_kes: float
    tax_rate_percent: float
    tax_amount_kes: float
    discount_kes: float
    total_kes: float
    amount_paid_kes: float
    balance_due_kes: float
    payment_ids: List[str]
    notes: Optional[str] = None
    terms: Optional[str] = None
    created_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    email_sent: bool
    sms_sent: bool

    class Config:
        populate_by_name = True