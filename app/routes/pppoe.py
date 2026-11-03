"""Staff API for PPPoE subscriber provisioning and service control."""
from typing import Optional
from datetime import datetime, timezone

from bson import ObjectId
from fastapi import APIRouter, Depends, Request, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.dependencies import get_db, require_permission
from app.core.exceptions import NotFoundError
from app.models.user import Permission, UserInDB
from app.schemas.pppoe import PppoePasswordReset, PppoeStatusChange, PppoeSubscriberCreate, PppoeSubscriberUpdate
from app.services.pppoe_service import PppoeService
from app.services.router_service import RouterService
from app.utils.helpers import paginated_response, success_response

router = APIRouter(prefix="/api/v1/pppoe", tags=["PPPoE"])


@router.get("/subscribers", response_model=dict)
async def list_subscribers(
    request: Request, site_id: Optional[str] = None, status: Optional[str] = None,
    page: int = 1, limit: int = 50,
    current_user: UserInDB = Depends(require_permission(Permission.SUBSCRIPTIONS_READ)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    rows, total = await PppoeService(db).list_subscribers(site_id, status, page, limit)
    return paginated_response(data=rows, total=total, page=page, limit=min(max(limit, 1), 100))


@router.post("/subscribers", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_subscriber(
    request: Request, data: PppoeSubscriberCreate,
    current_user: UserInDB = Depends(require_permission(Permission.SUBSCRIPTIONS_CREATE)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    created = await PppoeService(db).create_subscriber(data)
    return success_response(message="PPPoE subscriber provisioned as pending payment", data=created, status_code=201)


@router.get("/subscribers/{subscription_id}", response_model=dict)
async def get_subscriber(
    request: Request, subscription_id: str,
    current_user: UserInDB = Depends(require_permission(Permission.SUBSCRIPTIONS_READ)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    return success_response(data=await PppoeService(db).get_subscriber(subscription_id))


@router.patch("/subscribers/{subscription_id}", response_model=dict)
async def update_subscriber(
    request: Request, subscription_id: str, data: PppoeSubscriberUpdate,
    current_user: UserInDB = Depends(require_permission(Permission.SUBSCRIPTIONS_UPDATE)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    service = PppoeService(db)
    update = data.model_dump(exclude_unset=True, exclude_none=True)
    if "plan_id" in update:
        subscriber = await service.update_package(subscription_id, update["plan_id"])
    else:
        subscriber = await service.get_subscriber(subscription_id)
        try:
            sub_oid = ObjectId(subscription_id)
        except Exception as exc:
            raise NotFoundError("PPPoE subscriber not found") from exc
        subscription_update = {key: update[key] for key in ("ip_address", "framed_ip_pool") if key in update}
        radius_update = {"framed_ip_address" if key == "ip_address" else key: value for key, value in subscription_update.items()}
        if subscription_update:
            await db.subscriptions.update_one({"_id": sub_oid, "service_type": "pppoe"}, {"$set": subscription_update})
            await db.radius_users.update_one({"subscription_id": subscription_id, "user_type": "pppoe"}, {"$set": radius_update})
            subscriber = await service.get_subscriber(subscription_id)
    return success_response(message="PPPoE subscriber updated", data=subscriber)


@router.post("/subscribers/{subscription_id}/suspend", response_model=dict)
async def suspend_subscriber(
    request: Request, subscription_id: str, data: PppoeStatusChange,
    current_user: UserInDB = Depends(require_permission(Permission.SUBSCRIPTIONS_UPDATE)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    subscriber = await PppoeService(db).set_status(subscription_id, "suspended", data.reason)
    session = await db.radius_sessions.find_one({"subscription_id": subscription_id, "status": "online"})
    disconnected = False
    if session and subscriber.get("router_id") and session.get("username"):
        result = await RouterService(db).disconnect_pppoe_user(subscriber["router_id"], session["username"])
        disconnected = bool(result.get("disconnected"))
        if disconnected:
            await db.radius_sessions.update_one(
                {"_id": session["_id"], "status": "online"},
                {"$set": {"status": "offline", "last_seen": datetime.now(timezone.utc)}},
            )
    return success_response(message="PPPoE authentication suspended", data={**subscriber, "disconnect_confirmed": disconnected})


@router.post("/subscribers/{subscription_id}/reactivate", response_model=dict)
async def reactivate_subscriber(
    request: Request, subscription_id: str,
    current_user: UserInDB = Depends(require_permission(Permission.SUBSCRIPTIONS_UPDATE)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    # Restoration is only allowed through the existing billing guard, which
    # checks that no unpaid invoices remain. A staff click cannot create a
    # paid/active subscription by itself.
    service = PppoeService(db)
    try:
        subscription_oid = ObjectId(subscription_id)
    except Exception as exc:
        raise NotFoundError("PPPoE subscriber not found") from exc
    sub = await db.subscriptions.find_one({"_id": subscription_oid, "service_type": "pppoe"})
    if not sub:
        raise NotFoundError("PPPoE subscriber not found")
    from app.services.automation_service import AutomationService
    if not await AutomationService(db).try_restore_customer(str(sub["customer_id"])):
        raise NotFoundError("Subscription cannot be reactivated until billing is settled")
    updated = await service.get_subscriber(subscription_id)
    if updated.get("status") != "active":
        raise NotFoundError("Subscription cannot be reactivated because its paid term has expired")
    return success_response(message="PPPoE service restored after billing validation", data=updated)


@router.post("/subscribers/{subscription_id}/reset-password", response_model=dict)
async def reset_password(
    request: Request, subscription_id: str, data: PppoePasswordReset,
    current_user: UserInDB = Depends(require_permission(Permission.SUBSCRIPTIONS_UPDATE)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    await PppoeService(db).reset_password(subscription_id, data.password)
    return success_response(message="PPPoE credential reset; the new password was not returned")


@router.get("/subscribers/{subscription_id}/sessions", response_model=dict)
async def subscriber_sessions(
    request: Request, subscription_id: str,
    current_user: UserInDB = Depends(require_permission(Permission.SUBSCRIPTIONS_READ)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    try:
        subscription_oid = ObjectId(subscription_id)
    except Exception as exc:
        raise NotFoundError("PPPoE subscriber not found") from exc
    if not await db.subscriptions.find_one({"_id": subscription_oid, "service_type": "pppoe"}, {"_id": 1}):
        raise NotFoundError("PPPoE subscriber not found")
    rows = await db.radius_sessions.find({"subscription_id": subscription_id}).sort("acct_start_time", -1).limit(100).to_list(length=100)
    for row in rows:
        row["_id"] = str(row["_id"])
        row.pop("credential", None)
    return success_response(data=rows)
