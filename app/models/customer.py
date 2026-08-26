"""Customer model for MongoDB."""
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from bson import ObjectId
from pydantic import BaseModel, BeforeValidator, EmailStr, Field, field_validator
from typing_extensions import Annotated

ObjectIdStr = Annotated[str, BeforeValidator(lambda v: str(v) if isinstance(v, ObjectId) else v)]


class CustomerStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    PENDING = "pending"


class CustomerType(str, Enum):
    RESIDENTIAL = "residential"
    BUSINESS = "business"
    ENTERPRISE = "enterprise"


class Address(BaseModel):
    street: str
    city: str
    state: Optional[str] = None
    postal_code: Optional[str] = None
    country: str = "Kenya"
    coordinates: Optional[Dict[str, float]] = None  # {"lat": -1.2921, "lng": 36.8219}


class ContactPerson(BaseModel):
    name: str
    phone: str
    email: Optional[EmailStr] = None
    role: Optional[str] = None  # e.g. "IT Manager", "Owner"


class ServicePackage(BaseModel):
    package_id: str
    package_name: str
    bandwidth_down_mbps: int
    bandwidth_up_mbps: int
    price_kes: float
    billing_cycle: str = "monthly"  # monthly, quarterly, yearly
    activation_date: datetime
    expiry_date: Optional[datetime] = None
    status: str = "active"


class RouterAssignment(BaseModel):
    router_id: str
    router_name: str
    ip_address: str
    interface: Optional[str] = None
    assigned_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Customer(BaseModel):
    """MongoDB Customer document model."""
    id: Optional[ObjectIdStr] = Field(None, alias="_id")
    customer_code: str = Field(..., description="Unique customer code e.g. CUST-0001")

    # Account linkage
    user_id: Optional[str] = None  # Links to User model for portal login

    # Basic info
    full_name: str = Field(..., min_length=1, max_length=200)
    email: Optional[EmailStr] = None
    phone: str = Field(..., min_length=1)
    alt_phone: Optional[str] = None

    customer_type: CustomerType = CustomerType.RESIDENTIAL
    status: CustomerStatus = CustomerStatus.PENDING

    # Address
    address: Address
    installation_address: Optional[Address] = None  # Different from billing address

    # Business info (for business/enterprise customers)
    company_name: Optional[str] = None
    company_reg_no: Optional[str] = None
    tax_pin: Optional[str] = None  # KRA PIN for Kenya
    industry: Optional[str] = None

    # Contacts
    contacts: List[ContactPerson] = Field(default_factory=list)

    # Service
    current_package: Optional[ServicePackage] = None
    package_history: List[ServicePackage] = Field(default_factory=list)

    # Network
    router: Optional[RouterAssignment] = None
    ip_pool: Optional[str] = None
    vlan_id: Optional[int] = None

    # Billing
    billing_day: int = Field(default=1, ge=1, le=28)
    auto_billing: bool = True
    payment_method: Optional[str] = None  # mpesa, bank, cash
    outstanding_balance: float = 0.0
    credit_limit: float = 0.0

    # Documents
    id_document_url: Optional[str] = None
    kra_certificate_url: Optional[str] = None
    contract_url: Optional[str] = None

    # Metadata
    referral_source: Optional[str] = None
    notes: Optional[str] = None
    tags: List[str] = Field(default_factory=list)

    # Audit
    created_by: Optional[str] = None
    assigned_to: Optional[str] = None  # Sales agent / technician
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_billed_at: Optional[datetime] = None
    last_payment_at: Optional[datetime] = None

    class Config:
        populate_by_name = True
        json_encoders = {datetime: lambda v: v.isoformat(), ObjectId: lambda v: str(v)}


class CustomerInDB(Customer):
    """Customer as stored in MongoDB (with internal fields)."""
    pass