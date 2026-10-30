"""HotSpot plan (profile) API routes."""
from typing import Optional

from fastapi import APIRouter, Depends, Request
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.dependencies import get_db, require_permission
from app.core.exceptions import NotFoundError, ServiceUnavailableError, ValidationError
from app.core.logging import get_logger
from app.integrations.mikrotik.legacy_client import MikroTikLegacyError
from app.integrations.mikrotik.rest_client import MikroTikRestError
from app.models.user import Permission, UserInDB
from app.schemas.hotspot import HotspotPlanCreate, HotspotPlanUpdate
from app.schemas.portal import HotspotDeviceLookupRequest, HotspotPurchaseRequest, HotspotTrialRequest
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
    """Resolve a requested device against the configured routers' DHCP leases."""
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
    routers = await db.routers.find({}, {"_id": 1}).to_list(length=100)
    service = RouterService(db)
    failed_lookups = 0
    for router in routers:
        router_id = str(router["_id"])
        try:
            leases = await service.get_dhcp_leases(router_id)
        except (MikroTikLegacyError, MikroTikRestError) as exc:
            failed_lookups += 1
            logger.warning("HotSpot device lookup failed for configured router %s: %s", router_id, exc)
            continue
        for lease in leases:
            lease_ip = lease.get("address")
            lease_mac = (lease.get("mac_address") or "").replace("-", ":").upper()
            if (target_ip and lease_ip == target_ip) or (target_mac and lease_mac == target_mac):
                return {
                    "ip_address": lease_ip,
                    "mac_address": lease_mac,
                    "hostname": lease.get("hostname"),
                }
    if failed_lookups and failed_lookups == len(routers):
        raise ServiceUnavailableError("Configured hotspot routers are currently unavailable for device verification")
    raise NotFoundError("No matching device was found in configured router DHCP leases")


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
    site_id: Optional[str] = None,
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """No-auth listing of active plans - what a captive-portal splash page
    shows a guest before they buy/redeem a voucher."""
    service = HotspotService(db)
    plans = await service.list_plans(site_id=site_id, active_only=True)
    return success_response(
        message="Available HotSpot plans",
        data=[
            {
                "_id": str(p.id),  # the captive portal needs this to initiate a purchase - was missing entirely
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


@router.post("/devices/lookup", response_model=dict)
async def lookup_hotspot_device(data: HotspotDeviceLookupRequest, db: AsyncIOMotorDatabase = Depends(get_db)):
    """Resolve one private LAN IP or MAC against configured MikroTik DHCP leases."""
    device = await _resolve_hotspot_device(data, db)
    return success_response(message="Device verified", data=device)


@router.post("/purchase", response_model=dict, status_code=201)
async def purchase_hotspot_voucher(data: HotspotPurchaseRequest, db: AsyncIOMotorDatabase = Depends(get_db)):
    """Public, no-auth: a walk-up guest picks a plan on the captive
    portal and pays directly - no customer account involved. Pairs with
    GET /purchase/status/{checkout_request_id} for the frontend to poll
    until the voucher is ready."""
    verified_device = await _resolve_hotspot_device(
        HotspotDeviceLookupRequest(mac_address=data.device_mac),
        db,
    )
    from app.services.mpesa_service import MpesaService
    service = MpesaService(db)
    tx = await service.initiate_hotspot_purchase(
        plan_id=data.plan_id,
        phone_number=data.phone_number,
        device_type=data.device_type,
        device_mac=verified_device["mac_address"],
    )
    return success_response(
        message="STK push sent - check your phone",
        data={"checkout_request_id": tx.checkout_request_id},
        status_code=201,
    )


@router.get("/purchase/status/{checkout_request_id}", response_model=dict)
async def purchase_status(checkout_request_id: str, db: AsyncIOMotorDatabase = Depends(get_db)):
    """Public, no-auth: the captive portal polls this after POST /purchase
    until status is 'success' (voucher_code will be populated) or
    'failed'/'cancelled'/'timeout'."""
    from app.services.mpesa_service import MpesaService
    service = MpesaService(db)
    tx = await service.get_by_checkout_id(checkout_request_id)
    return success_response(
        message="Purchase status retrieved",
        data={"status": tx.status.value, "voucher_code": tx.voucher_code, "result_desc": tx.result_desc},
    )


@router.post("/free-trial", response_model=dict, status_code=201)
async def request_free_trial(data: HotspotTrialRequest, db: AsyncIOMotorDatabase = Depends(get_db)):
    """Issue a one-time, three-minute voucher bound to a captive client MAC."""
    service = HotspotService(db)
    trial = await service.request_free_trial(data.client_mac)
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
