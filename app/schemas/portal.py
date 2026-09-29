from typing import Optional

from pydantic import BaseModel, EmailStr, Field


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
