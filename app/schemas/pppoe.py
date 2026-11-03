"""Schemas for staff-managed PPPoE subscribers."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class PppoeSubscriberCreate(BaseModel):
    customer_id: str = Field(min_length=1, max_length=64)
    plan_id: str = Field(min_length=1, max_length=64)
    site_id: str = Field(min_length=1, max_length=64)
    router_id: str = Field(min_length=1, max_length=64)
    nas_client_id: str = Field(min_length=1, max_length=64)
    username: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.@-]+$")
    password: str = Field(min_length=12, max_length=128)
    ip_address: Optional[str] = None
    framed_ip_pool: Optional[str] = None


class PppoeSubscriberUpdate(BaseModel):
    plan_id: Optional[str] = Field(default=None, min_length=1, max_length=64)
    ip_address: Optional[str] = None
    framed_ip_pool: Optional[str] = None


class PppoePasswordReset(BaseModel):
    password: str = Field(min_length=12, max_length=128)


class PppoeStatusChange(BaseModel):
    reason: Optional[str] = Field(default=None, max_length=500)


class PppoeSubscriberResponse(BaseModel):
    id: str
    customer_id: str
    customer_name: Optional[str] = None
    plan_id: str
    plan_name: Optional[str] = None
    site_id: str
    router_id: str
    nas_client_id: str
    username: str
    status: str
    start_date: datetime
    end_date: Optional[datetime] = None
    ip_address: Optional[str] = None
    framed_ip_pool: Optional[str] = None

