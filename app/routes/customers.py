"""Customer API routes."""
from typing import Optional

from fastapi import APIRouter, Depends, Request, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.dependencies import get_current_user, get_db, require_permission
from app.core.logging import get_logger
from app.models.user import Permission, UserInDB
from app.schemas.customer import CustomerCreate, CustomerResponse, CustomerUpdate
from app.services.customer_service import CustomerService
from app.utils.helpers import paginated_response, success_response

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1/customers", tags=["Customers"])


def _to_customer_response(customer) -> dict:
    """Convert CustomerInDB to response dict."""
    return {
        "_id": str(customer.id),
        "customer_code": customer.customer_code,
        "user_id": customer.user_id,
        "full_name": customer.full_name,
        "email": customer.email,
        "phone": customer.phone,
        "alt_phone": customer.alt_phone,
        "customer_type": customer.customer_type.value,
        "status": customer.status.value,
        "address": customer.address.model_dump() if customer.address else None,
        "installation_address": customer.installation_address.model_dump() if customer.installation_address else None,
        "company_name": customer.company_name,
        "company_reg_no": customer.company_reg_no,
        "tax_pin": customer.tax_pin,
        "industry": customer.industry,
        "contacts": [c.model_dump() for c in customer.contacts] if customer.contacts else [],
        "current_package": customer.current_package.model_dump() if customer.current_package else None,
        "router": customer.router.model_dump() if customer.router else None,
        "ip_pool": customer.ip_pool,
        "billing_day": customer.billing_day,
        "auto_billing": customer.auto_billing,
        "payment_method": customer.payment_method,
        "outstanding_balance": customer.outstanding_balance,
        "credit_limit": customer.credit_limit,
        "tags": customer.tags,
        "notes": customer.notes,
        "referral_source": customer.referral_source,
        "assigned_to": customer.assigned_to,
        "created_by": customer.created_by,
        "created_at": customer.created_at.isoformat() if customer.created_at else None,
        "updated_at": customer.updated_at.isoformat() if customer.updated_at else None,
        "last_billed_at": customer.last_billed_at.isoformat() if customer.last_billed_at else None,
        "last_payment_at": customer.last_payment_at.isoformat() if customer.last_payment_at else None,
    }


@router.post("", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_customer(
    request: Request,
    data: CustomerCreate,
    current_user: UserInDB = Depends(require_permission(Permission.CUSTOMERS_CREATE)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Create a new customer."""
    service = CustomerService(db)
    customer = await service.create(data, created_by=str(current_user.id))
    return success_response(
        message="Customer created successfully",
        data=_to_customer_response(customer),
    )


@router.get("", response_model=dict)
async def list_customers(
    request: Request,
    status: Optional[str] = None,
    customer_type: Optional[str] = None,
    search: Optional[str] = None,
    assigned_to: Optional[str] = None,
    package_id: Optional[str] = None,
    page: int = 1,
    limit: int = 20,
    current_user: UserInDB = Depends(require_permission(Permission.CUSTOMERS_READ)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """List all customers with filters."""
    service = CustomerService(db)
    customers, total = await service.list_customers(
        status=status,
        customer_type=customer_type,
        search=search,
        assigned_to=assigned_to,
        package_id=package_id,
        page=page,
        limit=limit,
    )
    return paginated_response(
        data=[_to_customer_response(c) for c in customers],
        total=total,
        page=page,
        limit=limit,
        message="Customers retrieved successfully",
    )


@router.get("/{customer_id}", response_model=dict)
async def get_customer(
    request: Request,
    customer_id: str,
    current_user: UserInDB = Depends(require_permission(Permission.CUSTOMERS_READ)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Get a specific customer by ID."""
    service = CustomerService(db)
    customer = await service.get_by_id(customer_id)
    return success_response(
        message="Customer retrieved successfully",
        data=_to_customer_response(customer),
    )


@router.patch("/{customer_id}", response_model=dict)
async def update_customer(
    request: Request,
    customer_id: str,
    data: CustomerUpdate,
    current_user: UserInDB = Depends(require_permission(Permission.CUSTOMERS_UPDATE)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Update a customer."""
    service = CustomerService(db)
    customer = await service.update(customer_id, data)
    return success_response(
        message="Customer updated successfully",
        data=_to_customer_response(customer),
    )


@router.delete("/{customer_id}", response_model=dict)
async def delete_customer(
    request: Request,
    customer_id: str,
    current_user: UserInDB = Depends(require_permission(Permission.CUSTOMERS_DELETE)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Soft delete (deactivate) a customer."""
    service = CustomerService(db)
    await service.delete(customer_id)
    return success_response(message="Customer deactivated successfully")


@router.patch("/{customer_id}/status", response_model=dict)
async def update_customer_status(
    request: Request,
    customer_id: str,
    status: str,
    current_user: UserInDB = Depends(require_permission(Permission.CUSTOMERS_UPDATE)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Update customer status."""
    service = CustomerService(db)
    customer = await service.update_status(customer_id, status)
    return success_response(
        message=f"Customer status updated to {status}",
        data=_to_customer_response(customer),
    )


@router.get("/code/{customer_code}", response_model=dict)
async def get_customer_by_code(
    request: Request,
    customer_code: str,
    current_user: UserInDB = Depends(require_permission(Permission.CUSTOMERS_READ)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Get customer by customer code."""
    service = CustomerService(db)
    customer = await service.get_by_code(customer_code)
    return success_response(
        message="Customer retrieved successfully",
        data=_to_customer_response(customer),
    )