"""Admin dashboard summary endpoint.

Was previously calling an undefined get_database() (NameError on every
request) - fixed to use the same Depends(get_db) pattern as every other
route in the app.
"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.dependencies import get_db, require_permission
from app.models.user import Permission, UserInDB
from app.utils.helpers import success_response

router = APIRouter(prefix="/api/v1/dashboard", tags=["Dashboard"])


@router.get("/summary", response_model=dict)
async def dashboard_summary(
    current_user: UserInDB = Depends(require_permission(Permission.REPORTS_READ)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    thirty_days_ago = now - timedelta(days=30)

    customers = await db.customers.count_documents({"status": "active"})
    total_customers = await db.customers.count_documents({})
    service_plans = await db.service_plans.count_documents({"status": "active"})
    active_subscriptions = await db.subscriptions.count_documents({"status": "active"})
    unpaid_invoices = await db.invoices.count_documents({"status": {"$in": ["unpaid", "partially_paid", "overdue"]}})
    overdue_invoices = await db.invoices.count_documents({"status": "overdue"})

    revenue_cursor = db.payments.aggregate([
        {"$match": {"status": "completed", "created_at": {"$gte": month_start}}},
        {"$group": {"_id": None, "total": {"$sum": "$amount_kes"}}},
    ])
    revenue_docs = await revenue_cursor.to_list(length=1)
    revenue_this_month = revenue_docs[0]["total"] if revenue_docs else 0.0

    recent_payments_cursor = db.payments.aggregate([
        {"$match": {"status": "completed", "created_at": {"$gte": thirty_days_ago}}},
        {"$group": {"_id": None, "total": {"$sum": "$amount_kes"}, "count": {"$sum": 1}}},
    ])
    recent_docs = await recent_payments_cursor.to_list(length=1)
    revenue_last_30_days = recent_docs[0]["total"] if recent_docs else 0.0
    payments_last_30_days = recent_docs[0]["count"] if recent_docs else 0

    active_vouchers = await db.vouchers.count_documents({"status": "active"})
    online_sessions = await db.radius_sessions.count_documents({"status": "online"}) if "radius_sessions" in await db.list_collection_names() else 0
    routers_total = await db.routers.count_documents({})
    routers_online = await db.routers.count_documents({"status": "online"})

    return success_response(
        message="Dashboard summary retrieved",
        data={
            "customers": {"active": customers, "total": total_customers},
            "service_plans_active": service_plans,
            "subscriptions_active": active_subscriptions,
            "invoices": {"unpaid": unpaid_invoices, "overdue": overdue_invoices},
            "revenue": {"this_month_kes": revenue_this_month, "last_30_days_kes": revenue_last_30_days},
            "payments_last_30_days": payments_last_30_days,
            "vouchers_active": active_vouchers,
            "sessions_online": online_sessions,
            "routers": {"total": routers_total, "online": routers_online},
        },
    )
