"""HotSpot plan (profile) model.

A HotspotPlan is a reusable template - "1 Hour", "Daily Unlimited",
"Weekly 2GB" - bundling the duration, data cap, bandwidth rate limit and
price that a voucher batch is generated from. This keeps pricing/package
definitions in one place instead of re-typing duration/data/rate on every
batch-generation request, and lets a captive-portal splash page list
"available plans" without needing to know voucher internals.

rate_limit follows the same "upload/download" convention already used by
RadiusUser.rate_limit (Phase 6) and pushed to MikroTik as the
Mikrotik-Rate-Limit RADIUS attribute, e.g. "2M/5M".
"""
from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId
from pydantic import BaseModel, ConfigDict, Field


class HotspotPlan(BaseModel):
    model_config = ConfigDict(populate_by_name=True, json_encoders={ObjectId: str})

    id: Optional[str] = Field(alias="_id", default=None)
    name: str  # e.g. "1 Hour Access", "Daily Unlimited"
    site_id: Optional[str] = None  # None = available at all sites

    duration_hours: float
    data_allowance_mb: Optional[int] = None  # None = unlimited within duration
    rate_limit: Optional[str] = None  # "upload/download", e.g. "2M/5M"
    price: float = 0.0
    currency: str = "KES"

    description: Optional[str] = None
    is_active: bool = True
    sort_order: int = 0

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
