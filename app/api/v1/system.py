"""System health and info endpoints."""
from datetime import datetime, timezone

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.database import database
from app.utils.helpers import error_response, success_response

router = APIRouter(prefix="/api/v1/system", tags=["System"])


@router.get("/info")
async def system_info(request: Request):
    """Get system information and feature flags."""
    db_connected = False
    try:
        db_connected = await database.is_healthy()
    except Exception:
        db_connected = False

    return success_response(
        message="System information",
        data={
            "name": settings.app_name,
            "version": settings.app_version,
            "environment": settings.app_env,
            "debug": settings.debug,
            "timezone": settings.timezone,
            "currency": settings.currency,
            "features": {
                "authentication": True,
                "billing": True,
                "customer_lifecycle": True,
                "subscriptions": True,
                "invoices": True,
                "payments": True,
                "mpesa": True,
                "radius": True,
                "mikrotik": True,
                "vouchers": True,
                "customer_portal": True,
                "notifications": True,
                "admin_dashboard": True,
                "automation": True,
            },
            "lifecycle": {
                "customers": True,
                "service_plans": True,
                "subscriptions": True,
                "billing": True,
                "payments": True,
                "support": True,
            },
            "status": {
                "database": "connected" if db_connected else "unknown",
                "scheduler": "online",
            },
        },
    )