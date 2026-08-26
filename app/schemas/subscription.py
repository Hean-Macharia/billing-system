"""Pydantic schemas for subscription endpoints."""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from app.models.subscription import SubscriptionStatus


class SubscriptionCreate(BaseModel):
    customer_id: str
    plan_id: str
    start_date: datetime
    end_date: Optional[datetime] = None
    monthly_price_kes: float = Field(..., ge=0)
    setup_fee_kes: float = 0.0
    equipment_fee_kes: float = 0.0
    discount_kes: float = 0.0
    discount_reason: Optional[str] = None
    contract_months: int = 0
    auto_renew: bool = True
    notes: Optional[str] = None
    tags: List[str] = Field(default_factory=list)


class SubscriptionUpdate(BaseModel):
    status: Optional[SubscriptionStatus] = None
    monthly_price_kes: Optional[float] = Field(None, ge=0)
    discount_kes: Optional[float] = None
    discount_reason: Optional[str] = None
    auto_renew: Optional[bool] = None
    end_date: Optional[datetime] = None
    next_billing_date: Optional[datetime] = None
    notes: Optional[str] = None
    tags: Optional[List[str]] = None
    assigned_technician_id: Optional[str] = None
    installation_notes: Optional[str] = None
    pppoe_username: Optional[str] = None
    pppoe_password: Optional[str] = None
    ip_address: Optional[str] = None
    vlan_id: Optional[int] = None


class SubscriptionResponse(BaseModel):
    id: str = Field(..., alias="_id")
    customer_id: str
    customer_code: Optional[str] = None
    customer_name: Optional[str] = None
    plan_id: str
    plan_code: Optional[str] = None
    plan_name: Optional[str] = None
    status: str
    start_date: datetime
    end_date: Optional[datetime] = None
    next_billing_date: datetime
    last_billed_date: Optional[datetime] = None
    monthly_price_kes: float
    setup_fee_kes: float
    equipment_fee_kes: float
    discount_kes: float
    contract_months: int
    auto_renew: bool
    installation_completed: bool
    installation_date: Optional[datetime] = None
    ip_address: Optional[str] = None
    pppoe_username: Optional[str] = None
    data_used_gb: float
    data_cap_gb: Optional[int] = None
    total_billed_kes: float
    total_paid_kes: float
    notes: Optional[str] = None
    tags: List[str]
    created_at: datetime
    updated_at: datetime
    created_by: Optional[str] = None
    cancelled_at: Optional[datetime] = None
    cancellation_reason: Optional[str] = None

    class Config:
        populate_by_name = True