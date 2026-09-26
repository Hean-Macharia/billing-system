from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.models.site import SiteStatus


class SiteCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    code: str = Field(..., min_length=1, max_length=30)
    address: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    status: SiteStatus = SiteStatus.ACTIVE
    contact_person: Optional[str] = None
    contact_phone: Optional[str] = None
    notes: Optional[str] = None


class SiteUpdate(BaseModel):
    name: Optional[str] = None
    code: Optional[str] = None
    address: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    status: Optional[SiteStatus] = None
    contact_person: Optional[str] = None
    contact_phone: Optional[str] = None
    notes: Optional[str] = None


class SiteResponse(BaseModel):
    id: str = Field(alias="_id")
    name: str
    code: str
    address: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    status: str
    contact_person: Optional[str] = None
    contact_phone: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime
