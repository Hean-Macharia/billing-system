"""RADIUS admin schemas."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.models.radius import NasType, RadiusUserType


# ── NAS Client Schemas ──

class NasClientCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    site_id: Optional[str] = None
    ip_address: str
    secret: str = Field(..., min_length=8)
    description: Optional[str] = None
    location: Optional[str] = None
    nas_type: NasType = NasType.MIKROTIK
    coa_port: int = 3799


class NasClientUpdate(BaseModel):
    name: Optional[str] = None
    site_id: Optional[str] = None
    ip_address: Optional[str] = None
    secret: Optional[str] = None
    description: Optional[str] = None
    location: Optional[str] = None
    nas_type: Optional[NasType] = None
    status: Optional[str] = None
    coa_port: Optional[int] = None


class NasClientResponse(BaseModel):
    _id: str
    name: str
    site_id: Optional[str]
    ip_address: str
    description: Optional[str]
    location: Optional[str]
    nas_type: str
    status: str
    coa_port: int
    last_seen: Optional[datetime]
    created_at: datetime
    updated_at: datetime


# ── RADIUS User Schemas ──

class RadiusUserCreate(BaseModel):
    username: str = Field(..., min_length=1, max_length=128)
    password: str = Field(..., min_length=1, max_length=128)
    user_type: RadiusUserType = RadiusUserType.PPPOE
    customer_id: Optional[str] = None
    service_id: Optional[str] = None
    subscription_id: Optional[str] = None
    site_id: Optional[str] = None
    package_id: Optional[str] = None
    framed_ip_address: Optional[str] = None
    framed_ip_pool: Optional[str] = None
    session_timeout: Optional[int] = None
    idle_timeout: Optional[int] = None
    simultaneous_use: Optional[int] = 1
    rate_limit: Optional[str] = None


class RadiusUserUpdate(BaseModel):
    password: Optional[str] = None
    framed_ip_address: Optional[str] = None
    framed_ip_pool: Optional[str] = None
    session_timeout: Optional[int] = None
    idle_timeout: Optional[int] = None
    simultaneous_use: Optional[int] = None
    rate_limit: Optional[str] = None
    status: Optional[str] = None
    package_id: Optional[str] = None


class RadiusUserResponse(BaseModel):
    _id: str
    username: str
    user_type: str
    customer_id: Optional[str]
    service_id: Optional[str]
    subscription_id: Optional[str]
    site_id: Optional[str]
    package_id: Optional[str]
    framed_ip_address: Optional[str]
    framed_ip_pool: Optional[str]
    session_timeout: Optional[int]
    idle_timeout: Optional[int]
    simultaneous_use: Optional[int]
    rate_limit: Optional[str]
    status: str
    last_login: Optional[datetime]
    total_sessions: int
    created_at: datetime
    updated_at: datetime


# ── Session / Accounting Schemas ──

class RadiusSessionResponse(BaseModel):
    _id: str
    acct_session_id: str
    username: str
    nas_ip_address: str
    nas_port_id: Optional[str]
    framed_ip_address: Optional[str]
    calling_station_id: Optional[str]
    acct_start_time: datetime
    acct_session_time: int
    acct_input_octets: int
    acct_output_octets: int
    customer_id: Optional[str]
    site_id: Optional[str]
    status: str
    last_seen: datetime


class RadiusAccountingResponse(BaseModel):
    _id: str
    acct_session_id: str
    username: str
    nas_ip_address: str
    acct_start_time: Optional[datetime]
    acct_stop_time: Optional[datetime]
    acct_session_time: int
    acct_input_octets: int
    acct_output_octets: int
    acct_terminate_cause: str
    framed_ip_address: Optional[str]
    calling_station_id: Optional[str]
    customer_id: Optional[str]
    created_at: datetime