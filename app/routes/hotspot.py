"""HotSpot plan (profile) API routes."""
from typing import Optional

from fastapi import APIRouter, Depends, Header, Request, Response
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.dependencies import get_db, require_permission
from app.core.exceptions import ConflictError, NotFoundError, ServiceUnavailableError, ValidationError
from app.core.logging import get_logger
from app.models.user import Permission, UserInDB
from app.schemas.hotspot import HotspotPlanCreate, HotspotPlanUpdate
from app.schemas.portal import (
    HotspotDeviceAttestationRequest,
    HotspotDeviceLookupRequest,
    HotspotPurchaseRequest,
    HotspotTrialRequest,
)
from app.services.hotspot_attestation_service import HotspotAttestationService
from app.services.hotspot_service import HotspotService
from app.services.router_service import RouterService
from app.utils.helpers import success_response

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1/hotspot", tags=["HotSpot"])


def _plan_to_response(p) -> dict:
    return {
        "_id": str(p.id),
        "name": p.name,
        "site_id": p.site_id,
        "duration_hours": p.duration_hours,
        "data_allowance_mb": p.data_allowance_mb,
        "max_devices": p.max_devices,
        "rate_limit": p.rate_limit,
        "price": p.price,
        "currency": p.currency,
        "description": p.description,
        "is_active": p.is_active,
        "sort_order": p.sort_order,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


async def _resolve_hotspot_device(data: HotspotDeviceLookupRequest, db: AsyncIOMotorDatabase) -> dict:
    """Verify all supplied client identifiers against one unique live DHCP lease."""
    import asyncio
    import ipaddress

    if not data.ip_address and not data.mac_address:
        raise ValidationError("Provide an IP address or MAC address")
    if data.ip_address:
        try:
            address = ipaddress.ip_address(data.ip_address)
        except ValueError as exc:
            raise ValidationError("Enter a valid device IP address") from exc
        if not address.is_private or address.is_loopback or address.is_link_local:
            raise ValidationError("Device lookup is limited to private LAN IP addresses")

    target_ip = str(ipaddress.ip_address(data.ip_address)) if data.ip_address else None
    target_mac = data.mac_address.replace("-", ":").upper() if data.mac_address else None
    routers = await db.routers.find(
        {"status": {"$ne": "disabled"}},
        {"_id": 1, "name": 1, "site_id": 1},
    ).to_list(length=1000)
    if not routers:
        raise ServiceUnavailableError("No MikroTik routers are configured for device verification")

    service = RouterService(db)
    unavailable_routers = []
    matches = []
    expired_matches = []

    # Keep the multi-router scan bounded while avoiding a serial relay roundtrip
    # for every configured router. A partial scan still fails closed below.
    semaphore = asyncio.Semaphore(4)

    async def fetch_router_leases(router: dict) -> tuple[dict, list]:
        router_id = str(router["_id"])
        async with semaphore:
            try:
                return router, await service.get_dhcp_leases(router_id)
            except Exception as exc:
                unavailable_routers.append(router_id)
                logger.warning(
                    "HotSpot DHCP lease lookup failed for router %s (%s)",
                    router_id,
                    type(exc).__name__,
                )
                return router, []

    router_leases = await asyncio.gather(*(fetch_router_leases(router) for router in routers))
    for router, leases in router_leases:
        router_id = str(router["_id"])
        for lease in leases:
            lease_ip = str(lease.get("address") or "")
            lease_mac = (lease.get("mac_address") or "").replace("-", ":").upper()
            if not lease_ip or not lease_mac:
                continue
            if target_ip and lease_ip != target_ip:
                continue
            if target_mac and lease_mac != target_mac:
                continue

            lease_status = str(lease.get("status") or "").lower()
            expires_seconds = lease.get("expires_seconds")
            expired = (lease_status and lease_status != "bound") or (
                expires_seconds is not None and expires_seconds <= 0
            )
            result = {
                    "verification_status": "verified",
                    "verification_method": "router_dhcp_lease",
                    "ip_address": lease_ip,
                    "mac_address": lease_mac,
                    "hostname": lease.get("hostname"),
                    "lease_status": lease_status or None,
                    "lease_expires_in_seconds": expires_seconds,
                    "router_id": router_id,
                    "router_name": router.get("name"),
                    "site_id": router.get("site_id"),
                }
            (expired_matches if expired else matches).append(result)

    # A partial scan cannot establish uniqueness across sites or overlapping LANs.
    if unavailable_routers:
        raise ServiceUnavailableError(
            "Device verification is temporarily unavailable because one or more configured routers could not be checked"
        )
    if len(matches) > 1 or (matches and expired_matches):
        raise ConflictError("This device matches DHCP leases on multiple routers; ask support to resolve the site assignment")
    if matches:
        return matches[0]
    if expired_matches:
        raise ConflictError("The matching MikroTik DHCP lease is no longer active. Reconnect to Wi-Fi and try again")
    raise NotFoundError("No DHCP lease matched the supplied hotspot device details")


# ── Plans ──

@router.post("/plans", response_model=dict, status_code=201)
async def create_hotspot_plan(
    request: Request,
    data: HotspotPlanCreate,
    current_user: UserInDB = Depends(require_permission(Permission.VOUCHERS_CREATE)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    service = HotspotService(db)
    plan = await service.create_plan(data)
    return success_response(message="HotSpot plan created", data=_plan_to_response(plan), status_code=201)


@router.get("/plans", response_model=dict)
async def list_hotspot_plans(
    request: Request,
    site_id: Optional[str] = None,
    active_only: bool = False,
    current_user: UserInDB = Depends(require_permission(Permission.VOUCHERS_READ)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    service = HotspotService(db)
    plans = await service.list_plans(site_id=site_id, active_only=active_only)
    return success_response(message="HotSpot plans retrieved", data=[_plan_to_response(p) for p in plans])


@router.get("/plans/public", response_model=dict)
async def list_public_hotspot_plans(
    request: Request,
    response: Response,
    site_id: Optional[str] = None,
    hotspot_context: Optional[str] = Header(default=None, alias="X-Hotspot-Context"),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Serve global plans, plus plans for a valid short-lived router context.

    ``site_id`` remains accepted for compatibility but is never trusted.
    """
    service = HotspotService(db)
    context = await HotspotAttestationService(db).get_context(hotspot_context)
    if hotspot_context:
        response.headers["Cache-Control"] = "private, no-store"
    plans = await service.list_plans(
        site_id=context.site_id if context else None,
        active_only=True,
        include_global=bool(context),
        global_only=not context,
    )
    return success_response(
        message="Available HotSpot plans",
        data=[
            {
                "_id": str(p.id),
                "site_id": p.site_id,
                "name": p.name,
                "duration_hours": p.duration_hours,
                "data_allowance_mb": p.data_allowance_mb,
                "max_devices": p.max_devices,
                "rate_limit": p.rate_limit,
                "price": p.price,
                "currency": p.currency,
                "description": p.description,
            }
            for p in plans
        ],
    )


@router.post("/devices/attest", response_model=dict)
async def attest_hotspot_device(
    data: HotspotDeviceAttestationRequest,
    response: Response,
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Use untrusted RouterOS hints to request authenticated relay observation."""
    context = await HotspotAttestationService(db).create_context(data.ip_address, data.mac_address)
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return success_response(message="HotSpot device context verified", data=context)


@router.post("/devices/lookup", response_model=dict)
async def lookup_hotspot_device(data: HotspotDeviceLookupRequest, db: AsyncIOMotorDatabase = Depends(get_db)):
    """Resolve one private LAN IP or MAC against configured MikroTik DHCP leases."""
    device = await _resolve_hotspot_device(data, db)
    return success_response(message="Device verified against a unique active router lease", data=device)


@router.post("/purchase", response_model=dict, status_code=201)
async def purchase_hotspot_voucher(
    data: HotspotPurchaseRequest,
    response: Response,
    hotspot_context: Optional[str] = Header(default=None, alias="X-Hotspot-Context"),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Start a walk-up purchase after server-side device and site validation."""
    plan = await HotspotService(db).get_plan(data.plan_id)
    if not hotspot_context:
        raise ConflictError("Secure device verification is required before starting a HotSpot purchase")
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    trusted_context = await HotspotAttestationService(db).attest_purchase_device(
        raw_token=hotspot_context,
        device_type=data.device_type,
        client_ip=data.ip_address,
        client_mac=data.device_mac,
    )

    from app.services.mpesa_service import MpesaService
    service = MpesaService(db)
    tx = await service.initiate_hotspot_purchase(
        plan_id=data.plan_id,
        phone_number=data.phone_number,
        device_type=data.device_type,
        device_mac=trusted_context.client_mac,
        trusted_site_id=trusted_context.site_id,
        trusted_router_id=trusted_context.router_id,
    )
    return success_response(
        message="STK push sent - check your phone",
        data={"checkout_request_id": tx.checkout_request_id},
        status_code=201,
    )


@router.get("/purchase/status/{checkout_request_id}", response_model=dict)
async def purchase_status(checkout_request_id: str, db: AsyncIOMotorDatabase = Depends(get_db)):
    """Public status polling for a completed or pending HotSpot purchase."""
    from app.services.mpesa_service import MpesaService
    service = MpesaService(db)
    tx = await service.get_by_checkout_id(checkout_request_id)
    return success_response(
        message="Purchase status retrieved",
        data={"status": tx.status.value, "voucher_code": tx.voucher_code, "result_desc": tx.result_desc},
    )


@router.post("/free-trial", response_model=dict, status_code=201)
async def request_free_trial(data: HotspotTrialRequest, db: AsyncIOMotorDatabase = Depends(get_db)):
    """Issue a one-time, three-minute voucher bound to a verified captive client."""
    verified_device = await _resolve_hotspot_device(
        HotspotDeviceLookupRequest(
            ip_address=data.ip_address,
            mac_address=data.client_mac,
        ),
        db,
    )
    service = HotspotService(db)
    trial = await service.request_free_trial(verified_device["mac_address"])
    return success_response(
        message="Three-minute trial issued",
        data=trial,
        status_code=201,
    )


@router.get("/plans/{plan_id}", response_model=dict)
async def get_hotspot_plan(
    request: Request,
    plan_id: str,
    current_user: UserInDB = Depends(require_permission(Permission.VOUCHERS_READ)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    service = HotspotService(db)
    plan = await service.get_plan(plan_id)
    return success_response(message="HotSpot plan retrieved", data=_plan_to_response(plan))


@router.patch("/plans/{plan_id}", response_model=dict)
async def update_hotspot_plan(
    request: Request,
    plan_id: str,
    data: HotspotPlanUpdate,
    current_user: UserInDB = Depends(require_permission(Permission.VOUCHERS_UPDATE)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    service = HotspotService(db)
    plan = await service.update_plan(plan_id, data)
    return success_response(message="HotSpot plan updated", data=_plan_to_response(plan))


@router.delete("/plans/{plan_id}", response_model=dict)
async def delete_hotspot_plan(
    request: Request,
    plan_id: str,
    current_user: UserInDB = Depends(require_permission(Permission.VOUCHERS_DELETE)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    service = HotspotService(db)
    await service.delete_plan(plan_id)
    return success_response(message="HotSpot plan deleted")


# ── Live sessions enriched with voucher info ──

@router.get("/routers/{router_id}/active-sessions", response_model=dict)
async def get_hotspot_active_sessions(
    request: Request,
    router_id: str,
    current_user: UserInDB = Depends(require_permission(Permission.ROUTERS_READ)),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Live /ip/hotspot/active sessions from the router (Phase 7), each
    enriched with the voucher record behind it (status, expiry, data cap)."""
    service = HotspotService(db)
    sessions = await service.get_active_sessions_with_vouchers(router_id)
    return success_response(message="Active HotSpot sessions retrieved", data=sessions)
