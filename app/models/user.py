"""User model for MongoDB with roles and permissions."""
from datetime import datetime, timezone
from enum import Enum
from typing import Any, List, Optional

from bson import ObjectId
from pydantic import BaseModel, BeforeValidator, EmailStr, Field, field_validator
from typing_extensions import Annotated


# Custom validator to convert ObjectId to string
ObjectIdStr = Annotated[str, BeforeValidator(lambda v: str(v) if isinstance(v, ObjectId) else v)]


class UserRole(str, Enum):
    SUPER_ADMIN = "super_admin"
    ADMIN = "admin"
    BILLING_MANAGER = "billing_manager"
    NETWORK_ADMIN = "network_admin"
    TECHNICIAN = "technician"
    SALES_AGENT = "sales_agent"
    SUPPORT_AGENT = "support_agent"
    RESELLER = "reseller"
    CUSTOMER = "customer"


class UserStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    PENDING = "pending"


# Permission constants
class Permission:
    USERS_READ = "users.read"
    USERS_CREATE = "users.create"
    USERS_UPDATE = "users.update"
    USERS_DELETE = "users.delete"
    CUSTOMERS_READ = "customers.read"
    CUSTOMERS_CREATE = "customers.create"
    CUSTOMERS_UPDATE = "customers.update"
    CUSTOMERS_DELETE = "customers.delete"
    SERVICES_READ = "services.read"
    SERVICES_CREATE = "services.create"
    SERVICES_UPDATE = "services.update"
    SERVICES_DELETE = "services.delete"
    SUBSCRIPTIONS_READ = "subscriptions.read"
    SUBSCRIPTIONS_CREATE = "subscriptions.create"
    SUBSCRIPTIONS_UPDATE = "subscriptions.update"
    SUBSCRIPTIONS_DELETE = "subscriptions.delete"
    INVOICES_READ = "invoices.read"
    INVOICES_CREATE = "invoices.create"
    INVOICES_UPDATE = "invoices.update"
    INVOICES_DELETE = "invoices.delete"
    PAYMENTS_READ = "payments.read"
    PAYMENTS_CREATE = "payments.create"
    PAYMENTS_UPDATE = "payments.update"
    PAYMENTS_DELETE = "payments.delete"
    VOUCHERS_READ = "vouchers.read"
    VOUCHERS_CREATE = "vouchers.create"
    VOUCHERS_UPDATE = "vouchers.update"
    VOUCHERS_DELETE = "vouchers.delete"
    ROUTERS_READ = "routers.read"
    ROUTERS_CREATE = "routers.create"
    ROUTERS_UPDATE = "routers.update"
    ROUTERS_DELETE = "routers.delete"
    RADIUS_READ = "radius.read"
    RADIUS_MANAGE = "radius.manage"
    MPESA_READ = "mpesa.read"
    MPESA_MANAGE = "mpesa.manage"
    REPORTS_READ = "reports.read"
    REPORTS_CREATE = "reports.create"
    SETTINGS_READ = "settings.read"
    SETTINGS_UPDATE = "settings.update"
    AUDIT_READ = "audit.read"


# Role-to-permissions mapping
ROLE_PERMISSIONS = {
    UserRole.SUPER_ADMIN: [getattr(Permission, p) for p in dir(Permission) if not p.startswith("_")],
    UserRole.ADMIN: [
        Permission.USERS_READ, Permission.USERS_CREATE, Permission.USERS_UPDATE,
        Permission.CUSTOMERS_READ, Permission.CUSTOMERS_CREATE, Permission.CUSTOMERS_UPDATE, Permission.CUSTOMERS_DELETE,
        Permission.SERVICES_READ, Permission.SERVICES_CREATE, Permission.SERVICES_UPDATE, Permission.SERVICES_DELETE,
        Permission.SUBSCRIPTIONS_READ, Permission.SUBSCRIPTIONS_CREATE, Permission.SUBSCRIPTIONS_UPDATE, Permission.SUBSCRIPTIONS_DELETE,
        Permission.INVOICES_READ, Permission.INVOICES_CREATE, Permission.INVOICES_UPDATE, Permission.INVOICES_DELETE,
        Permission.PAYMENTS_READ, Permission.PAYMENTS_CREATE, Permission.PAYMENTS_UPDATE,
        Permission.VOUCHERS_READ, Permission.VOUCHERS_CREATE, Permission.VOUCHERS_UPDATE, Permission.VOUCHERS_DELETE,
        Permission.ROUTERS_READ, Permission.ROUTERS_CREATE, Permission.ROUTERS_UPDATE, Permission.ROUTERS_DELETE,
        Permission.RADIUS_READ, Permission.RADIUS_MANAGE,
        Permission.MPESA_READ, Permission.MPESA_MANAGE,
        Permission.REPORTS_READ, Permission.REPORTS_CREATE,
        Permission.SETTINGS_READ, Permission.SETTINGS_UPDATE,
        Permission.AUDIT_READ,
    ],
    UserRole.BILLING_MANAGER: [
        Permission.CUSTOMERS_READ, Permission.CUSTOMERS_CREATE, Permission.CUSTOMERS_UPDATE,
        Permission.SERVICES_READ,
        Permission.SUBSCRIPTIONS_READ, Permission.SUBSCRIPTIONS_CREATE, Permission.SUBSCRIPTIONS_UPDATE,
        Permission.INVOICES_READ, Permission.INVOICES_CREATE, Permission.INVOICES_UPDATE,
        Permission.PAYMENTS_READ, Permission.PAYMENTS_CREATE, Permission.PAYMENTS_UPDATE,
        Permission.VOUCHERS_READ, Permission.VOUCHERS_CREATE, Permission.VOUCHERS_UPDATE,
        Permission.REPORTS_READ, Permission.REPORTS_CREATE,
    ],
    UserRole.NETWORK_ADMIN: [
        Permission.CUSTOMERS_READ,
        Permission.SERVICES_READ, Permission.SERVICES_CREATE, Permission.SERVICES_UPDATE,
        Permission.ROUTERS_READ, Permission.ROUTERS_CREATE, Permission.ROUTERS_UPDATE, Permission.ROUTERS_DELETE,
        Permission.RADIUS_READ, Permission.RADIUS_MANAGE,
        Permission.REPORTS_READ,
    ],
    UserRole.TECHNICIAN: [
        Permission.CUSTOMERS_READ, Permission.CUSTOMERS_UPDATE,
        Permission.ROUTERS_READ, Permission.ROUTERS_UPDATE,
        Permission.RADIUS_READ,
    ],
    UserRole.SALES_AGENT: [
        Permission.CUSTOMERS_READ, Permission.CUSTOMERS_CREATE, Permission.CUSTOMERS_UPDATE,
        Permission.SERVICES_READ,
        Permission.SUBSCRIPTIONS_READ, Permission.SUBSCRIPTIONS_CREATE,
        Permission.VOUCHERS_READ, Permission.VOUCHERS_CREATE,
    ],
    UserRole.SUPPORT_AGENT: [
        Permission.CUSTOMERS_READ, Permission.CUSTOMERS_UPDATE,
        Permission.SERVICES_READ,
        Permission.SUBSCRIPTIONS_READ, Permission.SUBSCRIPTIONS_UPDATE,
        Permission.INVOICES_READ,
        Permission.PAYMENTS_READ,
        Permission.VOUCHERS_READ, Permission.VOUCHERS_UPDATE,
    ],
    UserRole.RESELLER: [
        Permission.CUSTOMERS_READ, Permission.CUSTOMERS_CREATE, Permission.CUSTOMERS_UPDATE,
        Permission.SERVICES_READ,
        Permission.SUBSCRIPTIONS_READ, Permission.SUBSCRIPTIONS_CREATE,
        Permission.VOUCHERS_READ, Permission.VOUCHERS_CREATE,
    ],
    UserRole.CUSTOMER: [
        Permission.CUSTOMERS_READ,
        Permission.INVOICES_READ,
        Permission.PAYMENTS_READ,
        Permission.SUBSCRIPTIONS_READ,
    ],
}


def get_permissions_for_role(role: UserRole) -> List[str]:
    return ROLE_PERMISSIONS.get(role, [])


def has_permission(role: UserRole, permission: str) -> bool:
    return permission in ROLE_PERMISSIONS.get(role, [])


class User(BaseModel):
    id: Optional[ObjectIdStr] = Field(None, alias="_id")
    email: EmailStr
    username: str = Field(..., min_length=3, max_length=50)
    full_name: str = Field(..., min_length=1, max_length=100)
    hashed_password: str
    role: UserRole = UserRole.CUSTOMER
    status: UserStatus = UserStatus.PENDING
    phone: Optional[str] = None
    avatar_url: Optional[str] = None
    permissions: List[str] = Field(default_factory=list)
    is_email_verified: bool = False
    last_login: Optional[datetime] = None
    password_changed_at: Optional[datetime] = None
    failed_login_attempts: int = 0
    locked_until: Optional[datetime] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    created_by: Optional[str] = None

    class Config:
        populate_by_name = True
        json_encoders = {datetime: lambda v: v.isoformat(), ObjectId: lambda v: str(v)}


class UserInDB(User):
    refresh_tokens: List[str] = Field(default_factory=list)