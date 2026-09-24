"""HotSpot plan schemas."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class HotspotPlanCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    site_id: Optional[str] = None
    duration_hours: float = Field(..., gt=0)
    data_allowance_mb: Optional[int] = Field(default=None, gt=0)
    rate_limit: Optional[str] = None
    price: float = 0.0
    currency: str = "KES"
    description: Optional[str] = None
    is_active: bool = True
    sort_order: int = 0


class HotspotPlanUpdate(BaseModel):
    name: Optional[str] = None
    site_id: Optional[str] = None
    duration_hours: Optional[float] = Field(default=None, gt=0)
    data_allowance_mb: Optional[int] = None
    rate_limit: Optional[str] = None
    price: Optional[float] = None
    currency: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None


class HotspotPlanResponse(BaseModel):
    id: str = Field(alias="_id")
    name: str
    site_id: Optional[str] = None
    duration_hours: float
    data_allowance_mb: Optional[int] = None
    rate_limit: Optional[str] = None
    price: float
    currency: str
    description: Optional[str] = None
    is_active: bool
    sort_order: int
    created_at: datetime
    updated_at: datetime
