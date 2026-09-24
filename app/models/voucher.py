"""Voucher (HotSpot prepaid code) and voucher batch models.

Lifecycle:
    GENERATED -> ACTIVE -> USED
                    (or)-> EXPIRED
                    (or)-> DISABLED  (any state except USED can be disabled)

- GENERATED: created by a batch run, printed, but not yet sold/issued.
  Not usable for auth (app.services.radius_auth_service._check_voucher
  only ever matches status == "active"), so a stack of printed vouchers
  sitting in a drawer never starts its validity countdown.
- ACTIVE: an admin/agent activated it (typically at point of sale). Its
  expiry_date is computed at that moment as now + duration/validity, and
  it becomes usable for RADIUS HotSpot authentication immediately.
- USED: consumed - set by app.services.radius_auth_service when a
  customer authenticates with the voucher code as the RADIUS username.
- EXPIRED: past its expiry_date and swept by VoucherService.expire_sweep()
  (or lazily expired inline by the RADIUS auth check itself).
- DISABLED: manually revoked (lost, refunded, printing error, etc).
"""
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional

from bson import ObjectId
from pydantic import BaseModel, ConfigDict, Field


class VoucherStatus(str, Enum):
    GENERATED = "generated"
    ACTIVE = "active"
    USED = "used"
    EXPIRED = "expired"
    DISABLED = "disabled"


class VoucherBatch(BaseModel):
    """A single generation run - N vouchers sharing the same package/pricing."""
    model_config = ConfigDict(populate_by_name=True, json_encoders={ObjectId: str})

    id: Optional[str] = Field(alias="_id", default=None)
    batch_name: str
    site_id: Optional[str] = None
    router_id: Optional[str] = None  # which MikroTik these are meant for (for printing/labeling)

    quantity: int
    code_prefix: str = ""
    code_length: int = 10

    duration_hours: Optional[float] = None       # validity once activated, e.g. 1, 24, 720
    data_allowance_mb: Optional[int] = None       # None = unlimited data within duration
    rate_limit: Optional[str] = None              # "upload/download" e.g. "5M/10M" (Mikrotik-Rate-Limit)
    price: float = 0.0
    currency: str = "KES"

    activate_on_generation: bool = False  # if True, vouchers are created directly as ACTIVE
    validity_days_after_generation: Optional[int] = None  # hard cutoff even if never activated (optional)

    generated_count: int = 0
    activated_count: int = 0
    used_count: int = 0

    created_by: Optional[str] = None  # user id
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Voucher(BaseModel):
    """A single prepaid HotSpot voucher code.

    Field names intentionally match what
    app.services.radius_auth_service.RadiusAuthService already reads/writes
    against the `vouchers` collection (voucher_code, status, expiry_date,
    duration_hours, data_allowance_mb, used_at, nas_ip, calling_station_id)
    so RADIUS auth keeps working unmodified.
    """
    model_config = ConfigDict(populate_by_name=True, json_encoders={ObjectId: str})

    id: Optional[str] = Field(alias="_id", default=None)
    batch_id: Optional[str] = None
    voucher_code: str = Field(..., min_length=4, max_length=32)

    status: VoucherStatus = VoucherStatus.GENERATED

    site_id: Optional[str] = None
    router_id: Optional[str] = None

    duration_hours: Optional[float] = None
    data_allowance_mb: Optional[int] = None
    rate_limit: Optional[str] = None
    price: float = 0.0
    currency: str = "KES"

    expiry_date: Optional[datetime] = None
    activated_at: Optional[datetime] = None
    activated_by: Optional[str] = None
    used_at: Optional[datetime] = None
    nas_ip: Optional[str] = None
    calling_station_id: Optional[str] = None

    printed: bool = False
    printed_at: Optional[datetime] = None

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
