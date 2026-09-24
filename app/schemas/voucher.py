"""Voucher schemas."""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from app.models.voucher import VoucherStatus


class VoucherBatchCreate(BaseModel):
    batch_name: str = Field(..., min_length=1, max_length=100)
    site_id: Optional[str] = None
    router_id: Optional[str] = None

    quantity: int = Field(..., gt=0, le=5000)
    code_prefix: str = Field(default="", max_length=8)
    code_length: int = Field(default=10, ge=6, le=20)

    # Either supply plan_id to copy settings from a HotspotPlan, or fill these in directly.
    plan_id: Optional[str] = None
    duration_hours: Optional[float] = Field(default=None, gt=0)
    data_allowance_mb: Optional[int] = Field(default=None, gt=0)
    rate_limit: Optional[str] = None
    price: float = 0.0
    currency: str = "KES"

    activate_on_generation: bool = False
    validity_days_after_generation: Optional[int] = Field(default=None, gt=0)


class VoucherActivateRequest(BaseModel):
    voucher_ids: Optional[List[str]] = None  # if omitted, activates the whole batch


class VoucherDisableRequest(BaseModel):
    reason: Optional[str] = None


class VoucherResponse(BaseModel):
    id: str = Field(alias="_id")
    batch_id: Optional[str] = None
    voucher_code: str
    status: str
    site_id: Optional[str] = None
    router_id: Optional[str] = None
    duration_hours: Optional[float] = None
    data_allowance_mb: Optional[int] = None
    rate_limit: Optional[str] = None
    price: float
    currency: str
    expiry_date: Optional[datetime] = None
    activated_at: Optional[datetime] = None
    used_at: Optional[datetime] = None
    printed: bool
    created_at: datetime
    updated_at: datetime


class VoucherBatchResponse(BaseModel):
    id: str = Field(alias="_id")
    batch_name: str
    site_id: Optional[str] = None
    router_id: Optional[str] = None
    quantity: int
    duration_hours: Optional[float] = None
    data_allowance_mb: Optional[int] = None
    rate_limit: Optional[str] = None
    price: float
    currency: str
    activate_on_generation: bool
    generated_count: int
    activated_count: int
    used_count: int
    created_at: datetime
    updated_at: datetime


class VoucherPublicCheckResponse(BaseModel):
    """Returned by the public (no-auth) check endpoint used by a captive portal."""
    voucher_code: str
    valid: bool
    status: str
    reason: Optional[str] = None
    duration_hours: Optional[float] = None
    data_allowance_mb: Optional[int] = None
    expiry_date: Optional[datetime] = None
