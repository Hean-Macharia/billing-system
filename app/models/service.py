"""Service package/plan model for MongoDB."""
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional

from bson import ObjectId
from pydantic import BaseModel, BeforeValidator, Field, field_validator
from typing_extensions import Annotated

ObjectIdStr = Annotated[str, BeforeValidator(lambda v: str(v) if isinstance(v, ObjectId) else v)]


class ServiceStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    DEPRECATED = "deprecated"


class ServiceType(str, Enum):
    FTTH = "ftth"
    FTTB = "fttb"
    WIRELESS = "wireless"
    VSAT = "vsat"
    DEDICATED = "dedicated"


class BillingCycle(str, Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    SEMI_ANNUAL = "semi_annual"
    YEARLY = "yearly"


class ServiceFeature(BaseModel):
    name: str
    included: bool = True
    limit: Optional[str] = None


class ServicePlan(BaseModel):
    id: Optional[ObjectIdStr] = Field(None, alias="_id")
    plan_code: str = Field(..., description="Unique plan code e.g. FTTH-10M")
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    service_type: ServiceType = ServiceType.FTTH
    status: ServiceStatus = ServiceStatus.ACTIVE
    download_speed_mbps: int = Field(..., gt=0)
    upload_speed_mbps: int = Field(..., gt=0)
    burst_speed_mbps: Optional[int] = None
    base_price_kes: float = Field(..., ge=0)
    setup_fee_kes: float = 0.0
    equipment_fee_kes: float = 0.0
    billing_cycle: BillingCycle = BillingCycle.MONTHLY
    features: List[ServiceFeature] = Field(default_factory=list)
    fair_usage_policy: Optional[str] = None
    data_cap_gb: Optional[int] = None
    minimum_contract_months: int = 0
    early_termination_fee_kes: float = 0.0
    grace_period_days: int = 7
    target_customer_types: List[str] = Field(default_factory=lambda: ["residential"])
    tags: List[str] = Field(default_factory=list)
    popularity_score: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    created_by: Optional[str] = None

    class Config:
        populate_by_name = True
        json_encoders = {datetime: lambda v: v.isoformat(), ObjectId: lambda v: str(v)}


class ServicePlanInDB(ServicePlan):
    pass


# ============================================================
# ✅ ALIASES for compatibility with other imports
# ============================================================
Service = ServicePlan
ServiceInDB = ServicePlanInDB


# ============================================================
# ✅ Additional model for simple service reference (if needed)
# ============================================================
class Service(BaseModel):
    """Simple Service model for backward compatibility."""
    id: Optional[ObjectIdStr] = Field(None, alias="_id")
    name: str
    description: Optional[str] = None
    service_type: ServiceType = ServiceType.FTTH
    status: ServiceStatus = ServiceStatus.ACTIVE
    price: float = 0.0
    setup_fee: float = 0.0
    bandwidth: int = 0  # in Mbps (0 = unlimited)
    validity_days: int = 30
    features: List[str] = []
    is_public: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = None
    
    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}