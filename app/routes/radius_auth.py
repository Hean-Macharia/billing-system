"""RADIUS internal endpoints for FreeRADIUS rlm_rest.

These endpoints are called by FreeRADIUS, NOT by end users.
They should be protected by IP whitelist and/or shared secret.
"""
from fastapi import APIRouter, Depends, Request, Header, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.core.dependencies import get_db
from typing import Optional

from app.core.config import settings
from app.core.database import database
from app.core.logging import get_logger
from app.schemas.radius_auth import RadiusAccountingRequest, RadiusAuthRequest
from app.services.radius_auth_service import RadiusAuthService

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1/radius", tags=["RADIUS Internal"], include_in_schema=False)


def verify_radius_secret(x_radius_secret: str = Header(None, alias="X-RADIUS-Secret")):
    """Verify shared secret from FreeRADIUS."""
    expected = getattr(settings, "RADIUS_SECRET", "")
    if not expected:
        logger.warning("RADIUS_SECRET not configured, skipping secret check")
        return True
    if not x_radius_secret or x_radius_secret != expected:
        logger.warning(f"Invalid RADIUS secret from caller")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid RADIUS secret")
    return True


@router.post("/auth", response_model=dict)
async def radius_auth(
    request: Request,
    data: RadiusAuthRequest,
    db: AsyncIOMotorDatabase = Depends(get_db),
    _: bool = Depends(verify_radius_secret),
):
    """FreeRADIUS Access-Request handler.

    Called by FreeRADIUS rlm_rest for every authentication attempt.
    Returns JSON that rlm_rest converts to RADIUS attributes.
    """
    service = RadiusAuthService(db)
    reply = await service.authenticate(data)
    # Convert Pydantic to dict with alias keys for FreeRADIUS
    return reply.model_dump(by_alias=True, exclude_none=True)


@router.post("/accounting", status_code=status.HTTP_204_NO_CONTENT)
async def radius_accounting(
    request: Request,
    data: RadiusAccountingRequest,
    db: AsyncIOMotorDatabase = Depends(get_db),
    _: bool = Depends(verify_radius_secret),
):
    """FreeRADIUS Accounting-Request handler.

    Called by FreeRADIUS rlm_rest for Start, Stop, Interim-Update.
    Returns 204 No Content on success.
    """
    service = RadiusAuthService(db)
    await service.accounting(data)
    return None


@router.get("/sessions/online", response_model=dict)
async def list_online_sessions(
    request: Request,
    site_id: Optional[str] = None,
    nas_ip: Optional[str] = None,
    page: int = 1,
    limit: int = 50,
    db: AsyncIOMotorDatabase = Depends(get_db),
    _: bool = Depends(verify_radius_secret),
):
    """List currently online RADIUS sessions."""
    service = RadiusAuthService(db)
    sessions, total = await service.get_online_sessions(site_id=site_id, nas_ip=nas_ip, page=page, limit=limit)
    return {
        "success": True,
        "message": "Online sessions retrieved",
        "data": sessions,
        "pagination": {"total": total, "page": page, "limit": limit, "pages": (total // limit) + (1 if total % limit else 0)},
    }


@router.post("/sessions/{session_id}/disconnect", response_model=dict)
async def disconnect_session(
    request: Request,
    session_id: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
    _: bool = Depends(verify_radius_secret),
):
    """Mark a session for disconnection (CoA in Phase 7)."""
    service = RadiusAuthService(db)
    ok = await service.disconnect_session(session_id)
    return {"success": ok, "message": "Session marked for disconnect" if ok else "Session not found"}