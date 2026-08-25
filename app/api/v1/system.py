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
                "billing": False,
                "mpesa": False,
                "radius": False,
                "mikrotik": False,
                "vouchers": False,
                "customer_portal": False,
                "notifications": False,
            },
        },
    )