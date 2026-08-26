"""Subscription model — links customers to service plans."""
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional

from bson import ObjectId
from pydantic import BaseModel, BeforeValidator, Field
from typing_extensions import Annotated

ObjectIdStr = Annotated[str, BeforeValidator(lambda v: str(v) if isinstance(v, ObjectId) else v)]


class SubscriptionStatus(str, Enum):
    ACTIVE = "active"
    PENDING = "pending"
    SUSPENDED = "suspended"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    TRIAL = "trial"


class Subscription(BaseModel):
    id: Optional[ObjectIdStr] = Field(None, alias="_id")
    customer_id: str
    customer_code: Optional[str] = None
    customer_name: Optional[str] = None
    plan_id: str
    plan_code: Optional[str] = None
    plan_name: Optional[str] = None
    status: SubscriptionStatus = SubscriptionStatus.PENDING
    start_date: datetime
    end_date: Optional[datetime] = None
    next_billing_date: datetime
    last_billed_date: Optional[datetime] = None
    trial_end_date: Optional[datetime] = None
    monthly_price_kes: float = Field(..., ge=0)
    setup_fee_kes: float = 0.0
    equipment_fee_kes: float = 0.0
    discount_kes: float = 0.0
    discount_reason: Optional[str] = None
    contract_months: int = 0
    auto_renew: bool = True
    installation_date: Optional[datetime] = None
    installation_completed: bool = False
    installation_notes: Optional[str] = None
    assigned_technician_id: Optional[str] = None
    ip_address: Optional[str] = None
    vlan_id: Optional[int] = None
    pppoe_username: Optional[str] = None
    pppoe_password: Optional[str] = None
    data_used_gb: float = 0.0
    data_cap_gb: Optional[int] = None
    invoice_ids: List[str] = Field(default_factory=list)
    total_billed_kes: float = 0.0
    total_paid_kes: float = 0.0
    notes: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    created_by: Optional[str] = None
    cancelled_at: Optional[datetime] = None
    cancellation_reason: Optional[str] = None

    class Config:
        populate_by_name = True
        json_encoders = {datetime: lambda v: v.isoformat(), ObjectId: lambda v: str(v)}


class SubscriptionInDB(Subscription):
    pass