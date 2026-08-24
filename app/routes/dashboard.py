from fastapi import APIRouter, Depends

from app.core.database import get_database
from app.core.security import get_current_user


router = APIRouter(
    prefix="/api/v1/dashboard",
    tags=["Dashboard"],
)


@router.get("/summary")
async def dashboard_summary(
    current_user=Depends(get_current_user),
):

    db = get_database()

    customers = await db.customers.count_documents(
        {"status": "active"}
    )

    packages = await db.packages.count_documents(
        {"status": "active"}
    )

    subscriptions = await db.subscriptions.count_documents(
        {"status": "active"}
    )

    unpaid_invoices = await db.invoices.count_documents(
        {"status": {"$in": ["unpaid", "partially_paid"]}}
    )

    completed_payments = await db.payments.count_documents(
        {"status": "completed"}
    )

    routers = await db.routers.count_documents({})

    return {
        "customers": customers,
        "active_packages": packages,
        "active_subscriptions": subscriptions,
        "unpaid_invoices": unpaid_invoices,
        "completed_payments": completed_payments,
        "routers": routers,
    }