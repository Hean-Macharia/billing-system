"""Pydantic schemas for service plan endpoints."""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from app.models.service import BillingCycle, ServiceStatus, ServiceType


class ServiceFeatureCreate(BaseModel):
    name: str
    included: bool = True
    limit: Optional[str] = None


class ServicePlanCreate(BaseModel):
    plan_code: str = Field(..., min_length=2, max_length=50)
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    service_type: ServiceType = ServiceType.FTTH
    download_speed_mbps: int = Field(..., gt=0)
    upload_speed_mbps: int = Field(..., gt=0)
    burst_speed_mbps: Optional[int] = None
    base_price_kes: float = Field(..., ge=0)
    setup_fee_kes: float = 0.0
    equipment_fee_kes: float = 0.0
    billing_cycle: BillingCycle = BillingCycle.MONTHLY
    features: List[ServiceFeatureCreate] = Field(default_factory=list)
    fair_usage_policy: Optional[str] = None
    data_cap_gb: Optional[int] = None
    minimum_contract_months: int = 0
    early_termination_fee_kes: float = 0.0
    grace_period_days: int = 7
    target_customer_types: List[str] = Field(default_factory=lambda: ["residential"])
    tags: List[str] = Field(default_factory=list)
    popularity_score: int = 0


class ServicePlanUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    status: Optional[ServiceStatus] = None
    download_speed_mbps: Optional[int] = Field(None, gt=0)
    upload_speed_mbps: Optional[int] = Field(None, gt=0)
    burst_speed_mbps: Optional[int] = None
    base_price_kes: Optional[float] = Field(None, ge=0)
    setup_fee_kes: Optional[float] = None
    equipment_fee_kes: Optional[float] = None
    billing_cycle: Optional[BillingCycle] = None
    features: Optional[List[ServiceFeatureCreate]] = None
    fair_usage_policy: Optional[str] = None
    data_cap_gb: Optional[int] = None
    minimum_contract_months: Optional[int] = None
    early_termination_fee_kes: Optional[float] = None
    grace_period_days: Optional[int] = None
    target_customer_types: Optional[List[str]] = None
    tags: Optional[List[str]] = None
    popularity_score: Optional[int] = None


class ServicePlanResponse(BaseModel):
    id: str = Field(..., alias="_id")
    plan_code: str
    name: str
    description: Optional[str] = None
    service_type: str
    status: str
    download_speed_mbps: int
    upload_speed_mbps: int
    burst_speed_mbps: Optional[int] = None
    base_price_kes: float
    setup_fee_kes: float
    equipment_fee_kes: float
    billing_cycle: str
    features: List[dict] = Field(default_factory=list)
    fair_usage_policy: Optional[str] = None
    data_cap_gb: Optional[int] = None
    minimum_contract_months: int
    early_termination_fee_kes: float
    grace_period_days: int
    target_customer_types: List[str]
    tags: List[str]
    popularity_score: int
    created_at: datetime
    updated_at: datetime
    created_by: Optional[str] = None

    class Config:
        populate_by_name = True