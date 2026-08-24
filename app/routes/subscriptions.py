from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException

from app.core.database import get_database
from app.core.security import get_current_user
from app.schemas.subscription import (
    SubscriptionCreate,
    SubscriptionUpdate,
)


router = APIRouter(
    prefix="/api/v1/subscriptions",
    tags=["Subscriptions"],
)


@router.post("/")
async def create_subscription(
    data: SubscriptionCreate,
    current_user=Depends(get_current_user),
):

    db = get_database()

    customer = await db.customers.find_one(
        {"customer_id": data.customer_id}
    )

    if not customer:
        raise HTTPException(
            status_code=404,
            detail="Customer not found",
        )

    package = await db.packages.find_one(
        {"package_id": data.package_id}
    )

    if not package:
        raise HTTPException(
            status_code=404,
            detail="Package not found",
        )

    subscription_id = (
        f"SUB-{uuid4().hex[:8].upper()}"
    )

    document = {
        "subscription_id": subscription_id,
        "customer_id": data.customer_id,
        "package_id": data.package_id,
        "status": "active",
        "start_date": data.start_date,
        "end_date": data.end_date,
        "auto_renew": data.auto_renew,
    }

    await db.subscriptions.insert_one(document)

    document.pop("_id", None)

    return document


@router.get("/")
async def get_subscriptions(
    current_user=Depends(get_current_user),
):

    db = get_database()

    subscriptions = []

    cursor = db.subscriptions.find({})

    async for item in cursor:
        item.pop("_id", None)
        subscriptions.append(item)

    return {
        "count": len(subscriptions),
        "subscriptions": subscriptions,
    }


@router.patch("/{subscription_id}")
async def update_subscription(
    subscription_id: str,
    data: SubscriptionUpdate,
    current_user=Depends(get_current_user),
):

    db = get_database()

    update_data = data.model_dump(
        exclude_unset=True
    )

    result = await db.subscriptions.update_one(
        {"subscription_id": subscription_id},
        {"$set": update_data},
    )

    if result.matched_count == 0:
        raise HTTPException(
            status_code=404,
            detail="Subscription not found",
        )

    subscription = await db.subscriptions.find_one(
        {"subscription_id": subscription_id}
    )

    subscription.pop("_id", None)

    return subscription