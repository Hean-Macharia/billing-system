"""Invoice model for MongoDB."""
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional

from bson import ObjectId
from pydantic import BaseModel, BeforeValidator, Field
from typing_extensions import Annotated

ObjectIdStr = Annotated[str, BeforeValidator(lambda v: str(v) if isinstance(v, ObjectId) else v)]


class InvoiceStatus(str, Enum):
    DRAFT = "draft"
    SENT = "sent"
    VIEWED = "viewed"
    PARTIAL = "partial"
    PAID = "paid"
    OVERDUE = "overdue"
    CANCELLED = "cancelled"
    WRITEOFF = "writeoff"


class InvoiceLineItem(BaseModel):
    description: str
    quantity: float = 1.0
    unit_price_kes: float
    total_kes: float
    item_type: str = "service"
    subscription_id: Optional[str] = None


class Invoice(BaseModel):
    id: Optional[ObjectIdStr] = Field(None, alias="_id")
    invoice_number: str = Field(..., description="e.g. INV-2026-0001")
    customer_id: str
    customer_code: Optional[str] = None
    customer_name: Optional[str] = None
    customer_email: Optional[str] = None
    subscription_id: Optional[str] = None
    invoice_date: datetime
    due_date: datetime
    paid_date: Optional[datetime] = None
    sent_date: Optional[datetime] = None
    status: InvoiceStatus = InvoiceStatus.DRAFT
    line_items: List[InvoiceLineItem] = Field(default_factory=list)
    subtotal_kes: float = 0.0
    tax_rate_percent: float = 0.0
    tax_amount_kes: float = 0.0
    discount_kes: float = 0.0
    total_kes: float = 0.0
    amount_paid_kes: float = 0.0
    balance_due_kes: float = 0.0
    payment_ids: List[str] = Field(default_factory=list)
    mpesa_request_id: Optional[str] = None
    mpesa_checkout_request_id: Optional[str] = None
    notes: Optional[str] = None
    terms: Optional[str] = None
    footer_message: Optional[str] = None
    created_by: Optional[str] = None
    sent_by: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    pdf_url: Optional[str] = None
    email_sent: bool = False
    sms_sent: bool = False

    class Config:
        populate_by_name = True
        json_encoders = {datetime: lambda v: v.isoformat(), ObjectId: lambda v: str(v)}


class InvoiceInDB(Invoice):
    pass