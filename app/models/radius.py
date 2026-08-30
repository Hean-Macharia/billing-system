"""RADIUS models for AAA (Authentication, Authorization, Accounting)."""
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field
from bson import ObjectId


class NasType(str, Enum):
    MIKROTIK = "mikrotik"
    CISCO = "cisco"
    OTHER = "other"


class NasClient(BaseModel):
    """RADIUS NAS client (MikroTik router)."""
    model_config = ConfigDict(populate_by_name=True, json_encoders={ObjectId: str})

    id: Optional[str] = Field(alias="_id", default=None)
    name: str
    site_id: Optional[str] = None
    ip_address: str  # NAS IP that FreeRADIUS sees
    secret: str  # RADIUS shared secret (never returned in API)
    description: Optional[str] = None
    location: Optional[str] = None
    nas_type: NasType = NasType.MIKROTIK
    status: str = "active"  # active, inactive
    coa_port: int = 3799  # Change of Authorization port
    last_seen: Optional[datetime] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class RadiusUserType(str, Enum):
    PPPOE = "pppoe"
    HOTSPOT = "hotspot"
    HOTSPOT_VOUCHER = "hotspot_voucher"


class RadiusUser(BaseModel):
    """RADIUS user credential record (PPPoE or HotSpot)."""
    model_config = ConfigDict(populate_by_name=True, json_encoders={ObjectId: str})

    id: Optional[str] = Field(alias="_id", default=None)
    username: str = Field(..., min_length=1, max_length=128)
    password: str = Field(..., min_length=1, max_length=128)  # Cleartext for RADIUS
    user_type: RadiusUserType = RadiusUserType.PPPOE
    customer_id: Optional[str] = None
    service_id: Optional[str] = None
    subscription_id: Optional[str] = None
    site_id: Optional[str] = None
    voucher_id: Optional[str] = None  # For hotspot voucher users
    package_id: Optional[str] = None

    # Authorization attributes (cached from package/subscription)
    framed_ip_address: Optional[str] = None
    framed_ip_pool: Optional[str] = None
    session_timeout: Optional[int] = None  # seconds
    idle_timeout: Optional[int] = None     # seconds
    simultaneous_use: Optional[int] = 1
    rate_limit: Optional[str] = None     # e.g. "10M/5M"
    data_cap_bytes: Optional[int] = None  # For data-limited packages

    status: str = "active"  # active, suspended, expired
    last_login: Optional[datetime] = None
    last_nas_ip: Optional[str] = None
    last_framed_ip: Optional[str] = None
    total_sessions: int = 0
    total_online_time_sec: int = 0
    total_input_bytes: int = 0
    total_output_bytes: int = 0

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class RadiusAccounting(BaseModel):
    """RADIUS accounting record (Start/Stop/Interim-Update)."""
    model_config = ConfigDict(populate_by_name=True, json_encoders={ObjectId: str})

    id: Optional[str] = Field(alias="_id", default=None)
    acct_session_id: str
    acct_unique_id: Optional[str] = None
    username: str
    realm: Optional[str] = None
    nas_ip_address: str
    nas_port_id: Optional[str] = None
    nas_port_type: Optional[str] = None
    acct_start_time: Optional[datetime] = None
    acct_update_time: Optional[datetime] = None
    acct_stop_time: Optional[datetime] = None
    acct_interval: Optional[int] = None
    acct_session_time: int = 0  # seconds
    acct_authentic: Optional[str] = None
    connectinfo_start: Optional[str] = None
    connectinfo_stop: Optional[str] = None
    acct_input_octets: int = 0   # download bytes
    acct_output_octets: int = 0  # upload bytes
    acct_input_gigawords: int = 0
    acct_output_gigawords: int = 0
    called_station_id: Optional[str] = None
    calling_station_id: Optional[str] = None  # MAC address
    acct_terminate_cause: str = "N/A"
    service_type: Optional[str] = None
    framed_protocol: Optional[str] = None
    framed_ip_address: Optional[str] = None
    framed_ipv6_address: Optional[str] = None
    framed_ipv6_prefix: Optional[str] = None
    framed_interface_id: Optional[str] = None
    delegated_ipv6_prefix: Optional[str] = None
    class_attr: Optional[str] = None

    # ISP Billing linkage
    customer_id: Optional[str] = None
    subscription_id: Optional[str] = None
    site_id: Optional[str] = None
    voucher_id: Optional[str] = None
    package_id: Optional[str] = None

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class RadiusSession(BaseModel):
    """Live session view (computed from latest accounting Start without Stop)."""
    model_config = ConfigDict(populate_by_name=True, json_encoders={ObjectId: str})

    id: Optional[str] = Field(alias="_id", default=None)
    acct_session_id: str
    username: str
    nas_ip_address: str
    nas_port_id: Optional[str] = None
    framed_ip_address: Optional[str] = None
    calling_station_id: Optional[str] = None
    acct_start_time: datetime
    acct_session_time: int = 0
    acct_input_octets: int = 0
    acct_output_octets: int = 0
    customer_id: Optional[str] = None
    subscription_id: Optional[str] = None
    site_id: Optional[str] = None
    status: str = "online"  # online, offline
    last_seen: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))