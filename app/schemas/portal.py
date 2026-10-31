from typing import Literal, Optional

from pydantic import BaseModel, EmailStr, Field, model_validator


class PortalRegisterRequest(BaseModel):
    """Self-service portal activation.

    Proves identity with customer_code + the phone number already on
    file (both set by staff when the account was created) rather than
    an SMS/email OTP, since no notification dispatch infrastructure
    exists in this codebase yet. If the customer record has no email on
    file, the one supplied here is saved to it.
    """
    customer_code: str = Field(..., min_length=1)
    phone: str = Field(..., min_length=1)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)


class PortalStkPushRequest(BaseModel):
    invoice_id: str
    phone_number: str = Field(..., pattern=r"^254[0-9]{9}$", description="2547XXXXXXXX format")


class HotspotPurchaseRequest(BaseModel):
    """Walk-up self-service HotSpot voucher purchase - no customer account needed."""
    plan_id: str
    phone_number: str = Field(..., pattern=r"^254[0-9]{9}$", description="2547XXXXXXXX format")
    device_type: Literal["this_device", "tv", "other"]
    device_mac: str = Field(..., pattern=r"(?i)^(?:[0-9a-f]{2}[:-]){5}[0-9a-f]{2}$")
    ip_address: Optional[str] = None


class HotspotDeviceAttestationRequest(BaseModel):
    """Untrusted RouterOS redirect hints; the relay must independently observe them."""
    ip_address: str = Field(..., min_length=1, max_length=64)
    mac_address: str = Field(..., pattern=r"(?i)^(?:[0-9a-f]{2}[:-]){5}[0-9a-f]{2}$")


class HotspotTrialRequest(BaseModel):
    """A device-bound request for a single short HotSpot trial.

    Captive redirects may provide a client IP instead of its MAC. The route
    resolves either value against a configured router's DHCP leases before
    issuing the trial entitlement.
    """
    client_mac: Optional[str] = Field(default=None, pattern=r"(?i)^(?:[0-9a-f]{2}[:-]){5}[0-9a-f]{2}$")
    ip_address: Optional[str] = None

    @model_validator(mode="after")
    def require_device_context(self):
        if not self.client_mac and not self.ip_address:
            raise ValueError("Provide the hotspot client IP address or MAC address")
        return self


class HotspotDeviceLookupRequest(BaseModel):
    """Find a connected client's MAC from a private LAN IP or confirm a MAC."""
    ip_address: Optional[str] = None
    mac_address: Optional[str] = Field(default=None, pattern=r"(?i)^(?:[0-9a-f]{2}[:-]){5}[0-9a-f]{2}$")
