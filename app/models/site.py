"""Site model - a physical location (tower, POP, branch office) that
routers, voucher batches, and hotspot plans link to via site_id."""
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from bson import ObjectId
from pydantic import BaseModel, ConfigDict, Field


class SiteStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    PLANNED = "planned"


class Site(BaseModel):
    model_config = ConfigDict(populate_by_name=True, json_encoders={ObjectId: str})

    id: Optional[str] = Field(alias="_id", default=None)
    name: str
    code: str  # short human code, e.g. "NYR-001"
    address: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    status: SiteStatus = SiteStatus.ACTIVE
    contact_person: Optional[str] = None
    contact_phone: Optional[str] = None
    notes: Optional[str] = None

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
