from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.database import get_database
from app.core.security import get_current_user
from app.schemas.customer import (
    CustomerCreate,
    CustomerResponse,
    CustomerUpdate,
)


router = APIRouter(
    prefix="/api/v1/customers",
    tags=["Customers"],
)


@router.post(
    "",
    response_model=CustomerResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_customer(
    customer: CustomerCreate,
    current_user=Depends(get_current_user),
):
    database = get_database()

    existing = await database.customers.find_one(
        {
            "$or": [
                {"phone": customer.phone},
                {"email": customer.email},
            ]
        }
    )

    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A customer with this phone or email already exists",
        )

    now = datetime.now(timezone.utc)

    customer_document = {
        "customer_id": str(ObjectId()),
        "full_name": customer.full_name,
        "phone": customer.phone,
        "email": customer.email,
        "address": customer.address,
        "customer_type": customer.customer_type,
        "status": "active",
        "created_at": now,
        "updated_at": now,
        "created_by": current_user.get("user_id"),
    }

    await database.customers.insert_one(customer_document)

    return customer_document


@router.get(
    "",
    response_model=list[CustomerResponse],
)
async def list_customers(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    current_user=Depends(get_current_user),
):
    database = get_database()

    customers = (
        await database.customers
        .find({})
        .skip(skip)
        .limit(limit)
        .to_list(length=limit)
    )

    for customer in customers:
        customer.pop("_id", None)

    return customers


@router.get(
    "/{customer_id}",
    response_model=CustomerResponse,
)
async def get_customer(
    customer_id: str,
    current_user=Depends(get_current_user),
):
    database = get_database()

    customer = await database.customers.find_one(
        {
            "customer_id": customer_id
        }
    )

    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found",
        )

    customer.pop("_id", None)

    return customer


@router.patch(
    "/{customer_id}",
    response_model=CustomerResponse,
)
async def update_customer(
    customer_id: str,
    customer: CustomerUpdate,
    current_user=Depends(get_current_user),
):
    database = get_database()

    update_data = customer.model_dump(
        exclude_unset=True
    )

    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields provided for update",
        )

    update_data["updated_at"] = datetime.now(timezone.utc)

    result = await database.customers.update_one(
        {
            "customer_id": customer_id
        },
        {
            "$set": update_data
        },
    )

    if result.matched_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found",
        )

    updated_customer = await database.customers.find_one(
        {
            "customer_id": customer_id
        }
    )

    updated_customer.pop("_id", None)

    return updated_customer


@router.delete(
    "/{customer_id}",
)
async def delete_customer(
    customer_id: str,
    current_user=Depends(get_current_user),
):
    database = get_database()

    result = await database.customers.update_one(
        {
            "customer_id": customer_id
        },
        {
            "$set": {
                "status": "deleted",
                "updated_at": datetime.now(timezone.utc),
            }
        },
    )

    if result.matched_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found",
        )

    return {
        "message": "Customer deleted successfully",
        "customer_id": customer_id,
    }