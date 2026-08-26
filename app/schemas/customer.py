"""Pydantic schemas for customer endpoints."""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.models.customer import Address, ContactPerson, CustomerStatus, CustomerType, ServicePackage


class AddressCreate(BaseModel):
    street: str
    city: str
    state: Optional[str] = None
    postal_code: Optional[str] = None
    country: str = "Kenya"
    coordinates: Optional[dict] = None


class ContactPersonCreate(BaseModel):
    name: str
    phone: str
    email: Optional[EmailStr] = None
    role: Optional[str] = None


class ServicePackageCreate(BaseModel):
    package_id: str
    package_name: str
    bandwidth_down_mbps: int = Field(..., gt=0)
    bandwidth_up_mbps: int = Field(..., gt=0)
    price_kes: float = Field(..., ge=0)
    billing_cycle: str = "monthly"
    activation_date: datetime
    expiry_date: Optional[datetime] = None


class CustomerCreate(BaseModel):
    """Create a new customer."""
    customer_code: str = Field(..., min_length=3, max_length=50)
    full_name: str = Field(..., min_length=1, max_length=200)
    email: Optional[EmailStr] = None
    phone: str = Field(..., min_length=1)
    alt_phone: Optional[str] = None
    customer_type: CustomerType = CustomerType.RESIDENTIAL
    address: AddressCreate
    installation_address: Optional[AddressCreate] = None
    company_name: Optional[str] = None
    company_reg_no: Optional[str] = None
    tax_pin: Optional[str] = None
    industry: Optional[str] = None
    contacts: List[ContactPersonCreate] = Field(default_factory=list)
    current_package: Optional[ServicePackageCreate] = None
    billing_day: int = Field(default=1, ge=1, le=28)
    auto_billing: bool = True
    payment_method: Optional[str] = None
    referral_source: Optional[str] = None
    notes: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    user_id: Optional[str] = None  # Link to existing user account

    @field_validator("company_name", "company_reg_no", "tax_pin", "industry")
    @classmethod
    def business_fields_for_business(cls, v, info):
        # Business validation can be added here if needed
        return v


class CustomerUpdate(BaseModel):
    """Update customer fields."""
    full_name: Optional[str] = Field(None, min_length=1, max_length=200)
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    alt_phone: Optional[str] = None
    customer_type: Optional[CustomerType] = None
    status: Optional[CustomerStatus] = None
    address: Optional[AddressCreate] = None
    installation_address: Optional[AddressCreate] = None
    company_name: Optional[str] = None
    company_reg_no: Optional[str] = None
    tax_pin: Optional[str] = None
    industry: Optional[str] = None
    contacts: Optional[List[ContactPersonCreate]] = None
    current_package: Optional[ServicePackageCreate] = None
    billing_day: Optional[int] = Field(None, ge=1, le=28)
    auto_billing: Optional[bool] = None
    payment_method: Optional[str] = None
    outstanding_balance: Optional[float] = None
    credit_limit: Optional[float] = None
    referral_source: Optional[str] = None
    notes: Optional[str] = None
    tags: Optional[List[str]] = None
    assigned_to: Optional[str] = None


class CustomerResponse(BaseModel):
    """Public customer data (returned in responses)."""
    id: str = Field(..., alias="_id")
    customer_code: str
    user_id: Optional[str] = None
    full_name: str
    email: Optional[str] = None
    phone: str
    alt_phone: Optional[str] = None
    customer_type: CustomerType
    status: CustomerStatus
    address: dict
    installation_address: Optional[dict] = None
    company_name: Optional[str] = None
    company_reg_no: Optional[str] = None
    tax_pin: Optional[str] = None
    industry: Optional[str] = None
    contacts: List[dict] = Field(default_factory=list)
    current_package: Optional[dict] = None
    router: Optional[dict] = None
    ip_pool: Optional[str] = None
    billing_day: int
    auto_billing: bool
    payment_method: Optional[str] = None
    outstanding_balance: float
    credit_limit: float
    tags: List[str] = Field(default_factory=list)
    notes: Optional[str] = None
    referral_source: Optional[str] = None
    assigned_to: Optional[str] = None
    created_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    last_billed_at: Optional[datetime] = None
    last_payment_at: Optional[datetime] = None

    class Config:
        populate_by_name = True


class CustomerListResponse(BaseModel):
    """Simplified customer for list views."""
    id: str = Field(..., alias="_id")
    customer_code: str
    full_name: str
    email: Optional[str] = None
    phone: str
    customer_type: CustomerType
    status: CustomerStatus
    current_package: Optional[dict] = None
    outstanding_balance: float
    created_at: datetime

    class Config:
        populate_by_name = True