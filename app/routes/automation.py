"""Admin-facing automation control.

Every job the scheduler runs on a timer (app.core.scheduler) is also
independently triggerable here - useful for testing without waiting for
the schedule, and for an ops dashboard showing "last run" status.
"""
from typing import Optional

from fastapi import APIRouter, Depends
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.dependencies import get_db, require_permission
from app.models.user import Permission, UserInDB
from app.services.automation_service import AutomationService
from app.services.notification_service import NotificationService
from app.utils.helpers import paginated_response, success_response

router = APIRouter(prefix="/api/v1/automation", tags=["Automation"])


@router.get("/status", response_model=dict)
async def automation_status(
    current_user: UserInDB = Depends(require_permission(Permission.AUTOMATION_READ)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Most recent run of each job, for an at-a-glance ops view."""
    service = AutomationService(db)
    job_names = ["billing_cycle", "expiry_sweep", "suspension_sweep", "restoration_sweep", "payment_reconciliation"]
    status = {}
    for job_name in job_names:
        runs = await service.get_recent_runs(job_name=job_name, limit=1)
        status[job_name] = runs[0] if runs else None
    return success_response(message="Automation status retrieved", data=status)


@router.get("/runs", response_model=dict)
async def automation_run_history(
    job_name: Optional[str] = None, limit: int = 50,
    current_user: UserInDB = Depends(require_permission(Permission.AUTOMATION_READ)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    service = AutomationService(db)
    runs = await service.get_recent_runs(job_name=job_name, limit=limit)
    return success_response(message="Run history retrieved", data=runs)


@router.post("/run/billing", response_model=dict)
async def trigger_billing(
    current_user: UserInDB = Depends(require_permission(Permission.AUTOMATION_MANAGE)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    result = await AutomationService(db).run_billing_cycle()
    return success_response(message="Billing cycle complete", data=result)


@router.post("/run/expiry", response_model=dict)
async def trigger_expiry(
    current_user: UserInDB = Depends(require_permission(Permission.AUTOMATION_MANAGE)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    result = await AutomationService(db).run_expiry_sweep()
    return success_response(message="Expiry sweep complete", data=result)


@router.post("/run/suspension", response_model=dict)
async def trigger_suspension(
    current_user: UserInDB = Depends(require_permission(Permission.AUTOMATION_MANAGE)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    result = await AutomationService(db).run_suspension_sweep()
    return success_response(message="Suspension sweep complete", data=result)


@router.post("/run/restoration", response_model=dict)
async def trigger_restoration(
    current_user: UserInDB = Depends(require_permission(Permission.AUTOMATION_MANAGE)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    result = await AutomationService(db).run_restoration_sweep()
    return success_response(message="Restoration sweep complete", data=result)


@router.post("/run/reconciliation", response_model=dict)
async def trigger_reconciliation(
    max_age_hours: int = 24,
    current_user: UserInDB = Depends(require_permission(Permission.AUTOMATION_MANAGE)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    result = await AutomationService(db).run_payment_reconciliation(max_age_hours=max_age_hours)
    return success_response(message="Payment reconciliation complete", data=result)


@router.post("/run/full-cycle", response_model=dict)
async def trigger_full_cycle(
    current_user: UserInDB = Depends(require_permission(Permission.AUTOMATION_MANAGE)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Runs billing → expiry → suspension → restoration → reconciliation in order."""
    result = await AutomationService(db).run_full_cycle()
    return success_response(message="Full automation cycle complete", data=result)


@router.get("/notifications", response_model=dict)
async def list_notifications(
    notification_type: Optional[str] = None, status_filter: Optional[str] = None, page: int = 1, limit: int = 50,
    current_user: UserInDB = Depends(require_permission(Permission.AUTOMATION_READ)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    service = NotificationService(db)
    items, total = await service.list_all(notification_type=notification_type, status=status_filter, page=page, limit=limit)
    return paginated_response(data=[n.model_dump(by_alias=True) for n in items], total=total, page=page, limit=limit)
