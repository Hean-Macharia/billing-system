"""Voucher model for HotSpot and PPPoE voucher management."""
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field
from bson import ObjectId
from app.models.base import PyObjectId


class VoucherStatus(str, Enum):
    ACTIVE = "active"
    USED = "used"
    EXPIRED = "expired"
    REVOKED = "revoked"
    PENDING = "pending"


class VoucherType(str, Enum):
    HOTSPOT = "hotspot"
    PPPOE = "pppoe"
    BOTH = "both"


class Voucher(BaseModel):
    """Voucher model for prepaid internet access."""
    id: Optional[PyObjectId] = Field(default=None, alias="_id")
    code: str = Field(..., description="Unique voucher code")
    voucher_type: VoucherType = VoucherType.HOTSPOT
    status: VoucherStatus = VoucherStatus.PENDING
    customer_id: Optional[str] = None
    service_id: Optional[str] = None
    router_id: Optional[str] = None
    
    # Validity
    validity_days: int = Field(default=30, ge=1)
    data_limit_mb: Optional[int] = None  # None = unlimited
    speed_limit_mbps: Optional[int] = None
    
    # Usage tracking
    used_by: Optional[str] = None  # username or MAC address
    used_at: Optional[datetime] = None
    data_used_mb: int = 0
    
    # Expiry
    expires_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Metadata
    batch_id: Optional[str] = None  # For bulk generation
    created_by: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}


class VoucherCreate(BaseModel):
    """Voucher creation schema."""
    code: str
    voucher_type: VoucherType = VoucherType.HOTSPOT
    validity_days: int = 30
    data_limit_mb: Optional[int] = None
    speed_limit_mbps: Optional[int] = None
    service_id: Optional[str] = None
    router_id: Optional[str] = None
    notes: Optional[str] = None


class VoucherBatchCreate(BaseModel):
    """Bulk voucher creation schema."""
    count: int = Field(..., gt=0, le=1000)
    voucher_type: VoucherType = VoucherType.HOTSPOT
    validity_days: int = 30
    data_limit_mb: Optional[int] = None
    speed_limit_mbps: Optional[int] = None
    service_id: Optional[str] = None
    router_id: Optional[str] = None
    notes: Optional[str] = None


class VoucherUpdate(BaseModel):
    """Voucher update schema."""
    status: Optional[VoucherStatus] = None
    customer_id: Optional[str] = None
    notes: Optional[str] = None


class VoucherInDB(Voucher):
    """Voucher as stored in database."""
    pass